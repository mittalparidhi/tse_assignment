# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: tests for the new fields and filters.
# Lines by git blame: Vidhi Jain 50%, Paridhi Mittal 50%. Full attribution:
# CREDITS.md.
"""The deterministic core: criteria filtering, window arithmetic, statistics."""

import pandas as pd
import pytest

from src.contract import MIN_SUFFICIENT_N
from src.trend import Criteria, apply_criteria, compute_trend, month_window


def _frame(rows):
    return pd.DataFrame(rows)


def _listing(lid, month, price, area, bhk=3, locality="A", max_price=None,
             valid=True, city="Hyderabad"):
    """One canonical row, shaped as src/loading.py builds it."""
    hi = float(price if max_price is None else max_price)
    rep = (float(price) + hi) / 2.0
    nan = float("nan")
    return {
        "listing_id": str(lid), "month": month, "price_valid": valid,
        "price_inr": float(price) if valid else nan,
        "max_price_inr": hi if valid else nan,
        "listing_price_inr": rep if valid else nan,
        "area_sqft": float(area), "psf_inr": rep / area if valid else nan,
        "bhk": bhk, "locality": locality, "locality_id": f"id-{locality}",
        "property_type": "Residential Apartment", "city": city,
        "area_sqm_raw": area / 10.7639104, "price_display_inr": float(price),
        "age_on_site_days": 34.0, "latitude": 17.44, "longitude": 78.39,
        "description": "test listing",
    }


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
    assert stat.median_price_per_sqft_inr == pytest.approx(3500.0)


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
    assert empty.listing_count == 0 and empty.coverage_status == "NO_DATA_IN_SNAPSHOT" and empty.median_price_per_sqft_inr is None


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
    assert lakh.month_stat("2023-08").median_price_per_sqft_inr == pytest.approx(
        inr.month_stat("2023-08").median_price_per_sqft_inr * 1e-5)
    for a, b in zip(inr.pct_change_series(), lakh.pct_change_series()):
        assert (a is None and b is None) or a == pytest.approx(b)


def test_min_and_max_price_medians_are_reported_separately():
    """Design note §2: the representative price is the (MIN + MAX) midpoint
    and price per sqft uses it; decision 7 keeps both bounds' medians too."""
    frame = _frame([
        _listing(1, "2023-07", 4e6, 1000, max_price=5e6),
        _listing(2, "2023-07", 6e6, 1000, max_price=9e6),
    ])
    stat = compute_trend(frame, Criteria(window_end="2023-08")).month_stat("2023-07")
    assert stat.median_min_price_inr == pytest.approx(5e6)
    assert stat.median_max_price_inr == pytest.approx(7e6)
    assert stat.median_listing_price_inr == pytest.approx(6e6)   # 4.5M, 7.5M
    assert stat.median_price_per_sqft_inr == pytest.approx(6000)


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


def test_invalid_price_listings_count_but_stay_out_of_the_medians():
    """Design note §2: listing_count includes listings with an invalid price;
    price_valid_count and both medians use only the valid ones."""
    rows = [_listing(i, "2023-07", 5e6, 1000) for i in range(30)]
    rows += [_listing(100 + i, "2023-07", 9e9, 1, valid=False) for i in range(5)]
    stat = compute_trend(_frame(rows), Criteria(window_end="2023-08")).month_stat("2023-07")
    assert (stat.listing_count, stat.price_valid_count) == (35, 30)
    assert stat.median_listing_price_inr == pytest.approx(5e6)
    assert stat.coverage_status == "ADEQUATE"


def test_coverage_status_distinguishes_no_data_from_limited():
    rows = [_listing(i, "2023-07", 5e6, 1000) for i in range(29)]
    rows += [_listing(99, "2023-06", 5e6, 1000, valid=False)]
    report = compute_trend(_frame(rows), Criteria(window_end="2023-08"))
    assert report.month_stat("2023-07").coverage_status == "LIMITED"
    assert report.month_stat("2023-06").coverage_status == "LIMITED"
    assert report.month_stat("2023-06").median_listing_price_inr is None
    assert report.month_stat("2023-05").coverage_status == "NO_DATA_IN_SNAPSHOT"


def test_city_and_locality_id_filters():
    rows = [_listing(1, "2023-07", 5e6, 1000, locality="A"),
            _listing(2, "2023-07", 5e6, 1000, locality="B", city="Secunderabad")]
    frame = _frame(rows)
    assert len(apply_criteria(frame, Criteria(window_end="2023-08",
                                              cities=("Secunderabad",)))) == 1
    assert apply_criteria(frame, Criteria(window_end="2023-08",
                                          localities=("id-A",)))["locality"].tolist() == ["A"]


def test_price_band_uses_the_listing_range_overlap_rule():
    """Design note MR5: a listing counts if [MIN, MAX] overlaps the band."""
    frame = _frame([_listing(1, "2023-07", 4e6, 1000, max_price=6e6)])
    band = Criteria(window_end="2023-08", price_min_inr=5e6, price_max_inr=8e6)
    assert len(apply_criteria(frame, band)) == 1
    assert len(apply_criteria(frame, band.with_(price_min_inr=7e6))) == 0
