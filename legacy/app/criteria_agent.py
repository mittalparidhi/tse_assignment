"""Typed Criteria Agent for the frozen Hyderabad housing snapshot.

The agent validates a structured request against values observed in the frozen
source, anchors calendar dates to the source's exact 12-month period, and
chooses a typed geographic query mode. It does not execute filters against the
listing rows; that is a downstream scanner responsibility.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from app.schemas import (
    FROZEN_SOURCE_SHA256,
    WINDOW_END,
    WINDOW_START,
    SourcePeriod,
)
from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"
# Implausibly large source bedroom counts are present in a small number of rows.
# The Criteria Agent supports only source-observed 1..10 BHK values.
MAX_SUPPORTED_BHK = 10
MAX_GEO_RADIUS_KM = 100.0
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class QueryMode(str, Enum):
    EXACT_LOCALITY = "EXACT_LOCALITY"
    GEO_RADIUS = "GEO_RADIUS"


class CriteriaValidationError(ValueError):
    """A user-facing, stable Criteria Agent validation failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict[str, str]:
        return {"status": "error", "error_code": self.code, "message": self.message}


def _norm(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _canonical(value: str, allowed: Mapping[str, str], field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CriteriaValidationError("invalid_" + field_name, f"{field_name} must be a non-blank string")
    canonical = allowed.get(_norm(value))
    if canonical is None:
        raise CriteriaValidationError(
            "unsupported_" + field_name,
            f"Unsupported {field_name} {value!r}; choose a value present in the frozen source.",
        )
    return canonical


def _as_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise CriteriaValidationError("invalid_" + field_name, f"{field_name} must be a string or a list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise CriteriaValidationError("invalid_" + field_name, f"{field_name} must contain only non-blank strings")
    # Case-insensitive stable de-duplication preserves first-request order.
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        key = _norm(item)
        if key not in seen:
            result.append(item.strip())
            seen.add(key)
    return result


def _as_bhk_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise CriteriaValidationError("invalid_bhk", "bhk must be an integer or a list of integers")


def _positive_inr(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CriteriaValidationError("invalid_price", f"{field_name} must be a numeric INR amount")
    if not math.isfinite(float(value)) or value <= 0:
        raise CriteriaValidationError("invalid_price", f"{field_name} must be finite and greater than zero INR")
    return int(value) if float(value).is_integer() else float(value)


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceCatalog:
    """Canonical values and city/locality relationships from the pinned CSV."""

    cities: tuple[str, ...]
    localities_by_city: Mapping[str, tuple[str, ...]]
    property_types: tuple[str, ...]
    bhk_values: tuple[int, ...]
    source_sha256: str
    # Appended with a default to preserve positional construction by existing callers.
    locality_ids_by_city: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def from_csv(cls, path: str | Path = DEFAULT_SOURCE_PATH) -> "SourceCatalog":
        source_path = Path(path)
        if not source_path.is_file():
            raise CriteriaValidationError("source_missing", f"Frozen source CSV not found: {source_path}")
        if source_path.resolve() == DEFAULT_SOURCE_PATH.resolve():
            try:
                _, digest = load_processed_snapshot()
            except SnapshotRepositoryError as exc:
                raise CriteriaValidationError(exc.code, exc.message) from exc
        else:
            # Explicit custom paths preserve the original pinned-raw/fixture behavior.
            digest = _source_sha256(source_path)
        if digest != FROZEN_SOURCE_SHA256:
            raise CriteriaValidationError(
                "snapshot_integrity_error",
                "The Criteria Agent source hash does not match the frozen Hyderabad snapshot.",
            )

        cities: dict[str, str] = {}
        locality_sets: dict[str, dict[str, str]] = {}
        locality_id_candidates: dict[str, dict[str, set[str]]] = {}
        property_types: dict[str, str] = {}
        bhk_values: set[int] = set()
        with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"CITY", "PROPERTY_TYPE", "BEDROOM_NUM", "location"}
            missing = sorted(required - set(reader.fieldnames or []))
            if missing:
                raise CriteriaValidationError("source_schema_error", f"Frozen source lacks required columns: {missing}")
            for row in reader:
                city_cell = (row.get("CITY") or "").strip()
                if city_cell:
                    cities.setdefault(_norm(city_cell), city_cell)

                kind = (row.get("PROPERTY_TYPE") or "").strip()
                if kind:
                    property_types.setdefault(_norm(kind), kind)

                bedroom_text = (row.get("BEDROOM_NUM") or "").strip()
                if bedroom_text:
                    try:
                        number = float(bedroom_text)
                    except ValueError:
                        number = float("nan")
                    if math.isfinite(number) and number.is_integer() and 1 <= int(number) <= MAX_SUPPORTED_BHK:
                        bhk_values.add(int(number))

                location_text = (row.get("location") or "").strip()
                if not location_text:
                    continue
                try:
                    location = ast.literal_eval(location_text)
                except (ValueError, SyntaxError):
                    continue
                if not isinstance(location, dict):
                    continue
                loc_city = location.get("CITY_NAME")
                loc_name = location.get("LOCALITY_NAME")
                if isinstance(loc_city, str) and loc_city.strip() and isinstance(loc_name, str) and loc_name.strip():
                    city = loc_city.strip()
                    locality = loc_name.strip()
                    city_key = _norm(city)
                    locality_sets.setdefault(city_key, {})
                    locality_sets[city_key].setdefault(_norm(locality), locality)
                    # IDs such as empty/0 are placeholders in this source and are
                    # not treated as usable locality identifiers. Keep only IDs
                    # that consistently identify one locality within a city.
                    locality_id = str(location.get("LOCALITY_ID") or "").strip()
                    if locality_id and locality_id != "0":
                        locality_id_candidates.setdefault(city_key, {}).setdefault(
                            _norm(locality_id), set()
                        ).add(locality_id)
                    # The embedded map is authoritative for the city/locality relation.
                    cities.setdefault(_norm(city), city)

        if not cities or not locality_sets or not property_types or not bhk_values:
            raise CriteriaValidationError("source_catalog_empty", "Unable to build a complete catalog from the frozen source")
        canon_localities = {
            city_key: tuple(sorted(values.values(), key=lambda item: (_norm(item), item)))
            for city_key, values in locality_sets.items()
        }
        canon_locality_ids = {
            city_key: {
                norm_id: next(iter(values))
                for norm_id, values in candidates.items()
                if len(values) == 1
            }
            for city_key, candidates in locality_id_candidates.items()
        }
        return cls(
            cities=tuple(sorted(cities.values(), key=lambda item: (_norm(item), item))),
            localities_by_city=canon_localities,
            locality_ids_by_city=canon_locality_ids,
            property_types=tuple(sorted(property_types.values(), key=lambda item: (_norm(item), item))),
            bhk_values=tuple(sorted(bhk_values)),
            source_sha256=digest,
        )

    def canonical_city(self, value: str) -> str:
        city_map = {_norm(item): item for item in self.cities}
        return _canonical(value, city_map, "city")

    def canonical_locality(self, city: str, value: str) -> str:
        city_key = _norm(city)
        city_localities = self.localities_by_city.get(city_key, ())
        loc_map = {_norm(item): item for item in city_localities}
        normalized = _norm(value)
        if normalized in loc_map:
            return loc_map[normalized]
        # Preserve source-known locality IDs as strings so the Retrieval Agent
        # can compare them directly with parsed location.LOCALITY_ID values.
        id_map = self.locality_ids_by_city.get(city_key, {})
        if normalized in id_map:
            return id_map[normalized]
        raise CriteriaValidationError(
            "unsupported_locality",
            f"Unsupported locality or locality ID {value!r}; choose a value present in the frozen source for {city!r}.",
        )

    def canonical_property_type(self, value: str) -> str:
        type_map = {_norm(item): item for item in self.property_types}
        return _canonical(value, type_map, "property_type")


@dataclass(frozen=True)
class FilterSpec:
    """Normalized, typed filter specification for a housing request."""

    city: str
    localities: tuple[str, ...]
    bhk: tuple[int, ...] = ()
    property_types: tuple[str, ...] = ()
    min_price_inr: int | float | None = None
    max_price_inr: int | float | None = None
    geo_radius_km: float | None = None
    source_period: SourcePeriod = field(default_factory=SourcePeriod)

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "localities": list(self.localities),
            "bhk": list(self.bhk),
            "property_types": list(self.property_types),
            "min_price_inr": self.min_price_inr,
            "max_price_inr": self.max_price_inr,
            "geo_radius_km": self.geo_radius_km,
            "source_period": self.source_period.to_dict(),
        }


@dataclass(frozen=True)
class CriteriaResult:
    filter_spec: FilterSpec
    query_mode: QueryMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "filter_spec": self.filter_spec.to_dict(),
            "query_mode": self.query_mode.value,
        }


class CriteriaAgent:
    """Validate a structured request and choose a geographic query mode."""

    _ALLOWED_KEYS = {
        "city", "locality", "localities", "bhk", "property_type", "property_types",
        "min_price_inr", "max_price_inr", "geo_radius_km", "start_month", "end_month", "query_mode",
    }

    def __init__(self, catalog: SourceCatalog | None = None, source_path: str | Path = DEFAULT_SOURCE_PATH) -> None:
        self.catalog = catalog if catalog is not None else SourceCatalog.from_csv(source_path)

    def run(self, request: Mapping[str, Any]) -> CriteriaResult:
        if not isinstance(request, Mapping):
            raise CriteriaValidationError("invalid_request", "Request must be a structured mapping/object")
        unknown = sorted(set(request) - self._ALLOWED_KEYS)
        if unknown:
            raise CriteriaValidationError("unknown_request_fields", f"Unknown request fields: {unknown}")

        # Calendar dates are source-anchored, never relative to today's date.
        start = request.get("start_month")
        end = request.get("end_month")
        if (start is None) != (end is None):
            raise CriteriaValidationError(
                "incomplete_date_window", "Provide both start_month and end_month, or omit both to use the frozen source window."
            )
        if start is None:
            period = SourcePeriod()
        else:
            if not isinstance(start, str) or not MONTH_RE.fullmatch(start) or not isinstance(end, str) or not MONTH_RE.fullmatch(end):
                raise CriteriaValidationError("invalid_date_format", "Calendar bounds must use YYYY-MM format")
            if start != WINDOW_START or end != WINDOW_END:
                raise CriteriaValidationError(
                    "unsupported_date_window",
                    f"Only the source-anchored 12-month window {WINDOW_START} through {WINDOW_END} is supported.",
                )
            period = SourcePeriod(start_month=start, end_month=end)

        city_raw = request.get("city")
        city = self.catalog.canonical_city(city_raw) if isinstance(city_raw, str) else self._invalid_city()

        locality_raw = request.get("localities", request.get("locality"))
        localities_input = _as_string_list(locality_raw, "localities")
        radius_raw = request.get("geo_radius_km")
        radius: float | None = None
        if radius_raw is not None:
            if isinstance(radius_raw, bool) or not isinstance(radius_raw, (int, float)) or not math.isfinite(float(radius_raw)):
                raise CriteriaValidationError("invalid_geo_radius", "geo_radius_km must be a finite numeric distance in kilometres")
            radius = float(radius_raw)
            if radius <= 0 or radius > MAX_GEO_RADIUS_KM:
                raise CriteriaValidationError("invalid_geo_radius", f"geo_radius_km must be greater than 0 and at most {MAX_GEO_RADIUS_KM:g} km")

        if not localities_input:
            raise CriteriaValidationError("missing_geographic_scope", "Provide at least one source-known locality; GEO_RADIUS uses one locality as its centre.")
        if radius is not None and len(localities_input) != 1:
            raise CriteriaValidationError("ambiguous_geo_radius_center", "GEO_RADIUS requires exactly one centre locality")
        localities = tuple(self.catalog.canonical_locality(city, item) for item in localities_input)

        bhk_input = _as_bhk_list(request.get("bhk"))
        bhk_values: list[int] = []
        for item in bhk_input:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) or not float(item).is_integer():
                raise CriteriaValidationError("invalid_bhk", "Every BHK value must be a finite whole number")
            number = int(item)
            if number not in self.catalog.bhk_values:
                raise CriteriaValidationError(
                    "unsupported_bhk", f"BHK {number} is not in the supported source-derived domain {list(self.catalog.bhk_values)}."
                )
            if number not in bhk_values:
                bhk_values.append(number)
        bhk_values.sort()

        property_type_raw = request.get("property_types", request.get("property_type"))
        types_input = _as_string_list(property_type_raw, "property_types")
        property_types = tuple(self.catalog.canonical_property_type(item) for item in types_input)

        min_price = _positive_inr(request.get("min_price_inr"), "min_price_inr")
        max_price = _positive_inr(request.get("max_price_inr"), "max_price_inr")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise CriteriaValidationError("invalid_price_range", "min_price_inr cannot exceed max_price_inr")

        inferred_mode = QueryMode.GEO_RADIUS if radius is not None else QueryMode.EXACT_LOCALITY
        explicit_mode = request.get("query_mode")
        if explicit_mode is not None:
            try:
                mode_value = explicit_mode.value if isinstance(explicit_mode, QueryMode) else str(explicit_mode).upper()
                requested_mode = QueryMode(mode_value)
            except (ValueError, AttributeError):
                raise CriteriaValidationError("unsupported_query_mode", "query_mode must be EXACT_LOCALITY or GEO_RADIUS") from None
            if requested_mode is not inferred_mode:
                raise CriteriaValidationError(
                    "query_mode_mismatch",
                    f"query_mode {requested_mode.value} conflicts with supplied geographic criteria; expected {inferred_mode.value}.",
                )
        else:
            requested_mode = inferred_mode

        spec = FilterSpec(
            city=city,
            localities=localities,
            bhk=tuple(bhk_values),
            property_types=property_types,
            min_price_inr=min_price,
            max_price_inr=max_price,
            geo_radius_km=radius,
            source_period=period,
        )
        return CriteriaResult(filter_spec=spec, query_mode=requested_mode)

    @staticmethod
    def _invalid_city() -> str:
        raise CriteriaValidationError("invalid_city", "city must be a non-blank string")


@lru_cache(maxsize=4)
def load_source_catalog(path: str | Path = DEFAULT_SOURCE_PATH) -> SourceCatalog:
    """Load and cache a catalog keyed by its path; the pinned hash is verified on load."""
    return SourceCatalog.from_csv(Path(path))


def run_criteria_agent(request: Mapping[str, Any], source_path: str | Path = DEFAULT_SOURCE_PATH) -> CriteriaResult:
    """Convenience entry point used by the runtime graph and tests."""
    return CriteriaAgent(catalog=load_source_catalog(str(Path(source_path).resolve()))).run(request)
