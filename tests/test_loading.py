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
    assert frame["psf_inr"].dropna().between(lo, hi).all()


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


# -- Contract v2 rules ported from the first implementation (Phase 3) --------

def _raw_row(prop_id, posting_ms, price=5_000_000, max_price=None,
             price_text="50 L", area="1000 sq.ft."):
    return {
        "PROP_ID": prop_id, "PREFERENCE": "S",
        "PROPERTY_TYPE": "Residential Apartment",
        "POSTING_DATE": posting_ms, "PRICE": price_text,
        "MIN_PRICE": price,
        "MAX_PRICE": price if max_price is None else max_price,
        "AREA": area, "SECONDARY_AREA": "", "BEDROOM_NUM": 2,
        "MAP_DETAILS": "", "location": "{'LOCALITY_NAME': 'Kondapur'}",
        "CITY": "Hyderabad", "DESCRIPTION": "fixture",
    }


def _load_fixture(tmp_path, rows):
    path = tmp_path / "raw.csv"
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")
    return loading.load_canonical(path, verify=False)


# 2023-07-31 19:00:00 UTC == 2023-08-01 00:30 IST
_NEAR_MIDNIGHT_MS = 1_690_830_000_000


def test_month_is_derived_in_india_time_not_utc(tmp_path):
    """Contract v2 decision 4: a listing posted at 00:30 IST on 1 August is
    an August listing, although it is still 31 July in UTC."""
    frame, _ = _load_fixture(tmp_path, [_raw_row("A", _NEAR_MIDNIGHT_MS)])
    assert frame["month"].tolist() == ["2023-08"]


def test_price_on_request_is_excluded_even_with_numeric_bounds(tmp_path):
    """Contract v2 decision 5 (D6): the numeric bounds of a Price on Request
    listing are placeholders, so it never reaches the price statistics. It is
    still a listing (design note §2: listing_count includes invalid prices)."""
    frame, log = _load_fixture(tmp_path, [
        _raw_row("A", _NEAR_MIDNIGHT_MS),
        _raw_row("B", _NEAR_MIDNIGHT_MS, price_text="Price on Request"),
        _raw_row("C", _NEAR_MIDNIGHT_MS, price_text="  price ON request "),
    ])
    valid = frame[frame["price_valid"]]
    assert valid["listing_id"].str.split("#").str[0].tolist() == ["A"]
    assert len(frame) == 3 and frame.loc[~frame["price_valid"], "price_inr"].isna().all()
    flags = log.flags_frame().set_index("check")
    assert flags.loc["not Price on Request", "flagged_invalid"] == 2


def test_max_price_must_be_valid_and_not_below_min_price(tmp_path):
    """Contract v2 decision 7: both bounds must be real prices, MIN <= MAX."""
    frame, _ = _load_fixture(tmp_path, [
        _raw_row("ok", _NEAR_MIDNIGHT_MS, price=5e6, max_price=6e6),
        _raw_row("inverted", _NEAR_MIDNIGHT_MS, price=6e6, max_price=5e6),
        _raw_row("sentinel", _NEAR_MIDNIGHT_MS, max_price=loading.INT32_SENTINEL),
        _raw_row("zero", _NEAR_MIDNIGHT_MS, max_price=0),
    ])
    valid = frame[frame["price_valid"]]
    assert valid["listing_id"].str.split("#").str[0].tolist() == ["ok"]
    assert valid["max_price_inr"].tolist() == [6e6]
    assert valid["listing_price_inr"].tolist() == [5.5e6]       # the midpoint
    assert len(frame) == 4                    # the others still count as listings


def test_real_snapshot_has_no_price_on_request_or_inverted_range(canonical):
    frame, _ = canonical
    valid = frame[frame["price_valid"]]
    assert (valid["price_inr"] <= valid["max_price_inr"]).all()
    raw = pd.read_csv(loading.RAW_PATH, low_memory=False)
    on_request = raw["PRICE"].astype("string").str.contains(
        loading.PRICE_ON_REQUEST_RE, case=False, regex=True, na=False)
    raw_rows = set(valid["listing_id"].str.split("#").str[1].astype(int))
    assert not set(raw.index[on_request]) & raw_rows


def test_frozen_canonical_snapshot_matches_a_fresh_rebuild(canonical):
    """Data.md R4: the app rebuilds the frame from the raw file on every run,
    so the frozen copy must still describe exactly that frame."""
    import hashlib
    frame, _ = canonical
    rebuilt = hashlib.sha256(loading.canonical_csv_bytes(frame)).hexdigest()
    recorded = (loading.RAW_PATH.parents[1] / "snapshot" / "CHECKSUMS.txt"
                ).read_text(encoding="utf-8").split()[0]
    assert rebuilt == recorded


def test_partial_month_constant_agrees_with_the_latest_posting():
    """PARTIAL_MONTH (src/contract.py) and LATEST_POSTING (src/loading.py)
    state one fact in two places; they must not drift apart, and
    LATEST_POSTING must really be the latest posting in the raw file."""
    from src.contract import PARTIAL_MONTH
    assert loading.LATEST_POSTING.strftime("%Y-%m") == PARTIAL_MONTH
    raw = pd.read_csv(loading.RAW_PATH, usecols=["POSTING_DATE"])
    latest = pd.to_datetime(pd.to_numeric(raw["POSTING_DATE"], errors="coerce"),
                            unit="ms", utc=True).max()
    assert latest.tz_convert(loading.LOCAL_TIMEZONE) == loading.LATEST_POSTING


def test_listing_id_is_unique_and_traceable_to_the_raw_row(canonical):
    """Data.md D7/§5: PROP_ID is not unique, so the raw row position is part
    of the ID; retrieval selects rows by ID and must never pick up a twin."""
    frame, _ = canonical
    assert frame["listing_id"].is_unique
    raw = pd.read_csv(loading.RAW_PATH, usecols=["PROP_ID"])
    parts = frame["listing_id"].str.rsplit("#", n=1)
    prop, row = parts.str[0], parts.str[1]
    assert (raw.loc[row.astype(int), "PROP_ID"].astype(str).to_numpy()
            == prop.to_numpy()).all()
