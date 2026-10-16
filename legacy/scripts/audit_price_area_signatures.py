# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from pathlib import Path
import ast
import hashlib
import json
import re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
SENTINEL = 2147483647


def parse_location(value):
    if not isinstance(value, str) or not value.strip():
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(value.strip())
            if isinstance(obj, dict):
                return obj
        except (ValueError, SyntaxError, TypeError):
            pass
    return {}


def area_sqft(value):
    """Return area in sq.ft.; ranges use their midpoint; unknown units are skipped."""
    if not isinstance(value, str):
        return np.nan
    text = value.lower().replace(",", "")
    if "sq.ft" not in text and "sq. ft" not in text:
        return np.nan
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return np.nan
    vals = [float(x) for x in numbers]
    if len(vals) >= 2 and "-" in text:
        result = (vals[0] + vals[1]) / 2
    else:
        result = vals[0]
    return result if result > 0 else np.nan


actual = hashlib.sha256(RAW.read_bytes()).hexdigest()
if actual != EXPECTED_SHA:
    raise SystemExit(f"STOP: raw checksum mismatch: {actual}")

df = pd.read_csv(RAW, low_memory=False)
ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
dt = pd.to_datetime(ms, unit="ms", utc=True, errors="coerce")
df["month"] = dt.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")
df["min_price"] = pd.to_numeric(df["MIN_PRICE"], errors="coerce")
df["max_price"] = pd.to_numeric(df["MAX_PRICE"], errors="coerce")
df["area_sqft_audit"] = df["AREA"].map(area_sqft)

loc = df["location"].map(parse_location)
df["locality_name"] = loc.map(lambda x: str(x.get("LOCALITY_NAME") or "").strip())
df["locality_id"] = loc.map(lambda x: str(x.get("LOCALITY_ID") or "").strip())

valid = (
    df["PREFERENCE"].astype(str).str.strip().str.upper().eq("S")
    & np.isfinite(df["min_price"])
    & np.isfinite(df["max_price"])
    & df["min_price"].gt(0)
    & df["max_price"].gt(0)
    & df["min_price"].ne(SENTINEL)
    & df["max_price"].ne(SENTINEL)
    & df["min_price"].le(df["max_price"])
    & np.isfinite(df["area_sqft_audit"])
    & df["month"].between("2022-09", "2023-08")
)

audit = df.loc[valid].copy()
audit["min_price_per_area_proxy"] = (
    audit["min_price"] / audit["area_sqft_audit"]
)
audit["max_price_per_area_proxy"] = (
    audit["max_price"] / audit["area_sqft_audit"]
)

print("Frozen raw checksum verified:", actual)
print("Valid sale rows with interpretable sq.ft. area:", len(audit))
print("IMPORTANT: price/area here is an audit proxy, not the validated PRICE_SQFT metric.")

columns = [
    "month", "PROP_ID", "locality_name", "PROPERTY_TYPE",
    "min_price", "max_price", "AREA", "min_price_per_area_proxy"
]

print("\n=== 10 HIGHEST DERIVED MIN-PRICE / SQ.FT. VALUES ===")
print(
    audit.nlargest(10, "min_price_per_area_proxy")[columns]
    .to_string(index=False, max_colwidth=45, formatters={
        "min_price": lambda x: f"{x:,.0f}",
        "max_price": lambda x: f"{x:,.0f}",
        "min_price_per_area_proxy": lambda x: f"{x:,.2f}",
    })
)

print("\n=== 10 LOWEST DERIVED MIN-PRICE / SQ.FT. VALUES ===")
print(
    audit.nsmallest(10, "min_price_per_area_proxy")[columns]
    .to_string(index=False, max_colwidth=45, formatters={
        "min_price": lambda x: f"{x:,.0f}",
        "max_price": lambda x: f"{x:,.0f}",
        "min_price_per_area_proxy": lambda x: f"{x:,.2f}",
    })
)

print("\n=== REPEATED PRICE-AREA-LOCALITY SIGNATURES ===")
keys = [
    "month", "locality_id", "locality_name", "PROPERTY_TYPE",
    "AREA", "min_price", "max_price"
]
signatures = (
    audit.groupby(keys, dropna=False)
    .agg(rows=("PROP_ID", "size"), unique_ids=("PROP_ID", "nunique"),
         property_ids=("PROP_ID", lambda s: ", ".join(s.astype(str).head(8))))
    .reset_index()
)
repeated = signatures[
    (signatures["rows"] > 1) & (signatures["unique_ids"] > 1)
].sort_values(["rows", "month"], ascending=[False, True])

if repeated.empty:
    print("No repeated signatures with different property IDs found.")
else:
    print(repeated.head(25).to_string(index=False, max_colwidth=45))

print("\nAudit finished. Raw CSV was not modified.")
