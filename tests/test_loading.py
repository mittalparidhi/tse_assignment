"""The loader must handle each documented defect, and say so in the log."""

import pandas as pd
import pytest

from src import loading


def test_snapshot_checksum_matches_the_audited_file():
    """Guards reproducibility: a changed snapshot must not run silently."""
    assert loading.verify_snapshot() == loading.EXPECTED_SHA256


@pytest.fixture(scope="module")
def canonical():
    frame, log = loading.load_canonical()
    return frame, log


def test_area_is_parsed_from_the_display_string_not_the_sqft_column(canonical):
    """D1: MIN_AREA_SQFT is square metres despite its name.

    The canonical area must agree with the sq.m restatement times 10.7639,
    which is only true if we parsed the display string.
    """
    frame, _ = canonical
    both = frame.dropna(subset=["area_sqm_raw"])
    ratio = both["area_sqft"] / (both["area_sqm_raw"] * 10.7639104)
    assert ratio.median() == pytest.approx(1.0, rel=1e-4)
    assert (ratio.sub(1).abs() > 0.01).sum() == 0


def test_int32_sentinel_and_zero_prices_are_gone(canonical):
    """D2."""
    frame, _ = canonical
    assert (frame["price_inr"] >= loading.INT32_SENTINEL).sum() == 0
    assert (frame["price_inr"] <= 0).sum() == 0


def test_only_sale_dwellings_survive(canonical):
    """D3 and D4."""
    frame, _ = canonical
    assert set(frame["property_type"]) <= set(loading.DWELLING_TYPES)
    # Residential Land carried the 2,806 missing bedroom counts.
    assert "Residential Land" not in set(frame["property_type"])


def test_d5_contamination_is_deliberately_retained(canonical):
    """D5 must survive the loader so the Analysis agent's targeted
    recomputation has a real fault to catch -- otherwise cycle 2 would be
    decorative."""
    frame, _ = canonical
    assert (frame["psf_inr"] > 100_000).sum() > 0, (
        "contamination was filtered out; cycle 2 would be a no-op"
    )


def test_plausibility_bounds_remove_it_when_asked():
    frame, _ = loading.load_canonical(apply_plausibility=True)
    lo, hi = loading.PSF_INR_BOUNDS
    assert frame["psf_inr"].between(lo, hi).all()


def test_reject_log_accounts_for_every_dropped_row(canonical):
    _, log = canonical
    table = log.as_frame()
    assert table["rows_remaining"].is_monotonic_decreasing
    assert table["rows_remaining"].iloc[0] == 9487


def test_price_display_parser_handles_indian_units():
    assert loading._parse_price_display("69.25 L") == pytest.approx(6_925_000)
    assert loading._parse_price_display("1.2 Cr") == pytest.approx(12_000_000)
    assert loading._parse_price_display("") is None
    assert loading._parse_price_display("on request") is None
