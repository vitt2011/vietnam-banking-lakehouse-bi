"""
UNIT TESTS: Kiá»ƒm thá»­ cÃ¡c hÃ m tÃ­nh toÃ¡n toÃ¡n há»c, cÃ´ng thá»©c nghiá»‡p vá»¥ vÃ  cáº¥u hÃ¬nh há»‡ thá»‘ng
"""

import unittest
import pandas as pd
import numpy as np
from pathlib import Path

from stock_analysis.common.paths import CODE_ROOT, DATA_LAKE_DIR, LOGS_DIR
from stock_analysis.transformation.silver_to_gold.feature_camels_engine import compute_camels_composite_score


class TestUnitModels(unittest.TestCase):

    def test_paths_and_env(self):
        """Kiá»ƒm tra há»‡ thá»‘ng Ä‘Æ°á»ng dáº«n táº­p trung vÃ  biáº¿n mÃ´i trÆ°á»ng."""
        self.assertTrue(CODE_ROOT.exists(), f"CODE_ROOT khÃ´ng tá»“n táº¡i: {CODE_ROOT}")
        self.assertTrue(DATA_LAKE_DIR.exists(), f"DATA_LAKE_DIR khÃ´ng tá»“n táº¡i: {DATA_LAKE_DIR}")
        self.assertTrue(LOGS_DIR.exists(), f"LOGS_DIR khÃ´ng tá»“n táº¡i: {LOGS_DIR}")
        self.assertIn(CODE_ROOT.name, ("Stock_Analysis", "vietnam-banking-lakehouse-bi"))

    def test_gordon_growth_formula(self):
        """Kiá»ƒm tra cÃ´ng thá»©c Ä‘á»‹nh giÃ¡ Gordon Growth P/B = (ROE - g) / (Ke - g)."""
        Ke = 0.13
        g = 0.06
        
        # Test trÆ°á»ng há»£p ROE = 20%
        roe = 0.20
        expected_pb = (roe - g) / (Ke - g)  # (0.14) / 0.07 = 2.0
        self.assertAlmostEqual(expected_pb, 2.0, places=4)

        # Test trÆ°á»ng há»£p ROE = 13% (báº±ng Ke) -> P/B = 1.0
        roe_fair = 0.13
        fair_pb = (roe_fair - g) / (Ke - g)
        self.assertAlmostEqual(fair_pb, 1.0, places=4)

    def test_camels_six_pillars_composite(self):
        """Kiá»ƒm tra tÃ­nh toÃ¡n tháº» Ä‘iá»ƒm CAMELS Ä‘áº§y Ä‘á»§ 6 trá»¥ cá»™t (C, A, M, E, L, S)."""
        data = {
            "car_total_pct": [0.12, 0.08],
            "npl_ratio_pct": [0.015, 0.045],
            "cir_pct": [0.30, 0.55],
            "roae_ttm_pct": [0.22, 0.07],
            "casa_ratio_pct": [0.38, 0.10],
            "nim_ttm_pct": [0.045, 0.022],
        }
        df = pd.DataFrame(data)
        scores = compute_camels_composite_score(df)
        
        self.assertEqual(len(scores), 2)
        # NgÃ¢n hÃ ng máº¡nh (dÃ²ng 0) pháº£i cÃ³ Ä‘iá»ƒm cao hÆ¡n ngÃ¢n hÃ ng yáº¿u (dÃ²ng 1)
        self.assertGreater(scores.iloc[0], scores.iloc[1])
        # Ä iá»ƒm náº±m trong dÃ£i 0 - 100
        self.assertTrue(0 <= scores.iloc[0] <= 100)
        self.assertTrue(0 <= scores.iloc[1] <= 100)
        # NgÃ¢n hÃ ng máº¡nh pháº£i cÃ³ Ä‘iá»ƒm > 70
        self.assertGreater(scores.iloc[0], 70.0)


if __name__ == "__main__":
    unittest.main()
