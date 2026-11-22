"""
===================================================================================
MODULE: src/stock_analysis/governance/gateways/dq1/candlestick_validator.py
CHỨC NĂNG: KIỂM ĐỊNH CHẤT LƯỢNG NẾN NHẬT (OHLCV INVARIANTS) TẠI CỔNG DQ1
===================================================================================
"""

import logging
from datetime import datetime
from typing import Tuple, Dict, Any
from pathlib import Path
import pandas as pd

from stock_analysis.common.paths import QUARANTINE_SCHEMA_DIR

logger = logging.getLogger("DQ1.Candlestick")


def validate_market_candlestick(
    df: pd.DataFrame,
    source_name: str = "vnstock",
    quarantine: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Kiểm định DQ Gateway 1 cho chuỗi dữ liệu giá cổ phiếu OHLCV:
    - Bắt buộc: ticker (hoặc symbol), time, close không được null.
    - Candlestick Invariants: 0 < Low <= min(Open, Close) <= max(Open, Close) <= High.
    - Volume non-negative: volume >= 0.
    - Khử trùng lặp (ticker, time).
    Bản ghi lỗi bị đẩy vào: 02_silver/_quarantine/01_Loi_Cau_Truc_Schema
    """
    total_records = len(df)
    if total_records == 0:
        return df, pd.DataFrame(), {
            "rule": "DQ1_OHLCV_CANDLESTICK",
            "total": 0,
            "failed": 0,
            "pass_rate_pct": 100.0,
            "is_passed": True
        }

    df_eval = df.copy()
    ticker_col = "ticker" if "ticker" in df_eval.columns else "symbol"
    if "time" in df_eval.columns:
        df_eval["time"] = pd.to_datetime(df_eval["time"])

    # 1. Null check
    cond_null = df_eval[ticker_col].isnull() | df_eval["time"].isnull() | df_eval["close"].isnull()

    # 2. Candlestick invariants
    cond_price_pos = (df_eval["low"] > 0) & (df_eval["high"] > 0) & (df_eval["open"] > 0) & (df_eval["close"] > 0)
    cond_hl = (df_eval["high"] >= df_eval["low"])
    cond_open_hl = (df_eval["open"] <= df_eval["high"]) & (df_eval["open"] >= df_eval["low"])
    cond_close_hl = (df_eval["close"] <= df_eval["high"]) & (df_eval["close"] >= df_eval["low"])
    cond_candlestick = cond_price_pos & cond_hl & cond_open_hl & cond_close_hl

    # 3. Volume non-negative
    cond_vol = (df_eval["volume"] >= 0) if "volume" in df_eval.columns else True

    is_valid = (~cond_null) & cond_candlestick & cond_vol

    valid_df = df_eval[is_valid].copy()
    quarantined_df = df_eval[~is_valid].copy()

    # Deduplicate trên valid set
    if valid_df.duplicated(subset=[ticker_col, "time"]).any():
        dup_mask = valid_df.duplicated(subset=[ticker_col, "time"], keep="last")
        dup_records = valid_df[dup_mask].copy()
        dup_records["quarantine_reason"] = "DUPLICATE_TICKER_TIME"
        valid_df = valid_df.drop_duplicates(subset=[ticker_col, "time"], keep="last")
        quarantined_df = pd.concat([quarantined_df, dup_records], ignore_index=True)

    failed_cnt = len(quarantined_df)
    pass_rate = round(((total_records - failed_cnt) / total_records) * 100, 3)

    if failed_cnt > 0 and quarantine:
        if "quarantine_reason" not in quarantined_df.columns:
            quarantined_df["quarantine_reason"] = "CANDLESTICK_INVARIANT_VIOLATION"
        quarantined_df["quarantine_timestamp"] = datetime.now().isoformat()
        quarantined_df["source"] = source_name

        QUARANTINE_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
        q_path = QUARANTINE_SCHEMA_DIR / "market_ohlcv_quarantine.parquet"
        quarantined_df.to_parquet(q_path, index=False)
        logger.warning("[DQ1] Phát hiện %d bản ghi vi phạm nến. Đã lưu/cập nhật cách ly tại: %s", failed_cnt, q_path)

    metrics = {
        "rule_code": "DQ1_OHLCV_CANDLESTICK",
        "domain": "market_trading",
        "total_records": total_records,
        "valid_records": len(valid_df),
        "failed_records": failed_cnt,
        "pass_rate_pct": pass_rate,
        "is_passed": failed_cnt == 0
    }
    return valid_df, quarantined_df, metrics
