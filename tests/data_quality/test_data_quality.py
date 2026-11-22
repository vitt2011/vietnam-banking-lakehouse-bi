"""
DATA QUALITY TESTS: Kiá»ƒm toÃ¡n sá»‘ lÆ°á»£ng báº£n ghi, tÃ­nh cÃ¢n Ä‘á»‘i káº¿ toÃ¡n, phÃ¢n phá»‘i P/B vÃ  cÆ¡ cáº¥u cá»• Ä‘Ã´ng lá»›n
"""

import unittest
from stock_analysis.common.db import get_db_connection


class TestDataQuality(unittest.TestCase):

    def setUp(self):
        self.conn = get_db_connection()
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.close()

    def test_dwh_row_counts(self):
        """Kiá»ƒm tra sá»‘ lÆ°á»£ng báº£n ghi cÃ¡c báº£ng chÃ­nh trong Data Warehouse."""
        # 1. 27 ngÃ¢n hÃ ng
        self.cur.execute("SELECT COUNT(*) FROM master_data.dim_bank WHERE is_active = TRUE;")
        bank_count = self.cur.fetchone()[0]
        self.assertEqual(bank_count, 27, f"Sá»‘ lÆ°á»£ng ngÃ¢n hÃ ng khÃ´ng pháº£i 27: {bank_count}")

        # 2. OHLCV > 70,000
        self.cur.execute("SELECT COUNT(*) FROM mart_technical.fact_daily_market_ohlcv;")
        ohlcv_count = self.cur.fetchone()[0]
        self.assertGreater(ohlcv_count, 70000, f"Sá»‘ lÆ°á»£ng OHLCV tháº¥p hÆ¡n 70k: {ohlcv_count}")

        # 3. BCTC > 900
        self.cur.execute("SELECT COUNT(*) FROM mart_camels.fact_quarterly_financial_statements;")
        fin_count = self.cur.fetchone()[0]
        self.assertGreater(fin_count, 900, f"Sá»‘ lÆ°á»£ng BCTC tháº¥p hÆ¡n 900: {fin_count}")

        # 4. Banking Ratios > 700
        self.cur.execute("SELECT COUNT(*) FROM mart_camels.fact_quarterly_banking_ratios;")
        ratio_count = self.cur.fetchone()[0]
        self.assertGreater(ratio_count, 700, f"Sá»‘ lÆ°á»£ng Tá»· sá»‘ tháº¥p hÆ¡n 700: {ratio_count}")

        # 5. Cá»• Ä‘Ã´ng lá»›n (>= 5%) pháº£i cÃ³ Ä‘á»§ 32 cá»• Ä‘Ã´ng lá»›n
        self.cur.execute("SELECT COUNT(*) FROM mart_governance.fact_bank_shareholders WHERE ownership_pct >= 5.0;")
        major_shareholders = self.cur.fetchone()[0]
        self.assertEqual(major_shareholders, 32, f"Sá»‘ lÆ°á»£ng cá»• Ä‘Ã´ng lá»›n >= 5% khÃ´ng pháº£i 32: {major_shareholders}")

    def test_valuation_pb_distribution(self):
        """Kiá»ƒm tra giÃ¡ trá»‹ P/B thá»±c táº¿, Ä‘áº£m báº£o khÃ´ng bá»‹ lá»—i gÃ¡n máº·c Ä‘á»‹nh 1.5."""
        self.cur.execute("""
            SELECT COUNT(DISTINCT pb_ratio), MIN(pb_ratio), MAX(pb_ratio), AVG(pb_ratio)
            FROM mart_valuation.view_gordon_pb_roe_matrix
            WHERE pb_ratio > 0;
        """)
        distinct_pb, min_pb, max_pb, avg_pb = self.cur.fetchone()
        
        self.assertGreater(distinct_pb, 500, f"P/B bá»‹ trÃ¹ng láº·p quÃ¡ nhiá» u: {distinct_pb} giÃ¡ trá»‹ riÃªng biá»‡t")
        self.assertGreaterEqual(float(min_pb), 0.4, f"Min P/B quÃ¡ tháº¥p: {min_pb}")
        self.assertLess(float(max_pb), 6.0, f"Max P/B quÃ¡ cao: {max_pb}")
        self.assertTrue(1.0 <= float(avg_pb) <= 2.5, f"P/B bÃ¬nh quÃ¢n báº¥t thÆ°á» ng: {avg_pb}")

    def test_accounting_reconciliation(self):
        """Kiá»ƒm tra cÃ¢n Ä‘á»‘i káº¿ toÃ¡n: Tá»•ng tÃ i sáº£n = Ná»£ pháº£i tráº£ + Vá»‘n chá»§ sá»Ÿ há»¯u."""
        self.cur.execute("""
            SELECT COUNT(*)
            FROM mart_camels.fact_quarterly_financial_statements
            WHERE total_assets IS NOT NULL 
              AND total_liabilities IS NOT NULL 
              AND owners_equity IS NOT NULL
              AND ABS(total_assets - (total_liabilities + owners_equity)) > (0.01 * total_assets);
        """)
        imbalanced_count = self.cur.fetchone()[0]
        self.assertEqual(imbalanced_count, 0, f"PhÃ¡t hiá»‡n {imbalanced_count} ká»³ BCTC máº¥t cÃ¢n Ä‘á»‘i káº¿ toÃ¡n > 1%!")

    def test_bank_surrogate_key_mapping(self):
        """
        Kiểm tra toàn vẹn ánh xạ Khóa thay thế (Surrogate Key Mapping):
        1. Tất cả bank_sk trong fact_financial_statements và fact_banking_ratios phải tồn tại trong dim_bank.
        2. Quan hệ 1-1 hoàn hảo: 1 ticker ánh xạ duy nhất 1 bank_sk và ngược lại.
        3. Đối soát chéo giữa fact BCTC và fact Tỷ số tài chính cho từng bank_sk.
        4. Kiểm tra hồi quy dữ liệu gốc: Số liệu của ACB và EIB không bị hoán vị chéo giữa 2 bảng.
        """
        # 1. Quan hệ 1-1 trong dim_bank: Không ticker nào trùng bank_sk, không bank_sk nào trùng ticker
        self.cur.execute("""
            SELECT ticker, COUNT(bank_sk) as cnt 
            FROM master_data.dim_bank 
            GROUP BY ticker 
            HAVING COUNT(bank_sk) > 1;
        """)
        dup_tickers = self.cur.fetchall()
        self.assertEqual(len(dup_tickers), 0, f"Phát hiện ticker ánh xạ nhiều bank_sk: {dup_tickers}")

        self.cur.execute("""
            SELECT bank_sk, COUNT(ticker) as cnt 
            FROM master_data.dim_bank 
            GROUP BY bank_sk 
            HAVING COUNT(ticker) > 1;
        """)
        dup_sks = self.cur.fetchall()
        self.assertEqual(len(dup_sks), 0, f"Phát hiện bank_sk ánh xạ nhiều ticker: {dup_sks}")

        # 2. Toàn bộ bank_sk trong fact_quarterly_financial_statements phải tồn tại hợp lệ trong dim_bank
        self.cur.execute("""
            SELECT COUNT(DISTINCT f.bank_sk)
            FROM mart_camels.fact_quarterly_financial_statements f
            LEFT JOIN master_data.dim_bank d ON f.bank_sk = d.bank_sk
            WHERE d.bank_sk IS NULL;
        """)
        orphan_fs = self.cur.fetchone()[0]
        self.assertEqual(orphan_fs, 0, f"Phát hiện {orphan_fs} bank_sk mồ côi trong fact_quarterly_financial_statements!")

        # 3. Toàn bộ bank_sk trong fact_quarterly_banking_ratios phải tồn tại hợp lệ trong dim_bank
        self.cur.execute("""
            SELECT COUNT(DISTINCT r.bank_sk)
            FROM mart_camels.fact_quarterly_banking_ratios r
            LEFT JOIN master_data.dim_bank d ON r.bank_sk = d.bank_sk
            WHERE d.bank_sk IS NULL;
        """)
        orphan_ratios = self.cur.fetchone()[0]
        self.assertEqual(orphan_ratios, 0, f"Phát hiện {orphan_ratios} bank_sk mồ côi trong fact_quarterly_banking_ratios!")

        # 4. Kiểm tra hồi quy chuyên biệt chống tái diễn lỗi ACB ↔ EIB:
        # Lấy bank_sk chuẩn từ dim_bank
        self.cur.execute("SELECT ticker, bank_sk FROM master_data.dim_bank WHERE ticker IN ('ACB', 'EIB');")
        mapping = dict(self.cur.fetchall())
        acb_sk = mapping.get("ACB")
        eib_sk = mapping.get("EIB")
        self.assertIsNotNone(acb_sk, "ACB không tồn tại trong dim_bank")
        self.assertIsNotNone(eib_sk, "EIB không tồn tại trong dim_bank")
        self.assertNotEqual(acb_sk, eib_sk, "ACB và EIB bị gán trùng bank_sk")

        # Kiểm tra số liệu tại 2026Q3:
        # ACB có VCSH > 50 nghìn tỷ (thực tế ~104 nghìn tỷ); EIB có VCSH < 40 nghìn tỷ (thực tế ~26 nghìn tỷ)
        self.cur.execute("""
            SELECT bank_sk, owners_equity, net_profit_after_tax 
            FROM mart_camels.fact_quarterly_financial_statements
            WHERE fiscal_year = 2026 AND fiscal_quarter = 3 AND bank_sk IN (%s, %s);
        """, (acb_sk, eib_sk))
        fs_rows = {r[0]: (float(r[1]), float(r[2])) for r in self.cur.fetchall()}

        self.assertIn(acb_sk, fs_rows, f"Không tìm thấy BCTC 2026Q3 của ACB (bank_sk={acb_sk})")
        self.assertIn(eib_sk, fs_rows, f"Không tìm thấy BCTC 2026Q3 của EIB (bank_sk={eib_sk})")

        acb_equity, acb_npat = fs_rows[acb_sk]
        eib_equity, eib_npat = fs_rows[eib_sk]

        # Khẳng định ACB không bị tráo đổi sang số liệu của EIB:
        self.assertGreater(acb_equity, 50e12, f"VCSH của ACB bị gán nhầm ({acb_equity:,.0f} VND < 50 nghìn tỷ)")
        self.assertGreater(acb_npat, 1e12, f"LNST của ACB bị gán nhầm sang EIB ({acb_npat:,.0f} VND < 1 nghìn tỷ)")
        self.assertLess(eib_equity, 40e12, f"VCSH của EIB bất thường ({eib_equity:,.0f} VND > 40 nghìn tỷ)")

        # Kiểm tra tỷ số ROE trong fact_quarterly_banking_ratios
        self.cur.execute("""
            SELECT bank_sk, roe 
            FROM mart_camels.fact_quarterly_banking_ratios
            WHERE fiscal_year = 2026 AND fiscal_quarter = 3 AND bank_sk IN (%s, %s);
        """, (acb_sk, eib_sk))
        ratio_rows = {r[0]: float(r[1]) for r in self.cur.fetchall()}

        self.assertIn(acb_sk, ratio_rows)
        self.assertIn(eib_sk, ratio_rows)
        self.assertGreater(ratio_rows[acb_sk], 0.10, f"ROE ACB bị thấp bất thường ({ratio_rows[acb_sk]} <= 10%)")
        self.assertLess(ratio_rows[eib_sk], 0.05, f"ROE EIB bị cao bất thường ({ratio_rows[eib_sk]} >= 5%)")


if __name__ == "__main__":
    unittest.main()
