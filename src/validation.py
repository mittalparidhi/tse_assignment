# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
"""Request validation at the application boundary (contracts/Criteria.md §3-4).

Ported from the first implementation's Criteria agent
(``legacy/app/criteria_agent.py``). A request is a plain mapping -- what the
dashboard sidebar or any programmatic caller supplies -- and is either turned
into a ``Criteria`` or rejected with a stable error code naming the field.

Every check is against values actually observed in the canonical frame, so a
request can never name a locality, BHK count or month the snapshot does not
contain. Unknown fields are rejected rather than silently ignored.

Metamorphic transformations deliberately do NOT pass through here: the
harness builds follow-up ``Criteria`` directly, so a valid transformation is
never rejected by a request-boundary rule. Base inputs themselves must pass.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields
from typing import Any, Mapping

import pandas as pd

from .contract import AREA_SCALE, CURRENCY_SCALE, DEFAULT_WINDOW_END
from .loading import DWELLING_TYPES, HYDERABAD_BBOX
from .trend import Criteria

#: Largest BHK the source supports; larger values are data-entry noise.
MAX_SUPPORTED_BHK = 10
MAX_GEO_RADIUS_KM = 100.0
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
#: Placeholder the loader uses when a listing has no locality name.
_UNKNOWN_LOCALITY = "Unknown"

_ALLOWED_FIELDS = frozenset(f.name for f in fields(Criteria))


class CriteriaValidationError(ValueError):
    """A user-facing validation failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict[str, str]:
        return {"status": "error", "error_code": self.code,
                "message": self.message}


def _norm(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


@dataclass(frozen=True)
class SourceCatalog:
    """The values a request may name, read from the canonical frame."""

    months: tuple[str, ...]
    bhk_values: tuple[int, ...]
    localities: dict[str, str]          # normalised -> canonical spelling
    property_types: tuple[str, ...]
    locality_ids: frozenset[str] = frozenset()
    cities: dict[str, str] = None       # normalised -> canonical spelling

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "SourceCatalog":
        bhk = pd.to_numeric(frame["bhk"], errors="coerce").dropna()
        bhk = bhk[(bhk == bhk.round()) & bhk.between(1, MAX_SUPPORTED_BHK)]
        names = sorted({str(n) for n in frame["locality"].dropna()}
                       - {_UNKNOWN_LOCALITY})
        return cls(
            months=tuple(sorted(frame["month"].dropna().unique().tolist())),
            bhk_values=tuple(sorted({int(b) for b in bhk})),
            localities={_norm(n): n for n in names},
            property_types=tuple(sorted(
                set(frame["property_type"].dropna()) & set(DWELLING_TYPES))),
            locality_ids=frozenset(str(i) for i in frame["locality_id"].dropna())
            if "locality_id" in frame.columns else frozenset(),
            cities={_norm(c): c for c in frame["city"].dropna().unique()},
        )


def _string_list(value: Any, name: str) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or any(
            not isinstance(v, str) or not v.strip() for v in value):
        raise CriteriaValidationError(
            f"invalid_{name}", f"{name} must be a string or a list of non-blank strings")
    out, seen = [], set()
    for item in value:                     # de-duplicate, keep first order
        key = _norm(item)
        if key not in seen:
            out.append(item.strip())
            seen.add(key)
    return out


def _positive(value: Any, name: str, code: str) -> float | None:
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) or value <= 0):
        raise CriteriaValidationError(
            code, f"{name} must be a finite number greater than zero")
    return float(value)


