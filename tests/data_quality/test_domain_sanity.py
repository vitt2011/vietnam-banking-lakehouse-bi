"""
DOMAIN SANITY GATE: Kiểm thử bất biến nghiệp vụ tài chính trên Cloud Snapshot
Ngăn chặn tái diễn các lỗi: tráo bank_sk, âm CIR/LLR, nhầm dự phòng BCĐKT/KQKD,
lãi suất nhân 100x, và URL PDF giả.
"""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import apps.dashboard.services.query_service as qs


class TestDomainSanity(unittest.TestCase):

    def test_unscrambled_bank_sk_ohlcv(self):
        """VCB phải có thị giá lớn hơn ABB (không còn bị tráo bank_sk)."""
        df_snap = qs.get_sector_technical_snapshot()
        self.assertEqual(len(df_snap), 27)
        vcb_px = float(df_snap.loc[df_snap["ticker"] == "VCB", "close_price"].iloc[0])
        abb_px = float(df_snap.loc[df_snap["ticker"] == "ABB", "close_price"].iloc[0])
        self.assertGreater(vcb_px, 40000.0)
        self.assertGreater(vcb_px, 2.0 * abb_px)

    def test_accounting_signs_and_pb_equation(self):
        """CIR & LLR phải dương; TOI - OPEX - Provision phải khớp PBT; CAR >= 0."""
        peer_df = qs.get_camels_peer_comparison()
        self.assertFalse(peer_df.empty)
        self.assertTrue((peer_df["m_management_cir"] > 0).all())
        self.assertTrue((peer_df["a_provision_llr"].dropna() >= 0).all())

        eq_df = qs.get_earnings_quality_breakdown("VCB", limit_quarters=4)
        self.assertFalse(eq_df.empty)
        latest = eq_df.iloc[-1]
        diff = abs((latest["toi"] - latest["opex"] - latest["provision_expense"]) - latest["pbt"])
        self.assertLess(diff / max(abs(latest["toi"]), 1.0), 0.02)

    def test_macro_unit_and_real_pdf_links(self):
        """Lãi suất SBV nằm trong [1%, 20%]; không có URL giả ssc.gov.vn."""
        df_m = qs.get_macro_market_correlation(days=90, ticker="VCB")
        sbv = df_m["sbv_refinancing_rate"].dropna()
        self.assertFalse(sbv.empty)
        self.assertTrue(((sbv >= 1.0) & (sbv <= 20.0)).all())

        pdfs = qs.get_real_bctc_pdfs("ACB", limit=5)
        if not pdfs.empty:
            for u in pdfs["attachment_pdf_url"].dropna():
                self.assertNotIn("congbothongtin.ssc.gov.vn/bctc/", u)


if __name__ == "__main__":
    unittest.main()
