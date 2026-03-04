"""Unit tests for pure calculation functions."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MSFI_APP_DIR = PROJECT_ROOT / "msfi_app"
if str(MSFI_APP_DIR) not in sys.path:
    sys.path.insert(0, str(MSFI_APP_DIR))

from calculations import (
    calculate_buffer_values,
    calculate_income_metrics,
    calculate_risk_status,
    calculate_weighted_return,
    normalize_return_percent_input,
)


class CalculationTests(unittest.TestCase):
    def test_normalize_return_percent_input(self):
        self.assertEqual(normalize_return_percent_input(6.5), 0.065)

    def test_calculate_weighted_return(self):
        total_value = 1000.0
        rows = [
            {"strategy_value": 600.0, "return_used": 0.08},
            {"strategy_value": 400.0, "return_used": 0.04},
        ]
        self.assertEqual(calculate_weighted_return(total_value, rows), 0.064)

    def test_income_metrics_rounding(self):
        metrics = calculate_income_metrics(total_value=1_000_000.0, weighted_return=0.0625)
        self.assertEqual(metrics["annual_earnings"], 62500.00)
        self.assertEqual(metrics["msfi"], 2403.85)

    def test_buffer_values_use_snapshot_percents(self):
        buffers = calculate_buffer_values(msfi=2000.0, buffer_1_percent=0.10, buffer_2_percent=0.20)
        self.assertEqual(buffers["buffer_1_value"], 1800.0)
        self.assertEqual(buffers["buffer_2_value"], 1600.0)

    def test_risk_status_safe(self):
        risk = calculate_risk_status(msfi=2000.0, actual_income=1500.0, buffer_1_value=1800.0, buffer_2_value=1600.0)
        self.assertEqual(risk, "Safe")

    def test_risk_status_alert(self):
        risk = calculate_risk_status(msfi=2000.0, actual_income=1850.0, buffer_1_value=1800.0, buffer_2_value=1600.0)
        self.assertEqual(risk, "Alert")

    def test_risk_status_caution(self):
        risk = calculate_risk_status(msfi=2000.0, actual_income=1700.0, buffer_1_value=1800.0, buffer_2_value=1600.0)
        self.assertEqual(risk, "Caution")

    def test_risk_status_equal_msfi_is_alert(self):
        risk = calculate_risk_status(msfi=2000.0, actual_income=2000.0, buffer_1_value=1800.0, buffer_2_value=1600.0)
        self.assertEqual(risk, "Alert")

    def test_risk_status_overdrawing(self):
        risk = calculate_risk_status(msfi=2000.0, actual_income=2100.0, buffer_1_value=1800.0, buffer_2_value=1600.0)
        self.assertEqual(risk, "Overdrawing")


if __name__ == "__main__":
    unittest.main()