def validate_request(request: Mapping[str, Any],
                     catalog: SourceCatalog) -> Criteria:
    """Return a validated ``Criteria`` or raise ``CriteriaValidationError``."""
    if not isinstance(request, Mapping):
        raise CriteriaValidationError(
            "invalid_request", "request must be a mapping of field to value")
    unknown = sorted(set(request) - _ALLOWED_FIELDS)
    if unknown:
        raise CriteriaValidationError(
            "unknown_request_fields", f"unknown request fields: {unknown}")

    # Rule 2 -- window.
    window_end = request.get("window_end", DEFAULT_WINDOW_END)
    if not isinstance(window_end, str) or not _MONTH_RE.fullmatch(window_end):
        raise CriteriaValidationError(
            "invalid_date_format", "window_end must use YYYY-MM")
    if window_end not in catalog.months:
        raise CriteriaValidationError(
            "unsupported_date_window",
            f"window_end {window_end} is not in the snapshot "
            f"({catalog.months[0]} to {catalog.months[-1]})")

    # Rule 3 -- BHK.
    bhk = request.get("bhk")
    if bhk is not None:
        values = [bhk] if isinstance(bhk, (int, float)) else bhk
        if not isinstance(values, (list, tuple)) or not values:
            raise CriteriaValidationError(
                "invalid_bhk", "bhk must be a whole number or a list of them")
        clean: set[int] = set()
        for item in values:
            if (isinstance(item, bool) or not isinstance(item, (int, float))
                    or not math.isfinite(float(item))
                    or not float(item).is_integer()):
                raise CriteriaValidationError(
                    "invalid_bhk", "every BHK value must be a whole number")
            if int(item) not in catalog.bhk_values:
                raise CriteriaValidationError(
                    "unsupported_bhk",
                    f"BHK {int(item)} is not in the snapshot's domain "
                    f"{list(catalog.bhk_values)}")
            clean.add(int(item))
        bhk = tuple(sorted(clean))

    # Rule 4 -- localities, canonicalised.
    localities = request.get("localities")
    if localities is not None:
        canon = []
        for name in _string_list(localities, "localities"):
            # A locality name (any case/spacing) or a source LOCALITY_ID.
            match = catalog.localities.get(_norm(name))
            if match is None and name.strip() in catalog.locality_ids:
                match = name.strip()
            if match is None:
                raise CriteriaValidationError(
                    "unsupported_locality",
                    f"locality {name!r} is not in the snapshot")
            canon.append(match)
        localities = tuple(canon) or None

    # Rule 4b -- city scope (design note §3: user-selectable; both by default).
    cities = request.get("cities")
    if cities is not None:
        canon = []
        for name in _string_list(cities, "cities"):
            match = (catalog.cities or {}).get(_norm(name))
            if match is None:
                raise CriteriaValidationError(
                    "unsupported_city",
                    f"city {name!r} is not in the snapshot "
                    f"{sorted((catalog.cities or {}).values())}")
            canon.append(match)
        cities = tuple(canon) or None

    # Rule 5 -- property types.
    property_types = request.get("property_types")
    if property_types is not None:
        allowed = {_norm(t): t for t in catalog.property_types}
        canon = []
        for name in _string_list(property_types, "property_types"):
            if _norm(name) not in allowed:
                raise CriteriaValidationError(
                    "unsupported_property_type",
                    f"property type {name!r} is not a dwelling type in the "
                    f"snapshot {list(catalog.property_types)}")
            canon.append(allowed[_norm(name)])
        property_types = tuple(canon) or None

    # Rule 6 -- price band, in rupees.
    lo = _positive(request.get("price_min_inr"), "price_min_inr", "invalid_price")
    hi = _positive(request.get("price_max_inr"), "price_max_inr", "invalid_price")
    if lo is not None and hi is not None and lo > hi:
        raise CriteriaValidationError(
            "invalid_price_range", "price_min_inr cannot exceed price_max_inr")

    # Rule 7 -- display units.
    currency = request.get("currency_unit", "INR")
    area = request.get("area_unit", "SQFT")
    if currency not in CURRENCY_SCALE or area not in AREA_SCALE:
        raise CriteriaValidationError(
            "unsupported_unit",
            f"currency_unit must be one of {list(CURRENCY_SCALE)} and "
            f"area_unit one of {list(AREA_SCALE)}")

    # Rule 8 -- geography and query_mode.
    radius = request.get("radius_km")
    lat, lon = request.get("center_lat"), request.get("center_lon")
    inferred = "RADIUS" if radius is not None else "EXACT_LOCALITY"
    mode = request.get("query_mode", inferred)
    if mode == "GEO_RADIUS":            # the design note's name for RADIUS
        mode = "RADIUS"
    if mode not in ("EXACT_LOCALITY", "RADIUS"):
        raise CriteriaValidationError(
            "query_mode_mismatch",
            "query_mode must be EXACT_LOCALITY or GEO_RADIUS (alias RADIUS)")
    if mode != inferred:
        raise CriteriaValidationError(
            "query_mode_mismatch",
            f"query_mode {mode} conflicts with the supplied geography; "
            f"expected {inferred}")
    if mode == "RADIUS":
        if localities:
            raise CriteriaValidationError(
                "query_mode_mismatch",
                "a RADIUS query takes a centre and radius, not localities")
        radius = _positive(radius, "radius_km", "invalid_geo_radius")
        if radius > MAX_GEO_RADIUS_KM:
            raise CriteriaValidationError(
                "invalid_geo_radius",
                f"radius_km must be at most {MAX_GEO_RADIUS_KM:g}")
        if lat is None or lon is None:
            raise CriteriaValidationError(
                "missing_geo_center", "a RADIUS query needs center_lat and center_lon")
        lat_min, lat_max, lon_min, lon_max = HYDERABAD_BBOX
        if (isinstance(lat, bool) or isinstance(lon, bool)
                or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float))
                or not (lat_min < lat < lat_max and lon_min < lon < lon_max)):
            raise CriteriaValidationError(
                "invalid_geo_center",
                f"the centre must lie in the Hyderabad area "
                f"(lat {lat_min}-{lat_max}, lon {lon_min}-{lon_max})")
        lat, lon = float(lat), float(lon)
    elif lat is not None or lon is not None:
        raise CriteriaValidationError(
            "query_mode_mismatch", "a centre was given without a radius")

    label = request.get("label", "")
    if not isinstance(label, str):
        raise CriteriaValidationError("invalid_request", "label must be a string")

    return Criteria(
        window_end=window_end, bhk=bhk, localities=localities, cities=cities,
        property_types=property_types, price_min_inr=lo, price_max_inr=hi,
        currency_unit=currency, area_unit=area, query_mode=mode,
        center_lat=lat, center_lon=lon, radius_km=radius, label=label,
    )


def criteria_as_request(criteria: Criteria) -> dict[str, Any]:
    """The request mapping that describes ``criteria``; used to check that a
    harness base input would itself pass validation."""
    out: dict[str, Any] = {}
    for f in fields(Criteria):
        value = getattr(criteria, f.name)
        if value is None or (f.name == "query_mode" and value == "EXACT_LOCALITY"):
            continue
        out[f.name] = list(value) if isinstance(value, tuple) else value
    return out
