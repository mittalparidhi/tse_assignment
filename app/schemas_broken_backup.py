"""Runtime schemas for the Hyderabad housing-trends application.

This module centralizes shared constants and validates request, month, and
runtime-state structures. It uses only the Python standard library.

Important distinctions:
- Month coverage status describes availability in a specific month.
- Month metric status describes whether a given month's metrics are usable.
- Run-level coverage status/decision describes the aggregate twelve-month run.
- PRICE_SQFT remains unverified; this schema never treats it as INR/sqft.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import hashlib
import json
import math
import re
from typing import Any, Literal

CONTRACT_VERSION = "1.0.0-draft"
WINDOW_START = "2022-09"
WINDOW_END = "2023-08"
LOCAL_TIMEZONE = "Asia/Kolkata"
FROZEN_SOURCE_SHA256 = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
PRICE_SENTINEL = 2147483647

# These caps count retries/revisions after the initial attempt.
COVERAGE_REPAIR_CAP = 3
CRITIQUE_REVISION_CAP = 2
LLM_RETRY_CAP = 2

EXPECTED_MONTHS = [
    f"{year:04d}-{month:02d}"
    for year, start, end in ((2022, 9, 12), (2023, 1, 8))
    for month in range(start, end + 1)
]

QUERY_MODES = {"structured", "natural_language"}

MONTH_STATUSES = {
    "ok",
    "no_listings",
    "partial_month",
    "no_valid_prices",
    "insufficient_price_coverage",
    "error",
}

# Public report status and coverage decision are separate fields in contract v1.
REPORT_STATUSES = {"ok", "partial", "error"}
COVERAGE_DECISIONS = {"accept", "partial", "fail"}
# Backward-compatible name for callers that imported the old constant.
COVERAGE_STATUSES = REPORT_STATUSES

MONTH_COVERAGE_STATUSES = {"observed", "partial_month", "no_listings"}

MONTH_METRIC_STATUSES = {
    "ok",
    "no_listings",
    "no_sale_listings",
    "no_valid_prices",
    "unverified_metric",
}

TRACE_AGENTS = {
    "planner",
    "scanner",
    "aggregator",
    "validator",
    "anomaly",
    "diagnostic",
    "reporter",
}
TRACE_KINDS = {"step", "decision", "loop", "warning", "error"}
TRACE_LOOPS = {"coverage_repair", "critique_revision"}
TRACE_KEYS = {"i", "agent", "kind", "loop", "msg", "data"}

# These fields are not applied by contract v1. The default unfiltered scope is
# the only implemented request scope in this schema version.
UNSUPPORTED_FILTERS = {
    "locality",
    "property_type",
    "min_price",
    "max_price",
    "min_area",
    "max_area",
    "geo_radius",
}


class ContractValidationError(ValueError):
    """Raised when runtime state violates the global contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


def _is_month(value: Any) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value)
    )


def _require_nonnegative_int(value: Any, name: str) -> None:
    # bool is an int subclass, but should not be accepted as a count.
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        f"{name} must be a non-negative integer",
    )


def _require_finite_number(value: Any, name: str) -> None:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        f"{name} must be a finite number",
    )


def _json_ready(value: Any) -> Any:
    """Convert dataclass contents to JSON-compatible values deterministically."""
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


@dataclass(frozen=True)
class SourcePeriod:
    """Fixed historical source period; never relative to the current date."""

    start_month: str = WINDOW_START
    end_month: str = WINDOW_END
    timezone: str = LOCAL_TIMEZONE
    months: tuple[str, ...] = tuple(EXPECTED_MONTHS)

    def __post_init__(self) -> None:
        _require(_is_month(self.start_month), "Invalid start_month")
        _require(_is_month(self.end_month), "Invalid end_month")
        _require(
            self.start_month == WINDOW_START,
            f"start_month must be {WINDOW_START}",
        )
        _require(
            self.end_month == WINDOW_END,
            f"end_month must be {WINDOW_END}",
        )
        _require(
            self.timezone == LOCAL_TIMEZONE,
            f"timezone must be {LOCAL_TIMEZONE}",
        )
        _require(
            tuple(self.months) == tuple(EXPECTED_MONTHS),
            "months must contain exactly the 12 ordered contract months",
        )

    def to_dict(self) -> dict[str, Any]:
        result = _json_ready(self)
        result["months"] = list(self.months)
        return result


