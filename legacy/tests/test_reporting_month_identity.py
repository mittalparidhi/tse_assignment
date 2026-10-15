from types import SimpleNamespace

import pandas as pd
import pytest

from app.filtered_execution import _aggregate_selected
from app.retrieval_agent import RetrievalError


def _retrieved(rows):
    frame = pd.DataFrame(rows)
    return SimpleNamespace(
        rows=frame,
        selected_row_count=len(frame),
        invalid_registration_date_rows=0,
        malformed_location_rows=0,
        invalid_coordinate_rows=0,
        source_sha256="test-source-hash",
    )


def _row(source_row_id, posting_month, posting_date_status="valid", **changes):
    row = {
        "source_row_id": source_row_id,
        "POSTING_DATE": "1609459200000",  # Deliberately not used to infer a report month here.
        "posting_month": posting_month,
        "posting_date_status": posting_date_status,
        "PREFERENCE": "S",
        "MIN_PRICE": "5000000",
        "MAX_PRICE": "6000000",
        "PRICE": "5500000",
        "PRICE_SQFT": "5000",
        "PROP_ID": f"P{source_row_id}",
        "REGISTER_DATE__U": "2023-08-15",  # Filter metadata must not redefine reporting month.
    }
    row.update(changes)
    return row


def test_reporting_month_uses_canonical_posting_month_not_register_or_raw_timestamp():
    retrieved = _retrieved([
        _row(0, "2022-09"),
        _row(1, "2022-10"),
        _row(2, "", "invalid_missing", REGISTER_DATE__U="2022-09-01"),
    ])
    aggregate = _aggregate_selected(None, retrieved)
    by_month = {record["month"]: record for record in aggregate["monthly_records"]}
    assert by_month["2022-09"]["observed_listing_count"] == 1
    assert by_month["2022-10"]["observed_listing_count"] == 1
    assert sum(r["observed_listing_count"] for r in aggregate["monthly_records"]) == 2
    assert aggregate["data_quality"]["rows_with_invalid_posting_date_in_retrieved_subset"] == 1


def test_duplicate_source_row_id_returns_structured_duplicate_delivery_error():
    retrieved = _retrieved([_row(7, "2022-09"), _row(7, "2022-10")])
    with pytest.raises(RetrievalError) as exc:
        _aggregate_selected(None, retrieved)
    assert exc.value.code == "duplicate_source_row_id"
    assert exc.value.to_dict()["error_code"] == "duplicate_source_row_id"


def test_impossible_non_null_posting_month_is_rejected():
    retrieved = _retrieved([_row(0, "2023-13")])
    with pytest.raises(RetrievalError) as exc:
        _aggregate_selected(None, retrieved)
    assert exc.value.code == "E_INVALID_MONTH"


def test_missing_month_is_retained_but_excluded_from_month_records():
    retrieved = _retrieved([
        _row(0, "", "invalid_missing"),
        _row(1, "2022-09", "valid"),
    ])
    aggregate = _aggregate_selected(None, retrieved)
    by_month = {record["month"]: record for record in aggregate["monthly_records"]}
    assert by_month["2022-09"]["observed_listing_count"] == 1
    assert aggregate["data_quality"]["rows_with_missing_or_invalid_posting_month_in_retrieved_subset"] == 1
