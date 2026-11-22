import os
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Stock_Warehouse', user='postgres', password=os.getenv("DB_PASS", ""))
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'master_data' AND table_name = 'dim_market_index'
    ORDER BY ordinal_position;
""")
print('dim_market_index columns:', cur.fetchall())

cur.execute("SELECT * FROM master_data.dim_market_index;")
print('dim_market_index rows:', cur.fetchall())

cur.execute("SELECT DISTINCT indicator_code FROM mart_technical.fact_macro_indicators;")
print('Macro indicators:', [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT b.ticker, count(*) 
    FROM mart_technical.fact_daily_market_ohlcv f 
    JOIN master_data.dim_bank b ON f.bank_sk = b.bank_sk 
    GROUP BY b.ticker 
    ORDER BY b.ticker;
""")
banks = cur.fetchall()
print(f'Total banks in fact_daily_market_ohlcv: {len(banks)}')
for b in banks[:5]:
    print(' ', b)
print(' ...')
for b in banks[-3:]:
    print(' ', b)

conn.close()
