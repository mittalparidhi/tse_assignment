"""The output contract.

Every metamorphic relation in this project is a statement about the objects
defined here and nothing else. The assignment brief requires this contract to
exist before any MR is written, because an MR without a fixed output surface is
unfalsifiable: "the trend is unchanged" means nothing until "the trend" is a
named, finite set of numbers.

Design decisions worth recording:

* The per-month fields follow the design note's output contract (§2):
  ``listing_count``, ``price_valid_count``, ``median_listing_price_inr``,
  ``median_price_per_sqft_inr`` and ``coverage_status``; the rest are
  extensions. The representative price is (MIN_PRICE + MAX_PRICE) / 2.
* ``median_price_per_sqft_inr`` is the headline series. The median (not the mean) is used
  because the snapshot's price tail is heavy and contaminated by data-entry
  errors (see ``loading.py``); a mean would make every invariance MR fail for
  reasons that have nothing to do with the agents.
* Counts are reported separately from the price statistics because the
  duplication and price-band MRs move these two in *different* directions. A
  contract that fused them would hide exactly the faults we are hunting.
* ``coverage_status`` distinguishes a month with no listing in the slice
  (NO_DATA_IN_SNAPSHOT) from a thin one (LIMITED); missing medians are null,
  never zero.
* ``month_is_sufficient`` exists because this snapshot is a single-point scrape: the
  oldest months of the window hold a few dozen listings, so their medians are
  noise. MRs that compare month-to-month are declared only over the
  sufficient subdomain. This is the "input subdomain on which it should hold"
  the brief asks each MR to state.
* ``yoy_median_psf_pct`` is measured between the first and last
  *sufficient* month, so on a thin snapshot it may span fewer than 12 months.
  ``yoy_span_months`` reports that span and the report is therefore
  self-describing: a consumer that needs a true 12-month figure must check it.
  Naming the field "yoy" while silently measuring six months would make the
  window-shift MR assert on an undefined quantity.
* ``currency_unit`` / ``area_unit`` are carried in the report so the
  unit-invariance MR has something observable to assert on. A report that
  silently normalised units could not express "only display scales".
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal
import json
import math

CurrencyUnit = Literal["INR", "INR_LAKH", "INR_CRORE"]
AreaUnit = Literal["SQFT", "SQM"]

#: Version of the contract suite in ``contracts/`` this code implements.
CONTRACT_VERSION = "2.1.0-draft"

#: Default last month of the 12-month window.
DEFAULT_WINDOW_END = "2023-08"

#: The month holding the snapshot's latest posting (2023-08-26 10:29 IST).
#: Observed only up to that date, so it is flagged and never extrapolated.
PARTIAL_MONTH = "2023-08"

#: The headline move (yoy_median_psf_pct) is measured only between months
#: with at least this many price-valid listings. Kept apart from the design
#: note's coverage threshold below: at 30 the headline jumps to +18.35%, away
#: from the external RESIDEX cross-check (REPORT.md §9).
MIN_SUFFICIENT_N = 50

#: Design note §4.3: a month's coverage is ADEQUATE with at least this many
#: usable price-and-area records; this also drives the Coverage agent's score.
ADEQUATE_N = 30

#: Design note §2 coverage_status values.
COVERAGE_ADEQUATE = "ADEQUATE"
COVERAGE_LIMITED = "LIMITED"
COVERAGE_NO_DATA = "NO_DATA_IN_SNAPSHOT"


def coverage_status(listing_count: int, price_valid_count: int,
                    adequate_n: int = ADEQUATE_N) -> str:
    """ADEQUATE with enough usable records; NO_DATA_IN_SNAPSHOT when the slice
    has no listing at all in the month; LIMITED otherwise (some listings, too
    few usable ones -- including listings that all lack a valid price)."""
    if listing_count == 0:
        return COVERAGE_NO_DATA
    return COVERAGE_ADEQUATE if price_valid_count >= adequate_n else COVERAGE_LIMITED

#: Multiplier to convert one rupee into the named display unit.
CURRENCY_SCALE: dict[str, float] = {
    "INR": 1.0,
    "INR_LAKH": 1e-5,
    "INR_CRORE": 1e-7,
}

#: Multiplier to convert one square foot into the named display unit.
AREA_SCALE: dict[str, float] = {
    "SQFT": 1.0,
    "SQM": 1.0 / 10.7639104,
}


@dataclass(frozen=True)
class MonthStat:
    """The statistics for one calendar month of the window.

    The first six fields are the design note's output contract (§2); the rest
    are extensions this implementation adds.
    """

    month: str                  # 'YYYY-MM'
    #: Qualifying listings in the month, including ones whose price or area
    #: is invalid (design note §2).
    listing_count: int
    #: Qualifying listings with valid, ordered price endpoints and a parsed
    #: area: the common eligible set for both medians.
    price_valid_count: int
    #: Median representative asking price, (MIN_PRICE + MAX_PRICE) / 2.
    median_listing_price_inr: float | None
    #: Median representative asking price / parsed area (sq ft).
    median_price_per_sqft_inr: float | None
    #: ADEQUATE / LIMITED / NO_DATA_IN_SNAPSHOT (see ``coverage_status``).
    coverage_status: str
    # -- extensions ---------------------------------------------------------
    #: Median MIN_PRICE and median MAX_PRICE, reported separately (contract v2
    #: decision 7). On this snapshot every price-valid listing has
    #: MIN_PRICE == MAX_PRICE, so both equal median_listing_price_inr.
    median_min_price_inr: float | None
    median_max_price_inr: float | None
    p25_psf: float | None
    p75_psf: float | None
    #: Median (scrape_date - posting_date) for listings live at the scrape.
    #:
    #: This fills the design note's ``median_days_on_market`` slot but is
    #: deliberately NOT called that. Every listing in a single-point scrape is
    #: still live, so the measure is right-censored: we observe how long a
    #: listing has been up, never how long it took to sell. It is also
    #: length-biased -- slow listings accumulate in a snapshot while fast ones
    #: exit -- so it overstates typical time-to-sale. Secondary statistic; no
    #: MR asserts on it.
    median_age_on_site_days: float | None
    #: price_valid_count >= MIN_SUFFICIENT_N: the months the headline move is
    #: measured between. Stricter than ADEQUATE (see MIN_SUFFICIENT_N).
    month_is_sufficient: bool
    #: True for PARTIAL_MONTH: observed only up to the latest posting date.
    is_partial_month: bool

    @property
    def iqr_psf(self) -> float | None:
        if self.p25_psf is None or self.p75_psf is None:
            return None
        return self.p75_psf - self.p25_psf


@dataclass(frozen=True)
class LocalityStat:
    """One row of the locality ranking table."""

    locality: str
    price_valid_count: int
    median_price_per_sqft_inr: float | None
    rank: int


@dataclass(frozen=True)
class TrendReport:
    """THE output contract. An MR may assert on these fields and no others."""

    window_months: tuple[str, ...]            # exactly 12, ascending
    monthly: tuple[MonthStat, ...]            # one per window month, aligned
    locality_rankings: tuple[LocalityStat, ...]
    yoy_median_psf_pct: float | None          # last vs first sufficient month
    yoy_span_months: int                      # how many months that spans
    n_listings_total: int                     # sum of listing_count
    n_price_valid_total: int                  # sum of price_valid_count
    currency_unit: CurrencyUnit
    area_unit: AreaUnit
    criteria: dict = field(default_factory=dict)   # the slice this describes
    provenance: dict = field(default_factory=dict) # seeds, loop counts, trace

    # -- derived series, the usual subjects of an MR ----------------------

    def psf_series(self) -> list[float | None]:
        return [m.median_price_per_sqft_inr for m in self.monthly]

    def count_series(self) -> list[int]:
        """listing_count per month -- what the count MRs compare (note §7)."""
        return [m.listing_count for m in self.monthly]

    def valid_count_series(self) -> list[int]:
        return [m.price_valid_count for m in self.monthly]

    def coverage_series(self) -> list[str]:
        return [m.coverage_status for m in self.monthly]

    def listing_price_series(self) -> list[float | None]:
        return [m.median_listing_price_inr for m in self.monthly]

    def min_price_series(self) -> list[float | None]:
        return [m.median_min_price_inr for m in self.monthly]

    def max_price_series(self) -> list[float | None]:
        return [m.median_max_price_inr for m in self.monthly]

    def age_series(self) -> list[float | None]:
        return [m.median_age_on_site_days for m in self.monthly]

    def sufficient_months(self) -> list[str]:
        return [m.month for m in self.monthly if m.month_is_sufficient]

    def pct_change_series(self) -> list[float | None]:
        """Month-on-month % change in median psf. Scale-invariant by design."""
        out: list[float | None] = [None]
        series = self.psf_series()
        for prev, cur in zip(series, series[1:]):
            if prev in (None, 0) or cur is None:
                out.append(None)
            else:
                out.append((cur - prev) / prev * 100.0)
        return out

    def ranking_order(self) -> list[str]:
        return [r.locality for r in self.locality_rankings]

    def month_stat(self, month: str) -> MonthStat | None:
        for m in self.monthly:
            if m.month == month:
                return m
        return None

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str, **kw)

    def __post_init__(self) -> None:
        if len(self.window_months) != 12:
            raise ValueError(
                f"contract violation: window must be 12 months, "
                f"got {len(self.window_months)}"
            )
        if len(self.monthly) != 12:
            raise ValueError(
                f"contract violation: need 12 MonthStat rows, got {len(self.monthly)}"
            )
        if tuple(m.month for m in self.monthly) != tuple(self.window_months):
            raise ValueError("contract violation: monthly rows misaligned with window")
        for value in (self.yoy_median_psf_pct,):
            if value is not None and not math.isfinite(value):
                raise ValueError("contract violation: non-finite yoy figure")
