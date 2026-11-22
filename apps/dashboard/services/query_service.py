"""
===================================================================================
DỊCH VỤ TRUY VẤN DỮ LIỆU TẬP TRUNG — DUAL-MODE (POSTGRESQL 16 + CLOUD PARQUET SNAPSHOT)
Path: apps/dashboard/services/query_service.py
Chức năng:
  - Tự động dùng PostgreSQL 16 khi chạy local có cấu hình DB_PASS
  - Tự động chuyển sang Cloud Parquet Snapshot (`data_snapshot/`) khi deploy lên
    Streamlit Community Cloud hoặc chạy showcase không cần cài đặt DB
  - Tích hợp @st.cache_data (TTL Cache) tối ưu tốc độ phản hồi UI < 50ms
===================================================================================
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv
from psycopg2.pool import SimpleConnectionPool
import streamlit as st

DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(DEC2FLOAT)

try:
    from stock_analysis.common.paths import CODE_ROOT
    REPO_ROOT = CODE_ROOT
except Exception:
    REPO_ROOT = Path(__file__).resolve().parents[3]

ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

SNAPSHOT_DIR = REPO_ROOT / "data_snapshot"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")
DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "auto").lower()


@st.cache_resource
def _check_postgres_available() -> bool:
    """Kiểm tra nhanh khả năng kết nối PostgreSQL; nếu không khả dụng dùng Cloud Snapshot."""
    if DATA_SOURCE_MODE == "snapshot":
        return False
    if DATA_SOURCE_MODE == "auto" and not DB_PASS and SNAPSHOT_DIR.exists():
        return False
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


def is_snapshot_mode() -> bool:
    return (not _check_postgres_available()) and SNAPSHOT_DIR.exists()


def get_data_source_label() -> str:
    if is_snapshot_mode():
        return "Cloud Parquet Snapshot (Verified Clean Data)"
    return f"PostgreSQL 16 DWH ({DB_NAME})"


@st.cache_resource
def get_connection_pool():
    """Khởi tạo Connection Pool kết nối PostgreSQL 16."""
    return SimpleConnectionPool(
        minconn=2,
        maxconn=20,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def execute_query(sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
    """Thực thi câu truy vấn SQL an toàn qua Connection Pool."""
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                columns = [col[0] for col in cur.description]
                data = cur.fetchall()
                return pd.DataFrame(data, columns=columns)
            return pd.DataFrame()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = pool.getconn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                columns = [col[0] for col in cur.description]
                data = cur.fetchall()
                return pd.DataFrame(data, columns=columns)
            return pd.DataFrame()
    except Exception as e:
        if conn and not conn.closed:
            conn.rollback()
        raise e
    finally:
        if conn and not conn.closed:
            conn.rollback()
            pool.putconn(conn)
        elif conn:
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass


@st.cache_data(ttl=3600, show_spinner=False)
def _load_snapshot(name: str) -> pd.DataFrame:
    p = SNAPSHOT_DIR / f"{name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


# =================================================================================
# 1. METADATA & EXECUTIVE SUMMARY
# =================================================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_all_banks() -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("dim_bank").copy()
        return df.sort_values(["tier_group", "charter_capital_vnd"], ascending=[True, False]).reset_index(drop=True)
    sql = """
        SELECT
            bank_sk, ticker, bank_name, bank_name_en, short_name, tax_code,
            listing_exchange, tier_group, charter_capital_vnd, is_active
        FROM master_data.dim_bank
        WHERE is_active = TRUE AND bank_sk > 0
        ORDER BY tier_group ASC, charter_capital_vnd DESC;
    """
    return execute_query(sql)


@st.cache_data(ttl=300, show_spinner=False)
def get_platform_health_kpis() -> Dict[str, Any]:
    if is_snapshot_mode():
        meta_path = SNAPSHOT_DIR / "platform_kpis.json"
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding="utf-8"))
        df_ohlcv = _load_snapshot("ohlcv_daily")
        df_fs = _load_snapshot("financials_quarterly")
        df_r = _load_snapshot("ratios_quarterly")
        return {
            "total_ohlcv": int(len(df_ohlcv)),
            "total_financials": int(len(df_fs)),
            "total_ratios": int(len(df_r)),
            "total_macro": int(len(_load_snapshot("macro_daily"))),
            "total_news": int(len(_load_snapshot("disclosures_feed"))),
            "total_governance_edges": 0,
            "latest_trading_date": "N/A",
        }
    sql_counts = """
        SELECT
            (SELECT COUNT(*) FROM mart_technical.fact_daily_market_ohlcv) as total_ohlcv,
            (SELECT COUNT(*) FROM mart_camels.fact_quarterly_financial_statements) as total_financials,
            (SELECT COUNT(*) FROM mart_camels.fact_quarterly_banking_ratios) as total_ratios,
            (SELECT COUNT(*) FROM mart_technical.fact_macro_indicators) as total_macro,
            (SELECT COUNT(*) FROM mart_sentiment.fact_media_sentiment_daily) as total_news,
            (SELECT COUNT(*) FROM mart_governance.bridge_governance_network) as total_governance_edges,
            (SELECT MAX(date_sk) FROM mart_technical.fact_daily_market_ohlcv) as latest_trading_sk;
    """
    df = execute_query(sql_counts)
    if not df.empty:
        r = df.iloc[0]
        latest_d = str(r["latest_trading_sk"])
        latest_fmt = f"{latest_d[6:8]}/{latest_d[4:6]}/{latest_d[:4]}" if len(latest_d) == 8 else "N/A"
        return {
            "total_ohlcv": int(r["total_ohlcv"]),
            "total_financials": int(r["total_financials"]),
            "total_ratios": int(r["total_ratios"]),
            "total_macro": int(r["total_macro"]),
            "total_news": int(r["total_news"]),
            "total_governance_edges": int(r["total_governance_edges"]),
            "latest_trading_date": latest_fmt,
        }
    return {}


# =================================================================================
# 2. MODULE 1: MA TRẬN ĐỊNH GIÁ GORDON (P/B vs ROE)
# =================================================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_available_quarter_periods() -> List[str]:
    if is_snapshot_mode():
        df = _load_snapshot("ratios_quarterly")
        if df.empty:
            return []
        periods = (
            df[["fiscal_year", "fiscal_quarter"]]
            .drop_duplicates()
            .sort_values(["fiscal_year", "fiscal_quarter"], ascending=[False, False])
        )
        return [f"{int(r.fiscal_year)}Q{int(r.fiscal_quarter)}" for r in periods.itertuples()]
    sql = """
        SELECT DISTINCT CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name
        FROM mart_valuation.view_gordon_pb_roe_matrix
        ORDER BY period_name DESC;
    """
    df = execute_query(sql)
    return df["period_name"].tolist() if not df.empty else []


def _classify_gordon_zone(row: pd.Series) -> str:
    roe = row.get("roe", 0.0) or 0.0
    pb = row.get("pb_ratio", 0.0) or 0.0
    if roe >= 0.15 and pb <= 1.25:
        return "Vùng Kim Cương (ROE Cao, P/B Hấp Dẫn)"
    if roe >= 0.15 and pb > 1.25:
        return "Tăng Trưởng Chất Lượng (ROE Cao, P/B Cao)"
    if roe < 0.15 and pb <= 1.10:
        return "Chiết Khấu / Thận Trọng (ROE Thấp, P/B Thấp)"
    return "Định Giá Cao / Hiệu Quả Thấp"


@st.cache_data(ttl=600, show_spinner=False)
def get_gordon_matrix_data(fiscal_year: Optional[Any] = None, fiscal_quarter: Optional[Any] = None) -> pd.DataFrame:
    if isinstance(fiscal_year, str) and not fiscal_year.isdigit():
        # Legacy call get_gordon_matrix_data("VCB") -> return latest snapshot
        fiscal_year = None
    if is_snapshot_mode():
        df = _load_snapshot("ratios_quarterly").copy()
        if df.empty:
            return df
        if fiscal_year and fiscal_quarter:
            df = df[(df["fiscal_year"] == int(fiscal_year)) & (df["fiscal_quarter"] == int(fiscal_quarter))].copy()
        else:
            df = df.sort_values(["fiscal_year", "fiscal_quarter"]).groupby("ticker", as_index=False).tail(1)
        df = df[(df["pb_ratio"] > 0) & df["roe"].notna()].copy()
        df["period_name"] = df["fiscal_year"].astype(int).astype(str) + "Q" + df["fiscal_quarter"].astype(int).astype(str)
        df["roe_to_pb_efficiency"] = (df["roe"] / df["pb_ratio"]).round(4)
        df["gordon_zone"] = df.apply(_classify_gordon_zone, axis=1)
        cols = [
            "bank_sk", "ticker", "short_name", "tier_group", "fiscal_year", "fiscal_quarter",
            "period_name", "pb_ratio", "roe", "roe_to_pb_efficiency", "gordon_zone",
        ]
        return df[cols].sort_values("roe", ascending=False).reset_index(drop=True)

    if fiscal_year and fiscal_quarter:
        sql = """
            SELECT
                bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
                CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
                pb_ratio, roe, roe_to_pb_efficiency, gordon_zone
            FROM mart_valuation.view_gordon_pb_roe_matrix
            WHERE fiscal_year = %s AND fiscal_quarter = %s
            ORDER BY roe DESC;
        """
        return execute_query(sql, (fiscal_year, fiscal_quarter))
    sql = """
        WITH Ranked AS (
            SELECT
                bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
                CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
                pb_ratio, roe, roe_to_pb_efficiency, gordon_zone,
                ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY fiscal_year DESC, fiscal_quarter DESC) as rn
            FROM mart_valuation.view_gordon_pb_roe_matrix
        )
        SELECT * FROM Ranked WHERE rn = 1 ORDER BY roe DESC;
    """
    return execute_query(sql)


# =================================================================================
# 3. MODULE 2: KHUNG ĐÁNH GIÁ SỨC KHỎE VẬN HÀNH CAMELS
# =================================================================================
def _format_camels_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["period_name"] = out["fiscal_year"].astype(int).astype(str) + "Q" + out["fiscal_quarter"].astype(int).astype(str)
    out["c_capital_car"] = out["capital_adequacy_ratio"]
    out["a_asset_quality_npl"] = out["npl_ratio"]
    out["a_provision_llr"] = out["loan_loss_reserve_to_npls"].abs()
    out["m_management_cir"] = out["cost_to_income_ratio"].abs()
    out["e_earnings_roe"] = out["roe"]
    out["e_earnings_nim"] = out["net_interest_margin"]
    out["l_liquidity_ldr"] = out["loan_to_deposit_ratio"]
    out["l_liquidity_casa"] = out["casa_ratio"]
    return out


@st.cache_data(ttl=600, show_spinner=False)
def get_camels_radar_data(ticker: str, fiscal_year: Optional[int] = None, fiscal_quarter: Optional[int] = None) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("ratios_quarterly")
        df = df[df["ticker"] == ticker].copy()
        if df.empty:
            return df
        if fiscal_year and fiscal_quarter:
            df = df[(df["fiscal_year"] == int(fiscal_year)) & (df["fiscal_quarter"] == int(fiscal_quarter))]
        else:
            df = df.sort_values(["fiscal_year", "fiscal_quarter"], ascending=[False, False]).head(1)
        if df.empty:
            return df
        df = _format_camels_cols(df)
        cols = [
            "bank_sk", "ticker", "short_name", "tier_group", "fiscal_year", "fiscal_quarter",
            "period_name", "c_capital_car", "a_asset_quality_npl", "a_provision_llr",
            "m_management_cir", "e_earnings_roe", "e_earnings_nim",
            "l_liquidity_ldr", "l_liquidity_casa", "is_car_carried_forward",
        ]
        return df[[c for c in cols if c in df.columns]].reset_index(drop=True)

    if fiscal_year and fiscal_quarter:
        sql = """
            SELECT
                bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
                CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
                c_capital_car, a_asset_quality_npl, a_provision_llr,
                m_management_cir, e_earnings_roe, e_earnings_nim,
                l_liquidity_ldr, l_liquidity_casa
            FROM mart_camels.view_camels_radar
            WHERE ticker = %s AND fiscal_year = %s AND fiscal_quarter = %s;
        """
        return execute_query(sql, (ticker, fiscal_year, fiscal_quarter))
    sql = """
        SELECT
            bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
            CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
            c_capital_car, a_asset_quality_npl, a_provision_llr,
            m_management_cir, e_earnings_roe, e_earnings_nim,
            l_liquidity_ldr, l_liquidity_casa
        FROM mart_camels.view_camels_radar
        WHERE ticker = %s
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        LIMIT 1;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_camels_peer_comparison(fiscal_year: Optional[int] = None, fiscal_quarter: Optional[int] = None) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("ratios_quarterly").copy()
        if df.empty:
            return df
        if fiscal_year and fiscal_quarter:
            df = df[(df["fiscal_year"] == int(fiscal_year)) & (df["fiscal_quarter"] == int(fiscal_quarter))]
        else:
            df = df.sort_values(["fiscal_year", "fiscal_quarter"]).groupby("ticker", as_index=False).tail(1)
        df = _format_camels_cols(df)
        df["car"] = df["c_capital_car"]
        df["npl"] = df["a_asset_quality_npl"]
        df["llr"] = df["a_provision_llr"]
        df["cir"] = df["m_management_cir"]
        df["roe"] = df["e_earnings_roe"]
        df["nim"] = df["e_earnings_nim"]
        df["ldr"] = df["l_liquidity_ldr"]
        df["casa"] = df["l_liquidity_casa"]
        return df.sort_values("e_earnings_roe", ascending=False).reset_index(drop=True)

    if fiscal_year and fiscal_quarter:
        sql = """
            SELECT
                b.bank_sk, b.ticker, b.short_name, b.tier_group,
                r.fiscal_year, r.fiscal_quarter,
                CONCAT(r.fiscal_year, 'Q', r.fiscal_quarter) as period_name,
                r.c_capital_car, r.a_asset_quality_npl, r.a_provision_llr,
                r.m_management_cir, r.e_earnings_roe, r.e_earnings_nim,
                r.l_liquidity_ldr, r.l_liquidity_casa,
                r.c_capital_car as car, r.a_asset_quality_npl as npl, r.a_provision_llr as llr,
                r.m_management_cir as cir, r.e_earnings_roe as roe, r.e_earnings_nim as nim,
                r.l_liquidity_ldr as ldr, r.l_liquidity_casa as casa
            FROM mart_camels.view_camels_radar r
            JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk
            WHERE r.fiscal_year = %s AND r.fiscal_quarter = %s
            ORDER BY r.e_earnings_roe DESC;
        """
        return execute_query(sql, (fiscal_year, fiscal_quarter))
    sql = """
        WITH Ranked AS (
            SELECT
                b.bank_sk, b.ticker, b.short_name, b.tier_group,
                r.fiscal_year, r.fiscal_quarter,
                CONCAT(r.fiscal_year, 'Q', r.fiscal_quarter) as period_name,
                r.c_capital_car, r.a_asset_quality_npl, r.a_provision_llr,
                r.m_management_cir, r.e_earnings_roe, r.e_earnings_nim,
                r.l_liquidity_ldr, r.l_liquidity_casa,
                r.c_capital_car as car, r.a_asset_quality_npl as npl, r.a_provision_llr as llr,
                r.m_management_cir as cir, r.e_earnings_roe as roe, r.e_earnings_nim as nim,
                r.l_liquidity_ldr as ldr, r.l_liquidity_casa as casa,
                ROW_NUMBER() OVER(PARTITION BY b.ticker ORDER BY r.fiscal_year DESC, r.fiscal_quarter DESC) as rn
            FROM mart_camels.view_camels_radar r
            JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk
        )
        SELECT * FROM Ranked WHERE rn = 1 ORDER BY e_earnings_roe DESC;
    """
    return execute_query(sql)


