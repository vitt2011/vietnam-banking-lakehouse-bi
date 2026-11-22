import os
import psycopg2
import pandas as pd

conn = psycopg2.connect(host='localhost', port='5432', dbname='Stock_Warehouse', user='postgres', password=os.getenv("DB_PASS", ""))
cur = conn.cursor()

# 1. Danh sách bảng
cur.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema IN ('master_data', 'mart_governance', 'mart_camels', 'mart_technical', 'mart_sentiment', 'metadata', 'ops')
      AND table_type = 'BASE TABLE'
    ORDER BY table_schema, table_name;
""")
tables = cur.fetchall()

print(f"=== TOÀN BỘ CÁC BẢNG TRONG DATA WAREHOUSE ({len(tables)} bảng) ===\n")

results = []
for schema, tbl in tables:
    full_tbl = f'"{schema}"."{tbl}"'
    
    # Đếm số dòng
    cur.execute(f"SELECT COUNT(*) FROM {full_tbl};")
    cnt = cur.fetchone()[0]
    
    # Kiểm tra các cột
    cur.execute(f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = '{schema}' AND table_name = '{tbl}';
    """)
    cols = {r[0]: r[1] for r in cur.fetchall()}
    
    # Tìm cột ticker hoặc bank_sk
    has_ticker = 'ticker' in cols
    has_bank_sk = 'bank_sk' in cols
    ticker_count = 'N/A'
    if has_ticker:
        cur.execute(f"SELECT COUNT(DISTINCT ticker) FROM {full_tbl};")
        ticker_count = f"{cur.fetchone()[0]}/27"
    elif has_bank_sk:
        cur.execute(f"SELECT COUNT(DISTINCT bank_sk) FROM {full_tbl} WHERE bank_sk > 0;")
        ticker_count = f"{cur.fetchone()[0]}/27"
        
    # Tìm min/max date
    date_info = 'N/A'
    if 'date_sk' in cols:
        cur.execute(f"SELECT MIN(date_sk), MAX(date_sk) FROM {full_tbl} WHERE date_sk IS NOT NULL;")
        mn, mx = cur.fetchone()
        date_info = f"{mn} -> {mx}"
    elif 'report_quarter' in cols or 'quarter' in cols:
        q_col = 'report_quarter' if 'report_quarter' in cols else 'quarter'
        cur.execute(f"SELECT MIN({q_col}), MAX({q_col}) FROM {full_tbl};")
        mn, mx = cur.fetchone()
        date_info = f"{mn} -> {mx}"
    elif 'record_date' in cols:
        cur.execute(f"SELECT MIN(record_date), MAX(record_date) FROM {full_tbl};")
        mn, mx = cur.fetchone()
        date_info = f"{mn} -> {mx}"
    elif 'full_date' in cols:
        cur.execute(f"SELECT MIN(full_date), MAX(full_date) FROM {full_tbl};")
        mn, mx = cur.fetchone()
        date_info = f"{mn} -> {mx}"
        
    results.append({
        'Schema': schema,
        'Table': tbl,
        'Rows': cnt,
        'Bank Coverage': ticker_count,
        'Date/Quarter Range': str(date_info)
    })

df_res = pd.DataFrame(results)
pd.set_option('display.max_columns', 10)
pd.set_option('display.width', 1000)
pd.set_option('display.max_rows', 100)
print(df_res.to_string(index=False))
