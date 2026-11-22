"""
===================================================================================
PACKAGE: src/stock_analysis/governance/gateways/dq2/__init__.py
CHỨC NĂNG: BỘ ĐIỀU PHỐI TRUNG TÂM (CENTRAL DISPATCHER) CHO CỔNG DQ2
===================================================================================
"""

from typing import Tuple, Dict, Any, List, Optional
import pandas as pd

from .reconciliation_validator import validate_accounting_identity, EPSILON_ACCOUNTING_VND
from .grain_validator import validate_silver_grain


def validate_dq2(
    df: pd.DataFrame,
    check_type: str = "auto",
    key_columns: Optional[List[str]] = None,
    source_name: str = "silver_data",
    quarantine: bool = True
) -> Any:
    """
    CỔNG GÁC DQ2 TẬP TRUNG (FACADE / DISPATCHER PATTERN):
    - Nếu check_type == 'accounting' (hoặc df có cột tài sản/nợ/vốn):
      Kiểm định phương trình cân đối kế toán.
    - Nếu check_type == 'grain' (hoặc truyền key_columns):
      Kiểm định grain và khóa đại diện không null, không trùng lặp.
    """
    if check_type == "grain" or (key_columns is not None):
        keys = key_columns or ["bank_sk", "date_sk"]
        return validate_silver_grain(df, key_columns=keys)

    return validate_accounting_identity(df, source_name=source_name, quarantine=quarantine)


__all__ = [
    "validate_dq2",
    "validate_accounting_identity",
    "validate_silver_grain",
    "EPSILON_ACCOUNTING_VND",
]