# =================================================================================
# 4. MODULE 3: KỸ THUẬT NẾN OHLCV & TÁC ĐỘNG VĨ MÔ
# =================================================================================
@st.cache_data(ttl=300, show_spinner=False)
def get_technical_ohlcv_data(ticker: str, days: int = 180) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("ohlcv_daily")
        banks = _load_snapshot("dim_bank")[["ticker", "short_name", "tier_group"]]
        sub = df[df["ticker"] == ticker].copy()
        if sub.empty:
            return sub
        sub["trading_date"] = pd.to_datetime(sub["trading_date"]).dt.date
        cutoff = pd.Timestamp(sub["trading_date"].max()) - pd.Timedelta(days=int(days))
        sub = sub[pd.to_datetime(sub["trading_date"]) >= cutoff].sort_values("trading_date")
        return sub.merge(banks, on="ticker", how="left").reset_index(drop=True)

    sql = f"""
        SELECT
            full_date as trading_date,
            date_sk, ticker, short_name, tier_group,
            open_price, high_price, low_price, close_price,
            volume, turnover_vnd, return_daily_pct,
            sma_20, sma_50, sma_200, avg_volume_20d, volume_surge_ratio
        FROM mart_technical.view_technical_market_daily
        WHERE ticker = %s
          AND full_date >= (
              SELECT COALESCE(MAX(full_date), CURRENT_DATE)
              FROM mart_technical.view_technical_market_daily
              WHERE ticker = %s
          ) - INTERVAL '{int(days)} days'
        ORDER BY full_date ASC;
    """
    return execute_query(sql, (ticker, ticker))


