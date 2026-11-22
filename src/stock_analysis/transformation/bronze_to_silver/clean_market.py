"""
===================================================================================
PIPELINE: src/transformation/bronze_to_silver/clean_market.py
CHỨC NĂNG: LÀM SẠCH VÀ CHUẨN HÓA DỮ LIỆU THỊ TRƯỜNG OHLCV SANG TẦNG SILVER
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 91-94)
Đầu ra: data_lake/02_silver/market_trading/stock_ohlcv/exchange=XXX/year=YYYY/
===================================================================================
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

from stock_analysis.governance.gateways.dq1 import validate_dq1

BRONZE_MARKET_PATH = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "01_Giao_Dich_Gia_OHLCV" / "vnstock_historical.parquet"
BRONZE_INDICES_PATH = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "03_Kinh_Te_Vi_Mo" / "market_indices_historical.parquet"
SILVER_BANK_PATH = DATA_LAKE_DIR / "02_silver" / "01_master_data" / "mdm_bank.snappy.parquet"

SILVER_STOCK_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "01_Giao_Dich_Gia_OHLCV" / "stock_ohlcv"
SILVER_INDEX_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "01_Giao_Dich_Gia_OHLCV" / "index_ohlcv"


def run_clean_stock_ohlcv() -> int:
    print(">>> [SILVER 1/4] Chuyển đổi Bronze -> Silver: Chuỗi giá cổ phiếu OHLCV 27 Ngân hàng...")
    if not BRONZE_MARKET_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy Bronze Market file: {BRONZE_MARKET_PATH}")

    df_raw = pd.read_parquet(BRONZE_MARKET_PATH)
    print(f"      Đã đọc {len(df_raw):,} dòng thô từ Bronze.")

    # 1. Kiểm định chất lượng qua DQ Gateway 1 (Bộ điều phối tập trung)
    valid_df, quarantined_df, metrics = validate_dq1(df_raw, dataset_type="market_ohlcv", source_name="vnstock")
    print(f"      [DQ1] Tỷ lệ đạt chuẩn: {metrics['pass_rate_pct']}% ({metrics['valid_records']:,} dòng hợp lệ).")

    # 2. Đọc Master Data ngân hàng để ánh xạ khóa
    df_banks = pd.read_parquet(SILVER_BANK_PATH)
    bank_map = df_banks.set_index("ticker")[["bank_uuid", "exchange_code", "bank_sk"]].to_dict(orient="index")

    # 3. Chuẩn hóa dữ liệu & Ép kiểu Downcasting
    valid_df["trading_date"] = pd.to_datetime(valid_df["time"]).dt.date
    valid_df["date_sk"] = pd.to_datetime(valid_df["time"]).dt.strftime("%Y%m%d").astype(int)
    valid_df["year"] = pd.to_datetime(valid_df["time"]).dt.year

    valid_df["bank_uuid"] = valid_df["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_uuid", ""))
    valid_df["exchange"] = valid_df["ticker"].apply(lambda t: bank_map.get(t, {}).get("exchange_code", "HOSE"))
    valid_df["bank_sk"] = valid_df["ticker"].apply(lambda t: bank_map.get(t, {}).get("bank_sk", 0))

    # Chuẩn hóa giá sang đơn vị Đồng (VND) nếu giá đang ở đơn vị nghìn đồng
    for col in ["open", "high", "low", "close"]:
        if valid_df[col].median() < 1000:
            valid_df[col] = (valid_df[col] * 1000).round(2)
        valid_df[col] = valid_df[col].astype("float32")

    valid_df["volume"] = valid_df["volume"].fillna(0).astype("int64")
    valid_df["turnover_vnd"] = (valid_df["close"] * valid_df["volume"]).round(2).astype("float64")

    # Sắp xếp và tính tỷ suất sinh lời hàng ngày theo từng mã
    valid_df = valid_df.sort_values(["ticker", "trading_date"]).reset_index(drop=True)
    valid_df["return_daily_pct"] = valid_df.groupby("ticker")["close"].pct_change().round(4).fillna(0.0)

    # 4. Ghi dữ liệu phân vùng Hive: exchange=XXX/year=YYYY/
    total_written = 0
    grouped = valid_df.groupby(["exchange", "year"])
    for (exchange, year), partition_df in grouped:
        part_dir = SILVER_STOCK_DIR / f"exchange={exchange}" / f"year={year}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        partition_df.drop(columns=["exchange", "year"]).to_parquet(part_file, compression="snappy", index=False)
        total_written += len(partition_df)

    print(f"      [✓] Hoàn tất xuất bản Silver Parquet: {total_written:,} phiên giao dịch tại {SILVER_STOCK_DIR}")
    return total_written


def run_clean_market_indices() -> int:
    print(">>> [SILVER 2/4] Chuyển đổi Bronze -> Silver: Chỉ số thị trường (VNINDEX, VN30, VNFINLEAD)...")
    if not BRONZE_INDICES_PATH.exists():
        print(f"      Không tìm thấy {BRONZE_INDICES_PATH}, bỏ qua.")
        return 0

    df_idx = pd.read_parquet(BRONZE_INDICES_PATH)
    if "time" in df_idx.columns:
        df_idx["trading_date"] = pd.to_datetime(df_idx["time"]).dt.date
        df_idx["date_sk"] = pd.to_datetime(df_idx["time"]).dt.strftime("%Y%m%d").astype(int)
        df_idx["year"] = pd.to_datetime(df_idx["time"]).dt.year
    else:
        return 0

    total_idx = 0
    for year, part_df in df_idx.groupby("year"):
        part_dir = SILVER_INDEX_DIR / f"year={year}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.drop(columns=["year"]).to_parquet(part_file, compression="snappy", index=False)
        total_idx += len(part_df)

    print(f"      [✓] Đã xuất bản Silver Index Parquet: {total_idx:,} điểm chỉ số tại {SILVER_INDEX_DIR}")
    return total_idx


if __name__ == "__main__":
    run_clean_stock_ohlcv()
    run_clean_market_indices()
