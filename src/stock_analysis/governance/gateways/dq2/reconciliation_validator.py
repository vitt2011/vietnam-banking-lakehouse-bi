"""
===================================================================================
MODULE: src/stock_analysis/governance/gateways/dq2/reconciliation_validator.py
CHỨC NĂNG: ĐỐI SOÁT PHƯƠNG TRÌNH CÂN ĐỐI KẾ TOÁN (ASSETS = LIAB + EQUITY) TẠI CỔNG DQ2
===================================================================================
"""

import logging
from datetime import datetime
from typing import Tuple, Dict, Any
from pathlib import Path
import pandas as pd

from stock_analysis.common.paths import QUARANTINE_RECON_DIR

logger = logging.getLogger("DQ2.Reconciliation")

EPSILON_ACCOUNTING_VND = 1_000_000_000.0


def validate_accounting_identity(
    df: pd.DataFrame,
    source_name: str = "silver_financials",
    quarantine: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    DQ Gateway 2: Đối soát phương trình cân đối kế toán sống còn:
    | Tổng Tài Sản - (Tổng Nợ Phải Trả + Tổng Vốn Chủ Sở Hữu) | <= 1.0 tỷ VND (hoặc 1% Tổng tài sản)
    Kỳ báo cáo nào vi phạm sẽ bị cách ly tại: 02_silver/_quarantine/02_Loi_Doi_Soat_Ke_Toan
    """
    total_records = len(df)
    if total_records == 0:
        return df, pd.DataFrame(), {
            "rule": "DQ2_ACCOUNTING_IDENTITY",
            "total": 0,
            "failed": 0,
            "pass_rate_pct": 100.0,
            "is_passed": True
        }

    df_eval = df.copy()

    col_assets = "total_assets" if "total_assets" in df_eval.columns else ("asset" if "asset" in df_eval.columns else None)
    col_liab = "total_liabilities" if "total_liabilities" in df_eval.columns else ("debt" if "debt" in df_eval.columns else None)
    col_equity = "owners_equity" if "owners_equity" in df_eval.columns else ("equity" if "equity" in df_eval.columns else ("total_equity" if "total_equity" in df_eval.columns else None))

    if not (col_assets and col_liab and col_equity):
        return df_eval, pd.DataFrame(), {
            "rule_code": "DQ2_ACCOUNTING_IDENTITY",
            "total": total_records,
            "failed": 0,
            "pass_rate_pct": 100.0,
            "is_passed": True
        }

    assets = pd.to_numeric(df_eval[col_assets], errors="coerce").fillna(0)
    liab = pd.to_numeric(df_eval[col_liab], errors="coerce").fillna(0)
    equity = pd.to_numeric(df_eval[col_equity], errors="coerce").fillna(0)

    # Ngưỡng dung sai: 1% tổng tài sản hoặc 1.0 tỷ VND (tự động nhận diện đơn vị Đồng hay Tỷ đồng)
    median_val = assets[assets > 0].median() if len(assets[assets > 0]) > 0 else 1.0
    epsilon = 1.0 if median_val < 10_000_000 else EPSILON_ACCOUNTING_VND

    diff = (assets - (liab + equity)).abs()
    threshold = (0.01 * assets).clip(lower=epsilon)
    is_valid = (diff <= threshold) | (assets == 0)

    valid_df = df_eval[is_valid].copy()
    quarantined_df = df_eval[~is_valid].copy()

    failed_cnt = len(quarantined_df)
    pass_rate = round(((total_records - failed_cnt) / total_records) * 100, 3)

    if failed_cnt > 0 and quarantine:
        quarantined_df["quarantine_reason"] = "ACCOUNTING_EQUATION_MISMATCH"
        quarantined_df["quarantine_timestamp"] = datetime.now().isoformat()
        quarantined_df["source"] = source_name
        QUARANTINE_RECON_DIR.mkdir(parents=True, exist_ok=True)
        q_path = QUARANTINE_RECON_DIR / "accounting_mismatch_quarantine.parquet"
        quarantined_df.to_parquet(q_path, index=False)
        logger.warning("[DQ2] Phát hiện %d kỳ BCTC lệch cân đối kế toán > 1%%. Đã lưu/cập nhật cách ly tại: %s", failed_cnt, q_path)

    metrics = {
        "rule_code": "DQ2_ACCOUNTING_IDENTITY",
        "domain": "financial_accounting",
        "total_records": total_records,
        "valid_records": len(valid_df),
        "failed_records": failed_cnt,
        "pass_rate_pct": pass_rate,
        "is_passed": failed_cnt == 0
    }
    return valid_df, quarantined_df, metrics
