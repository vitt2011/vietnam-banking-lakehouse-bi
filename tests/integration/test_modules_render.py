"""
INTEGRATION TEST: Kiá»ƒm tra import vÃ  cáº¥u trÃºc 6 Modules Dashboard theo chuáº©n Equity Research
"""

import sys
import unittest
from pathlib import Path
from stock_analysis.common.paths import CODE_ROOT


class TestModulesRender(unittest.TestCase):

    def setUp(self):
        sys.path.insert(0, str(CODE_ROOT))
        sys.path.insert(0, str(CODE_ROOT / "apps"))

    def test_theme_and_constants(self):
        """Kiá»ƒm tra common_theme vÃ  cÃ¡c hº±ng sá»‘ mÃ u."""
        from dashboard.common_theme import (
            BG_APP, BG_CARD, BG_SIDEBAR, COLOR_BRAND, COLOR_BRAND_LED,
            ACCENT_CYAN, ACCENT_PINK, TEXT_HEADING, TEXT_BODY, TEXT_MUTED,
            COLOR_UP, COLOR_DOWN, COLOR_WARN, apply_global_theme, apply_plotly_theme, render_led_card
        )
        self.assertIsNotNone(BG_APP)
        self.assertIsNotNone(COLOR_BRAND)

    def test_all_modules_import(self):
        """Kiểm tra toàn vẹn các modules giao diện phân tích nghiệp vụ (Chuẩn mới V3 & Legacy)."""
        # 5 Modules Chuẩn mới V3 (Kiến trúc 5 phân hệ phản biện)
        from dashboard.modules.mod0_overview import render_overview
        from dashboard.modules.mod1_valuation_gordon import render_valuation_gordon
        from dashboard.modules.mod2_bank_profile import render_bank_profile
        from dashboard.modules.mod3_catalysts_context import render_catalysts_context
        from dashboard.modules.mod4_research_evidence import render_research_evidence

        self.assertTrue(callable(render_overview))
        self.assertTrue(callable(render_valuation_gordon))
        self.assertTrue(callable(render_bank_profile))
        self.assertTrue(callable(render_catalysts_context))
        self.assertTrue(callable(render_research_evidence))


if __name__ == "__main__":
    unittest.main()
