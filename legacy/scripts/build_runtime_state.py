"""Build the frozen Hyderabad runtime report through the execution graph.

All numeric definitions intentionally match the previously validated builder.
The orchestration graph now owns stage order, trace creation, and loop accounting.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.anomaly_detector import detect_anomalies  # noqa: E402
from app.execution_graph import (  # noqa: E402
    CritiqueDecision,
    CoverageDecision,
    run_execution_graph,
)
from app.schemas import (  # noqa: E402
    AnalysisRequest,
    CoverageFlag,
    MonthState,
    RetryCounters,
    RunPlan,
    RuntimeState,
    SourcePeriod,
    EXPECTED_MONTHS,
)

RAW_FILE = ROOT / "data" / "raw" / "hyderabad.csv"
OUTPUT_FILE = ROOT / "audit" / "runtime_state.json"
EXPECTED_SHA256 = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
PRICE_SENTINEL = 2147483647
RUN_ID = "hyderabad-2022-09_2023-08-9e816983"
LOGIC_VERSION = "hyderabad-runtime-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric_column(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame[name], errors="coerce")


def _plan(request: AnalysisRequest) -> RunPlan:
    """Create the existing contract-v1 plan; filters remain unsupported."""
    request.validate()
    plan = RunPlan(
        source_period=SourcePeriod(),
        requested_filters=request.requested_filters,
        effective_filters=request.requested_filters,
        query_mode=request.query_mode,
    )
    plan.validate()
    return plan


def _scan_snapshot(plan: RunPlan, repair: Any | None) -> dict[str, Any]:
    """Verify the immutable snapshot and select the contract calendar window."""
    del plan  # The contract-v1 request scope is the fixed full snapshot.
    if repair is not None:
        raise ValueError("Snapshot scan does not permit data-changing repairs")
    if not RAW_FILE.is_file():
        raise FileNotFoundError(f"Raw CSV not found: {RAW_FILE}")

    source_hash = sha256_file(RAW_FILE)
    if source_hash != EXPECTED_SHA256:
        raise RuntimeError(
            "snapshot_integrity_error: the CSV hash does not match "
            "the frozen CONTRACT.md / Golden.md snapshot. "
            f"Expected {EXPECTED_SHA256}; got {source_hash}"
        )

    df = pd.read_csv(RAW_FILE, low_memory=False)
    raw_rows, raw_columns = df.shape
    required = {
        "POSTING_DATE", "PREFERENCE", "MIN_PRICE", "MAX_PRICE", "PRICE_SQFT", "PRICE", "PROP_ID"
    }
    missing_columns = sorted(required - set(df.columns))
    if missing_columns:
        raise ValueError(f"Missing required CSV columns: {missing_columns}")

    # POSTING_DATE is Unix milliseconds: parse as UTC, convert to Asia/Kolkata,
    # and only then derive the calendar month.
    raw_timestamp = numeric_column(df, "POSTING_DATE")
    valid_timestamp_number = raw_timestamp.notna() & np.isfinite(raw_timestamp)
    posting_date = pd.Series(
        pd.NaT, index=df.index, dtype="datetime64[ns, Asia/Kolkata]"
    )
    parsed_utc = pd.to_datetime(
        raw_timestamp.loc[valid_timestamp_number],
        unit="ms",
        utc=True,
        errors="coerce",
    )
    posting_date.loc[parsed_utc.index] = parsed_utc.dt.tz_convert("Asia/Kolkata")
    df["_posting_date_local"] = posting_date
    df["_month"] = df["_posting_date_local"].dt.strftime("%Y-%m")

    valid_date_mask = df["_posting_date_local"].notna()
    in_window_mask = valid_date_mask & df["_month"].isin(EXPECTED_MONTHS)
    in_window = df.loc[in_window_mask].copy()

    preference = in_window["PREFERENCE"].astype("string").str.strip().str.upper()
    in_window["_is_sale"] = preference.eq("S").fillna(False)
    min_price = numeric_column(in_window, "MIN_PRICE")
    max_price = numeric_column(in_window, "MAX_PRICE")
    valid_min = min_price.notna() & np.isfinite(min_price) & (min_price > 0) & (min_price != PRICE_SENTINEL)
    valid_max = max_price.notna() & np.isfinite(max_price) & (max_price > 0) & (max_price != PRICE_SENTINEL)
    in_window["_min_price_numeric"] = min_price
    in_window["_max_price_numeric"] = max_price
    price_text = in_window["PRICE"].astype("string").fillna("").str.strip()
    in_window["_price_on_request"] = price_text.str.contains(
        r"\bprice\s+on\s+request\b", case=False, regex=True, na=False
    )
    in_window["_valid_price_range"] = (
        in_window["_is_sale"]
        & valid_min
        & valid_max
        & (min_price <= max_price)
        & ~in_window["_price_on_request"]
    )

    price_sqft = numeric_column(in_window, "PRICE_SQFT")
    in_window["_valid_price_sqft"] = (
        in_window["_is_sale"]
        & price_sqft.notna()
        & np.isfinite(price_sqft)
        & (price_sqft > 0)
    )

    return {
        "source_sha256": source_hash,
        "raw_frame": df,
        "in_window": in_window,
        "raw_rows": int(raw_rows),
        "raw_columns": int(raw_columns),
        "valid_dated": int(valid_date_mask.sum()),
        "in_window_count": int(len(in_window)),
    }


def _aggregate_months(plan: RunPlan, scan: dict[str, Any]) -> dict[str, Any]:
    """Compute the pre-existing 12-month metrics and quality reconciliations."""
    del plan
    df: pd.DataFrame = scan["raw_frame"]
    in_window: pd.DataFrame = scan["in_window"]
    monthly_records: list[dict[str, Any]] = []
    month_states: list[MonthState] = []
    coverage_flags: list[CoverageFlag] = []

    for month in EXPECTED_MONTHS:
        rows = in_window.loc[in_window["_month"] == month]
        valid_ranges = rows.loc[rows["_valid_price_range"]]
        observed_count = int(len(rows))
        sale_count = int(rows["_is_sale"].sum())
        valid_range_count = int(rows["_valid_price_range"].sum())
        valid_sqft_count = int(rows["_valid_price_sqft"].sum())

        if valid_range_count:
            median_min = float(valid_ranges["_min_price_numeric"].median())
            median_max = float(valid_ranges["_max_price_numeric"].median())
        else:
            median_min = None
            median_max = None

        is_partial_month = month == "2023-08"
        if observed_count == 0:
            month_status = "no_listings"
            coverage_status = "no_listings"
            metric_status = "no_listings"
        elif sale_count == 0:
            month_status = "no_valid_prices"
            coverage_status = "partial_month" if is_partial_month else "observed"
            metric_status = "no_sale_listings"
        elif valid_range_count == 0:
            month_status = "no_valid_prices"
            coverage_status = "partial_month" if is_partial_month else "observed"
            metric_status = "no_valid_prices"
        else:
            month_status = "partial_month" if is_partial_month else "ok"
            coverage_status = "partial_month" if is_partial_month else "observed"
            # PRICE_SQFT semantics remain unresolved; do not emit a median.
            metric_status = "unverified_metric"

        month_state = MonthState(
            month=month,
            status=month_status,
            observed_listing_count=observed_count,
            sale_listing_count=sale_count,
            valid_price_count=valid_range_count,
            median_min_price_inr=median_min,
            median_max_price_inr=median_max,
            coverage_status=coverage_status,
            is_partial_month=is_partial_month,
            valid_price_sqft_count=valid_sqft_count,
            median_price_per_sqft_inr=None,
        )
        month_state.validate()
        month_states.append(month_state)

        coverage_flag = CoverageFlag(
            month=month,
            observed_listing_count=observed_count,
            sale_listing_count=sale_count,
            valid_price_count=valid_range_count,
            coverage_status=coverage_status,
            is_partial_month=is_partial_month,
            has_observed_listings=observed_count > 0,
            has_valid_prices=valid_range_count > 0,
        )
        coverage_flag.validate()
        coverage_flags.append(coverage_flag)

        # This dictionary is consumed by the anomaly detector and public report.
        monthly_records.append(
            {
                "month": month,
                "observed_listing_count": observed_count,
                "sale_listing_count": sale_count,
                "valid_price_range_count": valid_range_count,
                "valid_price_sqft_count": valid_sqft_count,
                "median_min_price_inr": median_min,
                "median_max_price_inr": median_max,
                "median_price_per_sqft_inr": None,
                "coverage_status": coverage_status,
                "metric_status": metric_status,
            }
        )

    valid_dated = int(scan["valid_dated"])
    in_window_count = int(len(in_window))
    outside_window_count = int(valid_dated - in_window_count)
    in_window_sales = int(in_window["_is_sale"].sum())
    in_window_valid_ranges = int(in_window["_valid_price_range"].sum())
    exact_duplicates = int(
        df.drop(columns=["_posting_date_local", "_month"], errors="ignore").duplicated().sum()
    )
    prop_counts = df["PROP_ID"].dropna().value_counts()
    repeated_groups = int((prop_counts > 1).sum())
    repeated_rows = int(prop_counts[prop_counts > 1].sum())

    data_quality = {
        "raw_rows": int(scan["raw_rows"]),
        "raw_columns": int(scan["raw_columns"]),
        "valid_posting_dates": valid_dated,
        "missing_or_invalid_posting_dates": int(scan["raw_rows"] - valid_dated),
        "valid_dated_rows_outside_window": outside_window_count,
        "in_window_observed_rows": in_window_count,
        "in_window_sale_rows": in_window_sales,
        "in_window_valid_price_ranges": in_window_valid_ranges,
        "in_window_valid_price_sqft_numeric_values": int(in_window["_valid_price_sqft"].sum()),
        "in_window_sale_rows_without_valid_coherent_range": in_window_sales - in_window_valid_ranges,
        "exact_duplicate_rows_detected": exact_duplicates,
        "exact_duplicate_rows_removed": 0,
        "repeated_prop_id_groups": repeated_groups,
        "repeated_prop_id_rows": repeated_rows,
    }

    # Reconcile aggregates against the scan counts before coverage validation.
    assert valid_dated + data_quality["missing_or_invalid_posting_dates"] == int(scan["raw_rows"])
    assert outside_window_count + in_window_count == valid_dated
    assert sum(x["observed_listing_count"] for x in monthly_records) == in_window_count
    assert sum(x["sale_listing_count"] for x in monthly_records) == in_window_sales
    assert sum(x["valid_price_range_count"] for x in monthly_records) == in_window_valid_ranges

    covered_months = sum(
        record["valid_price_range_count"] > 0
        and record["median_min_price_inr"] is not None
        and record["median_max_price_inr"] is not None
        for record in monthly_records
    )
    coverage_score = float(covered_months / 12.0)
    return {
        "source_sha256": scan["source_sha256"],
        "raw_rows": int(scan["raw_rows"]),
        "raw_columns": int(scan["raw_columns"]),
        "valid_dated": valid_dated,
        "in_window_count": in_window_count,
        "in_window_sales": in_window_sales,
        "in_window_valid_ranges": in_window_valid_ranges,
        "covered_months": int(covered_months),
        "coverage_score": coverage_score,
        "monthly_records": monthly_records,
        "month_states": month_states,
        "coverage_flags": coverage_flags,
        "data_quality": data_quality,
    }


def _validate_coverage(plan: RunPlan, aggregate: dict[str, Any]) -> CoverageDecision:
    del plan
    score = float(aggregate["coverage_score"])
    accepted = score == 1.0
    return CoverageDecision(
        score=score,
        accepted=accepted,
        reason=(
            "All 12 calendar months have valid coherent INR price-bound metrics"
            if accepted
            else f"Valid coherent price-bound coverage exists for {aggregate['covered_months']}/12 months"
        ),
        issue="" if accepted else "monthly_price_coverage_incomplete",
        # The frozen full-snapshot scan cannot repair a true missing/invalid month.
        repairable=False,
    )


def _write_diagnostics(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create deterministic, rule-grounded diagnostics without an LLM."""
    interpretations = {
        "AN-01": (
            "The reported median price bound changed materially between adjacent snapshot months. "
            "This is a listing-snapshot signal, not proof of a market-wide price movement."
        ),
        "AN-02": (
            "Observed posting count fell sharply versus the previous month. "
            "Check snapshot coverage and scrape/listing mix before inferring demand."
        ),
        "AN-03": (
            "Observed posting count rose sharply versus the previous month. "
            "Check listing ingestion, scrape concentration, and month coverage."
        ),
        "AN-04": (
            "The final two months contain a high share of rows; the last month is partial. "
            "Do not treat snapshot concentration as market share or extrapolate August."
        ),
    }
    diagnostics: list[dict[str, Any]] = []
    for flag in anomalies:
        rule_id = str(flag.get("rule_id", "unknown"))
        diagnostics.append(
            {
                "rule_id": rule_id,
                "month": str(flag.get("month", "")),
                "metric": str(flag.get("metric", "")),
                "diagnosis": interpretations.get(
                    rule_id,
                    "A deterministic anomaly rule was triggered; inspect its evidence before interpretation.",
                ),
                "evidence": str(flag.get("message", "")),
                "evidence_fields": {
                    key: value
                    for key, value in flag.items()
                    if key not in {"message"} and isinstance(value, (str, int, float, bool, type(None)))
                },
                "method": "deterministic_rule_based",
            }
        )
    return diagnostics


