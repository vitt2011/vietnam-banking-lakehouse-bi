"""
===================================================================================
PACKAGE: src/stock_analysis/governance/gateways/dq3/__init__.py
CHỨC NĂNG: BỘ ĐIỀU PHỐI TRUNG TÂM (CENTRAL DISPATCHER) CHO CỔNG DQ3
===================================================================================
"""

from typing import Tuple, Dict, Any
import pandas as pd

from .ratios_validator import validate_gold_metrics


def validate_dq3(df: pd.DataFrame, domain: str = "camels") -> Tuple[bool, Dict[str, Any]]:
    """
    CỔNG GÁC DQ3 TẬP TRUNG (FACADE / DISPATCHER PATTERN):
    - Kiểm định miền giá trị nghiệp vụ tài chính tầng Gold (CAMELS, Gordon P/B, NPL).
    """
    return validate_gold_metrics(df, domain=domain)


__all__ = [
    "validate_dq3",
    "validate_gold_metrics",
]