@st.cache_data(ttl=300, show_spinner=False)
def get_sector_technical_snapshot() -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("ohlcv_daily")
        banks = _load_snapshot("dim_bank")[["ticker", "short_name", "tier_group"]]
        latest = df.sort_values("trading_date").groupby("ticker", as_index=False).tail(1)
        latest = latest.merge(banks, on="ticker", how="left")
        cols = [
            "ticker", "short_name", "tier_group", "trading_date",
            "open_price", "high_price", "low_price", "close_price",
            "volume", "turnover_vnd", "return_daily_pct",
            "sma_20", "sma_50", "sma_200", "avg_volume_20d", "volume_surge_ratio",
        ]
        return latest[cols].sort_values("turnover_vnd", ascending=False).reset_index(drop=True)

    sql = """
        WITH ranked AS (
            SELECT
                ticker, short_name, tier_group, full_date as trading_date,
                open_price, high_price, low_price, close_price,
                volume, turnover_vnd, return_daily_pct,
                sma_20, sma_50, sma_200, avg_volume_20d, volume_surge_ratio,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY full_date DESC) as rn
            FROM mart_technical.view_technical_market_daily
        )
        SELECT
            ticker, short_name, tier_group, trading_date,
            open_price, high_price, low_price, close_price,
            volume, turnover_vnd, return_daily_pct,
            sma_20, sma_50, sma_200, avg_volume_20d, volume_surge_ratio
        FROM ranked
        WHERE rn = 1
        ORDER BY turnover_vnd DESC;
    """
    return execute_query(sql)


