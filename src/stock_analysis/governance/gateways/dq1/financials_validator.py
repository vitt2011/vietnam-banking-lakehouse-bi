"""
===================================================================================
MODULE: src/stock_analysis/governance/gateways/dq1/financials_validator.py
CHỨC NĂNG: KIỂM ĐỊNH & KHỬ TRÙNG LẶP ĐA BÁO CÁO BCTC THÔ TẠI CỔNG DQ1
===================================================================================
"""

import logging
from typing import Tuple, Dict, Any
import pandas as pd

logger = logging.getLogger("DQ1.Financials")


def validate_financials_raw(
    df: pd.DataFrame,
    source_name: str = "vnstock_bctc",
    quarantine: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Kiểm định DQ Gateway 1 cho Báo cáo tài chính thô:
    - Bắt buộc có ticker/symbol, fiscal_year, fiscal_quarter.
    - Quý tài chính phải thuộc [0, 1, 2, 3, 4].
    - Khử trùng lặp đa báo cáo (BS, IS, CF) bằng groupby.first() để không mất Balance Sheet.
    """
    total_records = len(df)
    if total_records == 0:
        return df, pd.DataFrame(), {
            "rule": "DQ1_FIN_RAW_SCHEMA",
            "total": 0,
            "failed": 0,
            "pass_rate_pct": 100.0,
            "is_passed": True
        }

    df_eval = df.copy()
    ticker_col = "ticker" if "ticker" in df_eval.columns else "symbol"

    if "period" in df_eval.columns and "fiscal_year" not in df_eval.columns:
        def _parse(val):
            s = str(val).strip()
            if "-Q" in s:
                p = s.split("-Q")
                return int(p[0]), int(p[1])
            elif "Q" in s:
                p = s.split("Q")
                return int(p[0]), int(p[1])
            elif len(s) == 4 and s.isdigit():
                return int(s), 0
            return None, None
        parsed = df_eval["period"].apply(_parse)
        df_eval["fiscal_year"] = parsed.apply(lambda x: x[0])
        df_eval["fiscal_quarter"] = parsed.apply(lambda x: x[1])

    year_col = "fiscal_year" if "fiscal_year" in df_eval.columns else "year"
    quarter_col = "fiscal_quarter" if "fiscal_quarter" in df_eval.columns else "quarter"

    cond_valid_id = df_eval[ticker_col].notnull() & df_eval[year_col].notnull() & df_eval[quarter_col].notnull()
    cond_valid_q = df_eval[quarter_col].isin([0, 1, 2, 3, 4])

    is_valid = cond_valid_id & cond_valid_q
    valid_df = df_eval[is_valid].copy()
    quarantined_df = df_eval[~is_valid].copy()

    # Hợp nhất các bản ghi từ 3 BCTC (CĐKT, KQKD, LCTT) thành 1 bản ghi duy nhất cho mỗi (ticker, year, quarter)
    if valid_df.duplicated(subset=[ticker_col, year_col, quarter_col]).any():
        valid_df = valid_df.groupby([ticker_col, year_col, quarter_col], as_index=False, observed=False).first()

    failed_cnt = len(quarantined_df)
    pass_rate = round(((total_records - failed_cnt) / total_records) * 100, 3)

    metrics = {
        "rule_code": "DQ1_FINANCIALS_SCHEMA_COMPLETENESS",
        "domain": "financials",
        "total_records": total_records,
        "valid_records": len(valid_df),
        "failed_records": failed_cnt,
        "pass_rate_pct": pass_rate,
        "is_passed": failed_cnt == 0
    }
    return valid_df, quarantined_df, metrics
