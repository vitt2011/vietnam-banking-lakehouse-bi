"""
===================================================================================
PACKAGE: src/stock_analysis/governance/gateways/__init__.py
CHỨC NĂNG: HỆ THỐNG TRẠM GÁC CHẤT LƯỢNG DỮ LIỆU ĐA TẦNG (DATA QUALITY GATEWAYS)
===================================================================================
Mặt tiền điều phối tập trung (Facade & Strategy Pattern):
  - validate_dq1: Cổng số 1 (Bronze -> Silver), tự động nhận diện nến vs BCTC thô.
  - validate_dq2: Cổng số 2 (Silver -> Gold / DWH), đối soát cân đối kế toán & Grain.
  - validate_dq3: Cổng số 3 (Gold -> Serving), kiểm tra miền giá trị CAMELS & P/B.
===================================================================================
"""

from .dq1 import validate_dq1, validate_market_candlestick, validate_financials_raw
from .dq2 import validate_dq2, validate_accounting_identity, validate_silver_grain, EPSILON_ACCOUNTING_VND
from .dq3 import validate_dq3, validate_gold_metrics

# Legacy Aliases để tương thích hoàn toàn với mã nguồn cũ
validate_dq1_market_candlestick = validate_market_candlestick
validate_dq1_financials_raw = validate_financials_raw
validate_dq2_accounting_identity = validate_accounting_identity
validate_dq2_silver_grain = validate_silver_grain
validate_dq3_gold_metrics = validate_gold_metrics

__all__ = [
    # Master Dispatchers
    "validate_dq1",
    "validate_dq2",
    "validate_dq3",
    # Specific Rule Validators
    "validate_market_candlestick",
    "validate_financials_raw",
    "validate_accounting_identity",
    "validate_silver_grain",
    "validate_gold_metrics",
    # Legacy Compatibility Names
    "validate_dq1_market_candlestick",
    "validate_dq1_financials_raw",
    "validate_dq2_accounting_identity",
    "validate_dq2_silver_grain",
    "validate_dq3_gold_metrics",
    # Constants
    "EPSILON_ACCOUNTING_VND",
]
