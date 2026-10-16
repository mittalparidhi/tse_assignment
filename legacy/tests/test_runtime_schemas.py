# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.

import unittest

from app.schemas import (
    AnalysisFilters,
    AnalysisRequest,
    ContractValidationError,
    CoverageFlag,
    EXPECTED_MONTHS,
    MonthState,
    RetryCounters,
    SourcePeriod,
    build_runtime_state,
)


class RuntimeSchemaTests(unittest.TestCase):

    def test_source_period_has_exactly_12_months(self):
        period = SourcePeriod()
        self.assertEqual(len(period.months), 12)
        self.assertEqual(period.months[0], "2022-09")
        self.assertEqual(period.months[-1], "2023-08")
        self.assertEqual(period.timezone, "Asia/Kolkata")

    def test_wrong_source_period_is_rejected(self):
        with self.assertRaises(ContractValidationError):
            SourcePeriod(start_month="2022-10")

    def test_default_request_is_valid(self):
        request = AnalysisRequest()
        request.validate()
        self.assertEqual(request.query_mode, "structured")

    def test_natural_language_mode_is_rejected_until_parser_exists(self):
        request = AnalysisRequest(query_mode="natural_language")
        with self.assertRaises(ContractValidationError):
            request.validate()

    def test_inverted_price_range_is_rejected(self):
        filters = AnalysisFilters(
            min_price_inr=5_000_000,
            max_price_inr=1_000_000,
        )
        with self.assertRaises(ContractValidationError):
            filters.validate(allow_unsupported=True)

    def test_unsupported_locality_filter_is_rejected(self):
        filters = AnalysisFilters(locality=["Gachibowli"])
        with self.assertRaises(ContractValidationError):
            filters.validate()

    def test_retry_caps_are_enforced(self):
        RetryCounters(
            coverage_repair_retries=3,
            critique_revisions=2,
            llm_retries_by_purpose={"planning": 2},
        ).validate()

        with self.assertRaises(ContractValidationError):
            RetryCounters(coverage_repair_retries=4).validate()

        with self.assertRaises(ContractValidationError):
            RetryCounters(critique_revisions=3).validate()

        with self.assertRaises(ContractValidationError):
            RetryCounters(
                llm_retries_by_purpose={"planning": 3}
            ).validate()

    def test_empty_month_has_null_medians(self):
        month = MonthState(
            month="2022-09",
            status="no_listings",
            observed_listing_count=0,
            sale_listing_count=0,
            valid_price_count=0,
            median_min_price_inr=None,
            median_max_price_inr=None,
            coverage_status="no_listings",
        )
        month.validate()

    def test_empty_month_cannot_have_zero_medians(self):
        month = MonthState(
            month="2022-09",
            status="no_listings",
            observed_listing_count=0,
            sale_listing_count=0,
            valid_price_count=0,
            median_min_price_inr=0,
            median_max_price_inr=0,
            coverage_status="no_listings",
        )
        with self.assertRaises(ContractValidationError):
            month.validate()

    def test_month_counts_must_be_coherent(self):
        month = MonthState(
            month="2022-09",
            status="no_listings",
            observed_listing_count=0,
            sale_listing_count=1,
            valid_price_count=0,
            coverage_status="no_listings",
        )
        with self.assertRaises(ContractValidationError):
            month.validate()

    def test_coverage_flags_must_match_counts(self):
        flag = CoverageFlag(
            month="2022-09",
            observed_listing_count=0,
            sale_listing_count=0,
            valid_price_count=0,
            coverage_status="no_listings",
            has_observed_listings=False,
            has_valid_prices=False,
        )
        flag.validate()

        invalid_flag = CoverageFlag(
            month="2022-09",
            observed_listing_count=0,
            sale_listing_count=0,
            valid_price_count=0,
            coverage_status="ok",
            has_observed_listings=True,
            has_valid_prices=False,
        )
        with self.assertRaises(ContractValidationError):
            invalid_flag.validate()

    def test_runtime_state_starts_valid(self):
        state = build_runtime_state(run_id="test-run-001")
        state.validate()
        self.assertEqual(state.plan.source_period.months, tuple(EXPECTED_MONTHS))
        self.assertEqual(state.retries.coverage_repair_retries, 0)
        self.assertEqual(state.coverage_flags, [])
        self.assertEqual(state.months, [])

    def test_runtime_fingerprint_is_deterministic(self):
        first = build_runtime_state(run_id="run-A")
        second = build_runtime_state(run_id="run-B")
        self.assertEqual(first.fingerprint(), second.fingerprint())




    def test_city_filter_is_rejected(self):
        filters = AnalysisFilters(city=["Hyderabad"])
        with self.assertRaises(ContractValidationError):
            filters.validate()

    def test_requested_and_effective_filters_must_match(self):
        from app.schemas import RunPlan

        plan = RunPlan(
            requested_filters=AnalysisFilters(),
            effective_filters=AnalysisFilters(city=["Hyderabad"]),
        )
        with self.assertRaises(ContractValidationError):
            plan.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
