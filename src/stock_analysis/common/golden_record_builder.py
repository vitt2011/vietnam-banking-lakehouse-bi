"""
===================================================================================
MODULE: src/mdm/golden_record_builder.py
CHỨC NĂNG: BỘ XÂY DỰNG BẢN GHI VÀNG (GOLDEN RECORDS BUILDER) CHO 5 THỰC THỂ MDM
Tuân thủ đặc tả: KIEN_TRUC_DATALAKE_DWH_MDM.md (Phần 3, Mục 225-270)
Đầu ra: data_lake/02_silver/dim_conformed/*.snappy.parquet & dw_core Dimensions
===================================================================================
"""

import sys
from pathlib import Path
from datetime import datetime, date

# Cấu hình UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from stock_analysis.common.paths import DATA_LAKE_DIR, LOGS_DIR, CODE_ROOT

from stock_analysis.common.hashing import generate_bank_uuid
from stock_analysis.common.trading_calendar import generate_dim_date_records
from stock_analysis.common.db import get_db_connection, execute_values_bulk

SILVER_CONFORMED_DIR = DATA_LAKE_DIR / "02_silver" / "01_master_data"
SILVER_CONFORMED_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DIR = CODE_ROOT / "config"
BANKS_SEED_PATH = CONFIG_DIR / "business_reference" / "bank_registry.yaml"
COA_MAPPING_PATH = CONFIG_DIR / "business_reference" / "coa_mapping.yaml"