@dataclass
class AnalysisFilters:
    """Requested/effective filters; unsupported filters fail closed in v1."""

    city: list[str] = field(default_factory=list)
    locality: list[str] = field(default_factory=list)
    property_type: list[str] = field(default_factory=list)
    min_price_inr: float | None = None
    max_price_inr: float | None = None
    min_area: float | None = None
    max_area: float | None = None
    geo_radius_km: float | None = None

    def validate(self, *, allow_unsupported: bool = False) -> None:
        for name in ("city", "locality", "property_type"):
            values = getattr(self, name)
            _require(isinstance(values, list), f"{name} must be a list")
            _require(
                all(isinstance(item, str) and bool(item.strip()) for item in values),
                f"{name} must contain only non-blank strings",
            )

        numeric_fields = (
            "min_price_inr",
            "max_price_inr",
            "min_area",
            "max_area",
            "geo_radius_km",
        )
        for name in numeric_fields:
            value = getattr(self, name)
            if value is not None:
                _require_finite_number(value, name)

        for name in ("min_price_inr", "max_price_inr", "min_area", "max_area"):
            value = getattr(self, name)
            if value is not None:
                _require(value >= 0, f"{name} cannot be negative")

        if self.min_price_inr is not None and self.max_price_inr is not None:
            _require(
                self.min_price_inr <= self.max_price_inr,
                "min_price_inr cannot exceed max_price_inr",
            )
        if self.min_area is not None and self.max_area is not None:
            _require(
                self.min_area <= self.max_area,
                "min_area cannot exceed max_area",
            )
        if self.geo_radius_km is not None:
            _require(self.geo_radius_km > 0, "geo_radius_km must be positive")

        if not allow_unsupported:
            unsupported_values = {
                "locality": self.locality,
                "property_type": self.property_type,
                "min_price": self.min_price_inr,
                "max_price": self.max_price_inr,
                "min_area": self.min_area,
                "max_area": self.max_area,
                "geo_radius": self.geo_radius_km,
            }
            present = [
                name
                for name, value in unsupported_values.items()
                if value is not None and value != []
            ]
            _require(
                not present,
                "Unsupported filters under contract v1: " + ", ".join(present),
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass
class AnalysisRequest:
    """Validated request envelope."""

    query_mode: Literal["structured", "natural_language"] = "structured"
    requested_filters: AnalysisFilters = field(default_factory=AnalysisFilters)
    request_id: str | None = None
    include_diagnostics: bool = True

    def validate(self) -> None:
        _require(
            self.query_mode in QUERY_MODES,
            f"query_mode must be one of {sorted(QUERY_MODES)}",
        )
        _require(
            self.query_mode == "structured",
            "Natural-language query parsing is not implemented; "
            "use query_mode='structured'.",
        )
        _require(isinstance(self.requested_filters, AnalysisFilters),
                 "requested_filters must be an AnalysisFilters instance")
        self.requested_filters.validate()
        _require(
            isinstance(self.include_diagnostics, bool),
            "include_diagnostics must be boolean",
        )
        if self.request_id is not None:
            _require(
                isinstance(self.request_id, str) and bool(self.request_id.strip()),
                "request_id cannot be blank",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_mode": self.query_mode,
            "requested_filters": self.requested_filters.to_dict(),
            "request_id": self.request_id,
            "include_diagnostics": self.include_diagnostics,
        }


@dataclass
class RetryCounters:
    """Retry counters count retries after an initial attempt."""

    coverage_repair_retries: int = 0
    critique_revisions: int = 0
    llm_retries_by_purpose: dict[str, int] = field(default_factory=dict)

    def validate(self) -> None:
        _require_nonnegative_int(self.coverage_repair_retries,
                                 "coverage_repair_retries")
        _require_nonnegative_int(self.critique_revisions, "critique_revisions")
        _require(
            self.coverage_repair_retries <= COVERAGE_REPAIR_CAP,
            f"coverage_repair_retries must be 0..{COVERAGE_REPAIR_CAP}",
        )
        _require(
            self.critique_revisions <= CRITIQUE_REVISION_CAP,
            f"critique_revisions must be 0..{CRITIQUE_REVISION_CAP}",
        )
        _require(isinstance(self.llm_retries_by_purpose, dict),
                 "llm_retries_by_purpose must be a dictionary")
        for purpose, count in self.llm_retries_by_purpose.items():
            _require(
                isinstance(purpose, str) and bool(purpose.strip()),
                "LLM retry purpose cannot be blank",
            )
            _require_nonnegative_int(count, f"LLM retries for {purpose!r}")
            _require(
                count <= LLM_RETRY_CAP,
                f"LLM retries for {purpose!r} must be 0..{LLM_RETRY_CAP}",
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass
class CoverageFlag:
    """Month-level availability and valid price-bound coverage metadata."""

    month: str
    observed_listing_count: int
    sale_listing_count: int
    valid_price_count: int
    coverage_status: str
    is_partial_month: bool = False
    has_observed_listings: bool = False
    has_valid_prices: bool = False

    def validate(self) -> None:
        _require(self.month in EXPECTED_MONTHS, "Unknown coverage month")
        for name in (
            "observed_listing_count",
            "sale_listing_count",
            "valid_price_count",
        ):
            _require_nonnegative_int(getattr(self, name), name)

        _require(
            self.sale_listing_count <= self.observed_listing_count,
            "sale_listing_count cannot exceed observed_listing_count",
        )
        _require(
            self.valid_price_count <= self.sale_listing_count,
            "valid_price_count cannot exceed sale_listing_count",
        )
        _require(
            self.coverage_status in MONTH_COVERAGE_STATUSES,
            f"Invalid month coverage status: {self.coverage_status}",
        )
        _require(isinstance(self.is_partial_month, bool),
                 "is_partial_month must be boolean")
        _require(
            self.is_partial_month == (self.month == WINDOW_END),
            "Only 2023-08 is marked as the partial source month",
        )
        _require(
            self.has_observed_listings == (self.observed_listing_count > 0),
            "has_observed_listings conflicts with observed_listing_count",
        )
        _require(
            self.has_valid_prices == (self.valid_price_count > 0),
            "has_valid_prices conflicts with valid_price_count",
        )

        expected_coverage = _expected_month_coverage(
            self.month, self.observed_listing_count
        )
        _require(
            self.coverage_status == expected_coverage,
            f"coverage_status for {self.month} must be {expected_coverage!r}",
        )

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


def _expected_month_coverage(month: str, observed_count: int) -> str:
    """Use no_listings before the partial-month label for an empty month."""
    if observed_count == 0:
        return "no_listings"
    if month == WINDOW_END:
        return "partial_month"
    return "observed"


def _expected_metric_status(
    observed_count: int, sale_count: int, valid_price_count: int
) -> str:
    if observed_count == 0:
        return "no_listings"
    if sale_count == 0:
        return "no_sale_listings"
    if valid_price_count == 0:
        return "no_valid_prices"
    # PRICE_SQFT's semantic/unit verification is unresolved in this snapshot.
    return "unverified_metric"


@dataclass
class MonthState:
    """Validated per-month processing status, metrics, and coverage."""

    month: str
    status: str
    observed_listing_count: int
    sale_listing_count: int
    valid_price_count: int
    median_min_price_inr: float | None = None
    median_max_price_inr: float | None = None
    coverage_status: str = "observed"
    is_partial_month: bool = False
    error_code: str | None = None
    metric_status: str | None = None

    def validate(self) -> None:
        _require(self.month in EXPECTED_MONTHS, "Unknown month")
        _require(self.status in MONTH_STATUSES, f"Invalid month status: {self.status}")
        _require(
            self.coverage_status in MONTH_COVERAGE_STATUSES,
            f"Invalid month coverage status: {self.coverage_status}",
        )

        for name in (
            "observed_listing_count",
            "sale_listing_count",
            "valid_price_count",
        ):
            _require_nonnegative_int(getattr(self, name), name)

        _require(
            self.sale_listing_count <= self.observed_listing_count,
            "sale_listing_count cannot exceed observed_listing_count",
        )
        _require(
            self.valid_price_count <= self.sale_listing_count,
            "valid_price_count cannot exceed sale_listing_count",
        )
        _require(isinstance(self.is_partial_month, bool),
                 "is_partial_month must be boolean")
        _require(
            self.is_partial_month == (self.month == WINDOW_END),
            "Only 2023-08 is marked as the partial source month",
        )

        expected_coverage = _expected_month_coverage(
            self.month, self.observed_listing_count
        )
        _require(
            self.coverage_status == expected_coverage,
            f"coverage_status for {self.month} must be {expected_coverage!r}",
        )

        if self.observed_listing_count == 0:
            _require(self.status == "no_listings",
                     "Empty month must have status='no_listings'")
        elif self.valid_price_count == 0 and self.status not in {"no_valid_prices", "error"}:
            _require(
                self.status == "insufficient_price_coverage",
                "A month without valid prices must be marked no_valid_prices, "
                "insufficient_price_coverage, or error",
            )
        elif self.valid_price_count > 0 and self.status not in {"ok", "partial_month", "error"}:
            _require(
                self.status == "insufficient_price_coverage",
                "A month with valid prices must be ok, partial_month, or error",
            )

        if self.valid_price_count == 0:
            _require(
                self.median_min_price_inr is None
                and self.median_max_price_inr is None,
                "No valid price ranges means both price medians must be null",
            )
        else:
            _require(
                self.median_min_price_inr is not None
                and self.median_max_price_inr is not None,
                "Valid price ranges require both INR price-bound medians",
            )

        for name in ("median_min_price_inr", "median_max_price_inr"):
            value = getattr(self, name)
            if value is not None:
                _require_finite_number(value, name)
                _require(value > 0, f"{name} must be positive when available")

        if (
            self.median_min_price_inr is not None
            and self.median_max_price_inr is not None
        ):
            _require(
                self.median_min_price_inr <= self.median_max_price_inr,
                "Median minimum price cannot exceed median maximum price",
            )

        expected_metric = _expected_metric_status(
            self.observed_listing_count,
            self.sale_listing_count,
            self.valid_price_count,
        )
        if self.metric_status is None:
            self.metric_status = expected_metric
        _require(
            self.metric_status in MONTH_METRIC_STATUSES,
            f"Invalid metric_status: {self.metric_status}",
        )
        _require(
            self.metric_status == expected_metric,
            f"metric_status must be {expected_metric!r} for these counts",
        )

        if self.status == "error":
            _require(
                isinstance(self.error_code, str) and bool(self.error_code.strip()),
                "Error month requires a non-blank error_code",
            )
        else:
            _require(self.error_code is None,
                     "error_code must be null unless status='error'")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return _json_ready(self)


@dataclass
class RunPlan:
    """Execution plan created from a validated request."""

    contract_version: str = CONTRACT_VERSION
    source_period: SourcePeriod = field(default_factory=SourcePeriod)
    requested_filters: AnalysisFilters = field(default_factory=AnalysisFilters)
    effective_filters: AnalysisFilters = field(default_factory=AnalysisFilters)
    query_mode: Literal["structured", "natural_language"] = "structured"
    topology: str = "consolidated"
    required_metrics: tuple[str, ...] = (
        "observed_listing_count",
        "sale_listing_count",
        "valid_price_count",
        "median_min_price_inr",
        "median_max_price_inr",
    )

    def validate(self) -> None:
        _require(self.contract_version == CONTRACT_VERSION,
                 "Contract version mismatch")
        _require(isinstance(self.source_period, SourcePeriod),
                 "source_period must be a SourcePeriod")
        # SourcePeriod is immutable and validates itself when constructed.
        _require(isinstance(self.requested_filters, AnalysisFilters),
                 "requested_filters must be an AnalysisFilters instance")
        _require(isinstance(self.effective_filters, AnalysisFilters),
                 "effective_filters must be an AnalysisFilters instance")
        self.requested_filters.validate()
        self.effective_filters.validate()
        _require(self.query_mode == "structured",
                 "Only structured query mode is currently implemented")
        _require(self.topology in {"consolidated", "parallel"},
                 "topology must be 'consolidated' or 'parallel'")
        _require(
            isinstance(self.required_metrics, (tuple, list))
            and all(isinstance(item, str) and bool(item.strip())
                    for item in self.required_metrics),
            "required_metrics must contain non-blank strings",
        )
        _require(
            len(self.required_metrics) == len(set(self.required_metrics)),
            "required_metrics must not contain duplicates",
        )

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(self)


@dataclass
class RuntimeState:
    """Complete internal state for one application run."""

    run_id: str
    request: AnalysisRequest
    plan: RunPlan
    retries: RetryCounters = field(default_factory=RetryCounters)
    coverage_flags: list[CoverageFlag] = field(default_factory=list)
    months: list[MonthState] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    source_sha256: str | None = None

    def _validate_trace(self) -> None:
        _require(isinstance(self.trace, list), "trace must be a list")
        loop_counts = {"coverage_repair": 0, "critique_revision": 0}
        for expected_index, event in enumerate(self.trace):
            _require(isinstance(event, dict), "Each trace event must be an object")
            _require(
                set(event) == TRACE_KEYS,
                f"Trace event {expected_index} must have exactly keys {sorted(TRACE_KEYS)}",
            )
            _require(
                isinstance(event["i"], int) and not isinstance(event["i"], bool)
                and event["i"] == expected_index,
                "Trace indices must be consecutive zero-based integers",
            )
            _require(
                isinstance(event["agent"], str) and event["agent"] in TRACE_AGENTS,
                f"Invalid trace agent at index {expected_index}",
            )
            _require(
                isinstance(event["kind"], str) and event["kind"] in TRACE_KINDS,
                f"Invalid trace kind at index {expected_index}",
            )
            _require(
                isinstance(event["msg"], str) and bool(event["msg"].strip()),
                f"Trace event {expected_index} msg must be non-blank",
            )
            _require(isinstance(event["data"], dict),
                     f"Trace event {expected_index} data must be an object")

            loop_name = event["loop"]
            if event["kind"] == "loop":
                _require(
                    isinstance(loop_name, str) and loop_name in TRACE_LOOPS,
                    "Loop events must name a registered feedback loop",
                )
                loop_counts[loop_name] += 1
            else:
                _require(loop_name is None,
                         "Only kind='loop' events may name a loop")

        _require(
            loop_counts["coverage_repair"] == self.retries.coverage_repair_retries,
            "coverage repair retry count must equal coverage_repair loop events",
        )
        _require(
            loop_counts["critique_revision"] == self.retries.critique_revisions,
            "critique revision count must equal critique_revision loop events",
        )

    def validate(self) -> None:
        _require(
            isinstance(self.run_id, str) and bool(self.run_id.strip()),
            "run_id cannot be blank",
        )
        _require(isinstance(self.request, AnalysisRequest),
                 "request must be an AnalysisRequest")
        _require(isinstance(self.plan, RunPlan), "plan must be a RunPlan")
        _require(isinstance(self.retries, RetryCounters),
                 "retries must be RetryCounters")
        self.request.validate()
        self.plan.validate()
        self.retries.validate()

        _require(
            self.plan.query_mode == self.request.query_mode,
            "Request and plan query_mode must match",
        )
        _require(
            self.plan.requested_filters.to_dict()
            == self.request.requested_filters.to_dict(),
            "Plan requested_filters must match request requested_filters",
        )

        _require(isinstance(self.months, list), "months must be a list")
        _require(isinstance(self.coverage_flags, list), "coverage_flags must be a list")
        _require(
            bool(self.months) == bool(self.coverage_flags),
            "months and coverage_flags must both be empty or both cover the window",
        )
        if self.months:
            _require(
                all(isinstance(month, MonthState) for month in self.months),
                "months must contain MonthState instances",
            )
            _require(
                all(isinstance(flag, CoverageFlag) for flag in self.coverage_flags),
                "coverage_flags must contain CoverageFlag instances",
            )
            month_names = [month.month for month in self.months]
            _require(
                month_names == EXPECTED_MONTHS,
                "Month states must be exactly the 12 ordered contract months",
            )
            coverage_month_names = [flag.month for flag in self.coverage_flags]
            _require(
                coverage_month_names == EXPECTED_MONTHS,
                "Coverage flags must cover all 12 ordered contract months",
            )
            for month, flag in zip(self.months, self.coverage_flags):
                month.validate()
                flag.validate()
                _require(
                    month.observed_listing_count == flag.observed_listing_count
                    and month.sale_listing_count == flag.sale_listing_count
                    and month.valid_price_count == flag.valid_price_count
                    and month.coverage_status == flag.coverage_status
                    and month.is_partial_month == flag.is_partial_month,
                    f"MonthState and CoverageFlag disagree for {month.month}",
                )

        _require(
            isinstance(self.source_sha256, (str, type(None))),
            "source_sha256 must be a string or null",
        )
        if self.source_sha256 is not None:
            _require(
                bool(re.fullmatch(r"[0-9a-f]{64}", self.source_sha256)),
                "source_sha256 must be a lowercase SHA-256 hex digest",
            )
        self._validate_trace()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return _json_ready(self)

    def fingerprint(self) -> str:
        """Stable fingerprint excluding run_id itself."""
        payload = self.to_dict()
        payload.pop("run_id", None)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_runtime_state(
    *,
    request: AnalysisRequest | None = None,
    effective_filters: AnalysisFilters | None = None,
    run_id: str = "draft-run",
) -> RuntimeState:
    """Construct a valid initial state before data processing begins."""
    if request is None:
        request = AnalysisRequest()
    request.validate()

    if effective_filters is None:
        effective_filters = AnalysisFilters()
    effective_filters.validate()

    plan = RunPlan(
        source_period=SourcePeriod(),
        requested_filters=request.requested_filters,
        effective_filters=effective_filters,
        query_mode=request.query_mode,
        topology="consolidated",
    )
    plan.validate()

    state = RuntimeState(run_id=run_id, request=request, plan=plan)
    state.validate()
    return state