def _critique_diagnostics(
    diagnostics: list[dict[str, Any]], anomalies: list[dict[str, Any]]
) -> CritiqueDecision:
    """Check coverage, evidence linkage, and required diagnostic fields."""
    expected = [(str(a.get("rule_id")), str(a.get("month")), str(a.get("metric"))) for a in anomalies]
    observed = [(str(d.get("rule_id")), str(d.get("month")), str(d.get("metric"))) for d in diagnostics]
    complete = (
        len(expected) == len(observed)
        and sorted(expected) == sorted(observed)
        and all(
            bool(str(d.get("diagnosis", "")).strip())
            and bool(str(d.get("evidence", "")).strip())
            and d.get("method") == "deterministic_rule_based"
            for d in diagnostics
        )
    )
    if complete:
        return CritiqueDecision(True, "Every anomaly has a matching diagnosis and source-rule evidence")
    return CritiqueDecision(
        False,
        "Diagnostic validation found missing or mismatched evidence",
        issue="diagnostic_evidence_incomplete",
    )


def _revise_diagnostics(
    diagnostics: list[dict[str, Any]],
    critique: CritiqueDecision,
    anomalies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del diagnostics, critique
    # Deterministic regeneration is bounded by the graph's critique revision cap.
    return _write_diagnostics(anomalies)


def _reporter(request: AnalysisRequest, payload: dict[str, Any]) -> dict[str, Any]:
    aggregate = payload["aggregate"]
    scan = payload["selected_rows"]
    plan = payload["plan"]
    runtime_state = RuntimeState(
        run_id=RUN_ID,
        request=request,
        plan=plan,
        retries=RetryCounters(
            coverage_repair_retries=int(payload["loop_counters"]["coverage_repair"]),
            critique_revisions=int(payload["loop_counters"]["critique_revision"]),
        ),
        coverage_flags=aggregate["coverage_flags"],
        months=aggregate["month_states"],
        trace=payload["trace"],
        source_sha256=scan["source_sha256"],
    )
    runtime_state.validate()
    analysis_report = runtime_state.to_analysis_report(
        data_quality=aggregate["data_quality"],
        seed=0,
        llm_mode="disabled",
        logic_version=LOGIC_VERSION,
        status=payload["status"],
        coverage_score=float(payload["coverage"]["score"]),
        coverage_decision=str(payload["coverage"]["decision"]),
    )
    report = analysis_report.to_dict()
    # Keep the assignment's public monthly output available at the report root.
    # AnalysisReport's internal serialization may organize month state differently;
    # this explicit view is the stable, user-facing 12-record contract.
    report["monthly_records"] = aggregate["monthly_records"]
    report["runtime_state"] = runtime_state.to_dict()
    report["anomalies"] = payload["anomalies"]
    report["diagnostics"] = payload["diagnostics"]
    report["execution_graph"] = {
        "stage_order": [
            "planner", "scanner", "aggregator", "validator", "anomaly", "diagnostic", "reporter"
        ],
        "topology": plan.topology,
        "coverage": payload["coverage"],
        "loop_counters": dict(payload["loop_counters"]),
        "trace_event_count": len(payload["trace"]),
    }
    return report


def main() -> None:
    request = AnalysisRequest()
    graph_result = run_execution_graph(
        request=request,
        planner=_plan,
        scanner=_scan_snapshot,
        aggregator=_aggregate_months,
        coverage_validator=_validate_coverage,
        anomaly_detector=lambda aggregate: detect_anomalies(aggregate["monthly_records"]),
        diagnostic_writer=_write_diagnostics,
        critique_gate=_critique_diagnostics,
        reporter=lambda payload: _reporter(request, payload),
        diagnostic_reviser=_revise_diagnostics,
        diagnostic_fallback=_write_diagnostics,
        # There is no permitted repair for the immutable full snapshot. In
        # particular, do not create artificial retries to exercise the graph.
        repair_provider=None,
    )
    report = graph_result.report
    aggregate = graph_result.aggregate
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(report, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print("Runtime state built successfully through execution graph.")
    print(f"Raw rows: {aggregate['raw_rows']:,}; columns: {aggregate['raw_columns']}")
    print(f"Valid posting dates: {aggregate['valid_dated']:,}")
    print(f"In-window observed rows: {aggregate['in_window_count']:,}")
    print(f"In-window sale rows: {aggregate['in_window_sales']:,}")
    print(f"Valid coherent sale-price ranges: {aggregate['in_window_valid_ranges']:,}")
    print(f"Covered months: {aggregate['covered_months']}/12")
    print(f"Coverage score: {graph_result.coverage.score:.6f}")
    print(f"Overall status: {report['status']}")
    print(f"Graph trace events: {len(graph_result.trace)}")
    print(f"Coverage retries: {graph_result.loop_counters['coverage_repair']}")
    print(f"Critique revisions: {graph_result.loop_counters['critique_revision']}")
    print(f"Anomaly flags: {len(graph_result.anomalies)}; diagnostics: {len(graph_result.diagnostics)}")
    print(f"Report: {OUTPUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