@st.cache_data(ttl=600, show_spinner=False)
def get_macro_market_correlation(days: Any = 365, ticker: str = "VCB") -> pd.DataFrame:
    if isinstance(days, str) and not isinstance(ticker, int) and not str(days).isdigit():
        ticker, days = str(days), 365
    elif isinstance(ticker, int):
        days, ticker = ticker, str(days)
    try:
        days_int = int(days)
    except Exception:
        days_int = 365

    if is_snapshot_mode():
        px = get_technical_ohlcv_data(ticker, days=days_int)
        macro = _load_snapshot("macro_daily").copy()
        if px.empty or macro.empty:
            return pd.DataFrame()
        macro["trading_date"] = pd.to_datetime(macro["trading_date"]).dt.date
        merged = px[["trading_date", "ticker", "tier_group", "close_price", "return_daily_pct", "volume"]].merge(
            macro[["trading_date", "vnindex_close", "sbv_refinancing_rate", "usdvnd_rate"]],
            on="trading_date",
            how="left",
        )
        for col in ["vnindex_close", "sbv_refinancing_rate", "usdvnd_rate"]:
            merged[col] = merged[col].ffill()
        return merged.sort_values("trading_date").reset_index(drop=True)

    sql = f"""
        SELECT
            full_date as trading_date, ticker, tier_group,
            close_price, return_daily_pct, volume,
            vnindex_close, sbv_refinancing_rate, usdvnd_rate
        FROM mart_technical.view_macro_market_correlation
        WHERE ticker = %s
          AND full_date >= (
              SELECT COALESCE(MAX(full_date), CURRENT_DATE)
              FROM mart_technical.view_macro_market_correlation
              WHERE ticker = %s
          ) - INTERVAL '{days_int} days'
        ORDER BY full_date ASC;
    """
    return execute_query(sql, (ticker, ticker))


# =================================================================================
# 5. MODULE 4: MẠNG LƯỚI SỞ HỮU, BAN LÃNH ĐẠO & CỔ TỨC
# =================================================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_bank_shareholders(ticker: str) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("shareholders")
        sub = df[df["ticker"] == ticker][["shareholder_name", "quantity", "ownership_pct", "update_date"]].copy()
        return sub.sort_values(["ownership_pct", "quantity"], ascending=[False, False]).reset_index(drop=True)
    sql = """
        SELECT shareholder_name, quantity, ownership_pct, update_date
        FROM mart_governance.fact_bank_shareholders
        WHERE ticker = %s
        ORDER BY ownership_pct DESC NULLS LAST, quantity DESC NULLS LAST;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_bank_officers(ticker: str) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("officers")
        sub = df[df["ticker"] == ticker][["officer_name", "position_title", "ownership_pct", "shares_quantity"]].copy()
        return sub.sort_values("ownership_pct", ascending=False).reset_index(drop=True)
    sql = """
        SELECT officer_name, position_title, ownership_pct, shares_quantity
        FROM mart_governance.fact_bank_officers
        WHERE ticker = %s
        ORDER BY ownership_pct DESC NULLS LAST;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_bank_subsidiaries(ticker: str) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("subsidiaries")
        sub = df[df["ticker"] == ticker][["subsidiary_name", "ownership_pct"]].copy()
        return sub.sort_values("ownership_pct", ascending=False).reset_index(drop=True)
    sql = """
        SELECT subsidiary_name, ownership_pct
        FROM mart_governance.fact_bank_subsidiaries
        WHERE ticker = %s
        ORDER BY ownership_pct DESC NULLS LAST;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_bank_corporate_events(ticker: str) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("corporate_events")
        sub = df[df["ticker"] == ticker][["event_type", "event_title", "exright_date", "record_date", "event_details"]].copy()
        return sub.sort_values("record_date", ascending=False).reset_index(drop=True)
    sql = """
        SELECT
            event_code as event_type, event_name_vi as event_title,
            exright_date, record_date,
            COALESCE(event_name_en, event_name_vi) as event_details
        FROM mart_governance.fact_corporate_events
        WHERE ticker = %s
        ORDER BY record_date DESC NULLS LAST;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_bank_dividends(ticker: str) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _load_snapshot("corporate_events")
        sub = df[df["ticker"] == ticker].copy()
        mask = (
            (sub["value_per_share"].fillna(0) > 0)
            | (sub["exercise_ratio"].fillna(0) > 0)
            | sub["event_title"].fillna("").str.lower().str.contains("cổ tức")
        )
        sub = sub[mask].copy()
        sub["cash_amount_vnd"] = sub["value_per_share"]
        sub["stock_ratio_pct"] = sub["exercise_ratio"]
        cols = [
            "event_title", "exright_date", "record_date", "payout_date",
            "value_per_share", "cash_amount_vnd", "stock_ratio_pct", "event_details",
        ]
        return sub[cols].sort_values("record_date", ascending=False).reset_index(drop=True)
    sql = """
        SELECT
            event_name_vi as event_title, exright_date, record_date, payout_date,
            value_per_share, value_per_share as cash_amount_vnd,
            exercise_ratio as stock_ratio_pct,
            COALESCE(event_name_en, event_name_vi) as event_details
        FROM mart_governance.fact_corporate_events
        WHERE ticker = %s AND (value_per_share > 0 OR exercise_ratio > 0 OR event_name_vi ILIKE '%%cổ tức%%')
        ORDER BY record_date DESC NULLS LAST;
    """
    return execute_query(sql, (ticker,))


