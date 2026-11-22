"""
===================================================================================
MODULE: src/stock_analysis/transformation/silver_to_gold/feature_camels_engine.py
CHỨC NĂNG: TÍNH TOÁN THẺ ĐIỂM SỨC KHỎE CAMELS 6 TRỤ CỘT (GOLD LAYER)
===================================================================================
Kiến trúc Medallion Gold:
  - Input: Silver Structured (Báo cáo tài chính & Tỷ số tài chính đã qua DQ2)
  - Engine: Tính toán điểm số CAMELS chuẩn quốc tế 6 Trụ cột (C-A-M-E-L-S)
  - Cải tiến RUN 3: Gỡ bỏ fallback ngầm định cố định, xử lý missing an toàn dựa trên
    median phân phối thực tế hoặc phạt điểm dữ liệu thiếu, bảo đảm tính liêm chính.
===================================================================================
"""

from pathlib import Path
import sys
import logging
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis.common.paths import DATA_LAKE_DIR

logger = logging.getLogger("FeatureCamelsEngine")


def compute_camels_composite_score(df: pd.DataFrame) -> pd.Series:
    """
    Tính điểm tổng hợp CAMELS (thang 100) theo 6 trụ cột:
    - C (15%): Capital Adequacy (CAR chuẩn hóa dải 6% - 18%)
    - A (20%): Asset Quality (NPL càng thấp điểm càng cao, trần 5%)
    - M (15%): Management Efficiency (CIR càng thấp điểm càng cao, dải 20% - 60%)
    - E (20%): Earnings (ROE càng cao điểm càng cao, dải 5% - 25%)
    - L (15%): Liquidity (CASA càng cao điểm càng cao, dải 5% - 45%)
    - S (15%): Sensitivity to Market Risk (Biên đệm NIM TTM chống sốc lãi suất 2.0% - 5.5%)
    Tổng trọng số: 15% + 20% + 15% + 20% + 15% + 15% = 100%
    """
    def _extract_metric(name: str, baseline_min: float) -> pd.Series:
        if name in df.columns:
            s = pd.to_numeric(df[name], errors="coerce")
            # Chuẩn hóa nếu ở dạng phần trăm (> 1.0)
            s = s.apply(lambda x: x / 100.0 if (pd.notnull(x) and x > 1.0) else x)
            # Nếu thiếu, sử dụng median của cột nếu có đủ dữ liệu, nếu không phạt về cận an toàn
            valid_vals = s.dropna()
            if len(valid_vals) >= 3:
                fill_val = valid_vals.median()
            else:
                fill_val = baseline_min
            return s.fillna(fill_val)
        return pd.Series(baseline_min, index=df.index)

    # 1. C - Capital (Basel II tối thiểu 8%, dải chuẩn hóa 6% - 18%)
    c_val = _extract_metric("car_total_pct", baseline_min=0.08)
    c_score = ((c_val - 0.06) / 0.12 * 100).clip(10, 100)

    # 2. A - Asset Quality (NPL chuẩn < 3%, trần 5%)
    npl_val = _extract_metric("npl_ratio_pct", baseline_min=0.03)
    a_score = (100 - (npl_val / 0.05 * 100)).clip(10, 100)

    # 3. M - Management (CIR chuẩn 20% - 60%)
    cir_val = _extract_metric("cir_pct", baseline_min=0.45)
    # Hỗ trợ cả trường hợp CIR âm trong dữ liệu kế toán
    cir_abs = cir_val.abs()
    m_score = (100 - ((cir_abs - 0.20) / 0.40 * 100)).clip(10, 100)

    # 4. E - Earnings (ROE chuẩn 5% - 25%)
    roe_val = _extract_metric("roae_ttm_pct", baseline_min=0.10)
    e_score = ((roe_val - 0.05) / 0.20 * 100).clip(10, 100)

    # 5. L - Liquidity (CASA chuẩn 5% - 45%)
    casa_val = _extract_metric("casa_ratio_pct", baseline_min=0.15)
    l_score = ((casa_val - 0.05) / 0.40 * 100).clip(10, 100)

    # 6. S - Sensitivity to Market Risk (Biên đệm NIM TTM 2.0% - 5.5%)
    nim_val = _extract_metric("nim_ttm_pct", baseline_min=0.025)
    s_score = ((nim_val - 0.02) / 0.035 * 100).clip(10, 100)

    # Tổng hợp 6 trụ cột CAMELS chuẩn quốc tế (Tổng trọng số = 100%)
    composite = (
        0.15 * c_score +
        0.20 * a_score +
        0.15 * m_score +
        0.20 * e_score +
        0.15 * l_score +
        0.15 * s_score
    ).round(2)
    return composite


