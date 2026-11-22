"""
INTEGRATION TESTS: Kiá»ƒm thá»­ tÃ­ch há»£p Ä‘áº§u cuá»‘i (End-to-End), Dashboard Services vÃ  BÃ¡o máº­t Chatbot Read-Only
"""

import os
import unittest
import psycopg2
from stock_analysis.common.db import get_db_connection
from stock_analysis.common.paths import CODE_ROOT


class TestIntegration(unittest.TestCase):

    def test_ops_and_pipeline_status(self):
        """Kiá»ƒm tra báº£ng ops.pipeline_runs vÃ  ops.dataset_publish_state."""
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Kiá»ƒm tra pipeline runs
        cur.execute("SELECT COUNT(*) FROM ops.pipeline_runs WHERE status = 'SUCCESS';")
        success_runs = cur.fetchone()[0]
        self.assertGreater(success_runs, 0, "ChÆ°a cÃ³ phiÃªn pipeline run nÃ o thÃ nh cÃ´ng!")

        # Kiá»ƒm tra cÃ¡c dataset Ä‘Ã£ Ä‘Æ°á»£c cÃ´ng bá»‘
        cur.execute("SELECT dataset_name, latest_record_count, status FROM ops.dataset_publish_state;")
        states = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        self.assertIn("market_ohlcv", states)
        self.assertIn("financial_statements", states)
        self.assertIn("banking_ratios_camels", states)

        self.assertGreater(states["market_ohlcv"][0], 70000)
        self.assertGreater(states["financial_statements"][0], 900)
        self.assertGreater(states["banking_ratios_camels"][0], 700)
        conn.close()

    def test_dashboard_query_service(self):
        """Kiá»ƒm tra toÃ n bá»™ cÃ¡c API truy váº¥n cá»§a Dashboard Service."""
        import sys
        sys.path.insert(0, str(CODE_ROOT / "apps"))
        import dashboard.services.query_service as qs

        # 1. Danh sÃ¡ch 27 ngÃ¢n hÃ ng
        banks = qs.get_all_banks()
        self.assertEqual(len(banks), 27)

        # 2. Platform Health KPIs
        kpis = qs.get_platform_health_kpis()
        self.assertIn("total_ohlcv", kpis)
        self.assertGreater(kpis["total_ohlcv"], 70000)
        self.assertIn("total_financials", kpis)
        self.assertGreater(kpis["total_financials"], 900)

        # 3. Gordon Valuation Matrix
        val_df = qs.get_gordon_matrix_data()
        self.assertFalse(val_df.empty)

        # 4. CAMELS Radar data cho VCB
        camels_df = qs.get_camels_radar_data("VCB")
        self.assertFalse(camels_df.empty)

        # 5. Top Shareholders cho VCB
        sh_df = qs.get_bank_shareholders("VCB")
        self.assertFalse(sh_df.empty)

    def test_chatbot_readonly_security(self):
        """Kiá»ƒm tra tÃ i khoáº£n chatbot_readonly chá»‰ Ä‘Æ°á»£c SELECT vÃ  bá»‹ cháº·n ghi/xÃ³a."""
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "Stock_Warehouse")
        chatbot_user = os.getenv("CHATBOT_DB_USER", "chatbot_readonly")
        chatbot_pass = os.getenv("CHATBOT_DB_PASSWORD", "chatbot_secure_pass")

        # 1. Káº¿t ná»‘i thÃ nh cÃ´ng
        bot_conn = psycopg2.connect(
            host=db_host, port=db_port, dbname=db_name,
            user=chatbot_user, password=chatbot_pass
        )
        bot_cur = bot_conn.cursor()

        # 2. SELECT thÃ nh cÃ´ng trÃªn Mart
        bot_cur.execute("SELECT COUNT(*) FROM mart_valuation.view_gordon_pb_roe_matrix;")
        cnt = bot_cur.fetchone()[0]
        self.assertGreater(cnt, 0)

        # 3. INSERT/DROP bá»‹ tá»« chá»‘i quyá» n (Permission Denied)
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            bot_cur.execute("CREATE TABLE mart_valuation.test_hack (id INT);")

        bot_conn.rollback()
        bot_conn.close()


if __name__ == "__main__":
    unittest.main()