@st.cache_data(ttl=600, show_spinner=False)
def get_dividend_yield_summary(ticker: str) -> Dict[str, Any]:
    if is_snapshot_mode():
        px = get_technical_ohlcv_data(ticker, days=30)
        close_p = float(px["close_price"].iloc[-1]) if not px.empty else 0.0
        divs = get_bank_dividends(ticker)
        tot_c = 0.0
        if not divs.empty:
            divs_c = divs.copy()
            divs_c["rdt"] = pd.to_datetime(divs_c["record_date"], errors="coerce")
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
            recent = divs_c[(divs_c["rdt"] >= cutoff) | divs_c["rdt"].isna()]
            tot_c = float(recent["value_per_share"].fillna(0).sum())
        macro = _load_snapshot("macro_daily")
        ref_r = float(macro["sbv_refinancing_rate"].dropna().iloc[-1]) if (not macro.empty and "sbv_refinancing_rate" in macro.columns and macro["sbv_refinancing_rate"].notna().any()) else 4.5
        dy = round((tot_c / close_p) * 100, 2) if close_p > 0 else 0.0
        return {
            "latest_close": close_p,
            "latest_cash": tot_c,
            "cash_yield_pct": dy,
            "sbv_rate_pct": ref_r,
            "spread_vs_sbv": dy - ref_r,
            "latest_stock_pct": 0.0,
            "latest_div_date": "Gần nhất",
            "close_price": close_p,
            "total_cash_1y": tot_c,
            "dividend_yield_pct": dy,
            "refinancing_rate": ref_r,
            "deposit_rate_12m_benchmark": 5.0,
        }

    sql = """
        WITH RecentPrice AS (
            SELECT close_price
            FROM mart_technical.view_technical_market_daily
            WHERE ticker = %s
            ORDER BY full_date DESC LIMIT 1
        ),
        Dividends1Y AS (
            SELECT COALESCE(SUM(value_per_share), 0) as total_cash_1y
            FROM mart_governance.fact_corporate_events
            WHERE ticker = %s
              AND (record_date >= CURRENT_DATE - INTERVAL '365 days' OR record_date IS NULL)
              AND value_per_share > 0
        ),
        MacroBenchmark AS (
            SELECT
                sbv_refinancing_rate as refinancing_rate,
                5.0 as deposit_rate_12m_benchmark
            FROM mart_technical.view_macro_market_correlation
            WHERE sbv_refinancing_rate IS NOT NULL
            ORDER BY full_date DESC LIMIT 1
        )
        SELECT
            p.close_price,
            d.total_cash_1y,
            CASE
                WHEN p.close_price > 0 THEN ROUND((d.total_cash_1y / p.close_price) * 100, 2)
                ELSE 0.0
            END as dividend_yield_pct,
            COALESCE(m.refinancing_rate, 4.5) as refinancing_rate,
            COALESCE(m.deposit_rate_12m_benchmark, 5.0) as deposit_rate_12m_benchmark
        FROM RecentPrice p
        CROSS JOIN Dividends1Y d
        CROSS JOIN MacroBenchmark m;
    """
    df = execute_query(sql, (ticker, ticker))
    if not df.empty:
        r = df.iloc[0]
        close_p = float(r["close_price"]) if r["close_price"] else 0.0
        tot_c = float(r["total_cash_1y"]) if r["total_cash_1y"] else 0.0
        dy = float(r["dividend_yield_pct"]) if r["dividend_yield_pct"] else 0.0
        ref_r = float(r["refinancing_rate"]) if r["refinancing_rate"] else 4.5
        dep_r = float(r["deposit_rate_12m_benchmark"]) if r["deposit_rate_12m_benchmark"] else 5.0
        return {
            "latest_close": close_p,
            "latest_cash": tot_c,
            "cash_yield_pct": dy,
            "sbv_rate_pct": ref_r,
            "spread_vs_sbv": dy - ref_r,
            "latest_stock_pct": 0.0,
            "latest_div_date": "Gần nhất",
            "close_price": close_p,
            "total_cash_1y": tot_c,
            "dividend_yield_pct": dy,
            "refinancing_rate": ref_r,
            "deposit_rate_12m_benchmark": dep_r,
        }
    return {
        "latest_close": 0.0, "latest_cash": 0.0, "cash_yield_pct": 0.0,
        "sbv_rate_pct": 4.5, "spread_vs_sbv": -4.5, "latest_stock_pct": 0.0,
        "latest_div_date": "N/A", "close_price": 0.0, "total_cash_1y": 0.0,
        "dividend_yield_pct": 0.0, "refinancing_rate": 4.5, "deposit_rate_12m_benchmark": 5.0,
    }


