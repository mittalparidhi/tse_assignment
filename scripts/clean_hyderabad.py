import ast
import csv
import hashlib
import json
import math
import re
from pathlib import Path

RAW = Path("data/raw/hyderabad.csv")
OUT = Path("data/processed/hyderabad_clean.csv")
HASH_OUT = Path("data/processed/hyderabad_clean.csv.sha256")
AUDIT_OUT = Path("audit/hyderabad_cleaning_audit.json")

# Exact international conversion: 1 square metre = 10.763910416709722 square feet.
SQM_TO_SQFT = 10.763910416709722
AREA_REL_TOLERANCE = 0.02
AREA_ABS_TOLERANCE_SQFT = 2.0

DERIVED_COLUMNS = [
    "SOURCE_ROW_NUMBER",
    "AREA_MIN_SQFT_PARSED",
    "AREA_MAX_SQFT_PARSED",
    "AREA_PARSE_STATUS",
    "SOURCE_AREA_FIELD_VALIDATION",
    "MAP_LATITUDE_PARSED",
    "MAP_LONGITUDE_PARSED",
    "MAP_DETAILS_PARSE_STATUS",
    "LOCATION_CITY_NAME_PARSED",
    "LOCALITY_NAME_PARSED",
    "LOCATION_PARSE_STATUS",
]

AREA_RE = re.compile(
    r"^\s*"
    r"(?P<low>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*[-–—]\s*(?P<high>\d[\d,]*(?:\.\d+)?))?"
    r"\s*(?P<unit>sq\.?\s*ft\.?|sqft|square\s+feet)"
    r"\s*$",
    re.IGNORECASE,
)

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clean_text(value):
    if value is None:
        return ""
    # Strip boundary whitespace; preserve meaningful internal text.
    value = value.strip()
    return "" if value == "" else value

def safe_dict(value):
    """Parse only literal dictionaries. Never execute source strings."""
    if not isinstance(value, str) or not value.strip():
        return None, "missing"
    try:
        parsed = ast.literal_eval(value.strip())
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None, "malformed"
    if not isinstance(parsed, dict):
        return None, "not_dictionary"
    return parsed, "parsed"

def safe_coordinate(value, lower, upper):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not lower <= number <= upper:
        return None
    return number

def parse_area(value):
    """Parse only explicit square-foot values/ranges from AREA."""
    if not isinstance(value, str) or not value.strip():
        return None, None, "missing"
    match = AREA_RE.fullmatch(value)
    if not match:
        return None, None, "unrecognized_or_unit_missing"

    try:
        low = float(match.group("low").replace(",", ""))
        high_text = match.group("high")
        high = float(high_text.replace(",", "")) if high_text else low
    except (ValueError, OverflowError):
        return None, None, "invalid_number"

    if (
        not math.isfinite(low)
        or not math.isfinite(high)
        or low <= 0
        or high <= 0
        or low > high
    ):
        return None, None, "invalid_range"

    return low, high, "valid_sqft"

def parse_source_area_number(value):
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return n

def close_enough(a, b):
    return math.isclose(
        a, b, rel_tol=AREA_REL_TOLERANCE,
        abs_tol=AREA_ABS_TOLERANCE_SQFT
    )

def format_number(value):
    if value is None:
        return ""
    # Stable decimal text; no scientific notation for ordinary values.
    return format(value, ".12g")

