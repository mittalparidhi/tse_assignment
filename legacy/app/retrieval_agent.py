# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
"""Deterministic retrieval for the frozen Hyderabad housing snapshot.

Supported behavior:
* exact locality matching by parsed LOCALITY_NAME or LOCALITY_ID;
* GEO_RADIUS using validated LATITUDE/LONGITUDE values in MAP_DETAILS;
* inclusive calendar-month bounds from REGISTER_DATE__U;
* source-derived city, BHK, property type, and INR price-band filters.

Only ``json.loads`` and ``ast.literal_eval`` are used for parsing dict-like CSV
cells. The raw CSV is never modified. ``source_row_id`` is a zero-based raw-row
ordinal attached to returned copies for stable traceability.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from app.criteria_agent import CriteriaResult, FilterSpec, QueryMode
from app.schemas import FROZEN_SOURCE_SHA256, SourcePeriod
from app.snapshot_repository import SnapshotRepositoryError, load_processed_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"
PRICE_SENTINEL = 2147483647
EARTH_RADIUS_KM = 6371.0088


class RetrievalError(ValueError):
    """Stable retrieval-layer error with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict[str, str]:
        return {"status": "error", "error_code": self.code, "message": self.message}


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return " ".join(str(value).strip().split()).casefold()


def _safe_dict(value: Any) -> dict[str, Any]:
    """Safely parse a dict cell; reject all non-dict or malformed payloads."""
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    text = value.strip()
    # Most source cells use Python-dict repr (single quotes / None); some may
    # be valid JSON. Neither parser executes expressions or statements.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    return {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coordinate_pair(value: Any) -> tuple[float, float] | None:
    payload = _safe_dict(value)
    if not payload:
        return None
    try:
        lat = float(payload.get("LATITUDE"))
        lon = float(payload.get("LONGITUDE"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _valid_price_bounds(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    lo = pd.to_numeric(frame["MIN_PRICE"], errors="coerce")
    hi = pd.to_numeric(frame["MAX_PRICE"], errors="coerce")
    valid = (
        np.isfinite(lo)
        & np.isfinite(hi)
        & lo.gt(0)
        & hi.gt(0)
        & lo.ne(PRICE_SENTINEL)
        & hi.ne(PRICE_SENTINEL)
        & lo.le(hi)
    )
    return lo.where(valid), hi.where(valid)


def _month_number(value: str) -> int:
    if not isinstance(value, str) or len(value) != 7 or value[4] != "-":
        raise RetrievalError("invalid_source_period", f"Invalid calendar month: {value!r}")
    try:
        year, month = int(value[:4]), int(value[5:7])
    except ValueError:
        raise RetrievalError("invalid_source_period", f"Invalid calendar month: {value!r}") from None
    if year < 1 or not 1 <= month <= 12:
        raise RetrievalError("invalid_source_period", f"Invalid calendar month: {value!r}")
    return year * 100 + month


def _registration_months(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    dates = pd.to_datetime(series, errors="coerce")
    valid = dates.notna()
    month_numbers = (dates.dt.year * 100 + dates.dt.month).where(valid)
    return month_numbers, valid


def _haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorized great-circle distances for valid lat/lon arrays."""
    p1 = math.radians(lat1)
    p2 = np.radians(lat2)
    dlat = p2 - p1
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


@dataclass(frozen=True)
class RetrievalResult:
    """Selected source rows plus reproducibility and parsing diagnostics."""

    rows: pd.DataFrame
    query_mode: QueryMode
    source_sha256: str
    raw_row_count: int
    invalid_registration_date_rows: int
    malformed_location_rows: int
    invalid_coordinate_rows: int
    source_period_start: str
    source_period_end: str
    center_latitude: float | None = None
    center_longitude: float | None = None

    @property
    def selected_row_count(self) -> int:
        return int(len(self.rows))

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "ok",
            "query_mode": self.query_mode.value,
            "source_sha256": self.source_sha256,
            "raw_row_count": self.raw_row_count,
            "selected_row_count": self.selected_row_count,
            "invalid_registration_date_rows": self.invalid_registration_date_rows,
            "malformed_location_rows": self.malformed_location_rows,
            "invalid_coordinate_rows": self.invalid_coordinate_rows,
            "source_period_start": self.source_period_start,
            "source_period_end": self.source_period_end,
            "center_coordinates": (
                {"latitude": self.center_latitude, "longitude": self.center_longitude}
                if self.center_latitude is not None and self.center_longitude is not None
                else None
            ),
        }
        if include_rows:
            result["rows"] = self.rows.replace({np.nan: None}).to_dict(orient="records")
        return result


class RetrievalAgent:
    """Apply a typed Criteria Agent result to the pinned canonical snapshot."""

    REQUIRED_COLUMNS = {
        "CITY", "PROPERTY_TYPE", "BEDROOM_NUM", "MIN_PRICE", "MAX_PRICE",
        "REGISTER_DATE__U", "MAP_DETAILS", "location", "PROP_ID",
    }

    def __init__(
        self,
        source_path: str | Path = DEFAULT_SOURCE_PATH,
        *,
        expected_sha256: str | None = FROZEN_SOURCE_SHA256,
    ) -> None:
        self.source_path = Path(source_path)
        self.expected_sha256 = expected_sha256

    def retrieve(
        self,
        criteria: CriteriaResult | FilterSpec,
        query_mode: QueryMode | str | None = None,
    ) -> RetrievalResult:
        spec, mode = self._unwrap(criteria, query_mode)
        is_default_processed = self.source_path.resolve() == DEFAULT_SOURCE_PATH.resolve()
        if is_default_processed:
            try:
                frame, digest = load_processed_snapshot()
            except SnapshotRepositoryError as exc:
                raise RetrievalError(exc.code, exc.message) from exc
        else:
            # Explicit raw paths and temporary fixture paths remain supported.
            if not self.source_path.is_file():
                raise RetrievalError("source_missing", f"Frozen source CSV not found: {self.source_path}")
            digest = _sha256(self.source_path)
            if self.expected_sha256 is not None and digest != self.expected_sha256:
                raise RetrievalError(
                    "snapshot_integrity_error",
                    "Raw CSV digest differs from the pinned frozen snapshot SHA-256.",
                )
            frame = pd.read_csv(self.source_path, low_memory=False)

        if self.expected_sha256 is not None and digest != self.expected_sha256:
            raise RetrievalError(
                "snapshot_integrity_error",
                "Source provenance hash differs from the pinned frozen raw snapshot SHA-256.",
            )

        missing = sorted(self.REQUIRED_COLUMNS - set(frame.columns))
        if missing:
            raise RetrievalError("source_schema_error", f"Frozen source lacks required columns: {missing}")
        frame = frame.copy()
        if "source_row_id" not in frame.columns:
            frame.insert(0, "source_row_id", np.arange(len(frame), dtype=np.int64))
        else:
            try:
                frame["source_row_id"] = pd.to_numeric(frame["source_row_id"], errors="raise").astype(np.int64)
            except (TypeError, ValueError, OverflowError) as exc:
                raise RetrievalError("source_schema_error", "source_row_id must contain integer row identities.") from exc

        start_month = getattr(spec.source_period, "start_month", None)
        end_month = getattr(spec.source_period, "end_month", None)
        start_n = _month_number(start_month)
        end_n = _month_number(end_month)
        if start_n > end_n:
            raise RetrievalError("invalid_source_period", "start_month must not be after end_month")

        registration_month_n, registration_valid = _registration_months(frame["REGISTER_DATE__U"])
        in_period = registration_valid & registration_month_n.ge(start_n) & registration_month_n.le(end_n)

        location_payloads = frame["location"].map(_safe_dict)
        malformed_location = location_payloads.map(lambda item: not bool(item))
        locality_names = location_payloads.map(lambda item: _norm(item.get("LOCALITY_NAME")))
        locality_ids = location_payloads.map(lambda item: _norm(item.get("LOCALITY_ID")))
        embedded_cities = location_payloads.map(lambda item: _norm(item.get("CITY_NAME")))
        top_cities = frame["CITY"].map(_norm)
        row_cities = top_cities.where(top_cities.ne(""), embedded_cities)

        map_payloads = frame["MAP_DETAILS"].map(_coordinate_pair)
        coord_valid = map_payloads.map(lambda pair: pair is not None)
        latitudes = map_payloads.map(lambda pair: pair[0] if pair is not None else np.nan).astype(float)
        longitudes = map_payloads.map(lambda pair: pair[1] if pair is not None else np.nan).astype(float)

        mask = in_period.copy()
        mask &= row_cities.eq(_norm(spec.city))

        if mode is QueryMode.EXACT_LOCALITY and spec.geo_radius_km is not None:
            raise RetrievalError(
                "query_mode_mismatch",
                "EXACT_LOCALITY cannot be used when geo_radius_km is specified.",
            )
        if mode is QueryMode.GEO_RADIUS and spec.geo_radius_km is None:
            raise RetrievalError("invalid_geo_radius", "GEO_RADIUS requires geo_radius_km")

        center_lat: float | None = None
        center_lon: float | None = None
        if mode is QueryMode.EXACT_LOCALITY:
            tokens = tuple(_norm(item) for item in spec.localities)
            if not tokens:
                raise RetrievalError("missing_locality", "Exact-locality retrieval requires at least one locality name or ID")
            locality_match = locality_names.isin(tokens) | locality_ids.isin(tokens)
            mask &= locality_match
        elif mode is QueryMode.GEO_RADIUS:
            if spec.geo_radius_km is None or isinstance(spec.geo_radius_km, bool):
                raise RetrievalError("invalid_geo_radius", "GEO_RADIUS requires geo_radius_km")
            radius = float(spec.geo_radius_km)
            if not math.isfinite(radius) or radius <= 0 or radius > 100:
                raise RetrievalError("invalid_geo_radius", "geo_radius_km must be finite, > 0, and <= 100")
            if len(spec.localities) != 1:
                raise RetrievalError("ambiguous_geo_radius_center", "GEO_RADIUS requires exactly one centre locality or ID")
            center_token = _norm(spec.localities[0])
            center_rows = (
                row_cities.eq(_norm(spec.city))
                & (locality_names.eq(center_token) | locality_ids.eq(center_token))
                & coord_valid
            )
            if not bool(center_rows.any()):
                raise RetrievalError(
                    "center_coordinates_unavailable",
                    "No valid MAP_DETAILS coordinates are available for the centre locality in the selected city.",
                )
            # Deterministic locality anchor: independent medians of valid source
            # coordinates for the selected centre locality.
            center_lat = float(latitudes.loc[center_rows].median())
            center_lon = float(longitudes.loc[center_rows].median())
            distances = np.full(len(frame), np.inf, dtype=float)
            valid_idx = np.flatnonzero(coord_valid.to_numpy())
            if len(valid_idx):
                distances[valid_idx] = _haversine_km(
                    center_lat,
                    center_lon,
                    latitudes.iloc[valid_idx].to_numpy(dtype=float),
                    longitudes.iloc[valid_idx].to_numpy(dtype=float),
                )
            mask &= coord_valid & pd.Series(distances <= radius, index=frame.index)
        else:
            raise RetrievalError("unsupported_query_mode", f"Unsupported query mode: {mode!r}")

        if spec.property_types:
            allowed_types = {_norm(item) for item in spec.property_types}
            mask &= frame["PROPERTY_TYPE"].map(_norm).isin(allowed_types)

        if spec.bhk:
            bedrooms = pd.to_numeric(frame["BEDROOM_NUM"], errors="coerce")
            bhk_values = set(int(item) for item in spec.bhk)
            mask &= bedrooms.isin(bhk_values)

        lo, hi = _valid_price_bounds(frame)
        if spec.min_price_inr is not None:
            if isinstance(spec.min_price_inr, bool):
                raise RetrievalError("invalid_price", "min_price_inr must be numeric, not boolean")
            minimum = float(spec.min_price_inr)
            if not math.isfinite(minimum) or minimum <= 0:
                raise RetrievalError("invalid_price", "min_price_inr must be finite and > 0")
            # Inclusive interval overlap: the listing's upper bound must be >=
            # requested lower bound. Invalid price ranges never match a price filter.
            mask &= hi.notna() & hi.ge(minimum)
        if spec.max_price_inr is not None:
            if isinstance(spec.max_price_inr, bool):
                raise RetrievalError("invalid_price", "max_price_inr must be numeric, not boolean")
            maximum = float(spec.max_price_inr)
            if not math.isfinite(maximum) or maximum <= 0:
                raise RetrievalError("invalid_price", "max_price_inr must be finite and > 0")
            mask &= lo.notna() & lo.le(maximum)
        if spec.min_price_inr is not None and spec.max_price_inr is not None:
            if float(spec.min_price_inr) > float(spec.max_price_inr):
                raise RetrievalError("invalid_price_range", "min_price_inr cannot exceed max_price_inr")

        selected = frame.loc[mask].copy().reset_index(drop=True)
        return RetrievalResult(
            rows=selected,
            query_mode=mode,
            source_sha256=digest,
            raw_row_count=len(frame),
            invalid_registration_date_rows=int((~registration_valid).sum()),
            malformed_location_rows=int(malformed_location.sum()),
            invalid_coordinate_rows=int((~coord_valid).sum()),
            source_period_start=start_month,
            source_period_end=end_month,
            center_latitude=center_lat,
            center_longitude=center_lon,
        )

    @staticmethod
    def _unwrap(
        criteria: CriteriaResult | FilterSpec,
        mode: QueryMode | str | None,
    ) -> tuple[FilterSpec, QueryMode]:
        if isinstance(criteria, CriteriaResult):
            spec = criteria.filter_spec
            inferred = criteria.query_mode
            if mode is not None and RetrievalAgent._parse_mode(mode) is not inferred:
                raise RetrievalError("query_mode_mismatch", "Explicit query mode conflicts with CriteriaResult.query_mode")
            return spec, inferred
        if not isinstance(criteria, FilterSpec):
            raise TypeError("criteria must be a CriteriaResult or FilterSpec")
        inferred_mode = QueryMode.GEO_RADIUS if criteria.geo_radius_km is not None else QueryMode.EXACT_LOCALITY
        return criteria, RetrievalAgent._parse_mode(mode) if mode is not None else inferred_mode

    @staticmethod
    def _parse_mode(mode: QueryMode | str) -> QueryMode:
        if isinstance(mode, QueryMode):
            return mode
        try:
            return QueryMode(str(mode).upper())
        except ValueError:
            raise RetrievalError("unsupported_query_mode", f"Unsupported query mode: {mode!r}") from None


def retrieve_rows(
    criteria: CriteriaResult | FilterSpec,
    *,
    source_path: str | Path = DEFAULT_SOURCE_PATH,
    query_mode: QueryMode | str | None = None,
) -> pd.DataFrame:
    """Convenience API returning selected rows only."""
    return RetrievalAgent(source_path).retrieve(criteria, query_mode).rows