# =================================================================================
# 6. MODULE 5: TRÍ TUỆ CÔNG BỐ & SẮC THÁI TIN TỨC
# =================================================================================
def _filter_snapshot_disclosures(
    ticker=None, category_name=None, category_code=None, source_type=None,
    sentiment_label=None, is_official_only=False, has_pdf_only=False,
    search_query=None, start_date=None, end_date=None,
) -> pd.DataFrame:
    df = _load_snapshot("disclosures_feed").copy()
    if df.empty:
        return df
    df["full_date"] = pd.to_datetime(df["full_date"]).dt.date
    if ticker and ticker not in ("ALL", "TẤT CẢ"):
        df = df[df["ticker"] == ticker]
    if category_name and category_name not in ("ALL", "TẤT CẢ", "Tất cả Danh mục", "Tất cả"):
        df = df[df["category_name"] == category_name]
    elif category_code and category_code not in ("ALL", "TẤT CẢ"):
        df = df[df["category_code"] == category_code]
    if source_type and source_type not in ("ALL", "TẤT CẢ", "Tất cả Nguồn tin", "Tất cả"):
        df = df[df["source_type"].fillna("").str.contains(source_type, case=False, na=False)]
    if sentiment_label and sentiment_label not in ("ALL", "TẤT CẢ", "Tất cả"):
        df = df[df["sentiment_label"] == sentiment_label]
    if is_official_only:
        df = df[df["is_official_disclosure"] == True]
    if has_pdf_only:
        df = df[df["has_attachment_pdf"] == True]
    if search_query and search_query.strip():
        df = df[df["title"].fillna("").str.contains(search_query.strip(), case=False, na=False)]
    if start_date:
        df = df[df["full_date"] >= pd.to_datetime(start_date).date()]
    if end_date:
        df = df[df["full_date"] <= pd.to_datetime(end_date).date()]
    return df


@st.cache_data(ttl=300, show_spinner=False)
def get_disclosure_date_range(ticker: Optional[str] = "VCB") -> Dict[str, Any]:
    if is_snapshot_mode():
        df = _filter_snapshot_disclosures(ticker=ticker)
        if not df.empty:
            return {"min_date": df["full_date"].min(), "max_date": df["full_date"].max(), "total_articles": int(len(df))}
        return {"min_date": datetime(2023, 1, 1).date(), "max_date": datetime.now().date(), "total_articles": 0}
    if ticker and ticker not in ("ALL", "TẤT CẢ"):
        sql = "SELECT MIN(full_date) as min_date, MAX(full_date) as max_date, COUNT(*) as total_articles FROM mart_sentiment.view_disclosure_feed WHERE ticker = %s;"
        df = execute_query(sql, (ticker,))
    else:
        sql = "SELECT MIN(full_date) as min_date, MAX(full_date) as max_date, COUNT(*) as total_articles FROM mart_sentiment.view_disclosure_feed;"
        df = execute_query(sql)
    if not df.empty and pd.notnull(df.iloc[0]["max_date"]):
        return {"min_date": df.iloc[0]["min_date"], "max_date": df.iloc[0]["max_date"], "total_articles": int(df.iloc[0]["total_articles"])}
    return {"min_date": datetime(2018, 1, 1).date(), "max_date": datetime.now().date(), "total_articles": 0}


@st.cache_data(ttl=300, show_spinner=False)
def get_disclosure_count(
    ticker: Optional[str] = None, category_name: Optional[str] = None, category_code: Optional[str] = None,
    source_type: Optional[str] = None, sentiment_label: Optional[str] = None, is_official_only: bool = False,
    has_pdf_only: bool = False, search_query: Optional[str] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None,
) -> int:
    if is_snapshot_mode():
        return int(len(_filter_snapshot_disclosures(
            ticker=ticker, category_name=category_name, category_code=category_code,
            source_type=source_type, sentiment_label=sentiment_label, is_official_only=is_official_only,
            has_pdf_only=has_pdf_only, search_query=search_query, start_date=start_date, end_date=end_date,
        )))
    conditions, params = [], []
    if ticker and ticker not in ("ALL", "TẤT CẢ"):
        conditions.append("ticker = %s"); params.append(ticker)
    if category_name and category_name not in ("ALL", "TẤT CẢ", "Tất cả Danh mục", "Tất cả"):
        conditions.append("category_name = %s"); params.append(category_name)
    elif category_code and category_code not in ("ALL", "TẤT CẢ"):
        conditions.append("category_code = %s"); params.append(category_code)
    if source_type and source_type not in ("ALL", "TẤT CẢ", "Tất cả Nguồn tin", "Tất cả"):
        conditions.append("source_name ILIKE %s"); params.append(f"%{source_type}%")
    if sentiment_label and sentiment_label not in ("ALL", "TẤT CẢ", "Tất cả"):
        conditions.append("sentiment_label = %s"); params.append(sentiment_label)
    if is_official_only:
        conditions.append("is_official_disclosure = TRUE")
    if has_pdf_only:
        conditions.append("has_attachment_pdf = TRUE")
    if search_query and search_query.strip():
        conditions.append("title ILIKE %s"); params.append(f"%{search_query.strip()}%")
    if start_date:
        conditions.append("full_date >= %s"); params.append(str(start_date))
    if end_date:
        conditions.append("full_date <= %s"); params.append(str(end_date))
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    df = execute_query(f"SELECT COUNT(*) as total FROM mart_sentiment.view_disclosure_feed {where_clause};", tuple(params) if params else None)
    return int(df.iloc[0]["total"]) if not df.empty else 0


