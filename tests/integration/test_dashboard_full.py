"""
INTEGRATION TEST: KIỂM TRA TOÀN DIỆN CÁC PHÂN HỆ VÀ TRUY VẤN DỮ LIỆU DASHBOARD
Path: tests/integration/test_dashboard_full.py
"""

import sys
import unittest
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from streamlit.testing.v1 import AppTest
import apps.dashboard.services.query_service as qs


class TestDashboardFull(unittest.TestCase):

    def test_query_service_core_apis(self):
        """Kiểm tra kết nối và tính toàn vẹn của các API truy vấn DWH."""
        # 1. Master banks
        df_banks = qs.get_all_banks()
        self.assertFalse(df_banks.empty)
        self.assertIn("ticker", df_banks.columns)
        self.assertEqual(len(df_banks), 27)

        # 2. KPI platform
        kpis = qs.get_platform_health_kpis()
        self.assertIsInstance(kpis, dict)
        self.assertGreater(kpis.get("total_ohlcv", 0), 0)

        # 3. CAMELS Peer & Radar
        peer_df = qs.get_camels_peer_comparison()
        self.assertFalse(peer_df.empty)
        self.assertIn("a_asset_quality_npl", peer_df.columns)
        self.assertIn("c_capital_car", peer_df.columns)

        radar_df = qs.get_camels_radar_data("VCB")
        self.assertFalse(radar_df.empty)

        # 4. Gordon valuation
        gordon_df = qs.get_gordon_matrix_data("VCB")
        self.assertFalse(gordon_df.empty)

        # 5. Dividends & Corporate Events
        div_df = qs.get_bank_dividends("VCB")
        self.assertIn("value_per_share", div_df.columns)
        div_sum = qs.get_dividend_yield_summary("VCB")
        self.assertIsInstance(div_sum, dict)

        # 6. Macro & Technical
        macro_df = qs.get_macro_market_correlation(days=365, ticker="VCB")
        self.assertFalse(macro_df.empty)
        tech_df = qs.get_technical_ohlcv_data("VCB", days=60)
        self.assertFalse(tech_df.empty)

    def test_all_modules_render_without_error(self):
        """Chạy AppTest qua toàn bộ 6 Module của Dashboard."""
        at = AppTest.from_file(str(PROJECT_ROOT / "apps" / "dashboard" / "app.py"), default_timeout=30)
        at.run()
        self.assertEqual(len(at.exception), 0, f"Exception on default render: {at.exception}")

        radios = at.sidebar.radio
        self.assertGreater(len(radios), 0)
        menu_options = radios[0].options
        self.assertEqual(len(menu_options), 5)

        for i, opt in enumerate(menu_options):
            at.sidebar.radio[0].set_value(opt).run()
            self.assertEqual(len(at.exception), 0, f"Module {i} ({opt}) threw exception: {at.exception}")
            self.assertEqual(len(at.error), 0, f"Module {i} ({opt}) showed st.error: {[e.value for e in at.error]}")

    def test_theme_mode_switching(self):
        """Kiểm tra cơ chế chuyển giao diện Sáng / Tối."""
        for mode in ["LIGHT", "DARK"]:
            at = AppTest.from_file(str(PROJECT_ROOT / "apps" / "dashboard" / "app.py"), default_timeout=30)
            at.session_state["theme_mode"] = mode
            at.run()
            self.assertEqual(len(at.exception), 0)
            self.assertEqual(len(at.error), 0)


if __name__ == "__main__":
    unittest.main()
