"""
Build a clean, verified, error-fixed Parquet snapshot in `data_snapshot/`
for standalone deployment on Streamlit Community Cloud (and local Dual-Mode).

Fixes applied during snapshot build:
1. Unscrambles OHLCV `bank_sk` by matching `ticker` from Silver Parquet to `dim_bank`.
2. Fixes `provision_expense` using Income Statement `provision_for_credit_losses`
   (instead of Balance Sheet cumulative loan loss reserves).
3. Normalizes accounting signs (`CIR`, `LLR`, `avg_cost_of_funds` >= 0) and
   recomputes `credit_cost_ratio`.
4. Forward-fills `CAR` from latest semi-annual filing per bank with flag `is_car_carried_forward`.
5. Forward-fills `SBV_REFINANCING_RATE` and `USDVND_RATE` across trading days.
6. Recomputes `comovement_latest.json`, `valuation_residual_latest.json`, and
   `event_study_latest.json` on the unscrambled & cleaned dataset.
"""

import os
import sys
import json
import glob
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import psycopg2
import statsmodels.api as sm
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / "data_snapshot"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
QUANT_CACHE_DIR = REPO_ROOT / "runtime" / "quant_cache"
QUANT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ORIG_ROOT = Path(r"D:\Do_an_II\Stock_Analysis")
ORIG_LAKE = Path(r"D:\Do_an_II\DataLake")
load_dotenv(ORIG_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )


def fdr_bh(pvals: np.ndarray) -> np.ndarray:
    n = len(pvals)
    if n == 0:
        return pvals
    order = np.argsort(pvals)
    ranked = pvals[order]
    adj = np.empty(n)
    prev = 1.0
    for i in range(n - 1, -1, -1):
        val = min(prev, ranked[i] * n / (i + 1))
        adj[i] = val
        prev = val
    out = np.empty(n)
    out[order] = np.clip(adj, 0.0, 1.0)
    return out


