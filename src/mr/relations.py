"""The metamorphic relation catalogue. Eleven relations, three families.

Each relation is a statement about ``TrendReport`` fields and nothing else
(see ``src/contract.py``). A relation declares:

* ``applicable``  -- the input subdomain on which the property should hold
* ``transform``   -- how to build the follow-up input
* ``check``       -- the assertion, with its tolerance

``check`` returns ``(violated, detail)``. ``detail`` is kept because the
root-cause analysis needs to know *how* a relation failed, not merely that it
did; a bare boolean cannot distinguish a sign error from an off-by-one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np
import pandas as pd

from ..contract import TrendReport
from ..trend import Criteria, apply_criteria, month_window
from . import transforms as tf

REL_TOL = 1e-9

Pair = tuple[pd.DataFrame, Criteria]


# ------------------------------------------------------------------ helpers

def _close(a: float | None, b: float | None, rel: float = REL_TOL) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return math.isclose(a, b, rel_tol=rel, abs_tol=rel)


def _series_close(
    a: list[float | None], b: list[float | None], rel: float = REL_TOL
) -> tuple[bool, str]:
    if len(a) != len(b):
        return False, f"length {len(a)} != {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if not _close(x, y, rel):
            return False, f"index {i}: {x} != {y}"
    return True, ""


def _reports_identical(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    """Full-report equality, used by the two pure-invariance relations."""
    if src.window_months != dst.window_months:
        return False, "window months differ"
    if src.count_series() != dst.count_series():
        return False, (f"count series differ: {src.count_series()} vs "
                       f"{dst.count_series()}")
    for name, a, b in (
        ("median_psf", src.psf_series(), dst.psf_series()),
        ("median_min_price", src.min_price_series(), dst.min_price_series()),
        ("median_max_price", src.max_price_series(), dst.max_price_series()),
        ("p25", [m.p25_psf for m in src.monthly], [m.p25_psf for m in dst.monthly]),
        ("p75", [m.p75_psf for m in src.monthly], [m.p75_psf for m in dst.monthly]),
    ):
        ok, why = _series_close(a, b)
        if not ok:
            return False, f"{name}: {why}"
    if src.ranking_order() != dst.ranking_order():
        return False, (f"ranking order differs: {src.ranking_order()} vs "
                       f"{dst.ranking_order()}")
    if not _close(src.yoy_median_psf_pct, dst.yoy_median_psf_pct):
        return False, (f"headline move differs: {src.yoy_median_psf_pct} vs "
                       f"{dst.yoy_median_psf_pct}")
    if src.n_listings_total != dst.n_listings_total:
        return False, (f"total listings differ: {src.n_listings_total} vs "
                       f"{dst.n_listings_total}")
    return True, ""


# -------------------------------------------------------------- the relation

@dataclass(frozen=True)
class MR:
    """One metamorphic relation.

    ``prepare`` normalises the base input before **both** the source and the
    follow-up run. It exists because some relations can only be stated on a
    projection of the input space: MR-M1 shifts prices, and a price-band
    criterion applied after that shift silently changes the selected
    population, so M1 declares itself on the band-free projection of each base
    input. Transforming only the follow-up cannot express that -- the source
    would still carry the band -- which is why the hook applies to both.
    """

    mr_id: str
    family: str
    name: str
    subdomain: str
    tolerance: str
    fault: str
    applicable: Callable[[pd.DataFrame, Criteria], bool]
    transform: Callable[[pd.DataFrame, Criteria, np.random.Generator], Pair]
    check: Callable[[TrendReport, TrendReport], tuple[bool, str]]
    #: Applied to the base input before both runs. Identity by default.
    prepare: Callable[[Criteria], Criteria] = lambda criteria: criteria


_always = lambda frame, criteria: True


# ============================== INVARIANCE ================================

MR_I1 = MR(
    mr_id="I1", family="invariance", name="reorder listings",
    subdomain="all criteria sets",
    tolerance="counts exact; floats rel 1e-9",
    fault="order-dependent aggregation; unstable ranking tie-break; shard "
          "assignment leaking row order",
    applicable=_always,
    transform=lambda frame, criteria, rng: (tf.reorder_rows(frame, rng), criteria),
    check=_reports_identical,
)

MR_I4 = MR(
    mr_id="I4", family="invariance", name="relabel listing ids",
    subdomain="all criteria sets",
    tolerance="exact",
    fault="agent keyed on id hash/order; shard-by-id-hash changing the "
          "accepted set",
    applicable=_always,
    transform=lambda frame, criteria, rng: (tf.relabel_ids(frame, rng), criteria),
    check=_reports_identical,
)


def _check_units(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    """Percentages, rankings and counts identical; levels scale exactly."""
    if src.count_series() != dst.count_series():
        return False, "counts changed under a display-unit change"
    if src.ranking_order() != dst.ranking_order():
        return False, "ranking order changed under a display-unit change"
    ok, why = _series_close(
        src.pct_change_series(), dst.pct_change_series(), rel=1e-9
    )
    if not ok:
        return False, f"pct-change series not invariant: {why}"
    factor = tf.unit_psf_factor(
        Criteria(window_end=src.window_months[-1],
                 currency_unit=src.currency_unit, area_unit=src.area_unit),
        Criteria(window_end=dst.window_months[-1],
                 currency_unit=dst.currency_unit, area_unit=dst.area_unit),
    )
    for a, b in zip(src.psf_series(), dst.psf_series()):
        if a is None and b is None:
            continue
        if a is None or b is None or not _close(a * factor, b, rel=1e-9):
            return False, f"median psf did not scale by {factor}: {a} -> {b}"
    return True, ""


MR_I2 = MR(
    mr_id="I2", family="invariance", name="change display units",
    subdomain="all criteria sets; price band stays in rupees",
    tolerance="rel 1e-9",
    fault="hard-coded unit assumptions; the sq.m/sqft confusion (D1); "
          "percentages computed after rounding",
    applicable=_always,
    transform=lambda frame, criteria, rng: (
        frame, tf.change_units(criteria, "INR_LAKH", "SQM")
    ),
    check=_check_units,
)


def _check_duplicate(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    """Scoped per DESIGN.md 4: price statistics on already-sufficient months
    are invariant and counts double. The yoy fields are deliberately excluded
    -- doubling flips the ``sufficient`` flag for months holding 25-49
    listings, which legitimately changes which months the headline spans."""
    for s, d in zip(src.monthly, dst.monthly):
        if d.n_active != 2 * s.n_active:
            return False, (f"{s.month}: count {s.n_active} -> {d.n_active}, "
                           f"expected exactly 2x")
        if not s.month_is_sufficient:
            continue
        if not _close(s.median_psf, d.median_psf):
            return False, f"{s.month}: median psf {s.median_psf} -> {d.median_psf}"
        for name in ("median_min_price_inr", "median_max_price_inr"):
            a, b = getattr(s, name), getattr(d, name)
            if not _close(a, b):
                return False, f"{s.month}: {name} {a} -> {b}"
    if dst.n_listings_total != 2 * src.n_listings_total:
        return False, (f"total {src.n_listings_total} -> "
                       f"{dst.n_listings_total}, expected exactly 2x")
    return True, ""


MR_I3 = MR(
    mr_id="I3", family="invariance", name="duplicate every listing (2x)",
    subdomain="price stats asserted on already-sufficient months only; "
              "yoy fields excluded by design",
    tolerance="medians rel 1e-9; counts exactly 2x",
    fault="de-duplication silently collapsing rows; count double-counting",
    applicable=_always,
    transform=lambda frame, criteria, rng: (tf.duplicate_rows(frame), criteria),
    check=_check_duplicate,
)


def _to_lakh(criteria: Criteria) -> Criteria:
    """Declare MR-I5 on the lakh-denominated projection of each base input."""
    return criteria.with_(currency_unit="INR_LAKH")


MR_I5 = MR(
    mr_id="I5", family="invariance",
    name="convert the display currency from lakh to crore",
    subdomain="the lakh-denominated projection of each base input (see prepare)",
    tolerance="rel 1e-9",
    fault="a hard-coded currency assumption, or a percentage computed after "
          "rounding to the display unit",
    applicable=_always,
    transform=lambda frame, criteria, rng: (
        frame, tf.change_units(criteria, "INR_CRORE", criteria.area_unit)
    ),
    check=_check_units,
    prepare=_to_lakh,
)


# ============================== MONOTONIC =================================

def _pick_shift_month(frame: pd.DataFrame, criteria: Criteria) -> str | None:
    """The densest month in the window -- the one whose median is meaningful."""
    window = month_window(criteria.window_end)
    sliced = apply_criteria(frame, criteria)
    counts = sliced[sliced["month"].isin(window)]["month"].value_counts()
    counts = counts[counts > 0]
    return str(counts.idxmax()) if not counts.empty else None


#: The constant added by MR-M1, in rupees. Small relative to the median asking
#: price (~Rs 1.3 cr) so that no listing is pushed across a plausibility
#: boundary -- the subdomain precondition from DESIGN.md 4.1.
M1_DELTA_INR = 500_000.0


def _drop_price_band(criteria: Criteria) -> Criteria:
    """The band-free projection MR-M1 is declared on.

    Shifting the band alongside the data does not work: it holds the target
    month's population fixed but changes every untouched month's, because
    their prices did not move. Measured: that variant violated 12/12 runs
    against 6/12 for leaving the band in place. Removing the band from both
    runs is the only form under which the population is fixed in all twelve
    months.
    """
    return criteria.with_(price_min_inr=None, price_max_inr=None)


def _m1_transform(frame, criteria, rng):
    """Shift one month's prices. The band is already gone via ``prepare``."""
    month = _pick_shift_month(frame, criteria)
    if month is None:
        return frame, criteria
    shifted = tf.add_to_month_price(frame, month, M1_DELTA_INR)
    return shifted, criteria.with_(label=f"{criteria.label}|m1:{month}")