@st.cache_data(ttl=300, show_spinner=False)
def get_disclosure_feed(
    ticker: Optional[str] = None, category_name: Optional[str] = None, category_code: Optional[str] = None,
    source_type: Optional[str] = None, sentiment_label: Optional[str] = None, is_official_only: bool = False,
    has_pdf_only: bool = False, search_query: Optional[str] = None, start_date: Optional[Any] = None,
    end_date: Optional[Any] = None, limit: Optional[int] = 50, offset: int = 0,
) -> pd.DataFrame:
    if is_snapshot_mode():
        df = _filter_snapshot_disclosures(
            ticker=ticker, category_name=category_name, category_code=category_code,
            source_type=source_type, sentiment_label=sentiment_label, is_official_only=is_official_only,
            has_pdf_only=has_pdf_only, search_query=search_query, start_date=start_date, end_date=end_date,
        )
        if offset:
            df = df.iloc[int(offset):]
        if limit:
            df = df.iloc[:int(limit)]
        return df.reset_index(drop=True)

    conditions, params = [], []
    if ticker and ticker not in ("ALL", "TẤT CẢ"):
        conditions.append("ticker = %s"); params.append(ticker)
    if category_name and category_name not in ("ALL", "TẤT CẢ", "Tất cả Danh mục", "Tất cả"):
        conditions.append("category_name = %s"); params.append(category_name)
    elif category_code and category_code not in ("ALL", "TẤT CẢ"):
        conditions.append("category_code = %s"); params.append(category_code)
    if source_type and source_type not in ("ALL", "TẤT CẢ", "Tất cả Nguồn tin", "Tất cả"):
        conditions.append("source_name ILIKE %s"); params.append(f"%{source_type}%")
    if sentiment_label and sentiment_label not in ("ALL", "TẤT CẢ", "Tất cả"):
        conditions.append("sentiment_label = %s"); params.append(sentiment_label)
    if is_official_only:
        conditions.append("is_official_disclosure = TRUE")
    if has_pdf_only:
        conditions.append("has_attachment_pdf = TRUE")
    if search_query and search_query.strip():
        conditions.append("title ILIKE %s"); params.append(f"%{search_query.strip()}%")
    if start_date:
        conditions.append("full_date >= %s"); params.append(str(start_date))
    if end_date:
        conditions.append("full_date <= %s"); params.append(str(end_date))
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    offset_clause = f"OFFSET {int(offset)}" if offset else ""
    sql = f"""
        SELECT
            fact_id, full_date, ticker, bank_name as short_name, tier_group,
            source_name as source_type, source_url, title, category_code, category_name,
            sentiment_score, sentiment_label, attachment_pdf_url, has_attachment_pdf,
            is_official_disclosure
        FROM mart_sentiment.view_disclosure_feed
        {where_clause}
        ORDER BY full_date DESC, fact_id DESC
        {limit_clause} {offset_clause};
    """
    return execute_query(sql, tuple(params) if params else None)


@st.cache_data(ttl=600, show_spinner=False)
def get_real_bctc_pdfs(ticker: str, limit: int = 12) -> pd.DataFrame:
    """Lấy danh sách PDF BCTC / Giải trình / Kiểm toán THẬT từ FiinGroup."""
    if is_snapshot_mode():
        df = _load_snapshot("disclosures_feed")
        sub = df[(df["ticker"] == ticker) & (df["has_attachment_pdf"] == True)].copy()
        mask = sub["title"].fillna("").str.lower().str.contains("báo cáo tài chính|bctc|kiểm toán|soát xét|giải trình")
        return sub[mask].sort_values("full_date", ascending=False).head(limit).reset_index(drop=True)
    sql = """
        SELECT full_date, ticker, title, source_name as source_type, attachment_pdf_url
        FROM mart_sentiment.view_disclosure_feed
        WHERE ticker = %s AND has_attachment_pdf = TRUE
          AND (LOWER(title) LIKE '%%báo cáo tài chính%%' OR LOWER(title) LIKE '%%bctc%%'
               OR LOWER(title) LIKE '%%kiểm toán%%' OR LOWER(title) LIKE '%%soát xét%%')
        ORDER BY full_date DESC
        LIMIT %s;
    """
    return execute_query(sql, (ticker, limit))


# =================================================================================
# 7. PHÂN HỆ EQUITY RESEARCH NÂNG CAO
# =================================================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_data_coverage_audit() -> pd.DataFrame:
    if is_snapshot_mode():
        return _load_snapshot("data_coverage_audit")
    sql = """
        SELECT
            b.ticker, b.short_name, b.tier_group, b.listing_exchange,
            a.expected_quarters, a.actual_quarters, a.missing_quarters,
            a.coverage_pct, a.earliest_quarter, a.latest_quarter,
            a.missing_quarter_list, a.last_audited_at
        FROM metadata.meta_data_coverage_audit a
        JOIN master_data.dim_bank b ON a.bank_sk = b.bank_sk
        ORDER BY a.coverage_pct DESC, b.tier_group ASC, b.ticker ASC;
    """
    return execute_query(sql)


@st.cache_data(ttl=600, show_spinner=False)
def get_earnings_quality_breakdown(ticker: Optional[str] = None, limit_quarters: int = 12) -> pd.DataFrame:
    if is_snapshot_mode():
        fs = _load_snapshot("financials_quarterly").copy()
        rt = _load_snapshot("ratios_quarterly")[[
            "ticker", "fiscal_year", "fiscal_quarter", "net_interest_margin",
            "cost_to_income_ratio", "credit_cost_ratio", "roe", "roa",
        ]].copy()
        df = fs.merge(rt, on=["ticker", "fiscal_year", "fiscal_quarter"], how="left")
        df["period_name"] = df["fiscal_year"].astype(int).astype(str) + "Q" + df["fiscal_quarter"].astype(int).astype(str)
        df["nii"] = df["net_interest_income"]
        df["nfi"] = df["net_fee_income"]
        df["toi"] = df["total_operating_income"]
        df["opex"] = df["general_and_admin_expenses"].abs()
        df["ppop"] = df["toi"] - df["opex"]
        df["pbt"] = df["net_profit_before_tax"]
        df["npat"] = df["net_profit_after_tax"]
        df["nim"] = df["net_interest_margin"]
        df["cir"] = df["cost_to_income_ratio"]
        if ticker:
            sub = df[df["ticker"] == ticker].sort_values(["fiscal_year", "fiscal_quarter"], ascending=[False, False]).head(limit_quarters)
            return sub.iloc[::-1].reset_index(drop=True)
        return df.sort_values(["fiscal_year", "fiscal_quarter"]).groupby("ticker", as_index=False).tail(1).sort_values("ppop", ascending=False).reset_index(drop=True)

    if ticker:
        sql = """
            SELECT
                bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
                CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
                nii, nfi, net_gain_fx, net_gain_securities, other_operating_income_residual,
                toi, opex, ppop, provision_expense, pbt, npat,
                nim, cir, credit_cost_ratio, roe, roa
            FROM mart_camels.view_earnings_quality_breakdown
            WHERE ticker = %s
            ORDER BY fiscal_year DESC, fiscal_quarter DESC
            LIMIT %s;
        """
        df = execute_query(sql, (ticker, limit_quarters))
        return df.iloc[::-1].reset_index(drop=True) if not df.empty else df
    sql = """
        WITH Ranked AS (
            SELECT
                bank_sk, ticker, short_name, tier_group, fiscal_year, fiscal_quarter,
                CONCAT(fiscal_year, 'Q', fiscal_quarter) as period_name,
                nii, nfi, net_gain_fx, net_gain_securities, other_operating_income_residual,
                toi, opex, ppop, provision_expense, pbt, npat,
                nim, cir, credit_cost_ratio, roe, roa,
                ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY fiscal_year DESC, fiscal_quarter DESC) as rn
            FROM mart_camels.view_earnings_quality_breakdown
        )
        SELECT * FROM Ranked WHERE rn = 1 ORDER BY ppop DESC;
    """
    return execute_query(sql)


