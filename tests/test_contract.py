# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: tests for the v2.1 fields. Lines by git
# blame: Vidhi Jain 85%, Paridhi Mittal 15%. Full attribution: CREDITS.md.
"""The output contract must reject malformed reports.

These are guard tests: the contract is the thing every MR asserts on, so a
silently-malformed report would make every relation meaningless rather than
failing loudly.
"""

import pytest

from src.contract import MonthStat, TrendReport


def _months(n=12, start=1):
    return tuple(f"2023-{m:02d}" for m in range(start, start + n))


def _stats(months):
    return tuple(
        MonthStat(month=m, listing_count=100, price_valid_count=100,
                  median_listing_price_inr=1.3e7, median_price_per_sqft_inr=7500.0,
                  coverage_status="ADEQUATE", median_min_price_inr=1.3e7,
                  median_max_price_inr=1.3e7, p25_psf=None, p75_psf=None,
                  median_age_on_site_days=None, month_is_sufficient=True,
                  is_partial_month=False)
        for m in months
    )


def _report(months, **kw):
    defaults = dict(
        window_months=months, monthly=_stats(months), locality_rankings=(),
        yoy_median_psf_pct=1.0, yoy_span_months=12, n_listings_total=1200, n_price_valid_total=1200,
        currency_unit="INR", area_unit="SQFT",
    )
    defaults.update(kw)
    return TrendReport(**defaults)


def test_accepts_a_well_formed_report():
    report = _report(_months())
    assert len(report.window_months) == 12
    assert report.count_series() == [100] * 12


def test_rejects_a_window_that_is_not_twelve_months():
    with pytest.raises(ValueError, match="12 months"):
        _report(_months(11))


def test_rejects_misaligned_monthly_rows():
    months = _months()
    shifted = _stats(_months(12, start=2))
    with pytest.raises(ValueError, match="misaligned"):
        _report(months, monthly=shifted)


def test_rejects_non_finite_headline():
    with pytest.raises(ValueError, match="non-finite"):
        _report(_months(), yoy_median_psf_pct=float("inf"))


def test_pct_change_series_is_scale_invariant():
    """The property MR-I2 and MR-D2 rely on, asserted directly."""
    months = _months()
    base = [1000.0 * (1 + i / 10) for i in range(12)]
    scaled = [v * 7.3 for v in base]

    def build(values):
        return _report(months, monthly=tuple(
            MonthStat(month=m, listing_count=100, price_valid_count=100,
                  median_listing_price_inr=v * 1500, median_price_per_sqft_inr=v,
                  coverage_status="ADEQUATE", median_min_price_inr=v * 1500,
                  median_max_price_inr=v * 1500, p25_psf=None, p75_psf=None,
                  median_age_on_site_days=None, month_is_sufficient=True,
                  is_partial_month=False)
            for m, v in zip(months, values)
        ))

    a = build(base).pct_change_series()
    b = build(scaled).pct_change_series()
    assert a[0] is None and b[0] is None
    for x, y in zip(a[1:], b[1:]):
        assert x == pytest.approx(y, rel=1e-12)


def test_first_pct_change_is_none_not_zero():
    """A zero would be read as 'no movement' rather than 'unknown'."""
    assert _report(_months()).pct_change_series()[0] is None
