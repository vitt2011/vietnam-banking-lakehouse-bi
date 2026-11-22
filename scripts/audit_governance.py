import os
import psycopg2
import pandas as pd

conn = psycopg2.connect(host='localhost', port='5432', dbname='Stock_Warehouse', user='postgres', password=os.getenv("DB_PASS", ""))
cur = conn.cursor()

print("=== 1. CỔ ĐÔNG (fact_bank_shareholders) ===")
cur.execute("""
    SELECT s.ticker, s.shareholder_name, s.ownership_pct, s.quantity, s.update_date
    FROM mart_governance.fact_bank_shareholders s
    WHERE s.ticker = 'VCB'
    ORDER BY s.ownership_pct DESC
    LIMIT 5;
""")
print("Sample VCB Shareholders:")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT MIN(update_date), MAX(update_date), COUNT(*), COUNT(DISTINCT ticker)
    FROM mart_governance.fact_bank_shareholders;
""")
print("Shareholders range & coverage:", cur.fetchone())

cur.execute("""
    SELECT ticker, COUNT(*), MAX(update_date)
    FROM mart_governance.fact_bank_shareholders
    GROUP BY ticker
    ORDER BY MAX(update_date) ASC
    LIMIT 5;
""")
print("Earliest updated tickers for shareholders:")
for r in cur.fetchall():
    print(r)

print("\n=== 2. BAN LÃNH ĐẠO (fact_bank_officers) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'mart_governance' AND table_name = 'fact_bank_officers';
""")
print("Columns:", [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT *
    FROM mart_governance.fact_bank_officers
    WHERE ticker = 'VCB'
    LIMIT 5;
""")
print("Sample VCB Officers:")
for r in cur.fetchall():
    print(r)

cur.execute("""
    SELECT COUNT(*), COUNT(DISTINCT ticker)
    FROM mart_governance.fact_bank_officers;
""")
print("Officers count & ticker coverage:", cur.fetchone())

print("\n=== 3. CÔNG TY CON (fact_bank_subsidiaries) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'mart_governance' AND table_name = 'fact_bank_subsidiaries';
""")
print("Columns:", [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT b.ticker, COUNT(s.id)
    FROM master_data.dim_bank b
    LEFT JOIN mart_governance.fact_bank_subsidiaries s ON b.bank_sk = s.bank_sk
    WHERE b.bank_sk > 0
    GROUP BY b.ticker
    ORDER BY COUNT(s.id) ASC
    LIMIT 6;
""")
print("Banks with fewest subsidiaries:")
for r in cur.fetchall():
    print(r)

print("\n=== 4. SỰ KIỆN DOANH NGHIỆP & CỔ TỨC (fact_corporate_events) ===")
cur.execute("""
    SELECT MIN(exright_date), MAX(exright_date), MIN(record_date), MAX(record_date), COUNT(*)
    FROM mart_governance.fact_corporate_events;
""")
print("Corporate events date range:", cur.fetchone())

cur.execute("""
    SELECT event_code, COUNT(*)
    FROM mart_governance.fact_corporate_events
    GROUP BY event_code
    ORDER BY COUNT(*) DESC;
""")
print("Event codes:", cur.fetchall())

print("\n=== 5. CHỈ SỐ THỊ TRƯỜNG & VĨ MÔ (fact_macro_indicators) ===")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'mart_technical' AND table_name = 'fact_macro_indicators';
""")
print("Columns:", [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT MIN(full_date), MAX(full_date), COUNT(*)
    FROM mart_technical.fact_macro_indicators;
""")
print("Macro range:", cur.fetchone())
