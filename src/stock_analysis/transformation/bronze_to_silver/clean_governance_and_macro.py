"""
===================================================================================
PIPELINE: src/transformation/bronze_to_silver/clean_governance_and_macro.py
CHỨC NĂNG: LÀM SẠCH DỮ LIỆU QUẢN TRỊ, SỞ HỮU & KINH TẾ VĨ MÔ SANG TẦNG SILVER
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 2, Mục 100-105)
===================================================================================
"""

import sys
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR

from stock_analysis.common.hashing import generate_stakeholder_uuid

BRONZE_GOV_DIR = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "04_Quan_Tri_So_Huu"
BRONZE_MACRO_DIR = DATA_LAKE_DIR / "01_bronze" / "01_structured" / "03_Kinh_Te_Vi_Mo"
SILVER_BANK_PATH = DATA_LAKE_DIR / "02_silver" / "01_master_data" / "mdm_bank.snappy.parquet"

SILVER_GOV_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "04_Quan_Tri_So_Huu" / "entity_relationships"
SILVER_EVENTS_DIR = DATA_LAKE_DIR / "02_silver" / "corporate_actions" / "events_standardized"
SILVER_MACRO_DIR = DATA_LAKE_DIR / "02_silver" / "02_structured" / "03_Kinh_Te_Vi_Mo" / "daily_macro_series"


def run_clean_governance():
    print(">>> [SILVER GOV] Chuyển đổi Bronze -> Silver: Mạng lưới Quản trị & Cổ đông...")
    df_banks = pd.read_parquet(SILVER_BANK_PATH)
    bank_map = df_banks.set_index("ticker")[["bank_uuid", "bank_sk"]].to_dict(orient="index")

    SILVER_GOV_DIR.mkdir(parents=True, exist_ok=True)
    all_edges = []

    # 1. Officers
    officers_path = BRONZE_GOV_DIR / "bank_officers.parquet"
    if officers_path.exists():
        df_off = pd.read_parquet(officers_path)
        sym_col = "ticker" if "ticker" in df_off.columns else "symbol"
        for _, r in df_off.iterrows():
            tk = r.get(sym_col)
            if tk in bank_map:
                name = str(r.get("officer_name") or r.get("name", "")).strip()
                own_pct = float(r.get("officer_own_percent") or r.get("ownership_pct") or 0.0)
                if 0 < own_pct <= 1.0:
                    own_pct = round(own_pct * 100, 4)
                shares = int(r.get("officer_own_quantity") or r.get("shares") or 0)
                all_edges.append({
                    "ticker": tk,
                    "bank_uuid": bank_map[tk]["bank_uuid"],
                    "bank_sk": bank_map[tk]["bank_sk"],
                    "stakeholder_type": "PERSON",
                    "stakeholder_name": name,
                    "stakeholder_uuid": generate_stakeholder_uuid("PERSON", f"{name}_{tk}"),
                    "relationship_type": "OFFICER",
                    "role_title": str(r.get("officer_position") or r.get("position") or r.get("role", "")).strip(),
                    "ownership_pct": own_pct,
                    "shares_quantity": shares,
                    "is_current": True
                })

    # 2. Shareholders
    shareholders_path = BRONZE_GOV_DIR / "bank_shareholders.parquet"
    if shareholders_path.exists():
        df_sh = pd.read_parquet(shareholders_path)
        sym_col = "ticker" if "ticker" in df_sh.columns else "symbol"
        for _, r in df_sh.iterrows():
            tk = r.get(sym_col)
            if tk in bank_map:
                name = str(r.get("share_holder") or r.get("shareholder_name") or r.get("name", "")).strip()
                own_pct = float(r.get("share_own_percent") or r.get("ownership_pct") or 0.0)
                if 0 < own_pct <= 1.0:
                    own_pct = round(own_pct * 100, 4)
                shares = int(r.get("quantity") or r.get("shares") or 0)
                s_type = "ORGANIZATION" if any(w in name.lower() for w in ["công ty", "tập đoàn", "quỹ", "scic", "viettel", "bộ tài chính", "corp", "fund", "ltd"]) else "PERSON"
                all_edges.append({
                    "ticker": tk,
                    "bank_uuid": bank_map[tk]["bank_uuid"],
                    "bank_sk": bank_map[tk]["bank_sk"],
                    "stakeholder_type": s_type,
                    "stakeholder_name": name,
                    "stakeholder_uuid": generate_stakeholder_uuid(s_type, f"{name}_{tk}"),
                    "relationship_type": "SHAREHOLDER",
                    "role_title": "Cổ đông lớn" if own_pct >= 5.0 else "Cổ đông",
                    "ownership_pct": own_pct,
                    "shares_quantity": shares,
                    "is_current": True
                })

    if all_edges:
        df_all = pd.DataFrame(all_edges)
        out_file = SILVER_GOV_DIR / "snapshot_year=2026.snappy.parquet"
        df_all.to_parquet(out_file, compression="snappy", index=False)
        print(f"      [✓] Đã xuất bản Silver Governance: {len(df_all):,} liên kết tại {out_file}")


def run_clean_macro():
    print(">>> [SILVER MACRO] Chuyển đổi Bronze -> Silver: Dữ liệu Vĩ mô & Tiền tệ...")
    macro_path = BRONZE_MACRO_DIR / "macro_economic_indicators.parquet"
    if not macro_path.exists():
        return

    df_macro = pd.read_parquet(macro_path)
    SILVER_MACRO_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SILVER_MACRO_DIR / "macro_series_2015_2026.snappy.parquet"
    df_macro.to_parquet(out_file, compression="snappy", index=False)
    print(f"      [✓] Đã xuất bản Silver Macro: {len(df_macro):,} bản ghi tại {out_file}")


if __name__ == "__main__":
    run_clean_governance()
    run_clean_macro()
