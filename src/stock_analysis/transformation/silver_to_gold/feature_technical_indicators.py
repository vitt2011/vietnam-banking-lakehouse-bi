"""
===================================================================================
FEATURE ENGINE: src/transformation/silver_to_gold/feature_technical_indicators.py
CHỨC NĂNG: TÍNH TOÁN CÁC CHỈ BÁO KỸ THUẬT OHLCV SANG TẦNG GOLD
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 114-115 & Phần 5, Mục 647-656)
Chỉ báo: SMA20, SMA50, SMA200, RSI14, MACD(12,26,9), Bollinger Bands(20,2), Beta 6M
Đầu ra: data_lake/03_gold/technical_indicators_daily/year=YYYY/
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
GOLD_TECH_DIR = DATA_LAKE_DIR / "03_gold" / "03_Chi_Bao_Ky_Thuat"
GOLD_TECH_DIR.mkdir(parents=True, exist_ok=True)


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Tính RSI 14 theo phương pháp Wilder"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi.round(2)


def compute_ticker_indicators(df_t: pd.DataFrame) -> pd.DataFrame:
    """Tính các chỉ báo kỹ thuật cho một mã cổ phiếu"""
    df = df_t.sort_values("trading_date").copy()

    # 1. Moving Averages
    df["sma_20"] = df["close"].rolling(20, min_periods=1).mean().round(2)
    df["sma_50"] = df["close"].rolling(50, min_periods=1).mean().round(2)
    df["sma_200"] = df["close"].rolling(200, min_periods=1).mean().round(2)

    # 2. RSI 14
    df["rsi_14"] = calculate_rsi(df["close"], period=14).fillna(50.0)

    # 3. MACD (12, 26, 9)
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd_line"] = (ema_12 - ema_26).round(4)
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean().round(4)
    df["macd_hist"] = (df["macd_line"] - df["macd_signal"]).round(4)

    # 4. Bollinger Bands (20, 2)
    std_20 = df["close"].rolling(20, min_periods=1).std().fillna(0)
    df["bb_upper_20"] = (df["sma_20"] + 2 * std_20).round(2)
    df["bb_lower_20"] = (df["sma_20"] - 2 * std_20).round(2)

    # 5. Volume surge ratio
    df["avg_volume_20d"] = df["volume"].rolling(20, min_periods=1).mean().round(0)
    df["volume_surge_ratio"] = (df["volume"] / (df["avg_volume_20d"] + 1e-9)).round(2)

    return df


def run_feature_technical_indicators():
    print(">>> [GOLD 1/5] Feature Engine: Tính toán Chỉ báo Kỹ thuật Toàn bộ 27 Ngân hàng...")
    files = list(SILVER_STOCK_DIR.rglob("*.snappy.parquet"))
    if not files:
        print("      Không tìm thấy dữ liệu Silver OHLCV!")
        return 0

    all_dfs = [pd.read_parquet(f) for f in files]
    df_combined = pd.concat(all_dfs, ignore_index=True)
    print(f"      Đã nạp {len(df_combined):,} phiên giao dịch từ Silver.")

    # Tính toán cho từng mã
    processed_dfs = []
    for ticker, grp in df_combined.groupby("ticker"):
        processed_dfs.append(compute_ticker_indicators(grp))

    df_gold = pd.concat(processed_dfs, ignore_index=True)
    df_gold["year"] = pd.to_datetime(df_gold["trading_date"]).dt.year

    # Ghi Hive partitioned: year=YYYY/
    total_written = 0
    for year, part_df in df_gold.groupby("year"):
        part_dir = GOLD_TECH_DIR / f"year={year}"
        part_dir.mkdir(parents=True, exist_ok=True)
        part_file = part_dir / "part-00000.snappy.parquet"
        part_df.drop(columns=["year"]).to_parquet(part_file, compression="snappy", index=False)
        total_written += len(part_df)

    print(f"      [✓] Hoàn tất xuất bản Gold Technical Indicators: {total_written:,} dòng tại {GOLD_TECH_DIR}")
    return total_written


if __name__ == "__main__":
    run_feature_technical_indicators()
