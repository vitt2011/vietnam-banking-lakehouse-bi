"""
===================================================================================
MODULE: src/stock_analysis/governance/gateways/dq3/ratios_validator.py
CHỨC NĂNG: KIỂM ĐỊNH MIỀN GIÁ TRỊ TỶ SỐ TÀI CHÍNH & CAMELS TẠI CỔNG DQ3
===================================================================================
"""

from typing import Tuple, Dict, Any
import pandas as pd


def validate_gold_metrics(df: pd.DataFrame, domain: str = "camels") -> Tuple[bool, Dict[str, Any]]:
    """
    DQ Gateway 3: Kiểm tra tính hợp lệ của các chỉ số phân tích nghiệp vụ tại tầng Gold:
    - Điểm CAMELS composite_score trong đoạn [0, 100].
    - Hệ số P/B trong khoảng hợp lý [0.2, 10.0].
    - Tỷ lệ NPL không âm và <= 100%.
    """
    total = len(df)
    if total == 0:
        return True, {"total": 0, "anomalies": [], "is_passed": True}

    anomalies = []

    # 1. CAMELS Composite Score
    for col in ["camels_composite_score", "composite_score"]:
        if col in df.columns:
            invalid_scores = int(((df[col] < 0) | (df[col] > 100)).sum())
            if invalid_scores > 0:
                anomalies.append(f"{invalid_scores} records with {col} outside [0, 100]")

    # 2. P/B Ratio sanity check
    if "pb_ratio" in df.columns:
        invalid_pb = int(((df["pb_ratio"] < 0.2) | (df["pb_ratio"] > 10.0)).sum())
        if invalid_pb > 0:
            anomalies.append(f"{invalid_pb} records with pb_ratio outside [0.2, 10.0]")

    # 3. NPL Ratio sanity check
    for col in ["npl_ratio_pct", "npl"]:
        if col in df.columns:
            invalid_npl = int(((df[col] < 0) | (df[col] > 100)).sum())
            if invalid_npl > 0:
                anomalies.append(f"{invalid_npl} records with {col} outside [0%, 100%]")

    passed = (len(anomalies) == 0)
    metrics = {
        "rule_code": f"DQ3_GOLD_{domain.upper()}_BOUNDS",
        "total_records": total,
        "anomalies": anomalies,
        "is_passed": passed
    }
    return passed, metrics
