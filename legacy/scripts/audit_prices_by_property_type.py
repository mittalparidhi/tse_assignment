# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
PRICE_SENTINEL = 2147483647
MONTHS = ["2023-06", "2023-07", "2023-08"]

actual_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
if actual_sha != EXPECTED_SHA:
    raise SystemExit(f"STOP: raw checksum mismatch: {actual_sha}")

df = pd.read_csv(RAW, low_memory=False)
required = {
    "POSTING_DATE", "PREFERENCE", "MIN_PRICE", "MAX_PRICE", "PROPERTY_TYPE"
}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns: {sorted(missing)}")

ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
utc = pd.to_datetime(ms, unit="ms", utc=True, errors="coerce")
df["month"] = utc.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")

df["min_price"] = pd.to_numeric(df["MIN_PRICE"], errors="coerce")
df["max_price"] = pd.to_numeric(df["MAX_PRICE"], errors="coerce")

finite = (
    np.isfinite(df["min_price"])
    & np.isfinite(df["max_price"])
)
valid = (
    df["PREFERENCE"].astype(str).str.strip().str.upper().eq("S")
    & finite
    & df["min_price"].gt(0)
    & df["max_price"].gt(0)
    & df["min_price"].ne(PRICE_SENTINEL)
    & df["max_price"].ne(PRICE_SENTINEL)
    & df["min_price"].le(df["max_price"])
    & df["month"].isin(MONTHS)
)

sales = df.loc[valid].copy()
sales["property_type"] = (
    sales["PROPERTY_TYPE"].fillna("<MISSING>").astype(str).str.strip()
)
sales.loc[sales["property_type"].eq(""), "property_type"] = "<MISSING>"

print("Frozen snapshot checksum verified:", actual_sha)
print("Valid sale-price ranges by month:")
print(sales.groupby("month").size().reindex(MONTHS, fill_value=0).to_string())

print("\n=== OVERALL MEDIAN PRICE BOUNDS (INR) ===")
overall = sales.groupby("month").agg(
    valid_sale_rows=("min_price", "size"),
    median_min_price_inr=("min_price", "median"),
    median_max_price_inr=("max_price", "median"),
).reindex(MONTHS)
print(overall.to_string(float_format=lambda x: f"{x:,.2f}"))

print("\n=== WITHIN-PROPERTY-TYPE MEDIANS (INR) ===")
grouped = sales.groupby(["month", "property_type"]).agg(
    n=("min_price", "size"),
    median_min_price_inr=("min_price", "median"),
    median_max_price_inr=("max_price", "median"),
).reset_index()

for property_type in sorted(grouped["property_type"].unique()):
    part = grouped[grouped["property_type"] == property_type].set_index("month")
    print(f"\n{property_type}")
    for month in MONTHS:
        if month not in part.index:
            print(f"  {month}: no valid sale-price rows")
            continue

        row = part.loc[month]
        print(
            f"  {month}: n={int(row['n'])}, "
            f"median_min=INR {row['median_min_price_inr']:,.0f}, "
            f"median_max=INR {row['median_max_price_inr']:,.0f}"
        )

print("\nRead-only audit finished; raw dataset was not modified.")
