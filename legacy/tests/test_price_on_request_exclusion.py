# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
"""Regression tests for textual Price on Request values with numeric bounds."""

import numpy as np
import pandas as pd

from scripts import build_runtime_state as runtime


def test_price_on_request_rows_are_excluded_from_runtime_price_ranges():
    request = runtime.AnalysisRequest()
    plan = runtime._plan(request)
    scan = runtime._scan_snapshot(plan, None)
    in_window = scan["in_window"]

    candidates = in_window.loc[
        in_window["_is_sale"] & in_window["_price_on_request"]
    ]
    # There are 83 textual matches, but only seven have coherent numeric
    # bounds and therefore would have been wrongly counted without the fix.
    assert len(candidates) == 83

    lo = pd.to_numeric(candidates["MIN_PRICE"], errors="coerce")
    hi = pd.to_numeric(candidates["MAX_PRICE"], errors="coerce")
    valid_lo = (
        lo.notna() & np.isfinite(lo) & lo.gt(0)
        & lo.ne(runtime.PRICE_SENTINEL)
    )
    valid_hi = (
        hi.notna() & np.isfinite(hi) & hi.gt(0)
        & hi.ne(runtime.PRICE_SENTINEL)
    )
    assert int((valid_lo & valid_hi & lo.le(hi)).sum()) == 7
    assert not candidates["_valid_price_range"].any()

    aggregate = runtime._aggregate_months(plan, scan)
    assert aggregate["in_window_valid_ranges"] == 7548
    assert aggregate["data_quality"]["in_window_sale_rows_without_valid_coherent_range"] == 85

    by_month = {r["month"]: r for r in aggregate["monthly_records"]}
    expected_counts = {
        "2022-11": 34,
        "2023-04": 269,
        "2023-05": 430,
        "2023-07": 2775,
        "2023-08": 2884,
    }
    for month, expected in expected_counts.items():
        assert by_month[month]["valid_price_range_count"] == expected


def test_price_on_request_rows_remain_in_listing_and_sale_counts():
    request = runtime.AnalysisRequest()
    plan = runtime._plan(request)
    scan = runtime._scan_snapshot(plan, None)
    aggregate = runtime._aggregate_months(plan, scan)

    assert aggregate["in_window_count"] == 9162
    assert aggregate["in_window_sales"] == 7633
