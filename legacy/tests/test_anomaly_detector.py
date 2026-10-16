# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.

import json
import unittest
from pathlib import Path

from app.anomaly_detector import detect_anomalies

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "audit" / "runtime_state.json"


class AnomalyDetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.records = cls.data["records"]
        cls.flags = detect_anomalies(cls.records)

    def test_expected_total_flag_count(self):
        self.assertEqual(len(self.flags), 17)

    def test_expected_counts_by_rule(self):
        counts = {
            rule: sum(flag["rule_id"] == rule for flag in self.flags)
            for rule in ("AN-01", "AN-02", "AN-03", "AN-04")
        }
        self.assertEqual(
            counts,
            {"AN-01": 14, "AN-02": 0, "AN-03": 2, "AN-04": 1},
        )

    def test_price_flags_use_only_verified_price_bounds(self):
        price_flags = [
            flag for flag in self.flags if flag["rule_id"] == "AN-01"
        ]
        self.assertTrue(
            all(
                flag["metric"]
                in ("median_min_price_inr", "median_max_price_inr")
                for flag in price_flags
            )
        )
        self.assertTrue(
            all(abs(flag["change_fraction"]) > 0.12 for flag in price_flags)
        )

    def test_count_spikes_are_march_and_july(self):
        spike_months = [
            flag["month"] for flag in self.flags
            if flag["rule_id"] == "AN-03"
        ]
        self.assertEqual(spike_months, ["2023-03", "2023-07"])

    def test_concentration_uses_final_two_months(self):
        flags = [flag for flag in self.flags if flag["rule_id"] == "AN-04"]
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["window_start"], "2023-07")
        self.assertEqual(flags[0]["window_end"], "2023-08")
        self.assertGreaterEqual(flags[0]["fraction"], 0.70)

    def test_output_is_deterministic(self):
        self.assertEqual(self.flags, detect_anomalies(self.records))

    def test_unsorted_months_are_rejected(self):
        with self.assertRaises(ValueError):
            detect_anomalies(list(reversed(self.records)))


if __name__ == "__main__":
    unittest.main()
