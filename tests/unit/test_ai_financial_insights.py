import unittest
from stock_analysis.ai_service.gemini_bctc_analyzer import (
    build_audit_prompt, get_bank_ai_insights, save_ai_insights_to_warehouse
)
from apps.dashboard.services.query_service import get_financial_statement_notes


class TestAIFinancialInsights(unittest.TestCase):
    def test_build_audit_prompt(self):
        ctx = {
            "short_name": "Vietcombank",
            "total_loans": 1400000000000000,
            "total_deposits": 1500000000000000,
            "npl_ratio": 0.012,
            "llr_ratio": 2.1,
            "car_ratio": 0.115,
            "roe": 0.18,
            "cir": 0.32
        }
        prompt = build_audit_prompt("VCB", "2026Q3", ctx)
        self.assertIn("VCB", prompt)
        self.assertIn("Vietcombank", prompt)
        self.assertIn("2026Q3", prompt)
        self.assertIn("JSON", prompt)

    def test_get_financial_statement_notes_from_warehouse(self):
        # Kiểm tra truy vấn Thuyết minh BCTC đã được ETL vào DWH
        for ticker in ["VCB", "BID", "CTG", "MBB", "TCB"]:
            notes = get_financial_statement_notes(ticker)
            self.assertIsNotNone(notes, f"Thuyết minh BCTC cho {ticker} phải tồn tại trong DWH")
            self.assertEqual(notes.get("ticker"), ticker)
            self.assertIn("auditor_opinion", notes)
            self.assertIsInstance(notes.get("key_strengths"), list)
            self.assertIsInstance(notes.get("red_flags"), list)
            self.assertIsInstance(notes.get("structured_notes"), dict)


if __name__ == "__main__":
    unittest.main()
