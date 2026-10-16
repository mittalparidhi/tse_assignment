#!/usr/bin/env python3
# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
"""Rebuild the canonical processed Hyderabad snapshot from the frozen raw CSV.

This wraps the existing cleaner rather than replacing its area/map parsers, then
adds the date, price-quality, and identity fields required by contracts/Data.md.
Run from any working directory: python scripts/build_processed_snapshot.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "scripts" else Path(__file__).resolve().parent
# This file is intended to live at <repo>/scripts/build_processed_snapshot.py.
if not (ROOT / "data" / "raw" / "hyderabad.csv").is_file():
    ROOT = Path.cwd().resolve()
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
BASE_CLEANER = ROOT / "scripts" / "clean_hyderabad.py"
OUT = ROOT / "data" / "processed" / "hyderabad_clean.csv"
HASH_OUT = ROOT / "data" / "processed" / "hyderabad_clean.csv.sha256"
AUDIT_OUT = ROOT / "audit" / "hyderabad_snapshot_manifest.json"
FROZEN_SOURCE_SHA256 = "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
CONTRACT_VERSION = "1.0.0-draft"
CLEANING_VERSION = "1.1.0"
TIMEZONE = "Asia/Kolkata"
WINDOW_START = "2022-09"
WINDOW_END = "2023-08"
PRICE_SENTINEL = 2147483647.0
EXPECTED = {
    "input_rows": 9487,
    "source_columns": 55,
    "valid_posting_dates": 9245,
    "invalid_posting_dates": 242,
    "in_window_observed_rows": 9162,
    "in_window_sale_rows": 7633,
    "in_window_valid_sale_price_rows": 7555,
    "exact_duplicate_excess_rows": 0,
}
ZONE = ZoneInfo(TIMEZONE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise RuntimeError(f"CSV has no header: {path}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise RuntimeError(f"CSV contains duplicate column names: {path}")
        return list(reader.fieldnames), list(reader)


def number(value: object) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_posting_date(value: object) -> tuple[str, str, str]:
    """Return ISO local datetime, YYYY-MM, and an explicit status."""
    if value is None or not str(value).strip():
        return "", "", "invalid_missing"
    try:
        milliseconds = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return "", "", "invalid_non_numeric"
    if not math.isfinite(milliseconds):
        return "", "", "invalid_non_finite"
    try:
        local_dt = datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc).astimezone(ZONE)
    except (OverflowError, OSError, ValueError):
        return "", "", "invalid_out_of_range"
    return local_dt.isoformat(), local_dt.strftime("%Y-%m"), "valid"


def price_flags(row: dict[str, str]) -> dict[str, str]:
    low = number(row.get("MIN_PRICE"))
    high = number(row.get("MAX_PRICE"))
    bad_bound = low is None or high is None
    sentinel = low == PRICE_SENTINEL or high == PRICE_SENTINEL
    non_positive = (low is not None and low <= 0) or (high is not None and high <= 0)
    eligible_numeric_bounds = (
        low is not None and high is not None
        and low > 0 and high > 0
        and low != PRICE_SENTINEL and high != PRICE_SENTINEL
    )
    inverted = eligible_numeric_bounds and low > high
    if bad_bound:
        status = "invalid_price_bound"
    elif sentinel:
        status = "price_sentinel"
    elif non_positive:
        status = "non_positive_price"
    elif inverted:
        status = "inverted_price_range"
    else:
        status = "valid"
    sqft = number(row.get("PRICE_SQFT"))
    review = sqft is not None and sqft >= 100000
    return {
        "invalid_price_bound": str(bad_bound).lower(),
        "non_positive_price": str(non_positive).lower(),
        "price_sentinel": str(sentinel).lower(),
        "inverted_price_range": str(bool(inverted)).lower(),
        "price_range_status": status,
        # This is only a review flag; it does not assert valid units or semantics.
        "price_sqft_review_flag": str(review).lower(),
    }


def main() -> int:
    if not RAW.is_file():
        raise RuntimeError(f"Frozen raw source not found: {RAW}")
    if not BASE_CLEANER.is_file():
        raise RuntimeError(f"Existing cleaner not found: {BASE_CLEANER}")

    raw_hash_before = sha256_file(RAW)
    if raw_hash_before != FROZEN_SOURCE_SHA256:
        raise RuntimeError(
            "snapshot_integrity_error: raw CSV hash differs from the pinned frozen snapshot; "
            "the expected hash will not be regenerated automatically"
        )

    source_columns, raw_rows = read_csv(RAW)
    if len(raw_rows) != EXPECTED["input_rows"] or len(source_columns) != EXPECTED["source_columns"]:
        raise RuntimeError(
            f"snapshot_integrity_error: expected {EXPECTED['input_rows']} rows and "
            f"{EXPECTED['source_columns']} source columns; found {len(raw_rows)} and {len(source_columns)}"
        )

    # Re-run the pre-existing, non-destructive area/map cleaner.
    subprocess.run([sys.executable, str(BASE_CLEANER)], cwd=ROOT, check=True)
    processed_columns, processed_rows = read_csv(OUT)
    if len(processed_rows) != len(raw_rows):
        raise RuntimeError(f"Row-count mismatch after base cleaner: {len(raw_rows)} -> {len(processed_rows)}")
    if processed_columns[: len(source_columns)] != source_columns:
        raise RuntimeError("Base cleaner changed the source-column order or removed source columns")
    # The existing cleaner intentionally strips boundary whitespace from source cells.
    # Verify row order and all original field values after that documented normalization.
    for row_index, (raw_row, processed_row) in enumerate(zip(raw_rows, processed_rows)):
        for column in source_columns:
            expected_cell = (raw_row.get(column) or "").strip()
            actual_cell = processed_row.get(column) or ""
            if actual_cell != expected_cell:
                raise RuntimeError(
                    f"Source-value/order validation failed at row {row_index}, column {column!r}"
                )

    added_columns = [
        "source_row_id",
        "posting_datetime_local",
        "posting_month",
        "posting_date_status",
        "invalid_price_bound",
        "non_positive_price",
        "price_sentinel",
        "inverted_price_range",
        "price_range_status",
        "price_sqft_review_flag",
        "prop_id_repeated_flag",
        "exact_duplicate_row_flag",
    ]
    clashes = sorted(set(added_columns) & set(processed_columns))
    if clashes:
        raise RuntimeError(f"Derived field collision; refusing to overwrite existing columns: {clashes}")

    # Detect full-row duplicates using the original source field values before cleaning.
    raw_signatures = [tuple(row.get(column, "") or "" for column in source_columns) for row in raw_rows]
    signature_counts = Counter(raw_signatures)
    exact_duplicate_rows = {i for i, signature in enumerate(raw_signatures) if signature_counts[signature] > 1}
    excess_duplicate_count = sum(count - 1 for count in signature_counts.values() if count > 1)

    prop_counts = Counter((row.get("PROP_ID") or "").strip() for row in processed_rows)
    prop_counts.pop("", None)
    repeated_prop_ids = {prop_id for prop_id, count in prop_counts.items() if count > 1}

    date_status_counts: Counter[str] = Counter()
    price_status_counts: Counter[str] = Counter()
    for row_index, row in enumerate(processed_rows):
        local_dt, month, date_status = parse_posting_date(row.get("POSTING_DATE"))
        row.update({
            "source_row_id": str(row_index),
            "posting_datetime_local": local_dt,
            "posting_month": month,
            "posting_date_status": date_status,
            **price_flags(row),
            "prop_id_repeated_flag": str((row.get("PROP_ID") or "").strip() in repeated_prop_ids).lower(),
            "exact_duplicate_row_flag": str(row_index in exact_duplicate_rows).lower(),
        })
        date_status_counts[date_status] += 1
        price_status_counts[row["price_range_status"]] += 1

    def in_window(row: dict[str, str]) -> bool:
        return row.get("posting_date_status") == "valid" and WINDOW_START <= row.get("posting_month", "") <= WINDOW_END

    window_rows = [row for row in processed_rows if in_window(row)]
    window_sales = [row for row in window_rows if row.get("PREFERENCE", "").strip() == "S"]
    window_valid_sale_ranges = [row for row in window_sales if row.get("price_range_status") == "valid"]
    actual = {
        "input_rows": len(raw_rows),
        "source_columns": len(source_columns),
        "valid_posting_dates": date_status_counts["valid"],
        "invalid_posting_dates": sum(count for status, count in date_status_counts.items() if status != "valid"),
        "in_window_observed_rows": len(window_rows),
        "in_window_sale_rows": len(window_sales),
        "in_window_valid_sale_price_rows": len(window_valid_sale_ranges),
        "exact_duplicate_excess_rows": excess_duplicate_count,
    }
    mismatches = {key: {"expected": value, "actual": actual[key]} for key, value in EXPECTED.items() if actual[key] != value}
    if mismatches:
        raise RuntimeError(f"Data-contract baseline mismatch; output not written: {json.dumps(mismatches, sort_keys=True)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    final_columns = processed_columns + added_columns
    with OUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=final_columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(processed_rows)

    processed_hash = sha256_file(OUT)
    HASH_OUT.write_text(f"{processed_hash}  data/processed/hyderabad_clean.csv\n", encoding="ascii", newline="\n")

    repeated_prop_audit = [
        {"prop_id": prop_id, "row_count": prop_counts[prop_id]}
        for prop_id in sorted(repeated_prop_ids)
    ]
    monthly_posting_counts = {
        month: sum(1 for row in processed_rows if row.get("posting_month") == month)
        for month in sorted({row.get("posting_month", "") for row in processed_rows if row.get("posting_month")})
    }
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "cleaning_script_version": CLEANING_VERSION,
        "timezone": TIMEZONE,
        "raw_path": "data/raw/hyderabad.csv",
        "raw_sha256": raw_hash_before,
        "processed_path": "data/processed/hyderabad_clean.csv",
        "processed_sha256": processed_hash,
        "input_rows": len(raw_rows),
        "output_rows": len(processed_rows),
        "source_columns": len(source_columns),
        "output_columns": len(final_columns),
        "date_status_counts": dict(sorted(date_status_counts.items())),
        "monthly_posting_counts_all_valid_months": monthly_posting_counts,
        "price_range_status_counts": dict(sorted(price_status_counts.items())),
        "analysis_window": {"start": WINDOW_START, "end": WINDOW_END},
        "window_baselines": {
            "observed_listing_count": len(window_rows),
            "sale_listing_count": len(window_sales),
            "valid_sale_price_range_count": len(window_valid_sale_ranges),
        },
        "exact_duplicate_excess_rows": excess_duplicate_count,
        "repeated_prop_ids": repeated_prop_audit,
        "audit_artifacts": [
            "audit/hyderabad_cleaning_audit.json",
            "audit/hyderabad_cleaning_summary.csv",
            "audit/hyderabad_snapshot_manifest.json",
        ],
    }
    AUDIT_OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    raw_hash_after = sha256_file(RAW)
    if raw_hash_after != raw_hash_before:
        raise RuntimeError("snapshot_integrity_error: raw CSV changed during processing")

    # ISSUE3_FINAL_AUDIT_FINALIZER: synchronize the audit/summary with the final
    # processed artifact after the base cleaner has written its preliminary audit.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "finalize_snapshot_audits.py")], cwd=ROOT, check=True)
    print(json.dumps({"status": "ok", **actual, "processed_sha256": processed_hash, "output_columns": len(final_columns)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
