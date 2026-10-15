"""Canonical listings -> TrendReport.

This module is the deterministic core: given a frame and a criteria set it
produces exactly one ``TrendReport``. The agents in ``src/agents`` decide
*which* criteria to ask for and *when to stop asking*; they do not re-implement
the statistics. Keeping the arithmetic in one deterministic place is what makes
the metamorphic relations meaningful -- a violation then points at the agent
logic or the data, not at two divergent copies of a median.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from typing import Literal

from .contract import (
    AREA_SCALE,
    CURRENCY_SCALE,
    MIN_SUFFICIENT_N,
    PARTIAL_MONTH,
    AreaUnit,
    CurrencyUnit,
    LocalityStat,
    MonthStat,
    TrendReport,
)


#: Which retrieval algorithm the Retrieval agents execute.
#:
#: This is the design note's genuine dependency: the Criteria agent sets the
#: mode, and Retrieval runs a different algorithm as a result -- not merely
#: the same algorithm over different rows.
QueryMode = Literal["EXACT_LOCALITY", "RADIUS"]

#: Earth radius used by the haversine distance, in kilometres.
EARTH_RADIUS_KM = 6371.0088


def haversine_km(
    lat1: float, lon1: float,
    lat2: "np.ndarray", lon2: "np.ndarray",
) -> "np.ndarray":
    """Great-circle distance from one point to many, in kilometres.

    Used by the RADIUS retrieval path. Haversine rather than a planar
    approximation because Hyderabad spans ~1.7 degrees of latitude in this
    snapshot, where a flat-earth shortcut would distort the catchment.
    """
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


@dataclass(frozen=True)
class Criteria:
    """A user-specified slice. This is the 'base input' an MR perturbs."""

    window_end: str                                  # 'YYYY-MM', inclusive
    bhk: tuple[int, ...] | None = None               # e.g. (2, 3)
    localities: tuple[str, ...] | None = None        # None = all
    property_types: tuple[str, ...] | None = None
    price_min_inr: float | None = None
    price_max_inr: float | None = None
    currency_unit: CurrencyUnit = "INR"
    area_unit: AreaUnit = "SQFT"
    #: Retrieval algorithm selector. EXACT_LOCALITY is the default so that
    #: every existing result set and metamorphic relation is unaffected.
    query_mode: QueryMode = "EXACT_LOCALITY"
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float | None = None
    label: str = ""

    def with_(self, **changes) -> "Criteria":
        """Return a copy with fields replaced -- the MR transformation hook."""
        return replace(self, **changes)

    def describe(self) -> dict:
        return {
            "window_end": self.window_end,
            "bhk": list(self.bhk) if self.bhk else None,
            "localities": list(self.localities) if self.localities else None,
            "property_types": (
                list(self.property_types) if self.property_types else None
            ),
            "price_min_inr": self.price_min_inr,
            "price_max_inr": self.price_max_inr,
            "currency_unit": self.currency_unit,
            "area_unit": self.area_unit,
            "query_mode": self.query_mode,
            "center_lat": self.center_lat,
            "center_lon": self.center_lon,
            "radius_km": self.radius_km,
            "label": self.label,
        }


def month_window(end_month: str, length: int = 12) -> tuple[str, ...]:
    """The ``length`` months ending at and including ``end_month``."""
    end = pd.Period(end_month, freq="M")
    return tuple(str(end - offset) for offset in range(length - 1, -1, -1))


def available_months(frame: pd.DataFrame) -> list[str]:
    return sorted(frame["month"].dropna().unique().tolist())


def apply_geo_filter(frame: pd.DataFrame, criteria: Criteria) -> pd.DataFrame:
    """The RADIUS retrieval path: keep listings within ``radius_km`` of a point.

    Listings with no usable coordinate are **excluded** rather than kept. A
    radius query is a statement about geography, and a row whose location is
    unknown cannot satisfy it; silently keeping them would make a tight radius
    return the whole city. 94.7% of the canonical frame carries coordinates,
    and the exclusion is reported by the Retrieval agent.
    """
    if criteria.center_lat is None or criteria.center_lon is None:
        raise ValueError("RADIUS query_mode requires center_lat and center_lon")
    if not criteria.radius_km:
        raise ValueError("RADIUS query_mode requires a positive radius_km")

    located = frame.dropna(subset=["latitude", "longitude"])
    if located.empty:
        return located
    distance = haversine_km(
        criteria.center_lat, criteria.center_lon,
        located["latitude"].to_numpy(dtype=float),
        located["longitude"].to_numpy(dtype=float),
    )
    return located[distance <= float(criteria.radius_km)]


def apply_criteria(frame: pd.DataFrame, criteria: Criteria) -> pd.DataFrame:
    """Filter to the slice. Price bounds are always in rupees, never display
    units -- a criterion expressed in display units would make the
    currency-invariance MR trivially true and therefore worthless.

    Geography is resolved by ``query_mode``: EXACT_LOCALITY matches the
    locality name list, RADIUS matches great-circle distance from a point.
    The two are mutually exclusive, which is what makes the Criteria agent's
    choice a genuine control dependency rather than a data filter.
    """
    out = frame
    if criteria.bhk is not None:
        out = out[out["bhk"].isin(list(criteria.bhk))]
    if criteria.query_mode == "RADIUS":
        out = apply_geo_filter(out, criteria)
    elif criteria.localities is not None:
        out = out[out["locality"].isin(list(criteria.localities))]
    if criteria.property_types is not None:
        out = out[out["property_type"].isin(list(criteria.property_types))]
    if criteria.price_min_inr is not None:
        out = out[out["price_inr"] >= criteria.price_min_inr]
    if criteria.price_max_inr is not None:
        out = out[out["price_inr"] <= criteria.price_max_inr]
    return out


def _median(values: np.ndarray) -> float | None:
    return float(np.median(values)) if values.size else None


def _quantile(values: np.ndarray, q: float) -> float | None:
    return float(np.quantile(values, q)) if values.size else None


def compute_trend(
    frame: pd.DataFrame,
    criteria: Criteria,
    *,
    min_sufficient_n: int = MIN_SUFFICIENT_N,
    top_localities: int = 10,
    provenance: dict | None = None,
) -> TrendReport:
    """Build the 12-month ``TrendReport`` for one criteria set."""
    window = month_window(criteria.window_end)
    sliced = apply_criteria(frame, criteria)
    in_window = sliced[sliced["month"].isin(window)]

    price_scale = CURRENCY_SCALE[criteria.currency_unit]
    area_scale = AREA_SCALE[criteria.area_unit]
    # psf is a ratio: rupees per sqft -> display-currency per display-area.
    psf_scale = price_scale / area_scale

    grouped = {month: group for month, group in in_window.groupby("month")}

    monthly: list[MonthStat] = []
    for month in window:
        group = grouped.get(month)
        if group is None or group.empty:
            monthly.append(MonthStat(
                month=month, n_active=0, median_psf=None,
                median_min_price_inr=None, median_max_price_inr=None,
                p25_psf=None, p75_psf=None,
                median_age_on_site_days=None, month_is_sufficient=False,
                is_partial_month=(month == PARTIAL_MONTH)))
            continue
        psf = group["psf_inr"].to_numpy(dtype=float) * psf_scale
        min_price = group["price_inr"].to_numpy(dtype=float) * price_scale
        max_price = group["max_price_inr"].to_numpy(dtype=float) * price_scale
        monthly.append(MonthStat(
            month=month,
            n_active=int(len(group)),
            median_psf=_median(psf),
            median_min_price_inr=_median(min_price),
            median_max_price_inr=_median(max_price),
            p25_psf=_quantile(psf, 0.25),
            p75_psf=_quantile(psf, 0.75),
            median_age_on_site_days=_median(
                group["age_on_site_days"].dropna().to_numpy(dtype=float)),
            month_is_sufficient=bool(len(group) >= min_sufficient_n),
            is_partial_month=(month == PARTIAL_MONTH),
        ))

    rankings = _rank_localities(in_window, psf_scale, top_localities,
                               min_n=max(5, min_sufficient_n // 10))
    yoy, yoy_span = _yoy_pct(monthly)

    return TrendReport(
        window_months=window,
        monthly=tuple(monthly),
        locality_rankings=tuple(rankings),
        yoy_median_psf_pct=yoy,
        yoy_span_months=yoy_span,
        n_listings_total=int(len(in_window)),
        currency_unit=criteria.currency_unit,
        area_unit=criteria.area_unit,
        criteria=criteria.describe(),
        provenance=dict(provenance or {}),
    )


def _rank_localities(
    in_window: pd.DataFrame,
    psf_scale: float,
    top_n: int,
    min_n: int,
) -> list[LocalityStat]:
    """Rank localities by median psf, descending.

    Ties are broken by locality name so the ordering is a deterministic
    function of the data. Without this, the reorder-invariance MR would report
    violations caused purely by groupby iteration order -- a harness bug
    masquerading as a fault.
    """
    if in_window.empty:
        return []
    agg = (
        in_window.groupby("locality")["psf_inr"]
        .agg(n_active="size", median_psf="median")
        .reset_index()
    )
    agg = agg[agg["n_active"] >= min_n]
    if agg.empty:
        return []
    agg["median_psf"] = agg["median_psf"] * psf_scale
    agg = agg.sort_values(
        ["median_psf", "locality"], ascending=[False, True], kind="mergesort"
    ).head(top_n)
    return [
        LocalityStat(
            locality=str(row.locality),
            n_active=int(row.n_active),
            median_psf=float(row.median_psf),
            rank=position,
        )
        for position, row in enumerate(agg.itertuples(index=False), start=1)
    ]


def _yoy_pct(monthly: Sequence[MonthStat]) -> tuple[float | None, int]:
    """Move between the first and last *sufficient* month, with its span.

    Using unreliable endpoint months would make the headline number a coin
    flip on this snapshot, so thin months are skipped -- but then the span is
    no longer twelve and the caller must be told. Returns (pct, span_months).
    """
    usable = [m for m in monthly if m.month_is_sufficient and m.median_psf]
    if len(usable) < 2:
        return None, 0
    first, last = usable[0], usable[-1]
    if not first.median_psf:
        return None, 0
    span = (pd.Period(last.month, freq="M")
            - pd.Period(first.month, freq="M")).n + 1
    pct = (last.median_psf - first.median_psf) / first.median_psf * 100.0
    return pct, int(span)


if __name__ == "__main__":
    from .loading import load_canonical

    frame, _ = load_canonical()
    months = available_months(frame)
    criteria = Criteria(window_end=months[-1], label="all-dwellings")
    report = compute_trend(frame, criteria)

    print(f"window: {report.window_months[0]} .. {report.window_months[-1]}")
    print(f"total listings in window: {report.n_listings_total}")
    print(f"median psf move: {report.yoy_median_psf_pct:+.2f}% "
          f"over {report.yoy_span_months} sufficient months "
          f"(window is 12)")
    print("\n month     n   median_psf  median_min_price  sufficient  partial")
    for m in report.monthly:
        psf = f"{m.median_psf:,.0f}" if m.median_psf else "-"
        price = (f"{m.median_min_price_inr:,.0f}"
                 if m.median_min_price_inr else "-")
        print(f" {m.month} {m.n_active:>5} {psf:>12} {price:>17}   "
              f"{m.month_is_sufficient!s:<10}  {m.is_partial_month}")
    print("\n top localities by median psf")
    for r in report.locality_rankings:
        print(f"  {r.rank:>2}. {r.locality:<26} n={r.n_active:<5} {r.median_psf:>10,.0f}")
