"""
UNIT TEST: tests/unit/test_ma_suite.py
Kiểm thử Sector Technical Snapshot 27 ngân hàng (SMA20/50/200 & Volume Surge)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "apps") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "apps"))

import unittest
from dashboard.services.query_service import get_sector_technical_snapshot


class TestMASuite(unittest.TestCase):

    def test_database_sector_technical_snapshot(self):
        """Kiểm thử Database Snapshot trả về đủ 27 ngân hàng với các đường SMA20/50/200."""
        df_sec = get_sector_technical_snapshot()
        self.assertEqual(len(df_sec), 27)
        self.assertTrue("sma_20" in df_sec.columns)
        self.assertTrue("sma_50" in df_sec.columns)
        self.assertTrue("sma_200" in df_sec.columns)
        self.assertTrue("volume_surge_ratio" in df_sec.columns)


if __name__ == "__main__":
    unittest.main()
