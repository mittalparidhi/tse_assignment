import unittest

from app.schemas import (
    ContractValidationError,
    CoverageFlag,
    MonthState,
)


class SchemaContractCompletionTests(unittest.TestCase):
    def make_month(self, sqft_count=8):
        return MonthState(
            month="2023-08",
            status="partial_month",
            observed_listing_count=10,
            sale_listing_count=8,
            valid_price_count=7,
            median_min_price_inr=5_000_000.0,
            median_max_price_inr=6_000_000.0,
            coverage_status="partial_month",
            is_partial_month=True,
            metric_status="unverified_metric",
            valid_price_sqft_count=sqft_count,
            median_price_per_sqft_inr=None,
        )

    def test_price_sqft_count_cannot_exceed_sale_count(self):
        month = self.make_month(sqft_count=9)
        with self.assertRaises(ContractValidationError):
            month.validate()

    def test_price_sqft_count_equal_to_sale_count_is_valid(self):
        month = self.make_month(sqft_count=8)
        month.validate()
        result = month.to_dict()
        self.assertEqual(result["valid_price_sqft_count"], 8)
        self.assertIsNone(result["median_price_per_sqft_inr"])
        self.assertEqual(result["valid_price_range_count"], 7)

    def test_coverage_flag_serializes_contract_count_name(self):
        flag = CoverageFlag(
            month="2023-08",
            observed_listing_count=10,
            sale_listing_count=8,
            valid_price_count=7,
            coverage_status="partial_month",
            is_partial_month=True,
            has_observed_listings=True,
            has_valid_prices=True,
        )
        flag.validate()
        result = flag.to_dict()
        self.assertEqual(result["valid_price_range_count"], 7)


if __name__ == "__main__":
    unittest.main()
