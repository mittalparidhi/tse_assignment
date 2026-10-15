"""Verified access to the canonical processed Hyderabad snapshot.

Production agents use this module instead of independently reading the raw CSV.
The frozen raw bytes are still hashed at every load; listing records are read from
``data/processed/hyderabad_clean.csv`` only after its manifest and checksum pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.schemas import FROZEN_SOURCE_SHA256, LOCAL_TIMEZONE, WINDOW_END, WINDOW_START

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "hyderabad.csv"
PROCESSED_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv"
CHECKSUM_PATH = ROOT / "data" / "processed" / "hyderabad_clean.csv.sha256"
MANIFEST_PATH = ROOT / "audit" / "hyderabad_snapshot_manifest.json"
EXPECTED_ROWS = 9487
EXPECTED_SOURCE_COLUMNS = 55
EXPECTED_OUTPUT_COLUMNS = 78

REQUIRED_COLUMNS = {
    "CITY", "PROPERTY_TYPE", "BEDROOM_NUM", "MIN_PRICE", "MAX_PRICE",
    "REGISTER_DATE__U", "MAP_DETAILS", "location", "PROP_ID", "PREFERENCE",
    "POSTING_DATE", "source_row_id", "posting_datetime_local", "posting_month",
    "posting_date_status", "invalid_price_bound", "non_positive_price",
    "price_sentinel", "inverted_price_range", "price_range_status",
    "price_sqft_review_flag", "prop_id_repeated_flag", "exact_duplicate_row_flag",
}


class SnapshotRepositoryError(RuntimeError):
    """Repository failure with a stable machine-readable error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(message: str, code: str = "snapshot_integrity_error") -> None:
    raise SnapshotRepositoryError(code, message)


def load_processed_snapshot() -> tuple[pd.DataFrame, str]:
    """Return ``(processed_frame, frozen_raw_sha256)`` after integrity checks."""
    if not RAW_PATH.is_file():
        _fail(f"Frozen raw snapshot is missing: {RAW_PATH}", "source_missing")
    if not PROCESSED_PATH.is_file():
        _fail(f"Processed snapshot is missing: {PROCESSED_PATH}", "source_missing")
    if not CHECKSUM_PATH.is_file() or not MANIFEST_PATH.is_file():
        _fail("Processed checksum or snapshot manifest is missing")

    raw_hash = _sha256(RAW_PATH)
    if raw_hash != FROZEN_SOURCE_SHA256:
        _fail(
            "Raw CSV digest differs from the pinned frozen snapshot SHA-256; "
            "the expected hash will not be regenerated automatically."
        )

    try:
        checksum_parts = CHECKSUM_PATH.read_text(encoding="ascii").strip().split()
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"Cannot read processed snapshot metadata: {exc}")
    if not checksum_parts or len(checksum_parts[0]) != 64:
        _fail("Processed checksum sidecar has an invalid format")

    processed_hash = _sha256(PROCESSED_PATH)
    if processed_hash != checksum_parts[0].lower():
        _fail("Processed CSV digest differs from its SHA-256 sidecar")
    if manifest.get("raw_sha256") != raw_hash:
        _fail("Snapshot manifest raw SHA-256 does not match the frozen raw source")
    if manifest.get("processed_sha256") != processed_hash:
        _fail("Snapshot manifest processed SHA-256 does not match the processed CSV")
    if manifest.get("timezone") != LOCAL_TIMEZONE:
        _fail("Snapshot manifest timezone differs from the global contract")
    if manifest.get("analysis_window") != {"start": WINDOW_START, "end": WINDOW_END}:
        _fail("Snapshot manifest analysis window differs from the global contract")

    try:
        frame = pd.read_csv(PROCESSED_PATH, low_memory=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        _fail(f"Cannot parse processed snapshot CSV: {exc}")
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        _fail(f"Processed snapshot is missing required columns: {missing}")

    if len(frame) != EXPECTED_ROWS or manifest.get("input_rows") != EXPECTED_ROWS or manifest.get("output_rows") != EXPECTED_ROWS:
        _fail(f"Expected exactly {EXPECTED_ROWS} processed rows; found {len(frame)}")
    if manifest.get("source_columns") != EXPECTED_SOURCE_COLUMNS:
        _fail("Snapshot manifest source-column count differs from the contract")
    if len(frame.columns) != EXPECTED_OUTPUT_COLUMNS or manifest.get("output_columns") != EXPECTED_OUTPUT_COLUMNS:
        _fail(f"Expected exactly {EXPECTED_OUTPUT_COLUMNS} processed columns; found {len(frame.columns)}")

    ids = pd.to_numeric(frame["source_row_id"], errors="coerce")
    if ids.isna().any() or not np.isfinite(ids.to_numpy(dtype=float)).all():
        _fail("source_row_id contains a missing or non-finite value")
    if not np.equal(ids.to_numpy(dtype=float), np.floor(ids.to_numpy(dtype=float))).all():
        _fail("source_row_id contains a non-integer value")
    if ids.nunique() != EXPECTED_ROWS or not np.array_equal(ids.to_numpy(dtype=np.int64), np.arange(EXPECTED_ROWS, dtype=np.int64)):
        _fail("source_row_id must uniquely preserve zero-based raw row order")

    valid_dates = frame["posting_date_status"].eq("valid")
    if int(valid_dates.sum()) != 9245 or int((~valid_dates).sum()) != 242:
        _fail("Posting-date quality counts do not match the frozen-snapshot baseline")
    months = frame["posting_month"].fillna("").astype(str)
    in_window = valid_dates & months.ge(WINDOW_START) & months.le(WINDOW_END)
    sale = in_window & frame["PREFERENCE"].astype(str).str.strip().eq("S")
    valid_sale_price = sale & frame["price_range_status"].eq("valid")
    baselines = {
        "observed_listing_count": int(in_window.sum()),
        "sale_listing_count": int(sale.sum()),
        "valid_sale_price_range_count": int(valid_sale_price.sum()),
    }
    expected_baselines = {
        "observed_listing_count": 9162,
        "sale_listing_count": 7633,
        "valid_sale_price_range_count": 7555,
    }
    if baselines != expected_baselines:
        _fail(f"Processed snapshot metric-eligibility baselines mismatch: {baselines}")
    if manifest.get("window_baselines") != baselines:
        _fail("Snapshot manifest window baselines differ from values recomputed from the CSV")
    if manifest.get("exact_duplicate_excess_rows") != 0:
        _fail("Snapshot manifest reports exact duplicate excess rows")
    if frame["PROP_ID"].astype(str).eq("Z70135726").sum() != 2:
        _fail("Repeated-property-ID baseline Z70135726 was not preserved")

    return frame, raw_hash
