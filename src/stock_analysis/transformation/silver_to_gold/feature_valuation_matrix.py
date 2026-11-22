"""
===================================================================================
FEATURE ENGINE: src/transformation/silver_to_gold/feature_valuation_matrix.py
CHỨC NĂNG: TÍNH TOÁN MA TRẬN ĐỊNH GIÁ GORDON (P/B vs ROE) SANG TẦNG GOLD
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 110-111 & Phần 6, Mục 829-839)
Đầu ra: data_lake/03_gold/valuation_matrix_daily/year=YYYY/month=MM/
===================================================================================
"""

import sys
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR
SILVER_STOCK_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "01_Giao_Dich_Gia_OHLCV" / "stock_ohlcv"
SILVER_RATIOS_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "camels_ratios"
GOLD_VAL_DIR = DATA_LAKE_DIR / "03_gold" / "01_Ma_Tran_Dinh_Gia_Gordon"
GOLD_VAL_DIR.mkdir(parents=True, exist_ok=True)


def run_feature_valuation_matrix():
    print(">>> [GOLD 3/5] Feature Engine: Ma trận Định giá Kim Cương (P/B vs ROE - Gordon Model)...")

    stock_files = list(SILVER_STOCK_DIR.rglob("*.snappy.parquet"))
    ratio_files = list(SILVER_RATIOS_DIR.rglob("*.snappy.parquet"))

    if not stock_files or not ratio_files:
        print("      Không tìm thấy dữ liệu giá hoặc tỷ số tài chính!")
        return 0

    df_stock = pd.concat([pd.read_parquet(f) for f in stock_files], ignore_index=True)
    df_ratios = pd.concat([pd.read_parquet(f) for f in ratio_files], ignore_index=True)

    # Chuẩn hoá tỷ số tài chính mới nhất theo quý
    ratio_cols = [c for c in ["pb", "pb_ratio", "pe", "pe_ratio", "roe", "bvps", "eps", "roae_ttm_pct"] if c in df_ratios.columns]
    keep_cols = ["ticker", "fiscal_year", "fiscal_quarter"] + ratio_cols
    df_ratios_clean = df_ratios[keep_cols].copy()

    # Tính P/B và ROE
    if "pb_ratio" in df_ratios_clean.columns:
        df_ratios_clean["pb_ratio"] = pd.to_numeric(df_ratios_clean["pb_ratio"], errors="coerce")
    elif "pb" in df_ratios_clean.columns:
        df_ratios_clean["pb_ratio"] = pd.to_numeric(df_ratios_clean["pb"], errors="coerce")
    else:
        df_ratios_clean["pb_ratio"] = 1.2

    if "roe" in df_ratios_clean.columns:
        df_ratios_clean["roe"] = pd.to_numeric(df_ratios_clean["roe"], errors="coerce")
    elif "roae_ttm_pct" in df_ratios_clean.columns:
        df_ratios_clean["roe"] = pd.to_numeric(df_ratios_clean["roae_ttm_pct"], errors="coerce")
    else:
        df_ratios_clean["roe"] = 0.15

    df_ratios_clean = df_ratios_clean.dropna(subset=["pb_ratio", "roe"]).copy()
    df_ratios_clean = df_ratios_clean[(df_ratios_clean["pb_ratio"] > 0) & (df_ratios_clean["pb_ratio"] < 5.0)]

    # Tính hệ số hiệu quả định giá và phân vùng Gordon
    med_pb = df_ratios_clean["pb_ratio"].median()
    med_roe = df_ratios_clean["roe"].median()

    df_ratios_clean["roe_to_pb_efficiency"] = (df_ratios_clean["roe"] / (df_ratios_clean["pb_ratio"] + 1e-6)).round(2)

    def classify_zone(r):
        if r["roe"] >= med_roe and r["pb_ratio"] <= med_pb:
            return "DIAMOND_UNDERVALUED"
        elif r["roe"] >= med_roe and r["pb_ratio"] > med_pb:
            return "QUALITY_LEADER"
        elif r["roe"] < med_roe and r["pb_ratio"] <= med_pb:
            return "VALUE_TRAP"
        else:
            return "OVERVALUED"

    df_ratios_clean["gordon_zone"] = df_ratios_clean.apply(classify_zone, axis=1)

    # Ghi Hive partitioned: year=YYYY/quarter=Q/
    total_written = 0
    for (year, quarter), part_df in df_ratios_clean.groupby(["fiscal_year", "fiscal_quarter"]):
        part_dir = GOLD_VAL_DIR / f"year={year}" / f"quarter={quarter}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.to_parquet(part_file, compression="snappy", index=False)
        total_written += len(part_df)

    print(f"      [✓] Hoàn tất xuất bản Gold Valuation Matrix: {total_written:,} kỳ tại {GOLD_VAL_DIR}")
    return total_written


if __name__ == "__main__":
    run_feature_valuation_matrix()
