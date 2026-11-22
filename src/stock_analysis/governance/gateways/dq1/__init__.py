"""
===================================================================================
PACKAGE: src/stock_analysis/governance/gateways/dq1/__init__.py
CHỨC NĂNG: BỘ ĐIỀU PHỐI TRUNG TÂM (CENTRAL DISPATCHER) CHO CỔNG DQ1
===================================================================================
Người gọi chỉ cần gọi duy nhất hàm:
    validate_dq1(df, dataset_type="auto")
Hàm này sẽ tự động nhận diện loại dữ liệu và chuyển đến đúng validator chuyên trách.
"""

from typing import Tuple, Dict, Any, Optional
import pandas as pd

from .candlestick_validator import validate_market_candlestick
from .financials_validator import validate_financials_raw


def validate_dq1(
    df: pd.DataFrame,
    dataset_type: str = "auto",
    source_name: str = "bronze_raw",
    quarantine: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    CỔNG GÁC DQ1 TẬP TRUNG (FACADE / DISPATCHER PATTERN):
    - dataset_type: 'market_ohlcv', 'financial_statements' (hoặc 'auto' để tự nhận diện qua columns).
    - Tự động điều hướng đến validator chuyên trách của từng nguồn.
    """
    if df is None or len(df) == 0:
        return df, pd.DataFrame(), {
            "rule": "DQ1_EMPTY_DATASET",
            "total": 0,
            "failed": 0,
            "pass_rate_pct": 100.0,
            "is_passed": True
        }

    cols = set(df.columns)

    # 1. Nhánh Giá giao dịch OHLCV
    if dataset_type in ["market_ohlcv", "ohlcv", "stock_price"] or {"open", "high", "low", "close"}.issubset(cols):
        return validate_market_candlestick(df, source_name=source_name, quarantine=quarantine)

    # 2. Nhánh Báo cáo tài chính thô
    if dataset_type in ["financial_statements", "financials", "bctc"] or (
        ("period" in cols or "fiscal_year" in cols or "year" in cols) and ("ticker" in cols or "symbol" in cols)
    ):
        return validate_financials_raw(df, source_name=source_name, quarantine=quarantine)

    # 3. Mặc định: Nếu là dữ liệu bảng khác chưa có rule riêng, trả về nguyên bản
    return df, pd.DataFrame(), {
        "rule_code": "DQ1_PASSTHROUGH",
        "domain": dataset_type,
        "total_records": len(df),
        "valid_records": len(df),
        "failed_records": 0,
        "pass_rate_pct": 100.0,
        "is_passed": True
    }


# Export các hàm con để ai thích gọi trực tiếp vẫn gọi được
__all__ = [
    "validate_dq1",
    "validate_market_candlestick",
    "validate_financials_raw",
]