def main():
    if not RAW.is_file():
        raise SystemExit(f"ERROR: Raw source not found: {RAW}")

    raw_hash_before = sha256_file(RAW)

    with RAW.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        source_columns = reader.fieldnames
        if not source_columns:
            raise SystemExit("ERROR: CSV has no header")
        if len(source_columns) != len(set(source_columns)):
            raise SystemExit("ERROR: Duplicate column names in raw CSV")
        if set(source_columns) & set(DERIVED_COLUMNS):
            raise SystemExit("ERROR: Derived column name collides with source")

        rows = list(reader)

    # Source row order is retained. SOURCE_ROW_NUMBER is a 1-based data-row
    # reference, not a claim that PROP_ID uniquely identifies a listing.
    output_rows = []
    counts = {
        "area_valid_sqft": 0,
        "area_missing": 0,
        "area_unrecognized_or_unit_missing": 0,
        "area_invalid": 0,
        "source_area_fields_consistent_after_sqm_conversion": 0,
        "source_area_fields_mismatch": 0,
        "source_area_fields_unverifiable": 0,
        "map_parsed": 0,
        "map_missing": 0,
        "map_invalid": 0,
        "location_parsed": 0,
        "location_missing": 0,
        "location_invalid": 0,
    }

    for row_number, raw_row in enumerate(rows, start=1):
        row = {k: clean_text(v) for k, v in raw_row.items()}

        area_low, area_high, area_status = parse_area(row.get("AREA", ""))
        if area_status == "valid_sqft":
            counts["area_valid_sqft"] += 1
        elif area_status == "missing":
            counts["area_missing"] += 1
        elif area_status == "unrecognized_or_unit_missing":
            counts["area_unrecognized_or_unit_missing"] += 1
        else:
            counts["area_invalid"] += 1

        source_min = parse_source_area_number(row.get("MIN_AREA_SQFT", ""))
        source_max = parse_source_area_number(row.get("MAX_AREA_SQFT", ""))

        # These source columns are untrusted. Compare the hypothesis that they
        # contain square metres against AREA converted to square feet.
        if area_status != "valid_sqft" or source_min is None or source_max is None:
            source_area_status = "unverifiable"
            counts["source_area_fields_unverifiable"] += 1
        else:
            converted_min = source_min * SQM_TO_SQFT
            converted_max = source_max * SQM_TO_SQFT
            consistent = (
                close_enough(converted_min, area_low)
                and close_enough(converted_max, area_high)
            )
            if consistent:
                source_area_status = "consistent_if_source_values_are_sqm"
                counts["source_area_fields_consistent_after_sqm_conversion"] += 1
            else:
                source_area_status = "mismatch_review_required"
                counts["source_area_fields_mismatch"] += 1

        map_dict, map_status = safe_dict(row.get("MAP_DETAILS", ""))
        lat = lon = None
        if map_status == "parsed":
            lat = safe_coordinate(map_dict.get("LATITUDE"), -90, 90)
            lon = safe_coordinate(map_dict.get("LONGITUDE"), -180, 180)
            if lat is None or lon is None:
                map_status = "parsed_but_coordinates_invalid"
                lat = lon = None
                counts["map_invalid"] += 1
            else:
                counts["map_parsed"] += 1
        elif map_status == "missing":
            counts["map_missing"] += 1
        else:
            counts["map_invalid"] += 1

        location_dict, location_status = safe_dict(row.get("location", ""))
        city_name = locality_name = ""
        if location_status == "parsed":
            city_name = clean_text(location_dict.get("CITY_NAME"))
            locality_name = clean_text(location_dict.get("LOCALITY_NAME"))
            counts["location_parsed"] += 1
        elif location_status == "missing":
            counts["location_missing"] += 1
        else:
            counts["location_invalid"] += 1

        row.update({
            "SOURCE_ROW_NUMBER": str(row_number),
            "AREA_MIN_SQFT_PARSED": format_number(area_low),
            "AREA_MAX_SQFT_PARSED": format_number(area_high),
            "AREA_PARSE_STATUS": area_status,
            "SOURCE_AREA_FIELD_VALIDATION": source_area_status,
            "MAP_LATITUDE_PARSED": format_number(lat),
            "MAP_LONGITUDE_PARSED": format_number(lon),
            "MAP_DETAILS_PARSE_STATUS": map_status,
            "LOCATION_CITY_NAME_PARSED": city_name,
            "LOCALITY_NAME_PARSED": locality_name,
            "LOCATION_PARSE_STATUS": location_status,
        })
        output_rows.append(row)

    output_columns = list(source_columns) + DERIVED_COLUMNS
    temp_out = OUT.with_suffix(".csv.tmp")

    # Fixed UTF-8, LF line endings, column order and row order.
    with temp_out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=output_columns, extrasaction="raise",
            lineterminator="\n", quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        writer.writerows(output_rows)
    temp_out.replace(OUT)

    output_hash = sha256_file(OUT)
    HASH_OUT.write_text(f"{output_hash}  {OUT.as_posix()}\n", encoding="ascii")

    raw_hash_after = sha256_file(RAW)
    raw_unchanged = raw_hash_before == raw_hash_after

    audit = {
        "cleaning_version": "1.0.0",
        "raw_file": RAW.as_posix(),
        "raw_sha256_before": raw_hash_before,
        "raw_sha256_after": raw_hash_after,
        "raw_unchanged": raw_unchanged,
        "processed_file": OUT.as_posix(),
        "processed_sha256": output_hash,
        "checksum_file": HASH_OUT.as_posix(),
        "row_count": len(output_rows),
        "source_column_count": len(source_columns),
        "output_column_count": len(output_columns),
        "row_order": "preserved",
        "canonicalization_rules": {
            "text": "strip boundary whitespace; empty strings represent missing values",
            "csv": "UTF-8 without BOM, LF line endings, fixed source-then-derived column order",
            "map_details": "ast.literal_eval dictionary only; coordinate ranges validated",
            "location": "ast.literal_eval dictionary only; CITY_NAME and LOCALITY_NAME extracted when available",
            "area": "AREA parsed only when explicit sq.ft. unit is present; ranges preserved",
            "source_area_columns": "MIN_AREA_SQFT/MAX_AREA_SQFT retained unchanged and only audited under the sqm-to-sqft hypothesis",
            "deduplication": "none; all source rows retained in source order",
        },
        "counts": counts,
    }
    AUDIT_OUT.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8"
    )

    print(f"Raw rows: {len(rows):,}")
    print(f"Output rows: {len(output_rows):,}")
    print(f"Source columns: {len(source_columns)}")
    print(f"Output columns: {len(output_columns)}")
    print(f"Raw SHA256 before: {raw_hash_before}")
    print(f"Raw SHA256 after:  {raw_hash_after}")
    print(f"Raw unchanged: {raw_unchanged}")
    print(f"Processed SHA256: {output_hash}")
    print(f"Processed CSV: {OUT}")
    print(f"Checksum: {HASH_OUT}")
    print(f"Audit: {AUDIT_OUT}")
    print("Counts:")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")

    if not raw_unchanged:
        raise SystemExit("ERROR: Raw source hash changed during cleaning")
    if len(output_rows) != len(rows):
        raise SystemExit("ERROR: Row count changed unexpectedly")
    print("VALIDATION: PASS")

if __name__ == "__main__":
    main()
