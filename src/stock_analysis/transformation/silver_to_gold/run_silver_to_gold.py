"""
===================================================================================
TẬP LỆNH: src/transformation/silver_to_gold/run_silver_to_gold.py
CHỨC NĂNG: ĐIỀU PHỐI TOÀN BỘ PIPELINE SILVER -> GOLD (DATA QUALITY GATEWAY 2)
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

from stock_analysis.transformation.silver_to_gold.feature_technical_indicators import run_feature_technical_indicators
from stock_analysis.transformation.silver_to_gold.feature_camels_engine import run_feature_camels_engine
from stock_analysis.transformation.silver_to_gold.feature_valuation_matrix import run_feature_valuation_matrix
from stock_analysis.transformation.silver_to_gold.feature_governance_analytics import run_feature_governance_analytics
from stock_analysis.transformation.silver_to_gold.feature_news_sentiment import run_feature_news_sentiment


def main():
    t0 = time.time()
    print("=" * 80)
    print(">>> KHỞI CHẠY MASTER PIPELINE SILVER -> GOLD (DATA QUALITY GATEWAY 2) <<<")
    print("=" * 80)

    run_feature_technical_indicators()
    run_feature_camels_engine()
    run_feature_valuation_matrix()
    run_feature_governance_analytics()
    run_feature_news_sentiment()

    print("\n" + "=" * 80)
    print(f">>> HOÀN TẤT XUẤT SẮC PIPELINE SILVER -> GOLD TRONG {time.time()-t0:.2f} GIÂY! <<<")
    print("=" * 80)


run_all_silver_to_gold = main


if __name__ == "__main__":
    main()
