"""
SQL Serving Loader package: Synchronizes Silver & Gold Lakehouse layers to PostgreSQL Data Marts.
"""
from stock_analysis.sql_serving_loader.publish_to_postgres import (
    publish_all_to_postgres,
    publish_stock_ohlcv,
    publish_financial_statements,
    publish_banking_ratios_and_camels,
    publish_macro_and_governance,
)
from stock_analysis.sql_serving_loader.load_financial_statements import run_pipeline as load_financial_statements
from stock_analysis.sql_serving_loader.load_banking_ratios import run_pipeline as load_banking_ratios
from stock_analysis.sql_serving_loader.load_macro_indicators import run_pipeline as load_macro_indicators
from stock_analysis.sql_serving_loader.load_governance import run_pipeline as load_governance
from stock_analysis.sql_serving_loader.load_corporate_disclosures import run_pipeline as load_corporate_disclosures

__all__ = [
    "publish_all_to_postgres",
    "publish_stock_ohlcv",
    "publish_financial_statements",
    "publish_banking_ratios_and_camels",
    "publish_macro_and_governance",
    "load_financial_statements",
    "load_banking_ratios",
    "load_macro_indicators",
    "load_governance",
    "load_corporate_disclosures",
]
