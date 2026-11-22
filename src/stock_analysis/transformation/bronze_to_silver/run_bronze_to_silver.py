"""
===================================================================================
TẬP LỆNH: src/transformation/bronze_to_silver/run_bronze_to_silver.py
CHỨC NĂNG: ĐIỀU PHỐI TOÀN BỘ PIPELINE BRONZE -> SILVER (DATA QUALITY GATEWAY 1)
===================================================================================
"""

import sys
from pathlib import Path
import time

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.transformation.bronze_to_silver.clean_market import run_clean_stock_ohlcv, run_clean_market_indices
from stock_analysis.transformation.bronze_to_silver.clean_financials import run_clean_financial_statements, run_clean_financial_ratios
from stock_analysis.transformation.bronze_to_silver.clean_news import run_clean_news
from stock_analysis.transformation.bronze_to_silver.clean_governance_and_macro import run_clean_governance, run_clean_macro


def main():
    t0 = time.time()
    print("=" * 80)
    print(">>> KHỞI CHẠY MASTER PIPELINE BRONZE -> SILVER (DATA QUALITY GATEWAY 1) <<<")
    print("=" * 80)

    run_clean_stock_ohlcv()
    run_clean_market_indices()
    run_clean_financial_statements()
    run_clean_financial_ratios()
    run_clean_governance()
    run_clean_macro()
    run_clean_news()

    print("\n" + "=" * 80)
    print(f">>> HOÀN TẤT XUẤT SẮC PIPELINE BRONZE -> SILVER TRONG {time.time()-t0:.2f} GIÂY! <<<")
    print("=" * 80)


run_all_bronze_to_silver = main


if __name__ == "__main__":
    main()
