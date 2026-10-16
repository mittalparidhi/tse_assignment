# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
import unittest

from app.schemas import (
    AnalysisReport,
    ContractValidationError,
    EXPECTED_MONTHS,
    FilterRelaxationEvent,
    LoopEvent,
    MonthState,
    MonthlyReportRecord,
    TraceEvent,
)


def make_month(month):
    is_august = month == "2023-08"
    return MonthState(
        month=month,
        status="partial_month" if is_august else "ok",
        observed_listing_count=10,
        sale_listing_count=8,
        valid_price_count=7,
        median_min_price_inr=5_000_000.0,
        median_max_price_inr=6_000_000.0,
        coverage_status="partial_month" if is_august else "observed",
        is_partial_month=is_august,
        metric_status="unverified_metric",
        valid_price_sqft_count=0,
        median_price_per_sqft_inr=None,
    )


class TypedReportSchemaTests(unittest.TestCase):

    def make_report(self):
        return AnalysisReport(
            run_id="test-run",
            months=[
                MonthlyReportRecord(state=make_month(month))
                for month in EXPECTED_MONTHS
            ],
        )

    def test_report_has_exactly_twelve_ordered_months(self):
        report = self.make_report()
        report.validate()
        self.assertEqual(
            [item.state.month for item in report.months],
            EXPECTED_MONTHS,
        )

    def test_monthly_report_uses_contract_count_names(self):
        result = MonthlyReportRecord(
            state=make_month("2023-08")
        ).to_dict()
        self.assertEqual(result["valid_price_range_count"], 7)
        self.assertEqual(result["valid_price_sqft_count"], 0)
        self.assertIsNone(result["median_price_per_sqft_inr"])
        self.assertEqual(result["coverage_status"], "partial_month")

    def test_report_rejects_missing_month(self):
        report = self.make_report()
        report.months.pop()
        with self.assertRaises(ContractValidationError):
            report.validate()

    def test_trace_indices_must_be_consecutive(self):
        report = self.make_report()
        report.trace = [
            TraceEvent(
                i=1,
                agent="planner",
                kind="message",
                msg="Planning completed",
            )
        ]
        with self.assertRaises(ContractValidationError):
            report.validate()

    def test_loop_counters_must_match_events(self):
        report = self.make_report()
        report.loop_events = [
            LoopEvent(
                loop="coverage_repair",
                attempt=1,
                issue="Coverage gap",
                action="Retry scan",
                outcome="completed",
                reason="Coverage check requested another scan",
                before_coverage=0.8,
                after_coverage=0.9,
            )
        ]
        with self.assertRaises(ContractValidationError):
            report.validate()

    def test_matching_loop_counter_is_valid(self):
        report = self.make_report()
        report.loop_events = [
            LoopEvent(
                loop="coverage_repair",
                attempt=1,
                issue="Coverage gap",
                action="Retry scan",
                outcome="completed",
                reason="Coverage check requested another scan",
                before_coverage=0.8,
                after_coverage=0.9,
            )
        ]
        report.loop_counters["coverage_repair"] = 1
        report.validate()

    def test_filter_relaxation_is_rejected_under_contract_v1(self):
        report = self.make_report()
        report.filter_relaxation_history = [
            FilterRelaxationEvent(
                attempt=1,
                filter_name="locality",
                before="A",
                after="B",
                reason="Illustrative test",
                action="relax",
                outcome="applied",
            )
        ]
        with self.assertRaises(ContractValidationError):
            report.validate()


    def test_public_report_has_required_metadata_and_exact_record_fields(self):
        report = self.make_report()
        payload = report.to_dict()

        required_metadata = {
            "contract_version", "snapshot_sha256", "run_id",
            "window_start", "window_end", "timezone", "seed",
            "llm_mode", "logic_version", "coverage_score", "topology",
            "loop_counters", "trace", "data_quality", "status",
        }
        self.assertTrue(required_metadata.issubset(payload))
        self.assertEqual(len(payload["records"]), 12)

        expected_month_fields = {
            "month", "observed_listing_count", "sale_listing_count",
            "valid_price_range_count", "median_min_price_inr",
            "median_max_price_inr", "valid_price_sqft_count",
            "median_price_per_sqft_inr", "coverage_status", "metric_status",
        }
        self.assertEqual(set(payload["records"][0]), expected_month_fields)

    def test_runtime_state_converts_to_typed_report(self):
        from app.schemas import (
            AnalysisRequest, CoverageFlag, RuntimeState, RunPlan,
            RetryCounters, SourcePeriod,
        )

        months = [make_month(month) for month in EXPECTED_MONTHS]
        flags = [
            CoverageFlag(
                month=month.month,
                observed_listing_count=month.observed_listing_count,
                sale_listing_count=month.sale_listing_count,
                valid_price_count=month.valid_price_count,
                coverage_status=month.coverage_status,
                is_partial_month=month.is_partial_month,
                has_observed_listings=True,
                has_valid_prices=True,
            )
            for month in months
        ]
        request = AnalysisRequest()
        plan = RunPlan(
            source_period=SourcePeriod(),
            requested_filters=request.requested_filters,
            effective_filters=request.requested_filters,
        )
        runtime = RuntimeState(
            run_id="integration-test",
            request=request,
            plan=plan,
            retries=RetryCounters(),
            coverage_flags=flags,
            months=months,
            trace=[
                {
                    "i": 0,
                    "agent": "planner",
                    "kind": "step",
                    "loop": None,
                    "msg": "Test planning step",
                    "data": {},
                }
            ],
            source_sha256="9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a",
        )
        report = runtime.to_analysis_report(
            data_quality={"raw_rows": 100},
            coverage_score=1.0,
            status="ok",
            coverage_decision="accept",
        )
        result = report.to_dict()
        self.assertEqual(result["run_id"], "integration-test")
        self.assertEqual(len(result["records"]), 12)
        self.assertEqual(result["trace"][0]["agent"], "planner")
        self.assertEqual(result["data_quality"]["raw_rows"], 100)



if __name__ == "__main__":
    unittest.main(verbosity=2)
