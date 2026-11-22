"""
Pre-flight Data Validation and Research Snapshot Extraction
Location: Stock_Analysis/scripts/quant_research/00_preflight_data_snapshot.py
Purpose:
  - Connect to PostgreSQL in STRICT Read-Only mode.
  - Extract OHLCV, Financial Ratios, Corporate Events, Macro Indicators.
  - Build Common Trading Calendar & Missing Rate Matrix.
  - Calculate SHA256 hashes and save manifest.
"""

import os
import sys
import json
import hashlib
from datetime import datetime
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Path configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime", "research_snapshots")
os.makedirs(RUNTIME_DIR, exist_ok=True)

# Load environment variables
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "Stock_Warehouse")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")

DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_engine():
    return create_engine(DB_URL, connect_args={"options": "-c default_transaction_read_only=on"})

def compute_sha256(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def extract_ohlcv(engine):
    print("[1/4] Extracting Daily OHLCV for 27 Banks...")
    query = """
    SELECT 
        d.full_date AS date_actual,
        b.ticker,
        b.tier_group,
        b.listing_exchange,
        f.open_price,
        f.high_price,
        f.low_price,
        f.close_price,
        f.volume,
        f.turnover_vnd,
        f.return_daily_pct
    FROM mart_technical.fact_daily_market_ohlcv f
    JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
    JOIN master_data.dim_date d ON f.date_sk = d.date_sk
    ORDER BY b.ticker, d.full_date;
    """
    df = pd.read_sql(text(query), engine)
    
    # Save CSV
    out_csv = os.path.join(RUNTIME_DIR, "daily_ohlcv.csv")
    df.to_csv(out_csv, index=False)
    print(f" -> Saved {len(df):,} rows to {out_csv}")
    return df, out_csv

def extract_financials(engine):
    print("[2/4] Extracting Financials & CAMELS Ratios...")
    query = """
    SELECT 
        b.ticker,
        b.tier_group,
        f.fiscal_year,
        f.fiscal_quarter,
        d.full_date AS period_date,
        f.pb_ratio,
        f.pe_ratio,
        f.roe,
        f.roa,
        f.net_interest_margin AS nim,
        f.cost_to_income_ratio AS cir,
        f.npl_ratio,
        f.loan_loss_reserve_to_npls AS llr,
        f.capital_adequacy_ratio AS car,
        f.casa_ratio,
        f.loan_to_deposit_ratio AS ldr,
        f.credit_cost_ratio AS credit_cost,
        f.credit_deposit_gap,
        f.loan_growth_yoy,
        f.deposit_growth_yoy,
        fs.total_assets,
        fs.loans_to_customers,
        fs.deposits_from_customers,
        fs.owners_equity,
        fs.net_interest_income,
        fs.total_operating_income,
        fs.net_profit_before_tax,
        fs.net_profit_after_tax,
        fs.provision_expense
    FROM mart_camels.fact_quarterly_banking_ratios f
    JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk
    JOIN master_data.dim_date d ON f.period_date_sk = d.date_sk
    LEFT JOIN mart_camels.fact_quarterly_financial_statements fs 
        ON f.bank_sk = fs.bank_sk 
        AND f.fiscal_year = fs.fiscal_year 
        AND f.fiscal_quarter = fs.fiscal_quarter
    ORDER BY b.ticker, f.fiscal_year, f.fiscal_quarter;
    """
    df = pd.read_sql(text(query), engine)
    out_csv = os.path.join(RUNTIME_DIR, "quarterly_financials.csv")
    df.to_csv(out_csv, index=False)
    print(f" -> Saved {len(df):,} rows to {out_csv}")
    return df, out_csv

def extract_corporate_events(engine):
    print("[3/4] Extracting Corporate Events...")
    query = """
    SELECT 
        e.ticker,
        e.event_code,
        e.event_name_vi,
        e.public_date,
        e.exright_date,
        e.record_date,
        e.payout_date,
        e.value_per_share,
        e.exercise_ratio
    FROM mart_governance.fact_corporate_events e
    ORDER BY e.ticker, COALESCE(e.exright_date, e.public_date);
    """
    df = pd.read_sql(text(query), engine)
    out_csv = os.path.join(RUNTIME_DIR, "corporate_events.csv")
    df.to_csv(out_csv, index=False)
    print(f" -> Saved {len(df):,} rows to {out_csv}")
    return df, out_csv

def extract_macro_indicators(engine):
    print("[4/4] Extracting Macro & Industry Indicators...")
    query = """
    SELECT 
        f.indicator_code,
        d.full_date AS date_actual,
        f.indicator_name,
        f.category,
        f.value,
        f.unit,
        f.frequency
    FROM mart_technical.fact_macro_indicators f
    JOIN master_data.dim_date d ON f.date_sk = d.date_sk
    ORDER BY f.indicator_code, d.full_date;
    """
    df = pd.read_sql(text(query), engine)
    out_csv = os.path.join(RUNTIME_DIR, "macro_indicators.csv")
    df.to_csv(out_csv, index=False)
    print(f" -> Saved {len(df):,} rows to {out_csv}")
    return df, out_csv

def build_data_quality_report(df_ohlcv, df_fin, df_events, df_macro):
    print("Building Data Quality & Common Trading Calendar Report...")
    
    df_ohlcv['date_actual'] = pd.to_datetime(df_ohlcv['date_actual'])
    df_macro['date_actual'] = pd.to_datetime(df_macro['date_actual'])
    
    # Identify VN-Index as the market benchmark calendar from macro indicators
    vnindex_series = df_macro[df_macro['indicator_code'] == 'INDEX_VNINDEX_CLOSE']
    vnindex_dates = set(vnindex_series['date_actual'])
    total_vnindex_days = len(vnindex_dates)
    
    stock_stats = []
    tickers = sorted(df_ohlcv['ticker'].unique())
    
    for t in tickers:
        sub = df_ohlcv[df_ohlcv['ticker'] == t]
        dates = set(sub['date_actual'])
        min_date = sub['date_actual'].min()
        max_date = sub['date_actual'].max()
        count_days = len(sub)
        
        active_vnindex_dates = {d for d in vnindex_dates if min_date <= d <= max_date}
        missing_in_range = len(active_vnindex_dates - dates)
        coverage_pct = round((count_days / len(active_vnindex_dates) * 100), 2) if active_vnindex_dates else 0.0
        
        p_pre2015 = len(sub[sub['date_actual'] < '2015-01-01'])
        p_2015_2019 = len(sub[(sub['date_actual'] >= '2015-01-01') & (sub['date_actual'] < '2020-01-01')])
        p_2020_2026 = len(sub[sub['date_actual'] >= '2020-01-01'])
        
        tier = sub['tier_group'].iloc[0] if 'tier_group' in sub.columns else 'UNKNOWN'
        
        stock_stats.append({
            "ticker": t,
            "tier_group": tier,
            "min_date": str(min_date.date()) if pd.notnull(min_date) else None,
            "max_date": str(max_date.date()) if pd.notnull(max_date) else None,
            "total_trading_days": count_days,
            "active_market_days": len(active_vnindex_dates),
            "missing_days_in_range": missing_in_range,
            "coverage_pct": coverage_pct,
            "days_pre_2015": p_pre2015,
            "days_2015_2019": p_2015_2019,
            "days_2020_2026": p_2020_2026
        })
        
    df_stock_stats = pd.DataFrame(stock_stats)
    
    # Financial Coverage Analysis
    fin_stats = []
    fin_tickers = sorted(df_fin['ticker'].unique())
    for t in fin_tickers:
        sub = df_fin[df_fin['ticker'] == t]
        fin_stats.append({
            "ticker": t,
            "total_quarters": len(sub),
            "min_quarter": f"{sub['fiscal_year'].min()}Q{sub['fiscal_quarter'].min()}",
            "max_quarter": f"{sub['fiscal_year'].max()}Q{sub['fiscal_quarter'].max()}",
            "roe_missing": int(sub['roe'].isna().sum()),
            "nim_missing": int(sub['nim'].isna().sum()),
            "npl_missing": int(sub['npl_ratio'].isna().sum()),
            "pb_missing": int(sub['pb_ratio'].isna().sum()),
            "cir_missing": int(sub['cir'].isna().sum()),
            "car_missing": int(sub['car'].isna().sum())
        })
    df_fin_stats = pd.DataFrame(fin_stats)
    
    # Corporate Events Summary
    event_counts = df_events['event_code'].value_counts().to_dict()
    events_with_public_date = int(df_events['public_date'].notna().sum())
    events_with_exright_date = int(df_events['exright_date'].notna().sum())
    events_with_both = int((df_events['public_date'].notna() & df_events['exright_date'].notna()).sum())
    
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_vnindex_trading_days": total_vnindex_days,
        "banking_tickers_count": len(stock_stats),
        "corporate_events_breakdown": {
            "total_events": len(df_events),
            "by_code": event_counts,
            "events_with_public_date": events_with_public_date,
            "events_with_exright_date": events_with_exright_date,
            "events_with_both_dates": events_with_both
        },
        "macro_indicators_count": len(df_macro['indicator_code'].unique()),
        "macro_series_list": sorted(df_macro['indicator_code'].unique().tolist())
    }
    
    return summary, df_stock_stats, df_fin_stats

