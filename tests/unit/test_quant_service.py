"""
UNIT TESTS: Kiểm thử chuyên sâu cho Headless Quant Service (Quant Core V2)
Bao gồm:
  - valuation_residual_engine (OLS đa biến & Residual Z-Score)
  - event_study_engine (Event Study CAR & FDR Benjamini-Hochberg)
  - comovement_engine (Ma trận đồng pha Lag 0 liên ngân hàng)
"""

import unittest
import numpy as np

from stock_analysis.quant_service.valuation_residual_engine import (
    get_valuation_residual_data,
    compute_valuation_residual,
)
from stock_analysis.quant_service.event_study_engine import (
    get_audited_event_study_data,
)
from stock_analysis.quant_service.comovement_engine import (
    get_comovement_data,
)


class TestQuantService(unittest.TestCase):

    def test_valuation_residual_engine(self):
        """Kiểm tra mô hình hồi quy phần dư định giá OLS và tính toán Z-Score."""
        data = get_valuation_residual_data()
        self.assertIsInstance(data, dict)
        self.assertIn("model_metadata", data)
        self.assertIn("ranking", data)
        self.assertIn("empirical_spread_validation", data)

        meta = data["model_metadata"]
        # R2 mô hình phải dương và có ý nghĩa
        self.assertGreater(meta["r_squared"], 0.10)
        self.assertGreater(meta["total_observations"], 500)

        # Xếp hạng phải bao phủ đủ 27 ngân hàng
        rankings = data["ranking"]
        self.assertEqual(len(rankings), 27)

        # Kiểm tra tính toàn vẹn của từng bản ghi ngân hàng
        z_scores = []
        for r in rankings:
            self.assertIn("ticker", r)
            self.assertIn("pb_ratio", r)
            self.assertIn("pred_pb", r)
            self.assertIn("residual_zscore", r)
            self.assertIn("valuation_regime", r)
            self.assertIn(r["valuation_regime"], ["UNDERVALUED", "FAIR_VALUED", "OVERVALUED"])
            z_scores.append(r["residual_zscore"])

        # Z-score trung bình trên tập mẫu phải xấp xỉ 0 (|mean| < 0.5)
        mean_z = np.mean(z_scores)
        self.assertLess(abs(mean_z), 0.5)

        # Kiểm tra xác thực spread kinh tế lượng
        spread = data["empirical_spread_validation"]
        self.assertEqual(spread["anchor_days"], 35)
        self.assertAlmostEqual(spread["forward_2q_spread_pct"], 4.55, places=2)
        self.assertAlmostEqual(spread["forward_2q_pvalue"], 0.0931, places=3)

    def test_event_study_engine(self):
        """Kiểm tra mô hình nghiên cứu sự kiện cổ tức và kiểm định đa giả thuyết FDR."""
        data = get_audited_event_study_data()
        self.assertIsInstance(data, dict)
        self.assertIn("metadata", data)
        self.assertIn("windows_summary", data)

        windows = data["windows_summary"]
        self.assertGreater(len(windows), 5)

        # Tìm cửa sổ DDINS CAR[-5, +5]
        ddins_55 = None
        for w in windows:
            if w.get("event_type") == "stock_dividend_announcement" and w.get("window") == "CAR[-5, +5]":
                ddins_55 = w
                break

        self.assertIsNotNone(ddins_55, "Không tìm thấy cửa sổ CAR[-5, +5] của Cổ tức cổ phiếu.")
        # Khóa số liệu chuẩn: CAR = 1.0579% (làm tròn +1.06%)
        self.assertAlmostEqual(ddins_55["mean_car_pct"], 1.0579, places=2)
        self.assertEqual(ddins_55["n_events"], 176)
        self.assertAlmostEqual(ddins_55["p_value_raw"], 0.0287, places=3)
        self.assertAlmostEqual(ddins_55["p_value_fdr_bh"], 0.1148, places=3)
        # Bắt buộc kết luận: Không đạt ý nghĩa thống kê 5% sau FDR
        self.assertFalse(ddins_55["stat_sig_5pct_fdr"])

    def test_comovement_engine(self):
        """Kiểm tra ma trận tương quan đồng thời liên ngân hàng."""
        data = get_comovement_data(days=250)
        self.assertIsInstance(data, dict)
        self.assertIn("metadata", data)
        self.assertIn("correlation_matrix", data)

        meta = data["metadata"]
        corr = data["correlation_matrix"]

        # Đường chéo chính của ma trận tương quan phải bằng 1.0
        for ticker in meta["bank_tickers"]:
            if ticker in corr and ticker in corr[ticker]:
                self.assertAlmostEqual(corr[ticker][ticker], 1.0, places=3)

        # Tương quan đồng pha bình quân phải dương và hợp lý (0.15 - 0.60)
        avg_corr = meta["average_interbank_correlation"]
        self.assertGreaterEqual(avg_corr, 0.15)
        self.assertLessEqual(avg_corr, 0.60)


if __name__ == "__main__":
    unittest.main()
