# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_audit_metadata_matches_final_artifact():
    processed = ROOT / "data/processed/hyderabad_clean.csv"
    checksum = ROOT / "data/processed/hyderabad_clean.csv.sha256"
    raw = ROOT / "data/raw/hyderabad.csv"
    audit = json.loads((ROOT / "audit/hyderabad_cleaning_audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "audit/hyderabad_snapshot_manifest.json").read_text(encoding="utf-8"))
    actual = sha256(processed)
    assert sha256(raw) == manifest["raw_sha256"]
    assert actual == checksum.read_text(encoding="ascii").split()[0]
    assert actual == manifest["processed_sha256"] == audit["processed_sha256"]

    with processed.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []
    assert len(rows) == audit["row_count"] == manifest["output_rows"] == 9487
    assert len(columns) == audit["output_column_count"] == manifest["output_columns"] == 78
    assert audit["source_column_count"] == 55


def test_summary_has_contract_required_columns_and_quality_counts():
    summary_path = ROOT / "audit/hyderabad_cleaning_summary.csv"
    with summary_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    required = {"rule_id", "rows_inspected", "rows_flagged_or_changed", "output_path"}
    assert required.issubset(rows[0])
    indexed = {row["rule_id"]: row for row in rows}
    assert int(indexed["D2_posting_date_quality"]["rows_flagged_or_changed"]) == 242
    assert int(indexed["D3_exact_duplicates"]["rows_flagged_or_changed"]) == 0
    assert int(indexed["D4_repeated_property_id"]["rows_flagged_or_changed"]) == 2
    assert int(indexed["D7_D8_price_range_quality"]["rows_flagged_or_changed"]) == 78
    assert int(indexed["D9_PRICE_SQFT_review"]["rows_flagged_or_changed"]) == 497


def test_final_cleaning_audit_has_localized_month_baseline():
    audit = json.loads((ROOT / "audit/hyderabad_cleaning_audit.json").read_text(encoding="utf-8"))
    derived = audit["derived_counts"]
    assert derived["date_status_counts"] == {"invalid_missing": 242, "valid": 9245}
    assert derived["window_baselines"] == {
        "observed_listing_count": 9162,
        "sale_listing_count": 7633,
        "valid_sale_price_range_count": 7555,
    }
    assert derived["price_sqft_review_rows"] == 497
    months = derived["monthly_posting_counts_all_valid_months"]
    assert months["2023-06"] == 947
    assert months["2023-07"] == 3447
    assert months["2023-08"] == 3531
