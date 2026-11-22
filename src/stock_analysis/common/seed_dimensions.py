import os
"""
==============================================================================
TẬP LỆNH: src/mdm/seed_dimensions.py
CHỨC NĂNG: NẠP DỮ LIỆU MỒI MASTER DATA (dim_bank, dim_date, dim_market_index)
TÁC GIẢ: Nguyễn Văn Việt (Toán - Tin K68 HUST) | GVHD: TS. Nguyễn Danh Tú
==============================================================================
"""

import sys
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Cấu hình kết nối PostgreSQL
DB_CONFIG = {
    "dbname": "Stock_Warehouse",
    "user": "postgres",
    "password": os.getenv("DB_PASS", ""),
    "host": "localhost",
    "port": 5432
}

# ==============================================================================
# 1. MASTER DATA: 27 NGÂN HÀNG THƯƠNG MẠI VIỆT NAM (mdm_bank)
# ==============================================================================
BANK_MASTER_DATA = [
    # TIER 1: BIG 4 QUỐC DOANH (Nhà nước sở hữu chi phối)
    ("VCB", "Ngân hàng TMCP Ngoại thương Việt Nam", "Vietcombank", "0100112437", "HOSE", "STATE_BIG4", 55890914440000),
    ("BID", "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam", "BIDV", "0100150619", "HOSE", "STATE_BIG4", 57004359000000),
    ("CTG", "Ngân hàng TMCP Công Thương Việt Nam", "VietinBank", "0100111948", "HOSE", "STATE_BIG4", 53699919500000),

    # TIER 2: TƯ NHÂN ĐẦU NGÀNH (Vốn điều lệ và lợi nhuận khủng)
    ("TCB", "Ngân hàng TMCP Kỹ Thương Việt Nam", "Techcombank", "0100230800", "HOSE", "TIER1_PRIVATE", 70450239000000),
    ("MBB", "Ngân hàng TMCP Quân Đội", "MBBank", "0100283873", "HOSE", "TIER1_PRIVATE", 52870845000000),
    ("VPB", "Ngân hàng TMCP Việt Nam Thịnh Vượng", "VPBank", "0100233583", "HOSE", "TIER1_PRIVATE", 79339236000000),
    ("ACB", "Ngân hàng TMCP Á Châu", "ACB", "0301452948", "HOSE", "TIER1_PRIVATE", 44666555000000),
    ("HDB", "Ngân hàng TMCP Phát triển TP.HCM", "HDBank", "0300608092", "HOSE", "TIER1_PRIVATE", 29076326000000),
    ("STB", "Ngân hàng TMCP Sài Gòn Thương Tín", "Sacombank", "0301103908", "HOSE", "TIER1_PRIVATE", 18852148000000),

    # TIER 3: TẦM TRUNG (MIDCAP)
    ("LPB", "Ngân hàng TMCP Lộc Phát Việt Nam", "LPBank", "6300048638", "HOSE", "TIER2_MIDCAP", 25576165000000),
    ("SHB", "Ngân hàng TMCP Sài Gòn - Hà Nội", "SHB", "1800278630", "HOSE", "TIER2_MIDCAP", 36629120000000),
    ("VIB", "Ngân hàng TMCP Quốc tế Việt Nam", "VIB", "0100793095", "HOSE", "TIER2_MIDCAP", 25368075000000),
    ("TPB", "Ngân hàng TMCP Tiên Phong", "TPBank", "0102744865", "HOSE", "TIER2_MIDCAP", 22016350000000),
    ("SSB", "Ngân hàng TMCP Đông Nam Á", "SeABank", "0200167734", "HOSE", "TIER2_MIDCAP", 28350000000000),
    ("MSB", "Ngân hàng TMCP Hàng Hải Việt Nam", "MSB", "0200124891", "HOSE", "TIER2_MIDCAP", 26000000000000),
    ("OCB", "Ngân hàng TMCP Phương Đông", "OCB", "0300852005", "HOSE", "TIER2_MIDCAP", 24658045000000),
    ("EIB", "Ngân hàng TMCP Xuất Nhập Khẩu Việt Nam", "Eximbank", "0301179079", "HOSE", "TIER2_MIDCAP", 17469561000000),
    ("NAB", "Ngân hàng TMCP Nam Á", "Nam A Bank", "0300879889", "HOSE", "TIER2_MIDCAP", 10580416000000),

    # TIER 4: NHỎ & ĐANG TÁI CƠ CẤU (SMALLCAP)
    ("ABB", "Ngân hàng TMCP An Bình", "ABBank", "0100619478", "UPCOM", "TIER3_SMALL", 10350367000000),
    ("BAB", "Ngân hàng TMCP Bắc Á", "Bac A Bank", "2900325521", "HNX", "TIER3_SMALL", 8959000000000),
    ("BVB", "Ngân hàng TMCP Bản Việt", "BVBank", "2000106528", "UPCOM", "TIER3_SMALL", 5018000000000),
    ("KLB", "Ngân hàng TMCP Kiên Long", "Kienlongbank", "1700197787", "UPCOM", "TIER3_SMALL", 3652819000000),
    ("NVB", "Ngân hàng TMCP Quốc Dân", "NCB", "0100579078", "HNX", "TIER3_SMALL", 5601550000000),
    ("PGB", "Ngân hàng TMCP Thịnh vượng và Phát triển", "PGBank", "0100777595", "UPCOM", "TIER3_SMALL", 4200000000000),
    ("SGB", "Ngân hàng TMCP Sài Gòn Công Thương", "Saigonbank", "0300610419", "UPCOM", "TIER3_SMALL", 3080000000000),
    ("VAB", "Ngân hàng TMCP Việt Á", "VietABank", "0302963650", "UPCOM", "TIER3_SMALL", 5399650000000),
    ("VBB", "Ngân hàng TMCP Việt Nam Thương Tín", "VietBank", "1900498706", "UPCOM", "TIER3_SMALL", 4776822000000),
]

