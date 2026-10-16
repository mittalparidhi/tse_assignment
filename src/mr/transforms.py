# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: MIN, MAX and midpoint shifted together;
# shrink_radius for M4. Lines by git blame: Vidhi Jain 91%, Paridhi Mittal 9%.
# Full attribution: CREDITS.md.
"""Metamorphic input transformations.

Each transformation takes ``(frame, criteria)`` and returns a transformed
``(frame, criteria)`` pair. Transformations never touch the raw snapshot on
disk; they operate on the in-memory canonical frame, which is what makes the
reorder/duplicate/scale relations cheap to apply (a hint the brief gives
explicitly).

A note on where each transformation acts. Some act on the *data*
(reorder, duplicate, relabel, shift prices) and some on the *criteria*
(units, price band, locality subset, window). Both are legitimate
metamorphic inputs because the system under test is the pair: the agents
consume a frame and a criteria set, and a fault in either consumption path is
a fault in the application.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..contract import AREA_SCALE, CURRENCY_SCALE
from ..trend import Criteria, month_window


# --------------------------------------------------------------- invariance

def reorder_rows(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Permute the listing rows. Index is reset so no positional information
    survives -- keeping the original index would let a stable sort silently
    restore the original order and make MR-I1 vacuous."""
    order = rng.permutation(len(frame))
    return frame.iloc[order].reset_index(drop=True)


def duplicate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Exactly double the dataset.

    Listing ids are suffixed so the duplicates are distinct listings rather
    than repeated ids. Repeating the id would instead test de-duplication,
    which is a different property; the brief's relation is about medians being
    insensitive to replication.
    """
    twin = frame.copy()
    twin["listing_id"] = twin["listing_id"].astype(str) + "#dup"
    return pd.concat([frame, twin], ignore_index=True)


def relabel_ids(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Bijectively relabel listing ids, preserving every other field."""
    out = frame.copy()
    new_ids = rng.permutation(len(out))
    out["listing_id"] = [f"RL{n:08d}" for n in new_ids]
    return out


def change_units(
    criteria: Criteria, currency_unit: str, area_unit: str
) -> Criteria:
    """Switch display units only. Price-band criteria stay in rupees, so the
    selected population is provably identical and the relation isolates
    presentation."""
    return criteria.with_(currency_unit=currency_unit, area_unit=area_unit)


def unit_psf_factor(
    src: Criteria, dst: Criteria
) -> float:
    """The exact factor by which median psf must change between two unit
    settings. psf is a ratio, so the currency and area factors divide."""
    src_f = CURRENCY_SCALE[src.currency_unit] / AREA_SCALE[src.area_unit]
    dst_f = CURRENCY_SCALE[dst.currency_unit] / AREA_SCALE[dst.area_unit]
    return dst_f / src_f


# --------------------------------------------------------------- monotonic

def add_to_month_price(
    frame: pd.DataFrame, month: str, delta_inr: float
) -> pd.DataFrame:
    """Add a constant to every asking price in one month.

    ``psf_inr`` is recomputed from the shifted price so the frame stays
    internally consistent. Leaving psf stale would make MR-M1 pass for the
    wrong reason -- the price series would move while the psf series did not.
    ``max_price_inr`` moves by the same constant, so ``MIN_PRICE <= MAX_PRICE``
    still holds and both reported medians shift by exactly ``delta_inr``.
    """
    out = frame.copy()
    mask = out["month"] == month
    out.loc[mask, "price_inr"] = out.loc[mask, "price_inr"] + delta_inr
    out.loc[mask, "max_price_inr"] = out.loc[mask, "max_price_inr"] + delta_inr
    # The representative price is the midpoint, so it moves by delta too, and
    # price per sqft is recomputed from it (design note MR4). Listings without
    # a valid price stay NaN: there is no price to shift.
    out.loc[mask, "listing_price_inr"] = (
        out.loc[mask, "price_inr"] + out.loc[mask, "max_price_inr"]) / 2.0
    out.loc[mask, "psf_inr"] = (
        out.loc[mask, "listing_price_inr"] / out.loc[mask, "area_sqft"]
    )
    out.loc[mask, "price_display_inr"] = out.loc[mask, "price_inr"]
    return out


def shift_price_criteria(criteria: Criteria, delta_inr: float) -> Criteria:
    """Shift the price-band criterion by the same constant as the data.

    Without this the band selects a *different population* after the shift and
    MR-M1 cannot hold however correct the system is: measured on the frozen
    snapshot, a single listing crossing the band boundary moved a thin month's
    median by up to Rs 1,122,750 against an expected Rs 500,000. This is the
    boundary interaction recorded in DESIGN.md 4.1, and it is the same
    correction ``scale_price_criteria`` applies for MR-D2.
    """
    return criteria.with_(
        price_min_inr=(None if criteria.price_min_inr is None
                       else criteria.price_min_inr + delta_inr),
        price_max_inr=(None if criteria.price_max_inr is None
                       else criteria.price_max_inr + delta_inr),
    )


def widen_price_band(criteria: Criteria, factor: float = 0.25) -> Criteria:
    """Strictly widen the band, producing a superset of listings."""
    lo = criteria.price_min_inr
    hi = criteria.price_max_inr
    return criteria.with_(
        price_min_inr=None if lo is None else lo * (1.0 - factor),
        price_max_inr=None if hi is None else hi * (1.0 + factor),
    )


def shrink_radius(criteria: Criteria, factor: float = 0.5) -> Criteria:
    """Shrink a radius query around the same centre: a geographic subset."""
    return criteria.with_(radius_km=criteria.radius_km * factor)


def restrict_localities(
    criteria: Criteria, keep: tuple[str, ...]
) -> Criteria:
    """Restrict to a subset of the current locality set."""
    return criteria.with_(localities=keep)


# --------------------------------------------------------------- directional

def shift_window(criteria: Criteria, months: int = 1) -> Criteria:
    """Move the 12-month window forward by ``months``."""
    end = pd.Period(criteria.window_end, freq="M") + months
    return criteria.with_(window_end=str(end))


def overlapping_months(src: Criteria, dst: Criteria) -> list[str]:
    """The months both windows share -- the subdomain MR-D1 asserts on."""
    a, b = set(month_window(src.window_end)), set(month_window(dst.window_end))
    return sorted(a & b)


def scale_prices(frame: pd.DataFrame, k: float) -> pd.DataFrame:
    """Scale every asking price by k, keeping the frame self-consistent."""
    out = frame.copy()
    out["price_inr"] = out["price_inr"] * k
    out["max_price_inr"] = out["max_price_inr"] * k
    out["listing_price_inr"] = out["listing_price_inr"] * k
    out["psf_inr"] = out["psf_inr"] * k
    out["price_display_inr"] = out["price_display_inr"] * k
    return out


def scale_price_criteria(criteria: Criteria, k: float) -> Criteria:
    """Scale the price-band criterion alongside the data.

    Without this the band would select a *different population* after scaling
    and the relation would fail for a reason that is not a fault. This is the
    boundary interaction recorded in DESIGN.md 4.1.
    """
    return criteria.with_(
        price_min_inr=(None if criteria.price_min_inr is None
                       else criteria.price_min_inr * k),
        price_max_inr=(None if criteria.price_max_inr is None
                       else criteria.price_max_inr * k),
    )
