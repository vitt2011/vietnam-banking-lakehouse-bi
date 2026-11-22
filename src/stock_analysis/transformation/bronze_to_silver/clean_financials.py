"""
===================================================================================
PIPELINE: src/transformation/bronze_to_silver/clean_financials.py
CHỨC NĂNG: LÀM SẠCH VÀ CHUẨN HÓA BÁO CÁO TÀI CHÍNH & TỶ SỐ SANG TẦNG SILVER
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 95-99)
Đầu ra: data_lake/02_silver/financials/standardized_statements/year=YYYY/quarter=Q/
===================================================================================
"""

import sys
from pathlib import Path
from datetime import datetime

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

from stock_analysis.governance.gateways import (
    validate_dq1,
    validate_dq2,
)

BRONZE_STATEMENTS_PATH = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "02_Bao_Cao_Tai_Chinh" / "vnstock_financial_statements.parquet"
BRONZE_RATIOS_PATH = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "02_Bao_Cao_Tai_Chinh" / "vnstock_financial_ratios.parquet"
SILVER_BANK_PATH = DATA_LAKE_DIR / "02_silver" / "01_master_data" / "mdm_bank.snappy.parquet"

SILVER_FIN_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "standardized_statements"
SILVER_RATIOS_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "camels_ratios"


def run_clean_financial_statements() -> int:
    print(">>> [SILVER 3/4] Chuyển đổi Bronze -> Silver: Báo cáo tài chính (CĐKT, KQKD, LCTT)...")
    if not BRONZE_STATEMENTS_PATH.exists():
        print(f"      Không tìm thấy {BRONZE_STATEMENTS_PATH}, bỏ qua.")
        return 0

    df_raw = pd.read_parquet(BRONZE_STATEMENTS_PATH)
    print(f"      Đã đọc {len(df_raw):,} kỳ báo cáo tài chính thô.")

    # DQ1 validation (Cổng gác số 1 tập trung)
    valid_df, _, metrics = validate_dq1(df_raw, dataset_type="financial_statements", source_name="vnstock_bctc")
    print(f"      [DQ1] Tỷ lệ đạt chuẩn: {metrics['pass_rate_pct']}% ({len(valid_df):,} kỳ hợp lệ).")

    # DQ2 validation: Đối soát phương trình cân đối kế toán sống còn (Cổng gác số 2 tập trung)
    valid_df, _, dq2_metrics = validate_dq2(valid_df, source_name="vnstock_bctc", quarantine=True)
    print(f"      [DQ2] Đối soát Cân đối Kế toán: Pass rate {dq2_metrics['pass_rate_pct']}% ({len(valid_df):,} kỳ đạt chuẩn).")

    # Đọc MDM Bank để map bank_uuid
    df_banks = pd.read_parquet(SILVER_BANK_PATH)
    bank_map = df_banks.set_index("ticker")[["bank_uuid", "bank_sk"]].to_dict(orient="index")

    ticker_col = "ticker" if "ticker" in valid_df.columns else "symbol"
    
    if "fiscal_year" not in valid_df.columns and "period" in valid_df.columns:
        def _parse(val):
            s = str(val).strip()
            if "-Q" in s:
                p = s.split("-Q")
                return int(p[0]), int(p[1])
            elif "Q" in s:
                p = s.split("Q")
                return int(p[0]), int(p[1])
            elif len(s) == 4 and s.isdigit():
                return int(s), 0
            return None, None
        parsed = valid_df["period"].apply(_parse)
        valid_df["fiscal_year"] = parsed.apply(lambda x: x[0])
        valid_df["fiscal_quarter"] = parsed.apply(lambda x: x[1])
    else:
        year_col = "year" if "year" in valid_df.columns else "fiscal_year"
        quarter_col = "quarter" if "quarter" in valid_df.columns else "fiscal_quarter"
        valid_df["fiscal_year"] = valid_df[year_col].astype(int)
        valid_df["fiscal_quarter"] = valid_df[quarter_col].astype(int)

    valid_df["ticker"] = valid_df[ticker_col]
    valid_df = valid_df.dropna(subset=["fiscal_year", "fiscal_quarter"])
    valid_df["fiscal_year"] = valid_df["fiscal_year"].astype(int)
    valid_df["fiscal_quarter"] = valid_df["fiscal_quarter"].astype(int)
    valid_df["bank_uuid"] = valid_df["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_uuid", ""))
    valid_df["bank_sk"] = valid_df["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_sk", 0))

    # Ghi Hive partitioned: year=YYYY/quarter=Q/
    total_written = 0
    for (year, quarter), part_df in valid_df.groupby(["fiscal_year", "fiscal_quarter"]):
        part_dir = SILVER_FIN_DIR / f"year={year}" / f"quarter={quarter}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.to_parquet(part_file, compression="snappy", index=False)
        total_written += len(part_df)

    print(f"      [✓] Đã xuất bản Silver Statements: {total_written:,} kỳ BCTC tại {SILVER_FIN_DIR}")
    return total_written


def run_clean_financial_ratios() -> int:
    print(">>> [SILVER 4/4] Chuyển đổi Bronze -> Silver: Tỷ số tài chính CAMELS...")
    if not BRONZE_RATIOS_PATH.exists():
        print(f"      Không tìm thấy {BRONZE_RATIOS_PATH}, bỏ qua.")
        return 0

    df_ratios = pd.read_parquet(BRONZE_RATIOS_PATH)
    print(f"      Đã đọc {len(df_ratios):,} dòng tỷ số tài chính thô.")

    df_banks = pd.read_parquet(SILVER_BANK_PATH)
    bank_map = df_banks.set_index("ticker")[["bank_uuid", "bank_sk"]].to_dict(orient="index")

    ticker_col = "ticker" if "ticker" in df_ratios.columns else "symbol"
    
    if "year" in df_ratios.columns and "quarter" in df_ratios.columns:
        df_ratios["fiscal_year"] = pd.to_numeric(df_ratios["year"], errors="coerce").fillna(0).astype(int)
        df_ratios["fiscal_quarter"] = pd.to_numeric(df_ratios["quarter"], errors="coerce").fillna(0).astype(int)
    else:
        def _parse(val):
            s = str(val).strip()
            if "-Q" in s:
                p = s.split("-Q")
                return int(p[0]), int(p[1])
            elif len(s) == 4 and s.isdigit():
                return int(s), 0
            return 0, 0
        parsed = df_ratios["period"].apply(_parse)
        df_ratios["fiscal_year"] = parsed.apply(lambda x: x[0])
        df_ratios["fiscal_quarter"] = parsed.apply(lambda x: x[1])

    df_ratios["ticker"] = df_ratios[ticker_col]
    df_ratios = df_ratios[df_ratios["fiscal_year"] > 2000]
    df_ratios["bank_uuid"] = df_ratios["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_uuid", ""))
    df_ratios["bank_sk"] = df_ratios["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_sk", 0))

    total_ratios = 0
    for (year, quarter), part_df in df_ratios.groupby(["fiscal_year", "fiscal_quarter"]):
        part_dir = SILVER_RATIOS_DIR / f"year={year}" / f"quarter={quarter}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.to_parquet(part_file, compression="snappy", index=False)
        total_ratios += len(part_df)

    print(f"      [✓] Đã xuất bản Silver Ratios: {total_ratios:,} kỳ tỷ số tài chính tại {SILVER_RATIOS_DIR}")
    return total_ratios


if __name__ == "__main__":
    run_clean_financial_statements()
    run_clean_financial_ratios()