# ==============================================================================
# 2. MASTER DATA: CHỈ SỐ THỊ TRƯỜNG (mdm_market_index)
# ==============================================================================
INDICES_MASTER_DATA = [
    ("VNINDEX", "Chỉ số VN-Index", "HOSE"),
    ("VN30", "Chỉ số VN30 - Top 30 Bluechip", "HOSE"),
    ("VNFINLEAD", "Chỉ số Tài chính Chọn lọc VNFINLEAD", "HOSE"),
    ("VNFINSELECT", "Chỉ số Tài chính Tuyển chọn VNFINSELECT", "HOSE"),
    ("VN100", "Chỉ số VN100", "HOSE"),
    ("HNXIndex", "Chỉ số HNX-Index", "HNX"),
    ("HNX30", "Chỉ số HNX30", "HNX"),
    ("UPCOMIndex", "Chỉ số UPCOM-Index", "UPCOM"),
]


def seed_dim_bank(conn):
    print(">>> 1/3: Nạp Master Data 27 Ngân hàng (dim_bank)...")
    cur = conn.cursor()
    inserted = 0
    for row in BANK_MASTER_DATA:
        ticker, name, short_name, tax, ex, tier, cap = row
        sql = """
        INSERT INTO master_data.dim_bank (ticker, bank_name, short_name, tax_code, listing_exchange, tier_group, charter_capital_vnd)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            bank_name = EXCLUDED.bank_name,
            short_name = EXCLUDED.short_name,
            tax_code = EXCLUDED.tax_code,
            listing_exchange = EXCLUDED.listing_exchange,
            tier_group = EXCLUDED.tier_group,
            charter_capital_vnd = EXCLUDED.charter_capital_vnd;
        """
        cur.execute(sql, (ticker, name, short_name, tax, ex, tier, cap))
        inserted += 1
    print(f"    [✓] Đã nạp thành công {inserted}/27 ngân hàng vào master_data.dim_bank.")


def seed_dim_market_index(conn):
    print(">>> 2/3: Nạp Master Data Chỉ số thị trường (dim_market_index)...")
    cur = conn.cursor()
    inserted = 0
    for sym, name, ex in INDICES_MASTER_DATA:
        sql = """
        INSERT INTO master_data.dim_market_index (index_symbol, index_name, exchange)
        VALUES (%s, %s, %s)
        ON CONFLICT (index_symbol) DO UPDATE SET
            index_name = EXCLUDED.index_name,
            exchange = EXCLUDED.exchange;
        """
        cur.execute(sql, (sym, name, ex))
        inserted += 1
    print(f"    [✓] Đã nạp thành công {inserted} chỉ số vào master_data.dim_market_index.")


def seed_dim_date(conn):
    print(">>> 3/3: Sinh Trục Thời Gian Tài Chính 2006 - 2030 (dim_date)...")
    cur = conn.cursor()
    
    # Kiểm tra xem dim_date đã có dữ liệu chưa
    cur.execute("SELECT count(*) FROM master_data.dim_date;")
    existing_count = cur.fetchone()[0]
    if existing_count >= 8000:
        print(f"    [✓] master_data.dim_date đã có sẵn {existing_count:,} ngày. Bỏ qua.")
        return

    start_date = datetime(2006, 1, 1)
    end_date = datetime(2030, 12, 31)
    current_date = start_date
    
    dates_to_insert = []
    
    while current_date <= end_date:
        date_sk = int(current_date.strftime("%Y%m%d"))
        year = current_date.year
        quarter = (current_date.month - 1) // 3 + 1
        month = current_date.month
        day = current_date.day
        day_of_week = current_date.isoweekday() # 1: Mon .. 7: Sun
        quarter_name = f"{year}-Q{quarter}"
        is_weekend = (day_of_week in (6, 7))
        is_trading = not is_weekend  # Mặc định ngày trong tuần là ngày giao dịch
        
        # Kiểm tra cuối tháng, cuối quý
        next_day = current_date + timedelta(days=1)
        is_month_end = (next_day.month != month)
        is_quarter_end = (is_month_end and month in (3, 6, 9, 12))
        
        dates_to_insert.append((
            date_sk, current_date.date(), year, quarter, month, day,
            day_of_week, quarter_name, is_weekend, is_trading,
            is_month_end, is_quarter_end
        ))
        
        current_date += timedelta(days=1)

    # Chèn dữ liệu theo batch
    insert_sql = """
    INSERT INTO master_data.dim_date (
        date_sk, full_date, year, quarter, month, day,
        day_of_week, quarter_name, is_weekend, is_trading_day,
        is_month_end, is_quarter_end
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (date_sk) DO NOTHING;
    """
    
    cur.executemany(insert_sql, dates_to_insert)
    print(f"    [✓] Đã sinh thành công {len(dates_to_insert):,} ngày vào master_data.dim_date.")


def main():
    print("=" * 70)
    print(">>> KHỞI TẠO DỮ LIỆU MỒI MASTER DATA (SEED DIMENSIONS) CHO POSTGRESQL 16 <<<")
    print("=" * 70)
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    
    try:
        seed_dim_bank(conn)
        seed_dim_market_index(conn)
        seed_dim_date(conn)
        print("=" * 70)
        print("[✓] TOÀN BỘ BẢNG CHIỀU (DIMENSIONS) ĐÃ ĐƯỢC NẠP SẴN SÀNG CHO ETL!")
        print("=" * 70)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
