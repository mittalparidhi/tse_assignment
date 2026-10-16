# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
import unittest

from app.execution_graph import (
    CoverageDecision,
    CritiqueDecision,
    RepairProposal,
    run_execution_graph,
)
from app.schemas import COVERAGE_REPAIR_CAP, CRITIQUE_REVISION_CAP


class ExecutionGraphTests(unittest.TestCase):

    def execute(
        self,
        coverage_for_scan,
        *,
        flags=None,
        repair_provider=None,
        writer=None,
        critique=None,
        reviser=None,
        fallback=None,
    ):
        state = {"scans": 0, "writer_calls": 0, "critique_calls": 0}

        def scanner(plan, repair):
            state["scans"] += 1
            return {
                "scan_number": state["scans"],
                "repair": repair,
            }

        def aggregator(plan, rows):
            return rows

        def validate_coverage(plan, aggregate):
            return coverage_for_scan(aggregate["scan_number"])

        def detect(aggregate):
            return [] if flags is None else flags

        def write(flags_in):
            state["writer_calls"] += 1
            if writer is not None:
                return writer(flags_in)
            return [
                {"flag_id": flag["flag_id"], "text": "Initial draft"}
                for flag in flags_in
            ]

        def critique_gate(diagnostics, flags_in):
            state["critique_calls"] += 1
            if critique is not None:
                return critique(diagnostics, flags_in)
            return CritiqueDecision(
                passed=True,
                reason="Default test critique passed",
            )

        def fallback_writer(flags_in):
            if fallback is not None:
                return fallback(flags_in)
            return [
                {"flag_id": flag["flag_id"], "text": "Deterministic template"}
                for flag in flags_in
            ]

        result = run_execution_graph(
            request={"mode": "structured"},
            planner=lambda request: {"topology": "consolidated"},
            scanner=scanner,
            aggregator=aggregator,
            coverage_validator=validate_coverage,
            repair_provider=repair_provider,
            anomaly_detector=detect,
            diagnostic_writer=write,
            critique_gate=critique_gate,
            diagnostic_reviser=reviser,
            diagnostic_fallback=fallback_writer,
            reporter=lambda payload: payload,
        )
        return result, state

    @staticmethod
    def passing_coverage(scan_number):
        return CoverageDecision(
            score=1.0,
            accepted=True,
            reason="Coverage accepted",
        )

    def test_no_retry_when_coverage_passes(self):
        result, state = self.execute(self.passing_coverage)
        self.assertEqual(state["scans"], 1)
        self.assertEqual(result.loop_counters["coverage_repair"], 0)
        self.assertEqual(result.loop_counters["critique_revision"], 0)

    def test_coverage_feedback_edge_executes_in_controlled_fixture(self):
        def coverage(scan_number):
            if scan_number == 1:
                return CoverageDecision(
                    score=0.4,
                    accepted=False,
                    issue="controlled coverage gap",
                    reason="Test fixture requests a retry",
                    repairable=True,
                )
            return CoverageDecision(
                score=1.0,
                accepted=True,
                reason="Coverage passes after controlled retry",
            )

        def repair(plan, decision, attempt):
            return RepairProposal(
                context={"fixture_attempt": attempt},
                action="retry_controlled_scan",
                reason="Explicit test-only repair",
                issue=decision.issue,
            )

        result, state = self.execute(
            coverage,
            repair_provider=repair,
        )

        self.assertEqual(state["scans"], 2)
        self.assertEqual(result.loop_counters["coverage_repair"], 1)
        self.assertEqual(
            result.loop_events[0].loop,
            "coverage_repair",
        )
        self.assertEqual(result.loop_events[0].before_coverage, 0.4)
        self.assertEqual(result.loop_events[0].after_coverage, 1.0)

    def test_coverage_retries_stop_at_cap(self):
        def failing_coverage(scan_number):
            return CoverageDecision(
                score=0.2,
                accepted=False,
                issue="controlled persistent gap",
                reason="Test fixture keeps coverage below threshold",
                repairable=True,
            )

        def repair(plan, decision, attempt):
            return RepairProposal(
                context={"attempt": attempt},
                action="retry_controlled_scan",
                reason="Test-only repair proposal",
                issue=decision.issue,
            )

        result, state = self.execute(
            failing_coverage,
            repair_provider=repair,
        )

        self.assertEqual(state["scans"], 1 + COVERAGE_REPAIR_CAP)
        self.assertEqual(
            result.loop_counters["coverage_repair"],
            COVERAGE_REPAIR_CAP,
        )
        self.assertFalse(result.coverage.accepted)
        self.assertEqual(result.report["status"], "partial")

    def test_coverage_does_not_retry_without_permitted_repair(self):
        def rejected_coverage(scan_number):
            return CoverageDecision(
                score=0.2,
                accepted=False,
                issue="controlled gap",
                reason="No configured soft-filter repair is allowed",
                repairable=False,
            )

        result, state = self.execute(rejected_coverage)

        self.assertEqual(state["scans"], 1)
        self.assertEqual(result.loop_counters["coverage_repair"], 0)

    def test_critique_feedback_edge_can_pass_after_one_revision(self):
        flags = [{"flag_id": "AN-TEST"}]

        def gate(diagnostics, flags_in):
            passed = diagnostics[0]["text"] == "Revised with caveat"
            return CritiqueDecision(
                passed=passed,
                issue="" if passed else "missing_caveat",
                reason="Pass" if passed else "Required caveat is missing",
            )

        def revise(diagnostics, critique, flags_in):
            return [
                {"flag_id": diagnostics[0]["flag_id"], "text": "Revised with caveat"}
            ]

        result, state = self.execute(
            self.passing_coverage,
            flags=flags,
            critique=gate,
            reviser=revise,
        )

        self.assertEqual(result.loop_counters["critique_revision"], 1)
        self.assertEqual(result.diagnostics[0]["text"], "Revised with caveat")
        self.assertEqual(
            state["writer_calls"],
            1,
        )

    def test_critique_revisions_stop_at_cap_then_use_fallback(self):
        flags = [{"flag_id": "AN-TEST"}]

        def failing_gate(diagnostics, flags_in):
            return CritiqueDecision(
                passed=False,
                issue="needs_caveat",
                reason="Controlled test critique remains unsatisfied",
            )

        def no_improvement(diagnostics, critique, flags_in):
            return diagnostics

        result, state = self.execute(
            self.passing_coverage,
            flags=flags,
            critique=failing_gate,
            reviser=no_improvement,
        )

        self.assertEqual(
            result.loop_counters["critique_revision"],
            CRITIQUE_REVISION_CAP,
        )
        self.assertEqual(
            result.diagnostics[0]["text"],
            "Deterministic template",
        )

    def test_no_flags_skip_diagnostic_writer_and_critique(self):
        result, state = self.execute(self.passing_coverage, flags=[])

        self.assertEqual(result.anomalies, [])
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(state["writer_calls"], 0)
        self.assertEqual(state["critique_calls"], 0)
        self.assertEqual(result.loop_counters["critique_revision"], 0)

    def test_trace_loop_event_counts_match_counters(self):
        def failing_coverage(scan_number):
            return CoverageDecision(
                score=0.1,
                accepted=False,
                issue="controlled gap",
                reason="Controlled fixture",
                repairable=True,
            )

        result, _ = self.execute(
            failing_coverage,
            repair_provider=lambda plan, decision, attempt: RepairProposal(
                context={"attempt": attempt},
                action="retry_controlled_scan",
                reason="Test fixture only",
                issue=decision.issue,
            ),
        )

        for loop_name, counter in result.loop_counters.items():
            matching = sum(
                event.kind == "loop" and event.loop == loop_name
                for event in result.trace
            )
            self.assertEqual(matching, counter)


if __name__ == "__main__":
    unittest.main(verbosity=2)
