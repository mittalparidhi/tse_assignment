from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
SENTINEL = 2147483647

MONTHS = pd.period_range("2022-09", "2023-08", freq="M").astype(str).tolist()
MAIN_TYPES = [
    "Residential Apartment",
    "Residential Land",
    "Independent House/Villa",
]

actual_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
if actual_sha != EXPECTED_SHA:
    raise SystemExit(f"STOP: raw checksum mismatch: {actual_sha}")

df = pd.read_csv(RAW, low_memory=False)
required = {
    "POSTING_DATE", "PREFERENCE", "MIN_PRICE", "MAX_PRICE", "PROPERTY_TYPE"
}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing columns: {sorted(missing)}")

ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
utc = pd.to_datetime(ms, unit="ms", utc=True, errors="coerce")
df["month"] = utc.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")

df["min_price"] = pd.to_numeric(df["MIN_PRICE"], errors="coerce")
df["max_price"] = pd.to_numeric(df["MAX_PRICE"], errors="coerce")

valid = (
    df["PREFERENCE"].astype(str).str.strip().str.upper().eq("S")
    & np.isfinite(df["min_price"])
    & np.isfinite(df["max_price"])
    & df["min_price"].gt(0)
    & df["max_price"].gt(0)
    & df["min_price"].ne(SENTINEL)
    & df["max_price"].ne(SENTINEL)
    & df["min_price"].le(df["max_price"])
    & df["month"].isin(MONTHS)
)

sales = df.loc[valid].copy()
sales["property_type"] = (
    sales["PROPERTY_TYPE"].fillna("<MISSING>").astype(str).str.strip()
)
sales.loc[sales["property_type"].eq(""), "property_type"] = "<MISSING>"

print("Frozen snapshot SHA-256 verified:", actual_sha)

print("\n=== OVERALL MONTHLY PRICE MEDIANS ===")
overall = sales.groupby("month").agg(
    valid_sale_rows=("min_price", "size"),
    median_min_inr=("min_price", "median"),
    median_max_inr=("max_price", "median"),
).reindex(MONTHS)
print(overall.to_string(float_format=lambda x: f"{x:,.0f}"))

print("\n=== PROPERTY-TYPE MIX AMONG VALID SALE ROWS ===")
for month in MONTHS:
    part = sales[sales["month"] == month]
    total = len(part)
    print(f"\n{month}: valid sale rows={total}")

    for typ in MAIN_TYPES:
        subset = part[part["property_type"] == typ]
        count = len(subset)
        share = 100 * count / total if total else 0
        print(f"  {typ}: n={count}, share={share:.2f}%")

print("\n=== MEDIANS WITHIN THE THREE MAIN PROPERTY TYPES ===")
grouped = sales.groupby(["month", "property_type"]).agg(
    n=("min_price", "size"),
    median_min_inr=("min_price", "median"),
    median_max_inr=("max_price", "median"),
)

for typ in MAIN_TYPES:
    print(f"\n{typ}")
    for month in MONTHS:
        key = (month, typ)
        if key not in grouped.index:
            print(f"  {month}: no valid sale-price rows")
            continue

        row = grouped.loc[key]
        print(
            f"  {month}: n={int(row['n'])}, "
            f"median_min=INR {row['median_min_inr']:,.0f}, "
            f"median_max=INR {row['median_max_inr']:,.0f}"
        )

print("\nAudit finished. Raw data was not modified.")