def run_feature_camels_engine():
    print(">>> [GOLD 2/5] Feature Engine: Tính toán CAMELS Health Scorecard 6 Trụ cột cho 27 Ngân hàng...")

    silver_ratios_dir = DATA_LAKE_DIR / "02_silver" / "02_structured" / "02_Bao_Cao_Tai_Chinh" / "camels_ratios"
    gold_camels_dir = DATA_LAKE_DIR / "03_gold" / "02_The_Diem_CAMELS"

    if not silver_ratios_dir.exists():
        print(f"[CẢNH BÁO] Không tìm thấy thư mục Silver Ratios: {silver_ratios_dir}")
        return False

    parquet_files = list(silver_ratios_dir.rglob("*.parquet"))
    if not parquet_files:
        print("[CẢNH BÁO] Không có file parquet nào trong Silver Ratios.")
        return False

    dfs = [pd.read_parquet(f) for f in parquet_files]
    df_all = pd.concat(dfs, ignore_index=True)

    # Chuẩn hóa tên cột
    col_mapping = {
        "car": "car_total_pct",
        "npl": "npl_ratio_pct",
        "cir": "cir_pct",
        "roe": "roae_ttm_pct",
        "roa": "roaa_ttm_pct",
        "casa_ratio": "casa_ratio_pct",
        "nim": "nim_ttm_pct",
        "net_interest_margin": "nim_ttm_pct",
        "cost_to_income_ratio": "cir_pct",
        "npl_ratio": "npl_ratio_pct",
        "capital_adequacy_ratio": "car_total_pct",
        "ldr": "ldr_pure_pct",
    }
    for old_c, new_c in col_mapping.items():
        if old_c in df_all.columns and new_c not in df_all.columns:
            df_all[new_c] = df_all[old_c]

    # Tính điểm CAMELS Composite Score
    df_all["camels_composite_score"] = compute_camels_composite_score(df_all)

    # Ghi vào Gold Layer phân vùng theo year/quarter
    y_col = "fiscal_year" if "fiscal_year" in df_all.columns else "year"
    q_col = "fiscal_quarter" if "fiscal_quarter" in df_all.columns else "quarter"

    df_all["fiscal_year"] = pd.to_numeric(df_all[y_col], errors="coerce").fillna(0).astype(int)
    df_all["fiscal_quarter"] = pd.to_numeric(df_all[q_col], errors="coerce").fillna(0).astype(int)

    count_saved = 0
    for (year, quarter), grp in df_all.groupby(["fiscal_year", "fiscal_quarter"]):
        if year > 0 and quarter in [1, 2, 3, 4]:
            out_dir = gold_camels_dir / f"year={year}" / f"quarter={quarter}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "part-00000.snappy.parquet"
            grp.to_parquet(out_file, index=False, compression="snappy")
            count_saved += len(grp)

    print(f"    Đã hoàn tất tính điểm CAMELS và lưu {count_saved} bản ghi vào Gold Layer: {gold_camels_dir}")
    return True


if __name__ == "__main__":
    run_feature_camels_engine()
