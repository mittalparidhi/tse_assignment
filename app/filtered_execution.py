"""Run Criteria -> Retrieval -> Aggregation through the existing execution graph.

The default full-snapshot reporting path remains separate. This pipeline executes a
verified filtered request against the same frozen CSV and reports the resulting
12-month POSTING_DATE view, while Retrieval Agent's inclusive filter bounds use
REGISTER_DATE__U as specified by the retrieval contract.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from app.anomaly_detector import detect_anomalies
from app.criteria_agent import CriteriaResult, run_criteria_agent
from app.execution_graph import CritiqueDecision, CoverageDecision, GraphResult, run_execution_graph
from app.retrieval_agent import RetrievalAgent, RetrievalError, RetrievalResult
from app.schemas import EXPECTED_MONTHS, LOCAL_TIMEZONE, WINDOW_END, WINDOW_START

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"
PRICE_SENTINEL = 2147483647
LOGIC_VERSION = "filtered-agent-graph-v1"


@dataclass(frozen=True)
class FilteredRunPlan:
    request: dict[str, Any]
    criteria_result: CriteriaResult
    topology: str = "consolidated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": dict(self.request),
            "criteria_result": self.criteria_result.to_dict(),
            "topology": self.topology,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _aggregate_selected(plan: FilteredRunPlan, retrieved: RetrievalResult) -> dict[str, Any]:
    """Aggregate by the canonical processed posting_month field.

    REGISTER_DATE__U remains a Retrieval Agent filter input only. Reporting
    must not independently reinterpret POSTING_DATE after cleaning.
    """
    del plan
    rows = retrieved.rows.copy()
    required = {
        "POSTING_DATE", "posting_month", "posting_date_status", "source_row_id",
        "PREFERENCE", "MIN_PRICE", "MAX_PRICE", "PRICE_SQFT", "PRICE", "PROP_ID",
    }
    missing = sorted(required - set(rows.columns))
    if missing:
        raise RetrievalError("source_schema_error", f"Filtered aggregation requires columns: {missing}")

    # source_row_id identifies a source row, not a property. A repeated ID at
    # the aggregation boundary indicates duplicate delivery and must not be
    # silently dropped or counted twice.
    source_ids = pd.to_numeric(rows["source_row_id"], errors="coerce")
    if (
        source_ids.isna().any()
        or not np.isfinite(source_ids.to_numpy(dtype=float)).all()
        or not np.equal(source_ids.to_numpy(dtype=float), np.floor(source_ids.to_numpy(dtype=float))).all()
    ):
        raise RetrievalError("invalid_source_row_id", "source_row_id must contain finite integer row identities.")
    source_ids = source_ids.astype("int64")
    if source_ids.duplicated().any():
        duplicates = source_ids.loc[source_ids.duplicated(keep=False)].unique().tolist()[:10]
        raise RetrievalError(
            "duplicate_source_row_id",
            f"Duplicate source_row_id values detected at aggregation: {duplicates}",
        )
    rows["source_row_id"] = source_ids

    # The cleaner is the only component that derives posting_month. Reject an
    # impossible non-null value rather than coercing it into another month.
    month_text = rows["posting_month"].astype("string").fillna("").str.strip()
    month_nonempty = month_text.ne("")
    month_well_formed = month_text.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", na=False)
    impossible_month = month_nonempty & ~month_well_formed
    if impossible_month.any():
        invalid_values = month_text.loc[impossible_month].drop_duplicates().tolist()[:10]
        raise RetrievalError(
            "E_INVALID_MONTH",
            f"Impossible non-null posting_month value(s): {invalid_values}",
        )

    date_status = rows["posting_date_status"].astype("string").fillna("").str.strip()
    valid_date = date_status.eq("valid") & month_well_formed
    rows["_report_month"] = month_text.where(valid_date, pd.NA)
    in_window = valid_date & month_text.isin(EXPECTED_MONTHS)
    report_rows = rows.loc[in_window].copy()
    pref = report_rows["PREFERENCE"].astype("string").str.strip().str.upper()
    report_rows["_is_sale"] = pref.eq("S").fillna(False)
    lo = pd.to_numeric(report_rows["MIN_PRICE"], errors="coerce")
    hi = pd.to_numeric(report_rows["MAX_PRICE"], errors="coerce")
    valid_lo = lo.notna() & np.isfinite(lo) & lo.gt(0) & lo.ne(PRICE_SENTINEL)
    valid_hi = hi.notna() & np.isfinite(hi) & hi.gt(0) & hi.ne(PRICE_SENTINEL)
    report_rows["_min_price_numeric"] = lo
    report_rows["_max_price_numeric"] = hi
    price_text = report_rows["PRICE"].astype("string").fillna("").str.strip()
    report_rows["_price_on_request"] = price_text.str.contains(
        r"\bprice\s+on\s+request\b", case=False, regex=True, na=False
    )
    report_rows["_valid_price_range"] = (
        report_rows["_is_sale"]
        & valid_lo
        & valid_hi
        & lo.le(hi)
        & ~report_rows["_price_on_request"]
    )
    psf = pd.to_numeric(report_rows["PRICE_SQFT"], errors="coerce")
    report_rows["_valid_price_sqft"] = (
        report_rows["_is_sale"] & psf.notna() & np.isfinite(psf) & psf.gt(0)
    )

    monthly_records: list[dict[str, Any]] = []
    for month in EXPECTED_MONTHS:
        month_rows = report_rows.loc[report_rows["_report_month"] == month]
        valid_prices = month_rows.loc[month_rows["_valid_price_range"]]
        observed = int(len(month_rows))
        sales = int(month_rows["_is_sale"].sum())
        valid_count = int(month_rows["_valid_price_range"].sum())
        sqft_count = int(month_rows["_valid_price_sqft"].sum())
        med_min = float(valid_prices["_min_price_numeric"].median()) if valid_count else None
        med_max = float(valid_prices["_max_price_numeric"].median()) if valid_count else None
        partial = month == "2023-08"
        if observed == 0:
            coverage_status, metric_status = "no_listings", "no_listings"
        elif sales == 0:
            coverage_status, metric_status = ("partial_month" if partial else "observed"), "no_sale_listings"
        elif valid_count == 0:
            coverage_status, metric_status = ("partial_month" if partial else "observed"), "no_valid_prices"
        else:
            coverage_status, metric_status = ("partial_month" if partial else "observed"), "unverified_metric"
        monthly_records.append({
            "month": month,
            "observed_listing_count": observed,
            "sale_listing_count": sales,
            "valid_price_range_count": valid_count,
            "valid_price_sqft_count": sqft_count,
            "median_min_price_inr": med_min,
            "median_max_price_inr": med_max,
            "median_price_per_sqft_inr": None,
            "coverage_status": coverage_status,
            "metric_status": metric_status,
        })

    covered_months = sum(
        r["valid_price_range_count"] > 0
        and r["median_min_price_inr"] is not None
        and r["median_max_price_inr"] is not None
        for r in monthly_records
    )
    invalid_posting_date = ~date_status.eq("valid")
    invalid_or_missing_month = ~month_well_formed
    data_quality = {
        "retrieved_row_count": int(retrieved.selected_row_count),
        "invalid_registration_date_rows_in_source": int(retrieved.invalid_registration_date_rows),
        "malformed_location_rows_in_source": int(retrieved.malformed_location_rows),
        "invalid_coordinate_rows_in_source": int(retrieved.invalid_coordinate_rows),
        "rows_with_invalid_posting_date_in_retrieved_subset": int(invalid_posting_date.sum()),
        "rows_with_missing_or_invalid_posting_month_in_retrieved_subset": int(invalid_or_missing_month.sum()),
        "rows_with_valid_date_status_but_missing_month": int((date_status.eq("valid") & ~month_nonempty).sum()),
        "valid_posting_date_rows_outside_reporting_window": int((valid_date & ~month_text.isin(EXPECTED_MONTHS)).sum()),
        "rows_eligible_for_reporting_window": int(len(report_rows)),
        "reporting_sale_rows": int(report_rows["_is_sale"].sum()),
        "reporting_valid_price_ranges": int(report_rows["_valid_price_range"].sum()),
        "exact_duplicates_removed": 0,
    }
    return {
        "source_sha256": retrieved.source_sha256,
        "retrieval": retrieved,
        "monthly_records": monthly_records,
        "covered_months": int(covered_months),
        "coverage_score": float(covered_months / 12.0),
        "data_quality": data_quality,
    }

def _coverage_validator(plan: FilteredRunPlan, aggregate: dict[str, Any]) -> CoverageDecision:
    del plan
    score = float(aggregate["coverage_score"])
    accepted = score == 1.0
    return CoverageDecision(
        score=score,
        accepted=accepted,
        reason=(
            "All 12 reporting months have valid coherent sale-price metrics"
            if accepted else f"Filtered subset has valid price coverage in {aggregate['covered_months']}/12 reporting months"
        ),
        issue="" if accepted else "filtered_monthly_price_coverage_incomplete",
        repairable=False,
    )


def _write_diagnostics(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interpretations = {
        "AN-01": "The selected listing subset's median price bound changed between adjacent reporting months; this is not proof of a market-wide price movement.",
        "AN-02": "Observed posting count fell sharply in this filtered subset; check subset size and coverage before interpreting the change.",
        "AN-03": "Observed posting count rose sharply in this filtered subset; check source coverage and listing composition.",
        "AN-04": "The final two months contain a large share of this subset; August is partial and must not be extrapolated.",
    }
    return [{
        "rule_id": str(flag.get("rule_id", "unknown")),
        "month": str(flag.get("month", "")),
        "metric": str(flag.get("metric", "")),
        "diagnosis": interpretations.get(str(flag.get("rule_id")), "Inspect the deterministic rule evidence before interpreting this flag."),
        "evidence": str(flag.get("message", flag)),
        "evidence_fields": {k: v for k, v in flag.items() if isinstance(v, (str, int, float, bool, type(None)))},
        "method": "deterministic_rule_based",
    } for flag in anomalies]


def _critique(diagnostics: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> CritiqueDecision:
    expected = sorted((str(a.get("rule_id")), str(a.get("month", "")), str(a.get("metric", ""))) for a in anomalies)
    observed = sorted((str(d.get("rule_id")), str(d.get("month", "")), str(d.get("metric", ""))) for d in diagnostics)
    valid = len(expected) == len(observed) and expected == observed and all(
        d.get("diagnosis") and d.get("evidence") and d.get("method") == "deterministic_rule_based"
        for d in diagnostics
    )
    return CritiqueDecision(
        passed=valid,
        reason="Each anomaly has a matching evidence-backed diagnostic" if valid else "Diagnostics are incomplete or do not match anomalies",
        issue="diagnostic_evidence_incomplete" if not valid else "",
    )


def run_filtered_execution_graph(
    request: Mapping[str, Any],
    *,
    source_path: str | Path = DEFAULT_SOURCE_PATH,
) -> GraphResult:
    """Execute typed Criteria -> Retrieval -> Aggregator on the existing graph."""
    source = Path(source_path)
    interactions: list[dict[str, Any]] = []
    retrieval_agent = RetrievalAgent(source)

    def planner(raw_request: Mapping[str, Any]) -> FilteredRunPlan:
        criteria_result = run_criteria_agent(raw_request, source_path=source)
        interactions.append({
            "sequence": len(interactions),
            "agent": "criteria_agent",
            "invoked_by": "planner",
            "outcome": "validated",
            "query_mode": criteria_result.query_mode.value,
            "filter_spec": criteria_result.filter_spec.to_dict(),
        })
        return FilteredRunPlan(request=dict(raw_request), criteria_result=criteria_result)

    def scanner(plan: FilteredRunPlan, repair: Any | None) -> RetrievalResult:
        if repair is not None:
            raise RuntimeError("Filtered Retrieval Agent does not permit implicit filter-relaxation repairs")
        retrieved = retrieval_agent.retrieve(plan.criteria_result)
        interactions.append({
            "sequence": len(interactions),
            "agent": "retrieval_agent",
            "invoked_by": "scanner",
            "outcome": "selected",
            "query_mode": retrieved.query_mode.value,
            "selected_row_count": retrieved.selected_row_count,
            "source_sha256": retrieved.source_sha256,
            "source_period_start": retrieved.source_period_start,
            "source_period_end": retrieved.source_period_end,
            "invalid_registration_date_rows": retrieved.invalid_registration_date_rows,
            "malformed_location_rows": retrieved.malformed_location_rows,
            "invalid_coordinate_rows": retrieved.invalid_coordinate_rows,
        })
        return retrieved

    def aggregator(plan: FilteredRunPlan, retrieved: RetrievalResult) -> dict[str, Any]:
        aggregate = _aggregate_selected(plan, retrieved)
        interactions.append({
            "sequence": len(interactions),
            "agent": "aggregator",
            "invoked_by": "execution_graph",
            "outcome": "aggregated",
            "reporting_month_count": len(aggregate["monthly_records"]),
            "covered_months": aggregate["covered_months"],
        })
        return aggregate

    def reporter(payload: dict[str, Any]) -> dict[str, Any]:
        plan: FilteredRunPlan = payload["plan"]
        retrieved: RetrievalResult = payload["selected_rows"]
        aggregate: dict[str, Any] = payload["aggregate"]
        graph_trace = payload["trace"]
        return {
            "status": payload["status"],
            "analysis_scope": "filtered_listing_subset",
            "logic_version": LOGIC_VERSION,
            "source_sha256": retrieved.source_sha256,
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
            "timezone": LOCAL_TIMEZONE,
            "request": dict(plan.request),
            "criteria_result": plan.criteria_result.to_dict(),
            "retrieval": retrieved.to_dict(),
            "monthly_records": aggregate["monthly_records"],
            "data_quality": aggregate["data_quality"],
            "coverage_score": aggregate["coverage_score"],
            "anomalies": payload["anomalies"],
            "diagnostics": payload["diagnostics"],
            "loop_counters": dict(payload["loop_counters"]),
            "loop_events": payload["loop_events"],
            "trace": graph_trace,
            "agent_interaction_trace": list(interactions),
            "execution_graph": {
                "topology": plan.topology,
                "stage_order": [
                    "planner (calls Criteria Agent)",
                    "scanner (calls Retrieval Agent)",
                    "aggregator",
                    "validator",
                    "anomaly",
                    "diagnostic",
                    "reporter",
                ],
                "coverage": payload["coverage"],
                "loop_counters": dict(payload["loop_counters"]),
                "trace_event_count": len(graph_trace),
                "agent_interaction_count": len(interactions),
            },
        }

    def fallback(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _write_diagnostics(anomalies)

    graph = run_execution_graph(
        request=dict(request),
        planner=planner,
        scanner=scanner,
        aggregator=aggregator,
        coverage_validator=_coverage_validator,
        anomaly_detector=lambda aggregate: detect_anomalies(aggregate["monthly_records"]),
        diagnostic_writer=_write_diagnostics,
        critique_gate=_critique,
        reporter=reporter,
        diagnostic_reviser=lambda diagnostics, critique, anomalies: _write_diagnostics(anomalies),
        diagnostic_fallback=fallback,
        repair_provider=None,
    )
    return graph