def main():
    print("=" * 70)
    print("RUN 2: PRE-FLIGHT DATA SNAPSHOT & EMPIRICAL AUDIT")
    print("=" * 70)
    
    engine = get_engine()
    
    # Extraction
    df_ohlcv, path_ohlcv = extract_ohlcv(engine)
    df_fin, path_fin = extract_financials(engine)
    df_events, path_events = extract_corporate_events(engine)
    df_macro, path_macro = extract_macro_indicators(engine)
    
    # Auditing
    summary, df_stock_stats, df_fin_stats = build_data_quality_report(df_ohlcv, df_fin, df_events, df_macro)
    
    # Save statistics
    stats_ohlcv_path = os.path.join(RUNTIME_DIR, "trading_calendar_coverage.csv")
    df_stock_stats.to_csv(stats_ohlcv_path, index=False)
    
    stats_fin_path = os.path.join(RUNTIME_DIR, "financials_coverage.csv")
    df_fin_stats.to_csv(stats_fin_path, index=False)
    
    summary_path = os.path.join(RUNTIME_DIR, "preflight_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    # Manifest with SHA256
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "files": {
            "daily_ohlcv.csv": {
                "path": path_ohlcv,
                "rows": len(df_ohlcv),
                "sha256": compute_sha256(path_ohlcv)
            },
            "quarterly_financials.csv": {
                "path": path_fin,
                "rows": len(df_fin),
                "sha256": compute_sha256(path_fin)
            },
            "corporate_events.csv": {
                "path": path_events,
                "rows": len(df_events),
                "sha256": compute_sha256(path_events)
            },
            "macro_indicators.csv": {
                "path": path_macro,
                "rows": len(df_macro),
                "sha256": compute_sha256(path_macro)
            }
        }
    }
    manifest_path = os.path.join(RUNTIME_DIR, "snapshot_manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
        
    print("=" * 70)
    print("SUCCESS: Pre-flight data snapshots, hashes, and calendar audits generated!")
    print(f"Manifest saved to: {manifest_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