def build_mdm_bank() -> pd.DataFrame:
    """
    1. Xây dựng Golden Record cho 27 Ngân hàng Thương mại:
       - Nạp từ config/business_reference/bank_registry.yaml
       - Sinh Deterministic UUIDv5 từ Mã số thuế
       - Phân nhóm 4 Tiers chuẩn: STATE_BIG4, TIER1_PRIVATE, TIER2_MIDCAP, TIER3_SMALL_RESTRUCT
       - Lưu vào data_lake/02_silver/dim_conformed/mdm_bank.snappy.parquet
    """
    print(">>> [MDM 1/4] Xây dựng Golden Records: mdm_bank (27 Ngân hàng)...")
    if not BANKS_SEED_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {BANKS_SEED_PATH}")

    with open(BANKS_SEED_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    banks_list = data.get("banks", [])
    df = pd.DataFrame(banks_list)

    # Sinh bank_uuid bất biến bằng UUIDv5
    df["bank_uuid"] = df["tax_code"].apply(generate_bank_uuid)
    df["bank_sk"] = range(1, len(df) + 1)
    df["is_active"] = True
    df["effective_from"] = "2015-01-01"
    df["effective_to"] = "9999-12-31"
    df["is_current"] = True

    # Xuất ra Silver Parquet Snappy
    out_parquet = SILVER_CONFORMED_DIR / "mdm_bank.snappy.parquet"
    df.to_parquet(out_parquet, compression="snappy", index=False)
    print(f"      [✓] Đã ghi Golden Record: {out_parquet} ({len(df)} ngân hàng)")

    # Đồng bộ cập nhật vào master_data.dim_bank
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _, r in df.iterrows():
                cur.execute("""
                    UPDATE master_data.dim_bank
                    SET bank_uuid = %s,
                        tier_group = %s,
                        charter_capital_vnd = %s
                    WHERE ticker = %s;
                """, (r["bank_uuid"], r["bank_tier_group"], r["charter_capital_vnd"], r["ticker"]))
            conn.commit()
            print("      [✓] Đã cập nhật UUIDv5 và Tier Group chuẩn vào master_data.dim_bank.")
    finally:
        conn.close()

    return df


def build_mdm_trading_calendar() -> pd.DataFrame:
    """
    2. Xây dựng Golden Record: mdm_trading_calendar (2015 - 2030):
       - Sinh cờ giao dịch, prev/next trading date, anti look-ahead bias
       - Lưu vào data_lake/02_silver/dim_conformed/mdm_trading_calendar.snappy.parquet
    """
    print(">>> [MDM 2/4] Xây dựng Golden Records: mdm_trading_calendar (2015 - 2030)...")
    df = generate_dim_date_records(start_year=2015, end_year=2030)
    out_parquet = SILVER_CONFORMED_DIR / "mdm_trading_calendar.snappy.parquet"
    df.to_parquet(out_parquet, compression="snappy", index=False)
    print(f"      [✓] Đã ghi Golden Record: {out_parquet} ({len(df):,} ngày)")

    # Nạp/Cập nhật vào master_data.dim_date nếu chưa đủ
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM master_data.dim_date;")
            cnt = cur.fetchone()[0]
            if cnt < len(df):
                records = [
                    (
                        int(r.date_sk), r.full_date, int(r.day_of_week), str(r.day_name_vi),
                        int(r.day_of_month), int(r.week_of_year), int(r.month_num), str(r.month_name_vi),
                        int(r.quarter_num), int(r.year_num), str(r.year_quarter), bool(r.is_weekend),
                        bool(r.is_vn_holiday), bool(r.is_trading_day), int(r.prev_trading_date_sk),
                        int(r.next_trading_date_sk), bool(r.is_quarter_end)
                    )
                    for r in df.itertuples(index=False)
                ]
                sql = """
                    INSERT INTO master_data.dim_date (
                        date_sk, full_date, day_of_week, day_name_vi, day_of_month,
                        week_of_year, month_num, month_name_vi, quarter_num, year_num,
                        year_quarter, is_weekend, is_vn_holiday, is_trading_day,
                        prev_trading_date_sk, next_trading_date_sk, is_quarter_end
                    ) VALUES %s
                    ON CONFLICT (date_sk) DO UPDATE SET
                        is_trading_day = EXCLUDED.is_trading_day,
                        prev_trading_date_sk = EXCLUDED.prev_trading_date_sk,
                        next_trading_date_sk = EXCLUDED.next_trading_date_sk;
                """
                execute_values_bulk(sql, records, page_size=2000)
                print(f"      [✓] Đã đồng bộ {len(records):,} ngày vào master_data.dim_date.")
    finally:
        conn.close()

    return df


def build_mdm_metric_dictionary() -> pd.DataFrame:
    """
    3. Xây dựng Golden Record: mdm_metric_dictionary (Từ điển Chỉ tiêu BCTC & CAMELS):
       - Đọc từ config/business_reference/coa_mapping.yaml
       - Lưu vào data_lake/02_silver/dim_conformed/mdm_metric_dictionary.snappy.parquet
    """
    print(">>> [MDM 3/4] Xây dựng Golden Records: mdm_metric_dictionary...")
    if not COA_MAPPING_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy: {COA_MAPPING_PATH}")

    with open(COA_MAPPING_PATH, "r", encoding="utf-8") as f:
        coa = yaml.safe_load(f)

    rows = []
    # Balance sheet
    for field, info in coa.get("balance_sheet", {}).items():
        rows.append({
            "metric_code": info.get("standard_code"),
            "field_name": field,
            "statement_type": "BALANCE_SHEET",
            "name_vi": info.get("vietnamese_name"),
            "name_en": info.get("english_name"),
            "role": info.get("accounting_equation_role", "OTHER")
        })

    # Income statement
    for field, info in coa.get("income_statement", {}).items():
        rows.append({
            "metric_code": info.get("standard_code"),
            "field_name": field,
            "statement_type": "INCOME_STATEMENT",
            "name_vi": info.get("vietnamese_name"),
            "name_en": info.get("english_name"),
            "role": "REVENUE_EXPENSE"
        })

    # Loan note
    for field, info in coa.get("loan_classification_notes", {}).items():
        rows.append({
            "metric_code": info.get("standard_code"),
            "field_name": field,
            "statement_type": "LOAN_NOTES",
            "name_vi": info.get("vietnamese_name"),
            "name_en": info.get("english_name"),
            "role": "CREDIT_RISK_GROUP"
        })

    # CAMELS KPIs
    camels_defs = [
        ("KPI_CAR", "car_total_pct", "CAMELS_RATIO", "Hệ số An toàn vốn (CAR)", "Capital Adequacy Ratio", "CAPITAL"),
        ("KPI_NPL", "npl_ratio_pct", "CAMELS_RATIO", "Tỷ lệ Nợ xấu (NPL)", "Non-Performing Loans Ratio", "ASSET_QUALITY"),
        ("KPI_LLR", "llr_coverage_pct", "CAMELS_RATIO", "Tỷ lệ Bao phủ Nợ xấu (LLR)", "Loan Loss Reserve Coverage", "ASSET_QUALITY"),
        ("KPI_CIR", "cir_pct", "CAMELS_RATIO", "Tỷ lệ Chi phí trên Thu nhập (CIR)", "Cost to Income Ratio", "MANAGEMENT"),
        ("KPI_NIM", "nim_ttm_pct", "CAMELS_RATIO", "Biên lãi ròng trượt 4 quý (NIM TTM)", "Net Interest Margin TTM", "EARNINGS"),
        ("KPI_ROAE", "roae_ttm_pct", "CAMELS_RATIO", "Tỷ suất Sinh lời trên Vốn CSH (ROAE)", "Return on Average Equity", "EARNINGS"),
        ("KPI_CASA", "casa_ratio_pct", "CAMELS_RATIO", "Tỷ lệ Tiền gửi không kỳ hạn (CASA)", "Current Account Savings Account", "LIQUIDITY"),
        ("KPI_LDR", "ldr_pure_pct", "CAMELS_RATIO", "Tỷ lệ Dư nợ trên Huy động thuần (LDR)", "Loan to Deposit Ratio", "LIQUIDITY"),
    ]
    for c in camels_defs:
        rows.append({
            "metric_code": c[0],
            "field_name": c[1],
            "statement_type": c[2],
            "name_vi": c[3],
            "name_en": c[4],
            "role": c[5]
        })

    df = pd.DataFrame(rows)
    out_parquet = SILVER_CONFORMED_DIR / "mdm_metric_dictionary.snappy.parquet"
    df.to_parquet(out_parquet, compression="snappy", index=False)
    print(f"      [✓] Đã ghi Golden Record: {out_parquet} ({len(df)} chỉ tiêu nghiệp vụ)")
    return df


def build_mdm_market_index() -> pd.DataFrame:
    """
    4. Xây dựng Golden Record: mdm_market_index (14 Chỉ số Thị trường & Ngành):
       - Định danh chuẩn 14 chỉ số (VNINDEX, VN30, VNFINLEAD, VNFINSELECT, VNDIAMOND...)
       - Lưu vào data_lake/02_silver/dim_conformed/mdm_market_index.snappy.parquet
    """
    print(">>> [MDM 4/4] Xây dựng Golden Records: mdm_market_index (14 Chỉ số)...")
    indices = [
        ("VNINDEX", "Chỉ số Toàn diện Sàn HOSE (VN-Index)", "HOSE", "BROAD_MARKET", "Giá trị vốn hóa thị trường có điều chỉnh free-float"),
        ("VN30", "Chỉ số 30 Cổ phiếu Vốn hóa Lớn nhất HOSE", "HOSE", "SIZE_SEGMENT", "Top 30 vốn hóa & thanh khoản cao nhất"),
        ("VN100", "Chỉ số 100 Cổ phiếu Đầu ngành HOSE", "HOSE", "SIZE_SEGMENT", "Top 100 cổ phiếu lớn nhất"),
        ("VNMIDCAP", "Chỉ số 70 Cổ phiếu Vốn hóa Trung bình", "HOSE", "SIZE_SEGMENT", "70 cổ phiếu kế tiếp VN30"),
        ("VNSMALLCAP", "Chỉ số Cổ phiếu Vốn hóa Nhỏ", "HOSE", "SIZE_SEGMENT", "Nhóm vốn hóa nhỏ"),
        ("VNALLSHARE", "Chỉ số Toàn bộ Cổ phiếu Đạt Chuẩn HOSE", "HOSE", "BROAD_MARKET", "Bao gồm VN100 và VNSmallCap"),
        ("VNFIN", "Chỉ số Ngành Tài chính HOSE", "HOSE", "SECTOR_FINANCE", "Ngân hàng, Chứng khoán, Bảo hiểm"),
        ("VNFINLEAD", "Chỉ số Tài chính Chọn lọc VNFINLEAD", "HOSE", "SECTOR_FINANCE", "Cổ phiếu tài chính thanh khoản cao, Capped 15%"),
        ("VNFINSELECT", "Chỉ số Tài chính Toàn diện VNFINSELECT", "HOSE", "SECTOR_FINANCE", "Toàn bộ cổ phiếu tài chính đủ điều kiện"),
        ("VNDIAMOND", "Chỉ số Kim cương Việt Nam VN DIAMOND", "HOSE", "THEMATIC_INVESTABLE", "Cổ phiếu hết room ngoại, tăng trưởng tốt"),
        ("HNXINDEX", "Chỉ số Toàn diện Sàn HNX", "HNX", "BROAD_MARKET", "Toàn bộ cổ phiếu niêm yết HNX"),
        ("HNX30", "Chỉ số 30 Cổ phiếu Lớn nhất HNX", "HNX", "SIZE_SEGMENT", "Top 30 cổ phiếu HNX"),
        ("UPCOMINDEX", "Chỉ số Thị trường Đăng ký Giao dịch UPCOM", "HNX", "BROAD_MARKET", "Toàn bộ doanh nghiệp UPCOM"),
        ("VNCOND", "Chỉ số Hàng Tiêu dùng Không Thiết yếu", "HOSE", "SECTOR_FINANCE", "Chỉ số ngành tiêu dùng tham chiếu"),
    ]

    df = pd.DataFrame([
        {
            "index_sk": idx + 1,
            "index_code": item[0],
            "index_name_vi": item[1],
            "exchange_managing": item[2],
            "index_category": item[3],
            "weighting_methodology": item[4],
            "is_active": True
        }
        for idx, item in enumerate(indices)
    ])

    out_parquet = SILVER_CONFORMED_DIR / "mdm_market_index.snappy.parquet"
    df.to_parquet(out_parquet, compression="snappy", index=False)
    print(f"      [✓] Đã ghi Golden Record: {out_parquet} ({len(df)} chỉ số thị trường)")

    # Đồng bộ vào master_data.dim_market_index
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _, r in df.iterrows():
                cur.execute("""
                    INSERT INTO master_data.dim_market_index (
                        index_symbol, index_name, exchange, is_active
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (index_symbol) DO UPDATE SET
                        index_name = EXCLUDED.index_name,
                        exchange = EXCLUDED.exchange;
                """, (r["index_code"], r["index_name_vi"], r["exchange_managing"], True))
            conn.commit()
            print("      [✓] Đã nạp 14 chỉ số chuẩn vào master_data.dim_market_index.")
    finally:
        conn.close()

    return df


def main():
    print("=" * 80)
    print(">>> BẮT ĐẦU XÂY DỰNG 5 BẢN GHI VÀNG DỮ LIỆU CHỦ (MDM GOLDEN RECORDS) <<<")
    print("=" * 80)

    build_mdm_bank()
    build_mdm_trading_calendar()
    build_mdm_metric_dictionary()
    build_mdm_market_index()

    print("\n" + "=" * 80)
    print(">>> HOÀN THÀNH XUẤT SẮC GIAI ĐOẠN 1: MDM GOLDEN RECORDS & CẤU HÌNH TẬP TRUNG! <<<")
    print("=" * 80)


if __name__ == "__main__":
    main()
