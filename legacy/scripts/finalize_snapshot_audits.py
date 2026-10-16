#!/usr/bin/env python3
# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
"""Reconcile the final snapshot audit artifacts with the 78-column CSV.

The base cleaner writes a preliminary 66-column audit. This finalizer upgrades
that record after build_processed_snapshot.py appends contract-derived fields.
It validates the raw/processed hashes and contract baselines before writing.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/hyderabad.csv"
PROCESSED = ROOT / "data/processed/hyderabad_clean.csv"
CHECKSUM = ROOT / "data/processed/hyderabad_clean.csv.sha256"
AUDIT = ROOT / "audit/hyderabad_cleaning_audit.json"
SUMMARY = ROOT / "audit/hyderabad_cleaning_summary.csv"
MANIFEST = ROOT / "audit/hyderabad_snapshot_manifest.json"
FROZEN_RAW_SHA256 = "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
WINDOW_START = "2022-09"
WINDOW_END = "2023-08"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise RuntimeError(f"CSV has no header: {path}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise RuntimeError(f"CSV has duplicate field names: {path}")
        return list(reader.fieldnames), list(reader)


def truth(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def main() -> int:
    for path in (RAW, PROCESSED, CHECKSUM, AUDIT, MANIFEST):
        if not path.is_file():
            raise RuntimeError(f"Required artifact missing: {path.relative_to(ROOT)}")

    raw_hash = sha256(RAW)
    processed_hash = sha256(PROCESSED)
    if raw_hash != FROZEN_RAW_SHA256:
        raise RuntimeError("snapshot_integrity_error: frozen raw hash mismatch")
    checksum_text = CHECKSUM.read_text(encoding="ascii").strip().split()
    if not checksum_text or checksum_text[0] != processed_hash:
        raise RuntimeError("processed checksum sidecar does not match the processed CSV")

    source_columns, raw_rows = read_rows(RAW)
    columns, rows = read_rows(PROCESSED)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if len(rows) != 9487 or len(source_columns) != 55:
        raise RuntimeError(f"Expected 9,487 rows/55 source columns; got {len(rows)}/{len(source_columns)}")
    if columns[:len(source_columns)] != source_columns:
        raise RuntimeError("Processed artifact does not preserve the 55 original source columns first")

    required = {
        "source_row_id", "posting_datetime_local", "posting_month", "posting_date_status",
        "invalid_price_bound", "non_positive_price", "price_sentinel", "inverted_price_range",
        "price_range_status", "price_sqft_review_flag", "prop_id_repeated_flag",
        "exact_duplicate_row_flag", "PROP_ID", "PREFERENCE", "POSTING_DATE",
    }
    missing = sorted(required - set(columns))
    if missing:
        raise RuntimeError(f"Processed CSV is missing required columns: {missing}")
    ids = [row["source_row_id"] for row in rows]
    if ids != [str(i) for i in range(len(rows))]:
        raise RuntimeError("source_row_id must be the continuous zero-based raw row ordinal")

    date_counts = Counter(row["posting_date_status"] for row in rows)
    month_counts = Counter(row["posting_month"] for row in rows if row["posting_date_status"] == "valid" and row["posting_month"])
    price_counts = Counter(row["price_range_status"] for row in rows)
    flag_counts = {
        column: sum(truth(row[column]) for row in rows)
        for column in (
            "invalid_price_bound", "non_positive_price", "price_sentinel",
            "inverted_price_range", "price_sqft_review_flag", "prop_id_repeated_flag",
            "exact_duplicate_row_flag",
        )
    }
    start_rows = [
        row for row in rows
        if row["posting_date_status"] == "valid" and WINDOW_START <= row["posting_month"] <= WINDOW_END
    ]
    sale_rows = [row for row in start_rows if row.get("PREFERENCE", "").strip() == "S"]
    valid_sale_rows = [row for row in sale_rows if row["price_range_status"] == "valid"]
    repeated_ids = Counter(row.get("PROP_ID", "").strip() for row in rows if row.get("PROP_ID", "").strip())
    repeated_prop_ids = [
        {"prop_id": prop_id, "row_count": count}
        for prop_id, count in sorted(repeated_ids.items()) if count > 1
    ]

    expected_month_counts = {
        "2022-05": 10, "2022-06": 34, "2022-07": 24, "2022-08": 15,
        "2022-09": 35, "2022-10": 51, "2022-11": 41, "2022-12": 46,
        "2023-01": 32, "2023-02": 45, "2023-03": 217, "2023-04": 288,
        "2023-05": 482, "2023-06": 947, "2023-07": 3447, "2023-08": 3531,
    }
    baseline = {
        "input_rows": len(raw_rows),
        "source_columns": len(source_columns),
        "valid_posting_dates": date_counts.get("valid", 0),
        "invalid_posting_dates": sum(count for status, count in date_counts.items() if status != "valid"),
        "observed_listing_count": len(start_rows),
        "sale_listing_count": len(sale_rows),
        "valid_sale_price_range_count": len(valid_sale_rows),
        "exact_duplicate_excess_rows": flag_counts["exact_duplicate_row_flag"],
        "price_sqft_review_rows": flag_counts["price_sqft_review_flag"],
    }
    expected_baseline = {
        "input_rows": 9487, "source_columns": 55, "valid_posting_dates": 9245,
        "invalid_posting_dates": 242, "observed_listing_count": 9162,
        "sale_listing_count": 7633, "valid_sale_price_range_count": 7555,
        "exact_duplicate_excess_rows": 0, "price_sqft_review_rows": 497,
    }
    if baseline != expected_baseline:
        raise RuntimeError(f"Contract baseline mismatch: expected={expected_baseline}, actual={baseline}")
    if dict(sorted(month_counts.items())) != expected_month_counts:
        raise RuntimeError("Localized posting-month counts do not match contracts/Data.md")
    if manifest.get("processed_sha256") != processed_hash or manifest.get("raw_sha256") != raw_hash:
        raise RuntimeError("Snapshot manifest hashes do not match the raw/processed files")
    if dict(sorted(date_counts.items())) != manifest.get("date_status_counts"):
        raise RuntimeError("Manifest date status counts disagree with processed CSV")
    if dict(sorted(price_counts.items())) != manifest.get("price_range_status_counts"):
        raise RuntimeError("Manifest price status counts disagree with processed CSV")
    if dict(sorted(month_counts.items())) != manifest.get("monthly_posting_counts_all_valid_months"):
        raise RuntimeError("Manifest month counts disagree with processed CSV")

    # Update, rather than discard, the base cleaner's area/map/location audit.
    audit.update({
        "cleaning_version": manifest.get("cleaning_script_version", "1.1.0"),
        "raw_file": "data/raw/hyderabad.csv",
        "raw_sha256_before": raw_hash,
        "raw_sha256_after": raw_hash,
        "raw_unchanged": True,
        "processed_file": "data/processed/hyderabad_clean.csv",
        "processed_sha256": processed_hash,
        "checksum_file": "data/processed/hyderabad_clean.csv.sha256",
        "row_count": len(rows),
        "source_column_count": len(source_columns),
        "output_column_count": len(columns),
        "row_order": "preserved; source_row_id is the zero-based raw row ordinal",
        "canonicalization_rules": {
            **audit.get("canonicalization_rules", {}),
            "posting_date": "POSTING_DATE is Unix milliseconds; parse explicitly as milliseconds, convert the instant to Asia/Kolkata, then derive posting_month; invalid dates remain retained and unassigned to a month",
            "price_bounds": "MIN_PRICE/MAX_PRICE must be numeric, finite, positive, non-sentinel, and coherent (MIN_PRICE <= MAX_PRICE); ineligible records are retained with reason flags",
            "price_sqft": "PRICE_SQFT is preserved; values >= 100000 are review flags only and are not automatically excluded",
            "row_identity": "source_row_id is the stable zero-based raw-row ordinal; source row order retained",
            "deduplication": "none; all source rows retained; exact duplicates are flagged, not removed",
        },
        "derived_counts": {
            "date_status_counts": dict(sorted(date_counts.items())),
            "monthly_posting_counts_all_valid_months": dict(sorted(month_counts.items())),
            "price_range_status_counts": dict(sorted(price_counts.items())),
            "price_reason_flag_counts": {
                "invalid_price_bound": flag_counts["invalid_price_bound"],
                "non_positive_price": flag_counts["non_positive_price"],
                "price_sentinel": flag_counts["price_sentinel"],
                "inverted_price_range": flag_counts["inverted_price_range"],
            },
            "price_sqft_review_rows": flag_counts["price_sqft_review_flag"],
            "repeated_prop_id_rows": flag_counts["prop_id_repeated_flag"],
            "exact_duplicate_rows_flagged": flag_counts["exact_duplicate_row_flag"],
            "window_baselines": {
                "observed_listing_count": len(start_rows),
                "sale_listing_count": len(sale_rows),
                "valid_sale_price_range_count": len(valid_sale_rows),
            },
            "repeated_prop_ids": repeated_prop_ids,
        },
        "audit_artifacts": [
            "audit/hyderabad_cleaning_audit.json",
            "audit/hyderabad_cleaning_summary.csv",
            "audit/hyderabad_snapshot_manifest.json",
        ],
    })
    AUDIT.write_text(json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    base_counts = audit.get("counts", {})
    base_flagged_area = (
        int(base_counts.get("area_missing", 0))
        + int(base_counts.get("area_unrecognized_or_unit_missing", 0))
        + int(base_counts.get("area_invalid", 0))
    )
    base_flagged_location = int(base_counts.get("location_missing", 0)) + int(base_counts.get("location_invalid", 0))
    base_flagged_map = int(base_counts.get("map_missing", 0)) + int(base_counts.get("map_invalid", 0))
    source_area_flags = sum(
        row.get("SOURCE_AREA_FIELD_VALIDATION", "") != "consistent_if_source_values_are_sqm"
        for row in rows
    )
    summary_rows = [
        ("D1_identity", len(rows), len(rows), "data/processed/hyderabad_clean.csv", "Stable source_row_id added to every retained row; source order preserved."),
        ("D2_posting_date_quality", len(rows), baseline["invalid_posting_dates"], "data/processed/hyderabad_clean.csv", "Invalid posting dates retained and excluded from monthly aggregates."),
        ("D3_exact_duplicates", len(rows), baseline["exact_duplicate_excess_rows"], "data/processed/hyderabad_clean.csv", "Exact duplicates flagged; no rows deleted."),
        ("D4_repeated_property_id", len(rows), flag_counts["prop_id_repeated_flag"], "audit/hyderabad_cleaning_audit.json", "Repeated PROP_ID rows reported and preserved."),
        ("D5_sale_scope", len(rows), baseline["sale_listing_count"], "audit/hyderabad_snapshot_manifest.json", "PREFERENCE == S sale rows in the reporting window; not a deduplication rule."),
        ("D7_D8_price_range_quality", len(rows), len(rows) - price_counts.get("valid", 0), "data/processed/hyderabad_clean.csv", "Ineligible price ranges retained with reason flags."),
        ("D9_PRICE_SQFT_review", len(rows), flag_counts["price_sqft_review_flag"], "data/processed/hyderabad_clean.csv", ">= 100000 review flag only; values are not automatically excluded."),
        ("D10_source_area_semantics", len(rows), source_area_flags, "data/processed/hyderabad_clean.csv", "Area source-field comparison is only a hypothesis audit, not a semantic assertion."),
        ("C_area_parse", len(rows), base_flagged_area, "data/processed/hyderabad_clean.csv", "AREA parse accepts explicit square-foot notation only."),
        ("C_map_details_parse", len(rows), base_flagged_map, "data/processed/hyderabad_clean.csv", "MAP_DETAILS is parsed safely and coordinates are range-checked."),
        ("C_location_parse", len(rows), base_flagged_location, "data/processed/hyderabad_clean.csv", "location is parsed with literal-dictionary parsing only."),
        ("R1_snapshot_integrity", len(rows), 0, "audit/hyderabad_snapshot_manifest.json", "Raw and processed hashes verified against frozen metadata."),
    ]
    with SUMMARY.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["rule_id", "rows_inspected", "rows_flagged_or_changed", "output_path", "description"])
        writer.writerows(summary_rows)

    print("FINAL AUDIT VALIDATION: PASS")
    print(f"Processed SHA256: {processed_hash}")
    print(f"Audit columns: {audit['output_column_count']}")
    print(f"Summary rows: {len(summary_rows)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
