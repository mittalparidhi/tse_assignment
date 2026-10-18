"""Deterministic orchestration graph with bounded feedback loops.

Agent implementations are injected explicitly. This module owns execution
order, feedback control, loop accounting, and trace generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable

from app.schemas import (
    COVERAGE_REPAIR_CAP,
    CRITIQUE_REVISION_CAP,
    ContractValidationError,
    LoopEvent,
    TraceEvent,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


@dataclass(frozen=True)
class CoverageDecision:
    score: float
    accepted: bool
    reason: str
    issue: str = ""
    repairable: bool = False

    def validate(self) -> None:
        _require(
            isinstance(self.score, (int, float))
            and not isinstance(self.score, bool)
            and math.isfinite(self.score)
            and 0.0 <= self.score <= 1.0,
            "Coverage score must be finite and between 0 and 1",
        )
        _require(isinstance(self.accepted, bool), "accepted must be boolean")
        _require(
            isinstance(self.reason, str) and bool(self.reason.strip()),
            "Coverage reason must be non-blank",
        )
        _require(isinstance(self.issue, str), "Coverage issue must be a string")
        _require(isinstance(self.repairable, bool), "repairable must be boolean")
        if not self.accepted:
            _require(bool(self.issue.strip()), "Rejected coverage needs a named issue")


@dataclass(frozen=True)
class RepairProposal:
    """Explicit, caller-approved scan adjustment; never changes the source."""

    context: Any
    action: str
    reason: str
    issue: str

    def validate(self) -> None:
        for name in ("action", "reason", "issue"):
            value = getattr(self, name)
            _require(
                isinstance(value, str) and bool(value.strip()),
                f"RepairProposal.{name} must be non-blank",
            )


@dataclass(frozen=True)
class CritiqueDecision:
    passed: bool
    reason: str
    issue: str = ""

    def validate(self) -> None:
        _require(isinstance(self.passed, bool), "passed must be boolean")
        _require(
            isinstance(self.reason, str) and bool(self.reason.strip()),
            "Critique reason must be non-blank",
        )
        _require(isinstance(self.issue, str), "Critique issue must be a string")
        if not self.passed:
            _require(bool(self.issue.strip()), "Failed critique needs an issue")


@dataclass
class GraphResult:
    plan: Any
    selected_rows: Any
    aggregate: Any
    coverage: CoverageDecision
    anomalies: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    report: Any
    trace: list[TraceEvent]
    loop_events: list[LoopEvent]
    loop_counters: dict[str, int]


def run_execution_graph(
    *,
    request: Any,
    planner: Callable[[Any], Any],
    scanner: Callable[[Any, RepairProposal | None], Any],
    aggregator: Callable[[Any, Any], Any],
    coverage_validator: Callable[[Any, Any], CoverageDecision],
    anomaly_detector: Callable[[Any], list[dict[str, Any]]],
    diagnostic_writer: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    critique_gate: Callable[
        [list[dict[str, Any]], list[dict[str, Any]]], CritiqueDecision
    ],
    reporter: Callable[[dict[str, Any]], Any],
    repair_provider: (
        Callable[[Any, CoverageDecision, int], RepairProposal | None] | None
    ) = None,
    diagnostic_reviser: (
        Callable[
            [list[dict[str, Any]], CritiqueDecision, list[dict[str, Any]]],
            list[dict[str, Any]],
        ]
        | None
    ) = None,
    diagnostic_fallback: (
        Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None
    ) = None,
) -> GraphResult:
    """Execute planner -> scanner -> aggregator -> validator, then analysis.

    The initial scan is not a retry. Only a repair proposal returned by the
    caller-approved repair provider can trigger a coverage retry. Diagnostic
    revisions are separately capped and never modify numeric results.
    Unexpected programming exceptions deliberately propagate.
    """
    trace: list[TraceEvent] = []
    loop_events: list[LoopEvent] = []

    def emit(
        agent: str,
        kind: str,
        msg: str,
        data: dict[str, Any],
        loop: str | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            i=len(trace),
            agent=agent,
            kind=kind,
            loop=loop,
            msg=msg,
            data=data,
        )
        event.validate()
        trace.append(event)
        return event

    plan = planner(request)
    emit(
        "planner",
        "step",
        "Execution plan created",
        {
            "action": "plan",
            "outcome": "ok",
            "reason": "Planner returned an execution plan",
        },
    )

    rows = None
    aggregate_result = None
    coverage = None
    pending_repair: RepairProposal | None = None
    repairs_used = 0
    pending_loop_event: LoopEvent | None = None
    pending_trace_event: TraceEvent | None = None

    # Initial attempt plus at most COVERAGE_REPAIR_CAP actual retries.
    for scan_number in range(COVERAGE_REPAIR_CAP + 1):
        rows = scanner(plan, pending_repair)
        emit(
            "scanner",
            "step",
            "Snapshot scan completed",
            {
                "attempt": scan_number + 1,
                "action": "scan",
                "outcome": "completed",
                "reason": (
                    "Initial scan"
                    if pending_repair is None
                    else pending_repair.reason
                ),
            },
        )

        aggregate_result = aggregator(plan, rows)
        emit(
            "aggregator",
            "step",
            "Monthly aggregation completed",
            {
                "action": "aggregate",
                "outcome": "completed",
                "reason": "Aggregator returned its result",
            },
        )

        coverage = coverage_validator(plan, aggregate_result)
        if not isinstance(coverage, CoverageDecision):
            raise ContractValidationError(
                "Coverage validator must return CoverageDecision"
            )
        coverage.validate()

        # Complete the record for the retry that led to this scan.
        if pending_loop_event is not None and pending_trace_event is not None:
            pending_loop_event.after_coverage = float(coverage.score)
            pending_loop_event.outcome = (
                "accepted" if coverage.accepted else "coverage_still_insufficient"
            )
            pending_loop_event.reason = coverage.reason

            pending_trace_event.data["after_coverage"] = float(coverage.score)
            pending_trace_event.data["outcome"] = pending_loop_event.outcome
            pending_trace_event.data["reason"] = coverage.reason

            pending_loop_event.validate()
            pending_loop_event = None
            pending_trace_event = None

        emit(
            "validator",
            "decision",
            "Coverage decision evaluated",
            {
                "action": "validate_coverage",
                "outcome": "accepted" if coverage.accepted else "not_accepted",
                "reason": coverage.reason,
                "coverage_score": float(coverage.score),
            },
        )

        if coverage.accepted:
            break

        if not coverage.repairable or repair_provider is None:
            emit(
                "validator",
                "decision",
                "Coverage repair stopped",
                {
                    "action": "stop",
                    "outcome": "repair_not_permitted",
                    "reason": (
                        "No permitted repair is available"
                        if not coverage.repairable
                        else "No repair provider was configured"
                    ),
                },
            )
            break

        if repairs_used >= COVERAGE_REPAIR_CAP:
            emit(
                "validator",
                "decision",
                "Coverage repair cap exhausted",
                {
                    "action": "stop",
                    "outcome": "max_attempts_exceeded",
                    "reason": "Coverage retry cap reached",
                    "cap": COVERAGE_REPAIR_CAP,
                },
            )
            break

        next_attempt = repairs_used + 1
        proposal = repair_provider(plan, coverage, next_attempt)

        if proposal is None:
            emit(
                "validator",
                "decision",
                "Coverage repair stopped",
                {
                    "action": "stop",
                    "outcome": "no_permitted_repair",
                    "reason": "Repair provider found no permissible adjustment",
                },
            )
            break

        if not isinstance(proposal, RepairProposal):
            raise ContractValidationError(
                "Repair provider must return RepairProposal or None"
            )
        proposal.validate()
        if not coverage.repairable:
            raise ContractValidationError(
                "Repair requested for a non-repairable coverage result"
            )

        repairs_used += 1
        pending_repair = proposal

        loop_event = LoopEvent(
            loop="coverage_repair",
            attempt=repairs_used,
            issue=coverage.issue,
            action=proposal.action,
            outcome="started",
            reason=proposal.reason,
            before_coverage=float(coverage.score),
        )
        loop_events.append(loop_event)

        loop_trace = emit(
            "validator",
            "loop",
            "Coverage feedback edge executed",
            {
                "attempt": repairs_used,
                "cap": COVERAGE_REPAIR_CAP,
                "issue": coverage.issue,
                "action": proposal.action,
                "outcome": "started",
                "reason": proposal.reason,
                "before_coverage": float(coverage.score),
                "after_coverage": None,
            },
            loop="coverage_repair",
        )
        pending_loop_event = loop_event
        pending_trace_event = loop_trace

    assert coverage is not None

    anomalies = anomaly_detector(aggregate_result)
    if not isinstance(anomalies, list):
        raise ContractValidationError("Anomaly detector must return a list")
    _require(
        all(isinstance(flag, dict) for flag in anomalies),
        "Each anomaly flag must be an object",
    )

    emit(
        "anomaly",
        "step",
        "Anomaly analysis completed",
        {
            "action": "detect_anomalies",
            "outcome": "completed",
            "reason": "Anomaly detector returned ordered flags",
            "flag_count": len(anomalies),
        },
    )

    diagnostics: list[dict[str, Any]] = []
    revision_events = 0

    # No flags means no writer or critique invocation.
    if anomalies:
        diagnostics = diagnostic_writer(anomalies)
        _require(isinstance(diagnostics, list), "Diagnostic writer must return a list")
        emit(
            "diagnostic",
            "step",
            "Initial diagnostic draft completed",
            {
                "action": "draft_diagnostics",
                "outcome": "completed",
                "reason": "Initial diagnostic draft returned",
                "diagnostic_count": len(diagnostics),
            },
        )

        critique = critique_gate(diagnostics, anomalies)
        if not isinstance(critique, CritiqueDecision):
            raise ContractValidationError(
                "Critique gate must return CritiqueDecision"
            )
        critique.validate()

        if not critique.passed and diagnostic_reviser is not None:
            for attempt in range(1, CRITIQUE_REVISION_CAP + 1):
                previous_issue = critique.issue
                diagnostics = diagnostic_reviser(
                    diagnostics, critique, anomalies
                )
                _require(
                    isinstance(diagnostics, list),
                    "Diagnostic reviser must return a list",
                )

                updated_critique = critique_gate(diagnostics, anomalies)
                if not isinstance(updated_critique, CritiqueDecision):
                    raise ContractValidationError(
                        "Critique gate must return CritiqueDecision"
                    )
                updated_critique.validate()

                revision_events += 1
                outcome = (
                    "accepted"
                    if updated_critique.passed
                    else "revision_still_required"
                )
                loop_event = LoopEvent(
                    loop="critique_revision",
                    attempt=attempt,
                    issue=previous_issue,
                    action="revise_diagnostics",
                    outcome=outcome,
                    reason=updated_critique.reason,
                )
                loop_events.append(loop_event)

                emit(
                    "diagnostic",
                    "loop",
                    "Diagnostic critique/revision executed",
                    {
                        "attempt": attempt,
                        "cap": CRITIQUE_REVISION_CAP,
                        "issue": previous_issue,
                        "action": "revise_diagnostics",
                        "outcome": outcome,
                        "reason": updated_critique.reason,
                    },
                    loop="critique_revision",
                )

                critique = updated_critique
                if critique.passed:
                    break

        if not critique.passed:
            if diagnostic_fallback is None:
                raise ContractValidationError(
                    "Critique failed and no deterministic diagnostic fallback exists"
                )
            diagnostics = diagnostic_fallback(anomalies)
            _require(
                isinstance(diagnostics, list),
                "Diagnostic fallback must return a list",
            )
            emit(
                "diagnostic",
                "warning",
                "Deterministic diagnostic fallback used",
                {
                    "action": "fallback",
                    "outcome": "template",
                    "reason": (
                        "Critique did not pass within the configured revision policy"
                    ),
                },
            )

    loop_counters = {
        "coverage_repair": sum(
            event.loop == "coverage_repair" for event in loop_events
        ),
        "critique_revision": sum(
            event.loop == "critique_revision" for event in loop_events
        ),
    }

    for name, cap in (
        ("coverage_repair", COVERAGE_REPAIR_CAP),
        ("critique_revision", CRITIQUE_REVISION_CAP),
    ):
        _require(
            loop_counters[name] <= cap,
            f"{name} loop exceeded its configured cap",
        )

    for event in trace:
        event.validate()

    trace_counts = {
        name: sum(
            event.kind == "loop" and event.loop == name for event in trace
        )
        for name in loop_counters
    }
    _require(
        trace_counts == loop_counters,
        "Loop counters do not match loop trace events",
    )

    status = "ok" if coverage.accepted else "partial"
    coverage_decision = (
        "accept"
        if coverage.accepted
        else "partial"
        if coverage.score > 0
        else "fail"
    )

    # Log reporter entry before assembling the payload, so the final trace
    # contains a visible report-assembly event.
    emit(
        "reporter",
        "step",
        "Final report assembly started",
        {
            "action": "assemble_report",
            "outcome": "started",
            "reason": "Validated outputs and execution trace are ready",
        },
    )

    payload = {
        "plan": plan,
        "selected_rows": rows,
        "aggregate": aggregate_result,
        "coverage": {
            "score": float(coverage.score),
            "accepted": coverage.accepted,
            "decision": coverage_decision,
            "reason": coverage.reason,
        },
        "anomalies": anomalies,
        "diagnostics": diagnostics,
        "status": status,
        "loop_counters": dict(loop_counters),
        "loop_events": [event.to_dict() for event in loop_events],
        "trace": [event.to_dict() for event in trace],
    }

    report = reporter(payload)

    return GraphResult(
        plan=plan,
        selected_rows=rows,
        aggregate=aggregate_result,
        coverage=coverage,
        anomalies=anomalies,
        diagnostics=diagnostics,
        report=report,
        trace=trace,
        loop_events=loop_events,
        loop_counters=loop_counters,
    )
