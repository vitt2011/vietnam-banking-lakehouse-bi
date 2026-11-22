import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    
    tables = [
        "master_data.dim_bank",
        "master_data.dim_date",
        "master_data.dim_stakeholder",
        "mart_technical.fact_daily_market_ohlcv",
        "mart_camels.fact_quarterly_financial_statements",
        "mart_camels.fact_quarterly_banking_ratios",
        "mart_technical.fact_macro_indicators",
        "mart_sentiment.fact_media_sentiment_daily",
        "mart_governance.bridge_governance_network",
        "metadata.meta_assets",
        "metadata.meta_data_dictionary",
        "metadata.meta_pipeline_executions",
        "metadata.meta_data_quality_metrics"
    ]
    
    print("=== KIỂM TRA SỐ LƯỢNG BẢN GHI TRONG CÁC BẢNG POSTGRESQL ===")
    for t in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t};")
            cnt = cur.fetchone()[0]
            print(f"  {t:<45}: {cnt:>10,}")
        except Exception as e:
            print(f"  {t:<45}: LỖI ({e})")
            conn.rollback()
            
    views = [
        "mart_valuation.view_gordon_pb_roe_matrix",
        "mart_camels.view_camels_radar",
        "mart_technical.view_technical_market_daily",
        "mart_technical.view_macro_market_correlation",
        "mart_governance.view_governance_network",
        "mart_sentiment.view_disclosure_feed"
    ]
    print("\n=== KIỂM TRA SỐ LƯỢNG BẢN GHI TRONG CÁC VIEW DW_MARTS ===")
    for v in views:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {v};")
            cnt = cur.fetchone()[0]
            print(f"  {v:<45}: {cnt:>10,}")
        except Exception as e:
            print(f"  {v:<45}: LỖI ({e})")
            conn.rollback()
            
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
