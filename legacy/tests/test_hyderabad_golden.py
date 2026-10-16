# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "audit" / "runtime_state.json"

EXPECTED = [
    ("2022-09", 35, 33, 33, 5800000.0, 5800000.0, "observed"),
    ("2022-10", 51, 43, 43, 7700000.0, 7700000.0, "observed"),
    ("2022-11", 41, 35, 34, 5249750.0, 5249750.0, "observed"),
    ("2022-12", 46, 42, 42, 6351485.0, 6351485.0, "observed"),
    ("2023-01", 32, 30, 30, 13500000.0, 13500000.0, "observed"),
    ("2023-02", 45, 38, 38, 9150000.0, 9150000.0, "observed"),
    ("2023-03", 217, 169, 169, 6500000.0, 6600000.0, "observed"),
    ("2023-04", 288, 270, 269, 10200003.0, 10509000.0, "observed"),
    ("2023-05", 482, 437, 430, 10488800.0, 10806000.0, "observed"),
    ("2023-06", 947, 817, 801, 10000000.0, 10623200.0, "observed"),
    ("2023-07", 3447, 2808, 2775, 9261000.0, 9400000.0, "observed"),
    ("2023-08", 3531, 2911, 2884, 9476000.0, 9800000.0, "partial_month"),
]


class HyderabadGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not REPORT.is_file():
            raise FileNotFoundError(
                f"{REPORT} does not exist. Run scripts/build_runtime_state.py first."
            )
        cls.data = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_twelve_months_match_golden_vector(self):
        records = self.data["records"]
        self.assertEqual(len(records), 12)

        for actual, expected in zip(records, EXPECTED):
            month, observed, sales, valid, median_min, median_max, status = expected

            with self.subTest(month=month):
                self.assertEqual(actual["month"], month)
                self.assertEqual(actual["observed_listing_count"], observed)
                self.assertEqual(actual["sale_listing_count"], sales)
                self.assertEqual(actual["valid_price_range_count"], valid)
                self.assertAlmostEqual(
                    actual["median_min_price_inr"], median_min, delta=0.01
                )
                self.assertAlmostEqual(
                    actual["median_max_price_inr"], median_max, delta=0.01
                )
                self.assertEqual(actual["coverage_status"], status)

    def test_aggregate_counts_reconcile(self):
        records = self.data["records"]
        quality = self.data["data_quality"]

        self.assertEqual(
            sum(r["observed_listing_count"] for r in records), 9162
        )
        self.assertEqual(
            sum(r["sale_listing_count"] for r in records), 7633
        )
        self.assertEqual(
            sum(r["valid_price_range_count"] for r in records), 7548
        )
        self.assertEqual(quality["raw_rows"], 9487)
        self.assertEqual(quality["valid_posting_dates"], 9245)
        self.assertEqual(quality["valid_dated_rows_outside_window"], 83)
        self.assertEqual(
            quality["missing_or_invalid_posting_dates"], 242
        )

    def test_price_per_sqft_remains_unverified(self):
        for record in self.data["records"]:
            self.assertIsNone(record["median_price_per_sqft_inr"])

    def test_coverage_is_complete_and_august_is_partial(self):
        self.assertEqual(self.data["coverage_score"], 1.0)
        self.assertEqual(self.data["coverage_decision"], "accept")
        self.assertEqual(self.data["status"], "ok")
        self.assertEqual(
            self.data["records"][-1]["coverage_status"], "partial_month"
        )


if __name__ == "__main__":
    unittest.main()