@st.cache_data(ttl=600, show_spinner=False)
def get_credit_growth_dynamics(ticker: Optional[str] = None, limit_quarters: int = 12) -> pd.DataFrame:
    if is_snapshot_mode():
        fs = _load_snapshot("financials_quarterly")[[
            "ticker", "short_name", "tier_group", "fiscal_year", "fiscal_quarter",
            "loans_to_customers", "deposits_from_customers", "total_assets", "owners_equity",
        ]].copy()
        rt = _load_snapshot("ratios_quarterly")[[
            "ticker", "fiscal_year", "fiscal_quarter", "loan_growth_yoy", "deposit_growth_yoy",
            "credit_deposit_gap", "loan_to_deposit_ratio", "ldr_simple", "npl_ratio",
            "estimated_npl_amount", "loan_loss_reserve_to_npls", "capital_adequacy_ratio", "casa_ratio",
        ]].copy()
        df = fs.merge(rt, on=["ticker", "fiscal_year", "fiscal_quarter"], how="left")
        df["period_name"] = df["fiscal_year"].astype(int).astype(str) + "Q" + df["fiscal_quarter"].astype(int).astype(str)
        df["ldr_reported"] = df["loan_to_deposit_ratio"]
        if ticker:
            sub = df[df["ticker"] == ticker].sort_values(["fiscal_year", "fiscal_quarter"], ascending=[False, False]).head(limit_quarters)
            return sub.iloc[::-1].reset_index(drop=True)
        return df.sort_values(["fiscal_year", "fiscal_quarter"]).groupby("ticker", as_index=False).tail(1).reset_index(drop=True)

    if ticker:
        sql = """
            SELECT
                b.ticker, b.short_name, b.tier_group,
                f.fiscal_year, f.fiscal_quarter,
                CONCAT(f.fiscal_year, 'Q', f.fiscal_quarter) as period_name,
                f.loans_to_customers, f.deposits_from_customers, f.total_assets, f.owners_equity,
                r.loan_growth_yoy, r.deposit_growth_yoy, r.credit_deposit_gap,
                r.loan_to_deposit_ratio as ldr_reported, r.ldr_simple,
                r.npl_ratio, r.estimated_npl_amount, r.loan_loss_reserve_to_npls,
                r.capital_adequacy_ratio, r.casa_ratio
            FROM mart_camels.fact_quarterly_financial_statements f
            JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
            LEFT JOIN mart_camels.fact_quarterly_banking_ratios r
                ON f.bank_sk = r.bank_sk AND f.fiscal_year = r.fiscal_year AND f.fiscal_quarter = r.fiscal_quarter
            WHERE b.ticker = %s
            ORDER BY f.fiscal_year DESC, f.fiscal_quarter DESC
            LIMIT %s;
        """
        df = execute_query(sql, (ticker, limit_quarters))
        return df.iloc[::-1].reset_index(drop=True) if not df.empty else df
    sql = """
        WITH Ranked AS (
            SELECT
                b.ticker, b.short_name, b.tier_group,
                f.fiscal_year, f.fiscal_quarter,
                CONCAT(f.fiscal_year, 'Q', f.fiscal_quarter) as period_name,
                f.loans_to_customers, f.deposits_from_customers, f.total_assets, f.owners_equity,
                r.loan_growth_yoy, r.deposit_growth_yoy, r.credit_deposit_gap,
                r.loan_to_deposit_ratio as ldr_reported, r.ldr_simple,
                r.npl_ratio, r.estimated_npl_amount, r.loan_loss_reserve_to_npls,
                r.capital_adequacy_ratio, r.casa_ratio,
                ROW_NUMBER() OVER(PARTITION BY b.ticker ORDER BY f.fiscal_year DESC, f.fiscal_quarter DESC) as rn
            FROM mart_camels.fact_quarterly_financial_statements f
            JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
            LEFT JOIN mart_camels.fact_quarterly_banking_ratios r
                ON f.bank_sk = r.bank_sk AND f.fiscal_year = r.fiscal_year AND f.fiscal_quarter = r.fiscal_quarter
            WHERE b.bank_sk > 0
        )
        SELECT * FROM Ranked WHERE rn = 1 ORDER BY loan_growth_yoy DESC NULLS LAST;
    """
    return execute_query(sql)


@st.cache_data(ttl=300, show_spinner=False)
def get_financial_statement_notes(ticker: str, period_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Chỉ trả dữ liệu thuyết minh khi DB có bản ghi xác thực; chế độ Cloud Snapshot không bịa."""
    if is_snapshot_mode():
        return None
    sql = """
        SELECT ticker, period_name, auditor_name, auditor_opinion,
               executive_summary, key_strengths, red_flags, structured_notes,
               source_pdf_url, created_at
        FROM mart_camels.fact_financial_notes
        WHERE ticker = %s
        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 1;
    """
    try:
        df = execute_query(sql, (ticker,))
    except Exception:
        return None
    if not df.empty:
        row = df.iloc[0].to_dict()
        for k in ["key_strengths", "red_flags", "structured_notes"]:
            if isinstance(row.get(k), str):
                try:
                    row[k] = json.loads(row[k])
                except Exception:
                    pass
        return row
    return None
