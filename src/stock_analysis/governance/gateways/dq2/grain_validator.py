"""
===================================================================================
MODULE: src/stock_analysis/governance/gateways/dq2/grain_validator.py
CHỨC NĂNG: KIỂM ĐỊNH TOÀN VẸN GRAIN & KHÓA ĐẠI DIỆN (SURROGATE KEYS) TẠI CỔNG DQ2
===================================================================================
"""

from typing import Tuple, Dict, Any, List
import pandas as pd


def validate_silver_grain(df: pd.DataFrame, key_columns: List[str]) -> Tuple[bool, Dict[str, Any]]:
    """
    DQ Gateway 2: Kiểm tra toàn vẹn Grain & Khóa đại diện tại tầng Silver.
    - Các khóa chính không được NULL.
    - Không trùng lặp trên bộ khóa chính.
    """
    total = len(df)
    if total == 0:
        return True, {"total": 0, "null_keys": 0, "duplicates": 0, "is_passed": True}

    null_count = int(df[key_columns].isnull().any(axis=1).sum())
    dup_count = int(df.duplicated(subset=key_columns).sum())

    passed = (null_count == 0) and (dup_count == 0)
    metrics = {
        "rule_code": "DQ2_GRAIN_KEY_INTEGRITY",
        "key_columns": key_columns,
        "total_records": total,
        "null_key_records": null_count,
        "duplicate_records": dup_count,
        "is_passed": passed
    }
    return passed, metrics