def main():
    conn = get_conn()
    print("[1/7] Exporting dim_bank & coverage audit...")
    dim_bank = pd.read_sql(
        """
        SELECT bank_sk, ticker, bank_name, bank_name_en, short_name, tax_code,
               listing_exchange, tier_group, charter_capital_vnd::float8, is_active
        FROM master_data.dim_bank
        WHERE is_active = TRUE AND bank_sk > 0
        ORDER BY tier_group ASC, charter_capital_vnd DESC
        """,
        conn,
    )
    dim_bank.to_parquet(SNAPSHOT_DIR / "dim_bank.parquet", index=False)
    ticker_to_sk = dict(zip(dim_bank["ticker"], dim_bank["bank_sk"]))

    df_audit = pd.read_sql(
        """
        SELECT b.ticker, b.short_name, b.tier_group, b.listing_exchange,
               a.expected_quarters, a.actual_quarters, a.missing_quarters,
               a.coverage_pct::float8, a.earliest_quarter, a.latest_quarter,
               a.missing_quarter_list, a.last_audited_at
        FROM metadata.meta_data_coverage_audit a
        JOIN master_data.dim_bank b ON a.bank_sk = b.bank_sk
        ORDER BY a.coverage_pct DESC, b.tier_group ASC, b.ticker ASC
        """,
        conn,
    )
    df_audit.to_parquet(SNAPSHOT_DIR / "data_coverage_audit.parquet", index=False)

    print("[2/7] Building UNSCRAMBLED ohlcv_daily from Silver Parquet (keyed by ticker)...")
    ohlcv_files = glob.glob(
        str(ORIG_LAKE / "02_silver/02_structured/01_Giao_Dich_Gia_OHLCV/stock_ohlcv/**/*.parquet"),
        recursive=True,
    )
    df_ohlcv = pd.concat([pd.read_parquet(f) for f in ohlcv_files], ignore_index=True)
    df_ohlcv["trading_date"] = pd.to_datetime(df_ohlcv["trading_date"]).dt.date
    df_ohlcv["bank_sk"] = df_ohlcv["ticker"].map(ticker_to_sk)
    df_ohlcv = df_ohlcv.dropna(subset=["bank_sk"]).copy()
    df_ohlcv["bank_sk"] = df_ohlcv["bank_sk"].astype(int)
    df_ohlcv = df_ohlcv.drop_duplicates(subset=["ticker", "trading_date"], keep="last")
    df_ohlcv = df_ohlcv.sort_values(["ticker", "trading_date"]).reset_index(drop=True)

    # Rename & compute clean technical indicators with proper warm-up windows
    df_ohlcv = df_ohlcv.rename(
        columns={
            "open": "open_price",
            "high": "high_price",
            "low": "low_price",
            "close": "close_price",
        }
    )
    for col in ["open_price", "high_price", "low_price", "close_price", "turnover_vnd", "return_daily_pct"]:
        df_ohlcv[col] = pd.to_numeric(df_ohlcv[col], errors="coerce").astype("float64")
    df_ohlcv["volume"] = pd.to_numeric(df_ohlcv["volume"], errors="coerce").fillna(0).astype("int64")

    # Compute exact daily return from close if missing/noisy
    df_ohlcv["return_daily_pct"] = (
        df_ohlcv.groupby("ticker")["close_price"].pct_change()
    )
    df_ohlcv["sma_20"] = df_ohlcv.groupby("ticker")["close_price"].transform(
        lambda s: s.rolling(20, min_periods=20).mean()
    )
    df_ohlcv["sma_50"] = df_ohlcv.groupby("ticker")["close_price"].transform(
        lambda s: s.rolling(50, min_periods=50).mean()
    )
    df_ohlcv["sma_200"] = df_ohlcv.groupby("ticker")["close_price"].transform(
        lambda s: s.rolling(200, min_periods=200).mean()
    )
    df_ohlcv["avg_volume_20d"] = df_ohlcv.groupby("ticker")["volume"].transform(
        lambda s: s.rolling(20, min_periods=10).mean()
    )
    df_ohlcv["volume_surge_ratio"] = np.where(
        df_ohlcv["avg_volume_20d"] > 0,
        df_ohlcv["volume"] / df_ohlcv["avg_volume_20d"],
        np.nan,
    )

    keep_ohlcv = [
        "bank_sk", "ticker", "date_sk", "trading_date",
        "open_price", "high_price", "low_price", "close_price",
        "volume", "turnover_vnd", "return_daily_pct",
        "sma_20", "sma_50", "sma_200", "avg_volume_20d", "volume_surge_ratio",
    ]
    df_ohlcv = df_ohlcv[keep_ohlcv]
    df_ohlcv.to_parquet(SNAPSHOT_DIR / "ohlcv_daily.parquet", index=False)
    vcb_last = df_ohlcv[df_ohlcv["ticker"] == "VCB"].iloc[-1]
    abb_last = df_ohlcv[df_ohlcv["ticker"] == "ABB"].iloc[-1]
    print(f"    Verified latest OHLCV: VCB={vcb_last['close_price']:.0f} ({vcb_last['trading_date']}), ABB={abb_last['close_price']:.0f}")

    print("[3/7] Exporting macro_daily (with forward-filled SBV rate & USDVND)...")
    df_macro_raw = pd.read_sql(
        """
        SELECT d.full_date as trading_date, m.indicator_code, m.value::float8
        FROM mart_technical.fact_macro_indicators m
        JOIN master_data.dim_date d ON m.date_sk = d.date_sk
        WHERE m.indicator_code IN ('INDEX_VNINDEX_CLOSE', 'SBV_REFINANCING_RATE', 'USDVND_RATE', 'INDEX_VNFIN_CLOSE', 'INDEX_VN30_CLOSE')
        ORDER BY d.full_date ASC
        """,
        conn,
    )
    df_macro_raw["trading_date"] = pd.to_datetime(df_macro_raw["trading_date"]).dt.date
    piv_macro = df_macro_raw.pivot_table(
        index="trading_date", columns="indicator_code", values="value", aggfunc="last"
    ).sort_index()
    piv_macro = piv_macro.rename(
        columns={
            "INDEX_VNINDEX_CLOSE": "vnindex_close",
            "SBV_REFINANCING_RATE": "sbv_refinancing_rate",
            "USDVND_RATE": "usdvnd_rate",
            "INDEX_VNFIN_CLOSE": "vnfin_close",
            "INDEX_VN30_CLOSE": "vn30_close",
        }
    )
    for col in ["sbv_refinancing_rate", "usdvnd_rate", "vnfin_close", "vn30_close"]:
        if col in piv_macro.columns:
            piv_macro[col] = piv_macro[col].ffill()
    piv_macro = piv_macro.dropna(subset=["vnindex_close"]).reset_index()
    piv_macro.to_parquet(SNAPSHOT_DIR / "macro_daily.parquet", index=False)

    print("[4/7] Exporting CLEANED financials_quarterly & ratios_quarterly...")
    df_fs = pd.read_sql(
        """
        SELECT f.bank_sk, b.ticker, b.short_name, b.tier_group,
               f.fiscal_year, f.fiscal_quarter,
               f.total_assets::float8, f.cash_and_gold::float8, f.balances_with_sbv::float8,
               f.loans_to_customers::float8, f.provision_for_credit_losses::float8,
               f.total_liabilities::float8, f.deposits_from_customers::float8,
               f.owners_equity::float8, f.charter_capital::float8,
               f.net_interest_income::float8, f.net_fee_income::float8,
               f.total_operating_income::float8, f.general_and_admin_expenses::float8,
               f.provision_expense::float8, f.net_profit_before_tax::float8,
               f.net_profit_after_tax::float8, f.net_gain_fx::float8,
               f.net_gain_securities::float8, f.other_operating_income_residual::float8
        FROM mart_camels.fact_quarterly_financial_statements f
        JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
        WHERE b.bank_sk > 0
        ORDER BY b.ticker, f.fiscal_year, f.fiscal_quarter
        """,
        conn,
    )

    # Load Silver standardized_statements to recover TRUE Income Statement provision_for_credit_losses
    fs_files = glob.glob(
        str(ORIG_LAKE / "02_silver/02_structured/02_Bao_Cao_Tai_Chinh/standardized_statements/**/*.parquet"),
        recursive=True,
    )
    df_silver_fs = pd.concat([pd.read_parquet(f) for f in fs_files], ignore_index=True)
    df_silver_fs = df_silver_fs[["ticker", "fiscal_year", "fiscal_quarter", "provision_for_credit_losses"]].drop_duplicates(
        subset=["ticker", "fiscal_year", "fiscal_quarter"], keep="last"
    )
    df_silver_fs = df_silver_fs.rename(columns={"provision_for_credit_losses": "true_is_provision"})

    df_fs = df_fs.merge(df_silver_fs, on=["ticker", "fiscal_year", "fiscal_quarter"], how="left")
    # Fallback: toi - abs(opex) - pbt if Silver IS provision missing
    opex_abs = df_fs["general_and_admin_expenses"].abs()
    derived_prov = (df_fs["total_operating_income"] - opex_abs - df_fs["net_profit_before_tax"]).clip(lower=0.0)
    df_fs["provision_expense"] = np.where(
        df_fs["true_is_provision"].notna(),
        df_fs["true_is_provision"].abs(),
        derived_prov,
    )
    df_fs = df_fs.drop(columns=["true_is_provision"])
    df_fs.to_parquet(SNAPSHOT_DIR / "financials_quarterly.parquet", index=False)

    df_ratios = pd.read_sql(
        """
        SELECT r.bank_sk, b.ticker, b.short_name, b.tier_group,
               r.fiscal_year, r.fiscal_quarter,
               r.pb_ratio::float8, r.pe_ratio::float8, r.roe::float8, r.roa::float8,
               r.net_interest_margin::float8, r.cost_to_income_ratio::float8,
               r.npl_ratio::float8, r.loan_loss_reserve_to_npls::float8,
               r.capital_adequacy_ratio::float8, r.casa_ratio::float8,
               r.loan_to_deposit_ratio::float8, r.ldr_simple::float8,
               r.avg_yield_on_assets::float8, r.avg_cost_of_funds::float8,
               r.credit_cost_ratio::float8, r.estimated_npl_amount::float8,
               r.loan_growth_yoy::float8, r.deposit_growth_yoy::float8,
               r.credit_deposit_gap::float8
        FROM mart_camels.fact_quarterly_banking_ratios r
        JOIN master_data.dim_bank b ON r.bank_sk = b.bank_sk
        WHERE b.bank_sk > 0
        ORDER BY b.ticker, r.fiscal_year, r.fiscal_quarter
        """,
        conn,
    )
    # Fix accounting sign inversions & extreme outliers
    df_ratios["cost_to_income_ratio"] = df_ratios["cost_to_income_ratio"].abs()
    df_ratios["loan_loss_reserve_to_npls"] = df_ratios["loan_loss_reserve_to_npls"].abs()
    df_ratios["avg_cost_of_funds"] = df_ratios["avg_cost_of_funds"].abs()
    df_ratios.loc[(df_ratios["pe_ratio"] < -100) | (df_ratios["pe_ratio"] > 200), "pe_ratio"] = np.nan

    # Recompute TRUE credit_cost_ratio from fixed IS provision_expense
    df_ratios = df_ratios.merge(
        df_fs[["ticker", "fiscal_year", "fiscal_quarter", "provision_expense", "loans_to_customers"]],
        on=["ticker", "fiscal_year", "fiscal_quarter"],
        how="left",
    )
    df_ratios["credit_cost_ratio"] = np.where(
        df_ratios["loans_to_customers"] > 0,
        (df_ratios["provision_expense"].fillna(0.0) * 4.0) / df_ratios["loans_to_customers"],
        0.0,
    )
    df_ratios = df_ratios.drop(columns=["provision_expense", "loans_to_customers"])

    # Handle CAR=0 missingness in Q1/Q3/Q4: treat <=0 as NaN, carry-forward latest reported semi-annual CAR
    df_ratios = df_ratios.sort_values(["ticker", "fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    car_raw = df_ratios["capital_adequacy_ratio"].where(df_ratios["capital_adequacy_ratio"] > 0.01, np.nan)
    df_ratios["is_car_carried_forward"] = car_raw.isna() & car_raw.groupby(df_ratios["ticker"]).ffill().notna()
    df_ratios["capital_adequacy_ratio"] = car_raw.groupby(df_ratios["ticker"]).ffill().fillna(0.0)

    df_ratios.to_parquet(SNAPSHOT_DIR / "ratios_quarterly.parquet", index=False)
    vcb_q = df_ratios[(df_ratios["ticker"] == "VCB") & (df_ratios["fiscal_year"] == 2026) & (df_ratios["fiscal_quarter"] == 3)].iloc[0]
    print(f"    Verified VCB 2026Q3 ratios: CIR={vcb_q['cost_to_income_ratio']:.3f}, LLR={vcb_q['loan_loss_reserve_to_npls']:.3f}, CreditCost={vcb_q['credit_cost_ratio']:.4f}, CAR={vcb_q['capital_adequacy_ratio']:.4f}")

    print("[5/7] Exporting governance tables & corporate events...")
    pd.read_sql("SELECT ticker, shareholder_name, quantity::float8, ownership_pct::float8, update_date FROM mart_governance.fact_bank_shareholders", conn).to_parquet(SNAPSHOT_DIR / "shareholders.parquet", index=False)
    pd.read_sql("SELECT ticker, officer_name, position_title, ownership_pct::float8, shares_quantity::float8 FROM mart_governance.fact_bank_officers", conn).to_parquet(SNAPSHOT_DIR / "officers.parquet", index=False)
    pd.read_sql("SELECT ticker, subsidiary_name, ownership_pct::float8 FROM mart_governance.fact_bank_subsidiaries", conn).to_parquet(SNAPSHOT_DIR / "subsidiaries.parquet", index=False)
    pd.read_sql(
        """
        SELECT ticker, event_code as event_type, event_name_vi as event_title,
               exright_date, record_date, payout_date,
               value_per_share::float8, exercise_ratio::float8,
               COALESCE(event_name_en, event_name_vi) as event_details
        FROM mart_governance.fact_corporate_events
        """,
        conn,
    ).to_parquet(SNAPSHOT_DIR / "corporate_events.parquet", index=False)

    print("[6/7] Exporting compact official disclosures (2023-2026 + all BCTC PDF links)...")
    df_news = pd.read_sql(
        """
        SELECT fact_id, full_date, ticker, bank_name as short_name, tier_group,
               source_name as source_type, source_url, title, category_code, category_name,
               sentiment_score::float8, sentiment_label, attachment_pdf_url,
               has_attachment_pdf, is_official_disclosure
        FROM mart_sentiment.view_disclosure_feed
        WHERE full_date >= '2023-01-01'
           OR (has_attachment_pdf = TRUE AND (LOWER(title) LIKE '%%báo cáo tài chính%%' OR LOWER(title) LIKE '%%bctc%%'))
        ORDER BY full_date DESC, fact_id DESC
        """,
        conn,
    )
    df_news.to_parquet(SNAPSHOT_DIR / "disclosures_feed.parquet", index=False)

    # Save exact full-warehouse totals for platform KPI cards
    totals = pd.read_sql(
        """
        SELECT
            (SELECT COUNT(*) FROM mart_camels.fact_quarterly_financial_statements) as total_financials,
            (SELECT COUNT(*) FROM mart_camels.fact_quarterly_banking_ratios) as total_ratios,
            (SELECT COUNT(*) FROM mart_technical.fact_macro_indicators) as total_macro,
            (SELECT COUNT(*) FROM mart_sentiment.fact_media_sentiment_daily) as total_news,
            (SELECT COUNT(*) FROM mart_governance.bridge_governance_network) as total_governance_edges
        """,
        conn,
    ).iloc[0].to_dict()
    meta_kpis = {
        "total_ohlcv": int(len(df_ohlcv)),
        "total_financials": int(totals["total_financials"]),
        "total_ratios": int(totals["total_ratios"]),
        "total_macro": int(totals["total_macro"]),
        "total_news": int(totals["total_news"]),
        "total_governance_edges": int(totals["total_governance_edges"]),
        "latest_trading_date": df_ohlcv["trading_date"].max().strftime("%d/%m/%Y"),
    }
    with open(SNAPSHOT_DIR / "platform_kpis.json", "w", encoding="utf-8") as f:
        json.dump(meta_kpis, f, ensure_ascii=False, indent=2)

    print("[7/7] Recomputing Quant Caches on UNSCRAMBLED & CLEANED dataset...")
    # A. Comovement matrix on unscrambled OHLCV
    max_dt = df_ohlcv["trading_date"].max()
    min_dt = pd.Timestamp(max_dt) - pd.Timedelta(days=365)
    sub_px = df_ohlcv[pd.to_datetime(df_ohlcv["trading_date"]) >= min_dt].copy()
    piv_ret = sub_px.pivot(index="trading_date", columns="ticker", values="return_daily_pct").dropna(how="all")
    core_banks = [b for b in ["VCB", "BID", "CTG", "TCB", "MBB", "ACB", "VPB", "HDB", "STB", "VIB", "TPB", "SHB", "LPB"] if b in piv_ret.columns]
    corr_mat = piv_ret[core_banks].corr().round(4)
    pairs = []
    for i in range(len(core_banks)):
        for j in range(i + 1, len(core_banks)):
            pairs.append({"pair": f"{core_banks[i]}-{core_banks[j]}", "corr": float(corr_mat.loc[core_banks[i], core_banks[j]])})
    pairs.sort(key=lambda x: abs(x["corr"]), reverse=True)
    comovement_payload = {
        "metadata": {
            "lookback_days": 250,
            "banks_count": len(core_banks),
            "avg_sector_corr": round(float(np.mean([p["corr"] for p in pairs])), 4) if pairs else 0.0,
            "generated_at": datetime.now().isoformat(),
            "methodology_disclaimer": "Lag 0 contemporaneous return correlation on unscrambled OHLCV. Granger lead-lag tests are rejected after 15 bps transaction costs.",
        },
        "matrix": corr_mat.to_dict(),
        "top_correlated_pairs": pairs[:8],
    }
    with open(QUANT_CACHE_DIR / "comovement_latest.json", "w", encoding="utf-8") as f:
        json.dump(comovement_payload, f, ensure_ascii=False, indent=2)

    # B. Valuation Residual OLS on cleaned ratios (positive CIR, valid PB)
    reg_df = df_ratios[
        (df_ratios["pb_ratio"] > 0.2) & (df_ratios["pb_ratio"] < 5.0)
        & (df_ratios["roe"].between(-0.5, 0.5))
    ].dropna(subset=["pb_ratio", "roe", "net_interest_margin", "npl_ratio", "casa_ratio", "cost_to_income_ratio"]).copy()
    reg_df["ln_pb"] = np.log(reg_df["pb_ratio"])
    X_cols = ["roe", "net_interest_margin", "npl_ratio", "casa_ratio", "cost_to_income_ratio"]
    X = sm.add_constant(reg_df[X_cols])
    ols_fit = sm.OLS(reg_df["ln_pb"], X).fit(cov_type="cluster", cov_kwds={"groups": reg_df["ticker"]})
    reg_df["predicted_pb"] = np.exp(ols_fit.fittedvalues)
    reg_df["valuation_residual"] = reg_df["pb_ratio"] - reg_df["predicted_pb"]
    reg_df["residual_zscore"] = reg_df.groupby(["fiscal_year", "fiscal_quarter"])["valuation_residual"].transform(
        lambda s: (s - s.mean()) / (s.std() + 1e-9)
    )
    latest_rows = reg_df.sort_values(["fiscal_year", "fiscal_quarter"]).groupby("ticker").tail(1).sort_values("valuation_residual")
    ranking_list = []
    for _, r in latest_rows.iterrows():
        z = float(r["residual_zscore"])
        status = "CHIẾT KHẤU (Rẻ tương đối)" if z < -0.5 else ("CAO HƠN MẶT BẰNG" if z > 0.5 else "HỢP LÝ")
        ranking_list.append({
            "ticker": r["ticker"],
            "short_name": r["short_name"],
            "tier_group": r["tier_group"],
            "actual_pb": round(float(r["pb_ratio"]), 3),
            "predicted_pb": round(float(r["predicted_pb"]), 3),
            "valuation_residual": round(float(r["valuation_residual"]), 3),
            "residual_zscore": round(z, 2),
            "roe_pct": round(float(r["roe"]) * 100, 2),
            "npl_pct": round(float(r["npl_ratio"]) * 100, 2),
            "valuation_status": status,
        })
    val_payload = {
        "metadata": {
            "n_observations": int(ols_fit.nobs),
            "r_squared": round(float(ols_fit.rsquared), 4),
            "adj_r_squared": round(float(ols_fit.rsquared_adj), 4),
            "f_statistic": round(float(ols_fit.fvalue), 2) if ols_fit.fvalue is not None else 0.0,
            "residual_std": round(float(reg_df["valuation_residual"].std()), 4),
            "se_type": "Bank-Clustered Robust SE",
            "latest_quarter": f"{int(latest_rows['fiscal_year'].max())}Q{int(latest_rows['fiscal_quarter'].max())}",
            "generated_at": datetime.now().isoformat(),
        },
        "coefficients": [
            {"feature": k, "coef": round(float(ols_fit.params[k]), 4), "p_value": round(float(ols_fit.pvalues[k]), 4), "significant_5pct": bool(ols_fit.pvalues[k] < 0.05)}
            for k in ols_fit.params.index
        ],
        "latest_ranking": ranking_list,
    }
    with open(QUANT_CACHE_DIR / "valuation_residual_latest.json", "w", encoding="utf-8") as f:
        json.dump(val_payload, f, ensure_ascii=False, indent=2)

    # C. Event Study on UNSCRAMBLED OHLCV + corporate_events (Cash vs Stock Dividend)
    df_ev = pd.read_parquet(SNAPSHOT_DIR / "corporate_events.parquet")
    df_ev["exright_date"] = pd.to_datetime(df_ev["exright_date"]).dt.date
    df_ev = df_ev.dropna(subset=["exright_date"]).copy()
    df_ev["ev_cat"] = np.where(df_ev["value_per_share"].fillna(0) > 0, "CASH", np.where(df_ev["exercise_ratio"].fillna(0) > 0, "STOCK", "OTHER"))
    df_ev = df_ev[df_ev["ev_cat"].isin(["CASH", "STOCK"])].copy()

    # Market return from VNINDEX
    df_mkt = pd.read_parquet(SNAPSHOT_DIR / "macro_daily.parquet")[["trading_date", "vnindex_close"]].sort_values("trading_date")
    df_mkt["mkt_ret"] = df_mkt["vnindex_close"].pct_change()
    px_merged = df_ohlcv[["ticker", "trading_date", "return_daily_pct"]].merge(df_mkt[["trading_date", "mkt_ret"]], on="trading_date", how="inner").dropna()

    windows_def = [(-5, -1), (0, 5), (-5, 5), (-10, 10)]
    summary_rows = []
    car_curves = {"rel_days": list(range(-5, 6)), "CASH": [0.0]*11, "STOCK": [0.0]*11}
    pvals_all = []
    temp_rows = []

    for cat in ["CASH", "STOCK"]:
        sub_ev = df_ev[df_ev["ev_cat"] == cat]
        daily_ar_matrix = []
        win_cars = {w: [] for w in windows_def}
        for _, ev in sub_ev.iterrows():
            tk = ev["ticker"]
            ed = ev["exright_date"]
            s_tk = px_merged[px_merged["ticker"] == tk].sort_values("trading_date").reset_index(drop=True)
            if s_tk.empty:
                continue
            idx_list = s_tk.index[s_tk["trading_date"] >= ed]
            if len(idx_list) == 0:
                continue
            t0 = idx_list[0]
            if t0 < 130 or t0 + 11 >= len(s_tk):
                continue
            est = s_tk.iloc[t0 - 130 : t0 - 10]
            if len(est) < 60:
                continue
            cov_m = np.cov(est["return_daily_pct"], est["mkt_ret"])
            beta = cov_m[0, 1] / cov_m[1, 1] if cov_m[1, 1] > 0 else 1.0
            alpha = est["return_daily_pct"].mean() - beta * est["mkt_ret"].mean()
            ev_slice = s_tk.iloc[t0 - 10 : t0 + 11].copy()
            ev_slice["ar"] = ev_slice["return_daily_pct"] - (alpha + beta * ev_slice["mkt_ret"])
            ev_slice["rel_t"] = range(-10, 11)
            for w in windows_def:
                sub_w = ev_slice[(ev_slice["rel_t"] >= w[0]) & (ev_slice["rel_t"] <= w[1])]
                win_cars[w].append(float(sub_w["ar"].sum()))
            sub_11 = ev_slice[(ev_slice["rel_t"] >= -5) & (ev_slice["rel_t"] <= 5)]
            if len(sub_11) == 11:
                daily_ar_matrix.append(sub_11["ar"].cumsum().values * 100.0)
        if daily_ar_matrix:
            car_curves[cat] = [round(float(x), 3) for x in np.mean(daily_ar_matrix, axis=0)]
        from scipy import stats
        for w in windows_def:
            arr = np.array(win_cars[w])
            n_ev = len(arr)
            mean_pct = float(np.mean(arr) * 100) if n_ev else 0.0
            t_stat, p_raw = stats.ttest_1samp(arr, 0.0) if n_ev > 2 else (0.0, 1.0)
            pvals_all.append(float(p_raw))
            temp_rows.append({
                "event_type": "Cổ tức Tiền mặt" if cat == "CASH" else "Cổ tức Cổ phiếu",
                "event_code": cat,
                "window": f"[{w[0]:+d}, {w[1]:+d}]",
                "n_events": int(n_ev),
                "mean_car_pct": round(mean_pct, 4),
                "t_stat": round(float(t_stat), 3),
                "p_value_raw": round(float(p_raw), 4),
            })
    fdr_adj = fdr_bh(np.array(pvals_all))
    for i, row in enumerate(temp_rows):
        row["p_value_fdr_bh"] = round(float(fdr_adj[i]), 4)
        row["significant_fdr_5pct"] = bool(fdr_adj[i] < 0.05)
        summary_rows.append(row)

    ev_payload = {
        "metadata": {
            "total_events_analyzed": int(sum(r["n_events"] for r in summary_rows if r["window"] == "[-5, +5]")),
            "methodology": "Market Model OLS ([-130, -10]) + Benjamini-Hochberg FDR on Unscrambled OHLCV",
            "generated_at": datetime.now().isoformat(),
        },
        "windows_summary": summary_rows,
        "car_curves": car_curves,
    }
    with open(QUANT_CACHE_DIR / "event_study_latest.json", "w", encoding="utf-8") as f:
        json.dump(ev_payload, f, ensure_ascii=False, indent=2)

    conn.close()
    total_mb = sum(p.stat().st_size for p in SNAPSHOT_DIR.glob("*")) / (1024 * 1024)
    print(f"\nDONE! Snapshot saved at {SNAPSHOT_DIR} | Total size: {total_mb:.2f} MB")


if __name__ == "__main__":
    main()
