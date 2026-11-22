"""
TESTS: Kiểm thử tích hợp các trạm kiểm soát chất lượng (DQ1, DQ2, DQ3) và SQL Serving Loader
"""

import unittest
import pandas as pd
from datetime import datetime

from stock_analysis.governance.gateways import (
    validate_dq1,
    validate_dq2,
    validate_dq3,
    validate_dq1_market_candlestick,
    validate_dq1_financials_raw,
    validate_dq2_accounting_identity,
    validate_dq2_silver_grain,
    validate_dq3_gold_metrics,
)
from stock_analysis.sql_serving_loader.publish_to_postgres import get_connection


class TestQualityGateways(unittest.TestCase):

    def test_dq1_candlestick_validation(self):
        """Kiểm tra DQ1: Phát hiện nến sai (High < Low) và lọc rác."""
        df_test = pd.DataFrame([
            {"ticker": "VCB", "time": "2024-01-02", "open": 80.0, "high": 85.0, "low": 79.0, "close": 82.0, "volume": 1000}, # Hợp lệ
            {"ticker": "VCB", "time": "2024-01-03", "open": 80.0, "high": 75.0, "low": 85.0, "close": 82.0, "volume": 1000}, # High < Low (Sai)
            {"ticker": "VCB", "time": "2024-01-04", "open": -10.0, "high": 85.0, "low": 79.0, "close": 82.0, "volume": 1000}, # Open âm (Sai)
        ])
        valid, quarantined, metrics = validate_dq1_market_candlestick(df_test, quarantine=False)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(quarantined), 2)
        self.assertFalse(metrics["is_passed"])
        self.assertEqual(valid.iloc[0]["time"], pd.to_datetime("2024-01-02"))

    def test_dq2_accounting_identity(self):
        """Kiểm tra DQ2: Phát hiện sai lệch cân đối kế toán (Tài sản != Nợ + Vốn CSH)."""
        df_test = pd.DataFrame([
            {"ticker": "CTG", "fiscal_year": 2024, "fiscal_quarter": 1, "total_assets": 100.0, "total_liabilities": 90.0, "owners_equity": 10.0}, # Cân bằng (100 = 90 + 10)
            {"ticker": "CTG", "fiscal_year": 2024, "fiscal_quarter": 2, "total_assets": 100.0, "total_liabilities": 50.0, "owners_equity": 10.0}, # Lệch nặng (100 != 60)
        ])
        valid, quarantined, metrics = validate_dq2_accounting_identity(df_test, quarantine=False)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(valid.iloc[0]["fiscal_quarter"], 1)
        self.assertEqual(quarantined.iloc[0]["fiscal_quarter"], 2)

    def test_dq3_gold_metrics_bounds(self):
        """Kiểm tra DQ3: Phát hiện điểm CAMELS vượt ngưỡng [0, 100]."""
        df_valid = pd.DataFrame([
            {"ticker": "TCB", "camels_composite_score": 85.5, "pb_ratio": 1.2, "npl_ratio_pct": 1.5}
        ])
        passed, metrics = validate_dq3_gold_metrics(df_valid)
        self.assertTrue(passed)

        df_invalid = pd.DataFrame([
            {"ticker": "TCB", "camels_composite_score": 150.0, "pb_ratio": 25.0, "npl_ratio_pct": -5.0}
        ])
        passed, metrics = validate_dq3_gold_metrics(df_invalid)
        self.assertFalse(passed)
        self.assertGreater(len(metrics["anomalies"]), 0)

    def test_sql_serving_loader_connection(self):
        """Kiểm tra kết nối PostgreSQL qua sql_serving_loader."""
        conn = get_connection()
        self.assertIsNotNone(conn)
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()


    def test_dq_central_dispatchers(self):
        """Kiểm tra Bộ điều phối trung tâm DQ1, DQ2, DQ3 (Facade / Dispatcher Pattern)."""
        # 1. DQ1 Dispatcher tự động nhận diện nến
        df_candle = pd.DataFrame([
            {"ticker": "ACB", "time": "2024-01-02", "open": 25.0, "high": 26.0, "low": 24.5, "close": 25.5, "volume": 5000}
        ])
        valid_c, _, m_c = validate_dq1(df_candle, quarantine=False)
        self.assertEqual(len(valid_c), 1)
        self.assertEqual(m_c["rule_code"], "DQ1_OHLCV_CANDLESTICK")

        # 2. DQ1 Dispatcher tự động nhận diện BCTC thô
        df_fin = pd.DataFrame([
            {"ticker": "MBB", "fiscal_year": 2024, "fiscal_quarter": 1, "item_code": "ASSET", "value": 100.0}
        ])
        valid_f, _, m_f = validate_dq1(df_fin, quarantine=False)
        self.assertEqual(len(valid_f), 1)
        self.assertEqual(m_f["rule_code"], "DQ1_FINANCIALS_SCHEMA_COMPLETENESS")

        # 3. DQ2 Dispatcher đối soát cân đối kế toán
        df_bal = pd.DataFrame([
            {"ticker": "BID", "fiscal_year": 2024, "fiscal_quarter": 1, "total_assets": 200.0, "total_liabilities": 180.0, "owners_equity": 20.0}
        ])
        valid_b, _, m_b = validate_dq2(df_bal, quarantine=False)
        self.assertEqual(len(valid_b), 1)
        self.assertTrue(m_b["is_passed"])

        # 4. DQ3 Dispatcher kiểm định ngưỡng CAMELS
        df_cam = pd.DataFrame([
            {"ticker": "VPB", "camels_composite_score": 78.0, "pb_ratio": 1.1, "npl_ratio_pct": 2.1}
        ])
        passed_3, m_3 = validate_dq3(df_cam)
        self.assertTrue(passed_3)


if __name__ == "__main__":
    unittest.main()