def _m1_raw_transform(frame, criteria, rng):
    """The original, unrefined form: the band is left where it was.

    Retained deliberately. The brief notes that an MR is a hypothesis, not an
    axiom; this relation is the documented counter-example, and keeping it
    measurable is stronger evidence than deleting it.
    """
    month = _pick_shift_month(frame, criteria)
    shifted = (frame if month is None
               else tf.add_to_month_price(frame, month, M1_DELTA_INR))
    return shifted, criteria.with_(label=f"{criteria.label}|m1:{month}")


def _check_m1(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    target = None
    if "|m1:" in str(dst.criteria.get("label", "")):
        target = str(dst.criteria["label"]).rsplit("|m1:", 1)[1]
    # Both price bounds are shifted by the transform, so both medians must move
    # by X in the target month and stay put elsewhere.
    for s, d in zip(src.monthly, dst.monthly):
        for name in ("median_min_price_inr", "median_max_price_inr"):
            a, b = getattr(s, name), getattr(d, name)
            if a is None or b is None:
                continue
            if s.month == target:
                moved = b - a
                if abs(moved - M1_DELTA_INR) > max(1e-6 * M1_DELTA_INR, 1e-6):
                    return False, (f"{s.month}: {name} moved {moved:,.2f}, "
                                   f"expected {M1_DELTA_INR:,.2f}")
            elif not _close(a, b):
                return False, f"{s.month}: untouched month {name} moved {a} -> {b}"
            if b < a - 1e-6:
                return False, f"{s.month}: {name} decreased"
    return True, ""


MR_M1 = MR(
    mr_id="M1", family="monotonic",
    name=f"add Rs {M1_DELTA_INR:,.0f} to every price in one month",
    subdomain="the band-free projection of each base input (see prepare), and "
              "a shift small enough that no listing crosses a plausibility bound",
    tolerance="|delta - X| <= 1e-6*X on the target month; others exact",
    fault="month bucketing bleeding across boundaries; plausibility filter "
          "applied after the transform, clipping shifted rows",
    applicable=lambda frame, criteria: _pick_shift_month(frame, criteria) is not None,
    transform=_m1_transform,
    check=_check_m1,
    prepare=_drop_price_band,
)


def _check_m2(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    for s, d in zip(src.monthly, dst.monthly):
        if d.n_active < s.n_active:
            return False, (f"{s.month}: widened band gave fewer listings "
                           f"({s.n_active} -> {d.n_active})")
    return True, ""


MR_M1_RAW = MR(
    mr_id="M1raw", family="monotonic",
    name=f"add Rs {M1_DELTA_INR:,.0f} to one month, band left in place",
    subdomain="DOES NOT HOLD where a price band is set -- retained as the "
              "documented ill-conceived relation, not as a passing check",
    tolerance="same as M1",
    fault="none: the relation itself is unsound. The shift moves listings "
          "across the band boundary, so the follow-up run selects a different "
          "population. On thin months one crossing listing moved the median "
          "by up to Rs 1,122,750 against an expected Rs 500,000.",
    applicable=lambda frame, criteria: _pick_shift_month(frame, criteria) is not None,
    transform=_m1_raw_transform,
    check=_check_m1,
)


MR_M2 = MR(
    mr_id="M2", family="monotonic", name="widen the price band (superset)",
    subdomain="criteria that set a price band",
    tolerance="exact inequality",
    fault="filter inversion; off-by-one on bounds; scan agent serving cached "
          "results for stale criteria",
    applicable=lambda frame, criteria: (
        criteria.price_min_inr is not None or criteria.price_max_inr is not None
    ),
    transform=lambda frame, criteria, rng: (frame, tf.widen_price_band(criteria)),
    check=_check_m2,
)


def _check_m3(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    for s, d in zip(src.monthly, dst.monthly):
        if d.n_active > s.n_active:
            return False, (f"{s.month}: locality subset gave MORE listings "
                           f"({s.n_active} -> {d.n_active})")
    return True, ""


def _m3_transform(frame, criteria, rng):
    # An explicit check, not ``assert``: assertions vanish under ``python -O``.
    if not criteria.localities or len(criteria.localities) < 2:
        raise ValueError("MR-M3 needs a criteria set naming >= 2 localities")
    keep = tuple(criteria.localities[: max(1, len(criteria.localities) // 2)])
    return frame, tf.restrict_localities(criteria, keep)


MR_M3 = MR(
    mr_id="M3", family="monotonic", name="restrict to a locality subset",
    subdomain="criteria naming at least two localities",
    tolerance="exact inequality",
    fault="leakage between scan shards; aggregator merging results from a "
          "previous criteria set",
    applicable=lambda frame, criteria: bool(
        criteria.localities and len(criteria.localities) >= 2
    ),
    transform=_m3_transform,
    check=_check_m3,
)


# ============================= DIRECTIONAL ================================

def _check_d1(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    """The overlapping months must agree exactly between the two windows."""
    shared = sorted(set(src.window_months) & set(dst.window_months))
    if not shared:
        return False, "windows do not overlap"
    for month in shared:
        a, b = src.month_stat(month), dst.month_stat(month)
        if a is None or b is None:
            return False, f"{month}: missing from one report"
        if a.n_active != b.n_active:
            return False, (f"{month}: count {a.n_active} != {b.n_active} "
                           f"across the shifted window")
        if not _close(a.median_psf, b.median_psf):
            return False, f"{month}: median psf {a.median_psf} != {b.median_psf}"
        for name in ("median_min_price_inr", "median_max_price_inr"):
            x, y = getattr(a, name), getattr(b, name)
            if not _close(x, y):
                return False, f"{month}: {name} {x} != {y}"
    return True, ""


def _d1_applicable(frame: pd.DataFrame, criteria: Criteria) -> bool:
    """Both windows must lie inside the observed data range, else the shifted
    window reaches past the scrape date and the relation compares a month to
    nothing."""
    latest = pd.Period(str(frame["month"].max()), freq="M")
    return pd.Period(criteria.window_end, freq="M") + 1 <= latest


MR_D1 = MR(
    mr_id="D1", family="directional", name="shift the window forward one month",
    subdomain="window ends with both windows inside the data range",
    tolerance="counts exact; floats rel 1e-9",
    fault="off-by-one window arithmetic; month bucketing drift; an agent "
          "carrying state between runs",
    applicable=_d1_applicable,
    transform=lambda frame, criteria, rng: (frame, tf.shift_window(criteria, 1)),
    check=_check_d1,
)


#: Scale factor for MR-D2.
D2_K = 1.5


def _check_d2(src: TrendReport, dst: TrendReport) -> tuple[bool, str]:
    for s, d in zip(src.monthly, dst.monthly):
        if s.median_psf is not None or d.median_psf is not None:
            if not _close(
                None if s.median_psf is None else s.median_psf * D2_K,
                d.median_psf, rel=1e-9
            ):
                return False, (f"{s.month}: median psf {s.median_psf} did not "
                               f"scale by {D2_K} (got {d.median_psf})")
        for name in ("median_min_price_inr", "median_max_price_inr"):
            a, b = getattr(s, name), getattr(d, name)
            if a is not None or b is not None:
                if not _close(None if a is None else a * D2_K, b, rel=1e-9):
                    return False, (f"{s.month}: {name} did not scale by "
                                   f"{D2_K} ({a} -> {b})")
    ok, why = _series_close(
        src.pct_change_series(), dst.pct_change_series(), rel=1e-9
    )
    if not ok:
        return False, f"pct-change shape not invariant under scaling: {why}"
    if src.ranking_order() != dst.ranking_order():
        return False, "locality ranking order changed under price scaling"
    return True, ""


MR_D2 = MR(
    mr_id="D2", family="directional", name=f"scale all prices by k={D2_K}",
    subdomain="k such that no listing crosses the price or psf bound; the "
              "price-band criterion is scaled alongside the data",
    tolerance="scaled values rel 1e-9; pct changes abs 1e-9",
    fault="unit mishandling; plausibility filter applied post-transform; "
          "non-linear aggregation",
    applicable=_always,
    transform=lambda frame, criteria, rng: (
        tf.scale_prices(frame, D2_K), tf.scale_price_criteria(criteria, D2_K)
    ),
    check=_check_d2,
)


ALL_RELATIONS: tuple[MR, ...] = (
    MR_I1, MR_I2, MR_I3, MR_I4,     # invariance
    MR_I5,                          # invariance: the brief's crore <-> lakh case
    MR_M1, MR_M2, MR_M3,            # monotonic
    MR_M1_RAW,                      # monotonic, documented counter-example
    MR_D1, MR_D2,                   # directional
)

BY_ID = {mr.mr_id: mr for mr in ALL_RELATIONS}
