"""
Governance package: Quality gateways, Lineage tracking, Catalog registration.
"""
from stock_analysis.governance.gateways import (
    validate_dq1,
    validate_dq2,
    validate_dq3,
    validate_dq1_market_candlestick,
    validate_dq1_financials_raw,
    validate_dq2_accounting_identity,
    validate_dq3_gold_metrics,
)
from stock_analysis.governance.lineage_tracker import PipelineRunContext, update_dataset_state

__all__ = [
    # Central Dispatchers
    "validate_dq1",
    "validate_dq2",
    "validate_dq3",
    # Specific Functions
    "validate_dq1_market_candlestick",
    "validate_dq1_financials_raw",
    "validate_dq2_accounting_identity",
    "validate_dq3_gold_metrics",
    "PipelineRunContext",
    "update_dataset_state",
]
