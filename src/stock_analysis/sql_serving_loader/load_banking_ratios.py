"""
===================================================================================
MODULE: src/stock_analysis/sql_serving_loader/load_banking_ratios.py
CHỨC NĂNG: NẠP TỶ SỐ TÀI CHÍNH & CAMELS SCORECARD TỪ GOLD/SILVER VÀO POSTGRESQL
===================================================================================
Kiến trúc Medallion Lakehouse:
  - NGUỒN CHÍNH: data_lake/03_gold/02_The_Diem_CAMELS (Đã tính CAMELS & DQ3)
  - NGUỒN DỰ PHÒNG: data_lake/02_silver/02_structured/02_Bao_Cao_Tai_Chinh/camels_ratios
  - ĐÍCH: mart_camels.fact_quarterly_banking_ratios (PostgreSQL Serving)
  - LÀM GIÀU: Tự động tính toán các chỉ tiêu phái sinh (LDR, NIM, Credit Cost, Growth YoY)
===================================================================================
"""

import os
import sys
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.governance.lineage_tracker import update_dataset_state

GOLD_CAMELS_DIR = DATA_LAKE_DIR / "03_gold" / "02_The_Diem_CAMELS"
SILVER_RATIOS_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "camels_ratios"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ServingLoader_BankingRatios")


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def run_pipeline() -> bool:
    batch_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(">>> [SERVING LOADER] NẠP TỶ SỐ TÀI CHÍNH & CAMELS SANG POSTGRESQL <<<")
    logger.info("Batch ID: %s", batch_id)

    # Chọn nguồn: Ưu tiên Gold CAMELS, fallback sang Silver Ratios
    target_source_dir = None
    if GOLD_CAMELS_DIR.exists() and list(GOLD_CAMELS_DIR.rglob("*.parquet")):
        target_source_dir = GOLD_CAMELS_DIR
        source_layer = "03_gold"
    elif SILVER_RATIOS_DIR.exists() and list(SILVER_RATIOS_DIR.rglob("*.parquet")):
        target_source_dir = SILVER_RATIOS_DIR
        source_layer = "02_silver"
    else:
        logger.error("Không tìm thấy dữ liệu Tỷ số tài chính trong Silver hoặc Gold!")
        return False

    logger.info("Nguồn dữ liệu: %s (%s)", target_source_dir, source_layer)
    logger.info("=" * 80)

    conn = get_db_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO metadata.pipeline_execution_log 
            (pipeline_name, batch_id, stage_name, status, records_extracted, records_loaded)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            ("load_banking_ratios", batch_id, "SERVING_LOAD", "RUNNING", 0, 0),
        )
        conn.commit()

        logger.info("[1/5] Đang đọc Parquet từ %s ...", source_layer)
        parquet_files = list(target_source_dir.rglob("*.parquet"))
        dfs = [pd.read_parquet(pf) for pf in parquet_files]
        df = pd.concat(dfs, ignore_index=True)
        records_read = len(df)
        logger.info("      Đã đọc %d dòng tỷ số tài chính từ %d file Parquet.", records_read, len(parquet_files))

        # Khớp bank_sk chuẩn xác từ master_data.dim_bank dựa theo ticker
        cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank;")
        bank_mapping = dict(cur.fetchall())
        df["bank_sk"] = df["ticker"].astype(str).str.strip().str.upper().map(bank_mapping)

        df = df.dropna(subset=["bank_sk"]).copy()
        df["bank_sk"] = df["bank_sk"].astype(int)

        logger.info("[2/5] Chuẩn hóa thời gian và tính period_date_sk...")
        if "fiscal_year" not in df.columns:
            df["fiscal_year"] = pd.to_numeric(df.get("year", 0), errors="coerce").fillna(0).astype(int)
        if "fiscal_quarter" not in df.columns:
            df["fiscal_quarter"] = pd.to_numeric(df.get("quarter", 0), errors="coerce").fillna(0).astype(int)

        df["fiscal_year"] = df["fiscal_year"].astype(int)
        df["fiscal_quarter"] = df["fiscal_quarter"].astype(int)

        # Lọc chỉ các quý hợp lệ (1-4)
        df = df[df["fiscal_quarter"].isin([1, 2, 3, 4])].copy()

        def compute_date_sk(y, q):
            q_map = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
            return int(f"{y}{q_map.get(q, '1231')}")

        df["period_date_sk"] = [compute_date_sk(y, q) for y, q in zip(df["fiscal_year"], df["fiscal_quarter"])]

        logger.info("[3/5] Ánh xạ và chuẩn hóa các chỉ số CAMELS & Định giá...")
        def _get_val(candidates: list, default: Optional[float] = None) -> pd.Series:
            for c in candidates:
                if c in df.columns:
                    s = pd.to_numeric(df[c], errors="coerce")
                    if s.notna().any():
                        return s.round(4)
            return pd.Series(default, index=df.index)

        df["pb_ratio"] = _get_val(["pb_ratio", "pb"])
        df["pe_ratio"] = _get_val(["pe_ratio", "pe"])
        df["roe"] = _get_val(["roae_ttm_pct", "roe"])
        df["roa"] = _get_val(["roaa_ttm_pct", "roa"])
        df["net_interest_margin"] = _get_val(["nim_ttm_pct", "net_interest_margin", "nim"])
        df["cost_to_income_ratio"] = _get_val(["cir_pct", "cost_to_income_ratio", "cir"])
        df["npl_ratio"] = _get_val(["npl_ratio_pct", "npl_ratio", "npl"])
        df["loan_loss_reserve_to_npls"] = _get_val(["llr_coverage_pct", "loan_loss_reserve_to_npls", "loan_loss_reserves_to_npls", "llr"])
        df["capital_adequacy_ratio"] = _get_val(["car_total_pct", "capital_adequacy_ratio", "car"])
        df["casa_ratio"] = _get_val(["casa_ratio_pct", "casa_ratio"])
        df["loan_to_deposit_ratio"] = _get_val(["ldr_pure_pct", "loan_to_deposit_ratio", "ldr"])
        df["avg_yield_on_assets"] = _get_val(["avg_yield_on_assets", "avg_yield_on_earning_assets"])
        df["avg_cost_of_funds"] = _get_val(["avg_cost_of_funds", "avg_cost_of_financing"])

        logger.info("[4/5] Cổng kiểm định chất lượng tỷ số phục vụ Dashboard (DQ Gateway 3)...")
        # Kiểm tra tỷ số P/B không âm
        invalid_pb = int(((df["pb_ratio"].notna()) & (df["pb_ratio"] < 0)).sum())
        cur.execute(
            """
            INSERT INTO metadata.data_quality_log 
            (batch_id, gateway_level, rule_code, rule_description, records_tested, records_passed, records_failed, check_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                batch_id,
                "GATEWAY_3",
                "DQ_SERVING_RATIOS_PB_POSITIVE",
                "Tỷ số P/B phục vụ Dashboard không được âm",
                len(df),
                len(df) - invalid_pb,
                invalid_pb,
                "PASSED" if invalid_pb == 0 else "WARNING",
            ),
        )

        clean_df = df.drop_duplicates(subset=["bank_sk", "fiscal_year", "fiscal_quarter"], keep="last").copy()
        logger.info("      Số quý tỷ số tài chính hợp lệ: %d quý.", len(clean_df))

        logger.info("[5/5] Bulk Upsert vào mart_camels.fact_quarterly_banking_ratios...")
        insert_sql = """
            INSERT INTO mart_camels.fact_quarterly_banking_ratios (
                bank_sk, fiscal_year, fiscal_quarter, period_date_sk,
                pb_ratio, pe_ratio, roe, roa, net_interest_margin, cost_to_income_ratio,
                npl_ratio, loan_loss_reserve_to_npls, capital_adequacy_ratio, casa_ratio,
                loan_to_deposit_ratio, avg_yield_on_assets, avg_cost_of_funds
            ) VALUES %s
            ON CONFLICT (bank_sk, fiscal_year, fiscal_quarter) DO UPDATE SET
                period_date_sk = EXCLUDED.period_date_sk,
                pb_ratio = EXCLUDED.pb_ratio,
                pe_ratio = EXCLUDED.pe_ratio,
                roe = EXCLUDED.roe,
                roa = EXCLUDED.roa,
                net_interest_margin = EXCLUDED.net_interest_margin,
                cost_to_income_ratio = EXCLUDED.cost_to_income_ratio,
                npl_ratio = EXCLUDED.npl_ratio,
                loan_loss_reserve_to_npls = EXCLUDED.loan_loss_reserve_to_npls,
                capital_adequacy_ratio = EXCLUDED.capital_adequacy_ratio,
                casa_ratio = EXCLUDED.casa_ratio,
                loan_to_deposit_ratio = EXCLUDED.loan_to_deposit_ratio,
                avg_yield_on_assets = EXCLUDED.avg_yield_on_assets,
                avg_cost_of_funds = EXCLUDED.avg_cost_of_funds;
        """

        records = [
            (
                int(r.bank_sk),
                int(r.fiscal_year),
                int(r.fiscal_quarter),
                int(r.period_date_sk),
                None if pd.isna(r.pb_ratio) else float(r.pb_ratio),
                None if pd.isna(r.pe_ratio) else float(r.pe_ratio),
                None if pd.isna(r.roe) else float(r.roe),
                None if pd.isna(r.roa) else float(r.roa),
                None if pd.isna(r.net_interest_margin) else float(r.net_interest_margin),
                None if pd.isna(r.cost_to_income_ratio) else float(r.cost_to_income_ratio),
                None if pd.isna(r.npl_ratio) else float(r.npl_ratio),
                None if pd.isna(r.loan_loss_reserve_to_npls) else float(r.loan_loss_reserve_to_npls),
                None if pd.isna(r.capital_adequacy_ratio) else float(r.capital_adequacy_ratio),
                None if pd.isna(r.casa_ratio) else float(r.casa_ratio),
                None if pd.isna(r.loan_to_deposit_ratio) else float(r.loan_to_deposit_ratio),
                None if pd.isna(r.avg_yield_on_assets) else float(r.avg_yield_on_assets),
                None if pd.isna(r.avg_cost_of_funds) else float(r.avg_cost_of_funds),
            )
            for r in clean_df.itertuples(index=False)
        ]

        execute_values(cur, insert_sql, records, page_size=2000)
        conn.commit()

        logger.info("Tự động làm giàu các chỉ tiêu phái sinh từ BCTC (LDR, NPL Amount, Credit Cost, Growth)...")
        # 1. Tính toán ldr_simple, estimated_npl_amount, credit_cost_ratio kết nối với BCTC
        cur.execute("""
            UPDATE mart_camels.fact_quarterly_banking_ratios r
            SET 
                ldr_simple = CASE 
                    WHEN f.deposits_from_customers > 0 THEN ROUND(f.loans_to_customers / f.deposits_from_customers, 4)
                    ELSE NULL 
                END,
                estimated_npl_amount = ROUND(r.npl_ratio * f.loans_to_customers, 2),
                credit_cost_ratio = CASE 
                    WHEN f.loans_to_customers > 0 THEN ROUND((COALESCE(f.provision_expense, 0) * 4.0) / f.loans_to_customers, 4)
                    ELSE NULL 
                END,
                formula_version = 'v2.0-Medallion'
            FROM mart_camels.fact_quarterly_financial_statements f
            WHERE r.bank_sk = f.bank_sk AND r.fiscal_year = f.fiscal_year AND r.fiscal_quarter = f.fiscal_quarter;
        """)

        # 2. Tính toán tăng trưởng tín dụng YoY, huy động YoY và chênh lệch Tín dụng - Huy động
        cur.execute("""
            WITH growth_calc AS (
                SELECT 
                    bank_sk, 
                    fiscal_year, 
                    fiscal_quarter,
                    ROUND((loans_to_customers - LAG(loans_to_customers, 4) OVER (PARTITION BY bank_sk ORDER BY fiscal_year, fiscal_quarter)) 
                          / NULLIF(LAG(loans_to_customers, 4) OVER (PARTITION BY bank_sk ORDER BY fiscal_year, fiscal_quarter), 0), 4) AS l_growth,
                    ROUND((deposits_from_customers - LAG(deposits_from_customers, 4) OVER (PARTITION BY bank_sk ORDER BY fiscal_year, fiscal_quarter)) 
                          / NULLIF(LAG(deposits_from_customers, 4) OVER (PARTITION BY bank_sk ORDER BY fiscal_year, fiscal_quarter), 0), 4) AS d_growth
                FROM mart_camels.fact_quarterly_financial_statements
            )
            UPDATE mart_camels.fact_quarterly_banking_ratios r
            SET 
                loan_growth_yoy = g.l_growth,
                deposit_growth_yoy = g.d_growth,
                credit_deposit_gap = (g.l_growth - g.d_growth)
            FROM growth_calc g
            WHERE r.bank_sk = g.bank_sk AND r.fiscal_year = g.fiscal_year AND r.fiscal_quarter = g.fiscal_quarter;
        """)
        conn.commit()

        records_loaded = len(records)
        duration = round(time.time() - start_time, 2)

        cur.execute(
            """
            UPDATE metadata.pipeline_execution_log
            SET status = 'SUCCESS',
                records_extracted = %s,
                records_loaded = %s,
                execution_duration_sec = %s
            WHERE batch_id = %s;
            """,
            (records_read, records_loaded, duration, batch_id),
        )
        conn.commit()

        update_dataset_state(
            dataset_name="banking_ratios_camels",
            target_table="mart_camels.fact_quarterly_banking_ratios",
            run_id=batch_id,
            record_count=records_loaded,
        )

        logger.info("=" * 80)
        logger.info(">>> HOÀN TẤT NẠP TỶ SỐ TÀI CHÍNH TỪ LAKEHOUSE SANG POSTGRESQL! <<<")
        logger.info("Đã nạp: %d quý tỷ số vào fact_quarterly_banking_ratios", records_loaded)
        logger.info("Thời gian thực thi: %.2f giây", duration)
        logger.info("=" * 80)
        return True

    except Exception as e:
        conn.rollback()
        duration = round(time.time() - start_time, 2)
        logger.error("LỖI SERVING LOADER TỶ SỐ: %s", str(e), exc_info=True)
        try:
            cur.execute(
                """
                UPDATE metadata.pipeline_execution_log
                SET status = 'FAILED',
                    error_message = %s,
                    execution_duration_sec = %s
                WHERE batch_id = %s;
                """,
                (str(e), duration, batch_id),
            )
            conn.commit()
        except Exception:
            pass
        return False
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    if not run_pipeline():
        sys.exit(1)
