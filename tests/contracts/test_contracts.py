"""
CONTRACT TESTS: Kiá»ƒm thá»­ há»£p Ä‘á»“ng dá»¯ liá»‡u (Data Contracts), Metrics Dictionary vÃ  Database Schemas
"""

import unittest
import yaml
from pathlib import Path
from stock_analysis.common.paths import CODE_ROOT
from stock_analysis.common.db import get_db_connection


class TestContracts(unittest.TestCase):

    def test_metrics_dictionary_contract(self):
        """Kiá»ƒm tra tá»‡p quy Æ°á»›c Metrics Dictionary YAML."""
        yaml_path = CODE_ROOT / "config" / "contracts" / "metrics_dictionary.yaml"
        self.assertTrue(yaml_path.exists(), f"Thiáº¿u file: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            dic = yaml.safe_load(f)

        self.assertIn("metrics", dic)
        metrics = dic["metrics"]

        # Kiá»ƒm tra cÃ¡c trá»¥ cá»™t CAMELS
        required_pillars = [
            "CAMELS_C_CAR",
            "CAMELS_A_NPL",
            "CAMELS_A_LLR",
            "CAMELS_M_CIR",
            "CAMELS_E_NIM",
            "CAMELS_E_ROE",
            "CAMELS_L_CASA",
            "CAMELS_S_NIM_SENSITIVITY",
            "VALUATION_GORDON_PB",
            "TECHNICAL_RSI_14",
        ]
        for pillar in required_pillars:
            self.assertIn(pillar, metrics, f"Thiáº¿u metric contract cho {pillar}")
            self.assertIn("formula", metrics[pillar])
            self.assertIn("authoritative_source", metrics[pillar])
            self.assertIn("grain", metrics[pillar])

    def test_database_schemas_contract(self):
        """Kiá»ƒm tra sá»± tá»“n táº¡i cá»§a 8 Schemas chuáº©n vÃ  10 Views nghiá»‡p vá»¥ trong PostgreSQL."""
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Kiá»ƒm tra 8 Schemas
        cur.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name IN (
                'master_data', 'silver_analytics', 'mart_valuation', 
                'mart_camels', 'mart_technical', 'mart_governance', 
                'mart_sentiment', 'ops', 'metadata'
            );
        """)
        found_schemas = {r[0] for r in cur.fetchall()}
        expected_schemas = {
            'master_data', 'silver_analytics', 'mart_valuation', 
            'mart_camels', 'mart_technical', 'mart_governance', 
            'mart_sentiment', 'ops', 'metadata'
        }
        self.assertEqual(expected_schemas - found_schemas, set(), f"Thiáº¿u schemas: {expected_schemas - found_schemas}")

        # 2. Kiá»ƒm tra 10 Views
        cur.execute("""
            SELECT schemaname || '.' || viewname 
            FROM pg_views 
            WHERE schemaname IN ('mart_valuation', 'mart_camels', 'mart_technical', 'mart_governance', 'mart_sentiment');
        """)
        found_views = {r[0] for r in cur.fetchall()}
        expected_views = {
            "mart_valuation.view_gordon_pb_roe_matrix",
            "mart_valuation.view_valuation_regime_matrix",
            "mart_camels.view_camels_radar",
            "mart_camels.view_earnings_quality_breakdown",
            "mart_technical.view_technical_market_daily",
            "mart_technical.view_macro_market_correlation",
            "mart_governance.view_governance_network",
            "mart_governance.view_top_shareholders",
            "mart_governance.view_bank_officers_list",
            "mart_sentiment.view_disclosure_feed",
        }
        missing_views = expected_views - found_views
        self.assertEqual(missing_views, set(), f"Thiáº¿u views trong database: {missing_views}")
        conn.close()


if __name__ == "__main__":
    unittest.main()
