"""The deterministic core: criteria filtering, window arithmetic, statistics."""

import pandas as pd
import pytest

from src.contract import MIN_SUFFICIENT_N
from src.trend import Criteria, apply_criteria, compute_trend, month_window


def _frame(rows):
    return pd.DataFrame(rows, columns=[
        "listing_id", "month", "price_inr", "max_price_inr", "area_sqft",
        "psf_inr", "bhk", "locality", "property_type", "city",
        "area_sqm_raw", "price_display_inr", "age_on_site_days",
        "latitude", "longitude", "description",
    ])


def _listing(lid, month, price, area, bhk=3, locality="A", max_price=None):
    return [str(lid), month, float(price),
            float(price if max_price is None else max_price), float(area),
            price / area, bhk, locality, "Residential Apartment", "Hyderabad",
            area / 10.7639104, float(price), 34.0, 17.44, 78.39, "test listing"]


def test_window_is_twelve_months_ending_inclusive():
    window = month_window("2023-08")
    assert len(window) == 12
    assert window[0] == "2022-09"
    assert window[-1] == "2023-08"


def test_median_is_the_middle_value_not_the_mean():
    """Guards the contract decision to use the median: one contaminated
    listing must not move the headline."""
    rows = [_listing(i, "2023-08", 1_000_000 * (i + 1), 1000)
            for i in range(5)]
    rows.append(_listing(99, "2023-08", 10_000_000_000, 1000))
    report = compute_trend(_frame(rows), Criteria(window_end="2023-08"))
    stat = report.month_stat("2023-08")
    assert stat.median_psf == pytest.approx(3500.0)


def test_sufficiency_flag_tracks_the_threshold():
    thin = [_listing(i, "2023-08", 1e7, 1000) for i in range(MIN_SUFFICIENT_N - 1)]
    assert compute_trend(_frame(thin), Criteria(window_end="2023-08")) \
        .month_stat("2023-08").month_is_sufficient is False

    thick = [_listing(i, "2023-08", 1e7, 1000) for i in range(MIN_SUFFICIENT_N)]
    assert compute_trend(_frame(thick), Criteria(window_end="2023-08")) \
        .month_stat("2023-08").month_is_sufficient is True


def test_empty_month_reports_zero_not_a_gap():
    """The contract requires all 12 rows present; a missing month would break
    every series-aligned MR."""
    rows = [_listing(i, "2023-08", 1e7, 1000) for i in range(3)]
    report = compute_trend(_frame(rows), Criteria(window_end="2023-08"))
    assert len(report.monthly) == 12
    empty = report.month_stat("2022-09")
    assert empty.n_active == 0 and empty.median_psf is None


def test_yoy_span_is_reported_and_can_be_under_twelve():
    """The honesty fix: a headline measured over fewer than 12 months must
    say so, or the window-shift relation asserts on an undefined quantity."""
    rows = []
    for month in ("2023-07", "2023-08"):
        rows += [_listing(f"{month}-{i}", month, 1e7, 1000)
                 for i in range(MIN_SUFFICIENT_N)]
    report = compute_trend(_frame(rows), Criteria(window_end="2023-08"))
    assert report.yoy_span_months == 2


def test_locality_ranking_ties_break_deterministically():
    """Without a stable tie-break, MR-I1 would report violations caused by
    groupby iteration order -- a harness bug posing as a fault."""
    rows = []
    for name in ("Zeta", "Alpha", "Mid"):
        rows += [_listing(f"{name}{i}", "2023-08", 1e7, 1000, locality=name)
                 for i in range(6)]
    report = compute_trend(_frame(rows), Criteria(window_end="2023-08"))
    assert report.ranking_order() == ["Alpha", "Mid", "Zeta"]


def test_price_band_criterion_is_applied_in_rupees():
    rows = [_listing(1, "2023-08", 5_000_000, 1000),
            _listing(2, "2023-08", 50_000_000, 1000)]
    criteria = Criteria(window_end="2023-08", price_max_inr=10_000_000)
    assert len(apply_criteria(_frame(rows), criteria)) == 1


def test_unit_change_scales_levels_but_not_percentages():
    """The property MR-I2 asserts."""
    rows = []
    for month, price in (("2023-07", 1e7), ("2023-08", 1.1e7)):
        rows += [_listing(f"{month}-{i}", month, price, 1000)
                 for i in range(MIN_SUFFICIENT_N)]
    frame = _frame(rows)
    inr = compute_trend(frame, Criteria(window_end="2023-08"))
    lakh = compute_trend(frame, Criteria(window_end="2023-08",
                                         currency_unit="INR_LAKH"))
    assert lakh.month_stat("2023-08").median_psf == pytest.approx(
        inr.month_stat("2023-08").median_psf * 1e-5)
    for a, b in zip(inr.pct_change_series(), lakh.pct_change_series()):
        assert (a is None and b is None) or a == pytest.approx(b)


def test_min_and_max_price_medians_are_reported_separately():
    """Contract v2 decision 7: both bounds have their own median, and price
    per sqft is computed from MIN_PRICE."""
    frame = _frame([
        _listing(1, "2023-07", 4e6, 1000, max_price=5e6),
        _listing(2, "2023-07", 6e6, 1000, max_price=9e6),
    ])
    stat = compute_trend(frame, Criteria(window_end="2023-08")).month_stat("2023-07")
    assert stat.median_min_price_inr == pytest.approx(5e6)
    assert stat.median_max_price_inr == pytest.approx(7e6)
    assert stat.median_psf == pytest.approx(5000)


def test_only_the_snapshot_end_month_is_flagged_partial():
    """August 2023 is observed only to the 26th; it is flagged, never
    extrapolated, wherever it falls in the window."""
    frame = _frame([_listing(1, "2023-08", 5e6, 1000)])
    for end in ("2023-08", "2023-09"):
        report = compute_trend(frame, Criteria(window_end=end))
        partial = [m.month for m in report.monthly if m.is_partial_month]
        assert partial == ["2023-08"]
    earlier = compute_trend(frame, Criteria(window_end="2023-07"))
    assert not any(m.is_partial_month for m in earlier.monthly)
