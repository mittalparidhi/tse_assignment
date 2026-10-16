# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from __future__ import annotations

from app.schemas import FROZEN_SOURCE_SHA256
from app.snapshot_repository import load_processed_snapshot


def test_processed_snapshot_is_verified_and_preserves_contract_baselines():
    frame, raw_sha256 = load_processed_snapshot()
    assert raw_sha256 == FROZEN_SOURCE_SHA256
    assert len(frame) == 9487
    assert len(frame.columns) == 78
    assert frame["source_row_id"].tolist() == list(range(9487))
    assert frame["posting_date_status"].eq("valid").sum() == 9245
    assert frame["posting_date_status"].ne("valid").sum() == 242
    months = frame["posting_month"].fillna("").astype(str)
    in_window = frame["posting_date_status"].eq("valid") & months.ge("2022-09") & months.le("2023-08")
    assert int(in_window.sum()) == 9162
    sales = in_window & frame["PREFERENCE"].astype(str).str.strip().eq("S")
    assert int(sales.sum()) == 7633
    assert int((sales & frame["price_range_status"].eq("valid")).sum()) == 7555
    assert frame["PROP_ID"].astype(str).eq("Z70135726").sum() == 2
