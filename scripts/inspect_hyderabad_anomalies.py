
import pandas as pd
from pathlib import Path

path = Path("data/raw/hyderabad.csv")
df = pd.read_csv(path, low_memory=False)

# Parse posting date for readable output.
df["listing_date"] = pd.to_datetime(
    df["POSTING_DATE"], unit="ms", errors="coerce"
)

# 1. Duplicate property IDs.
print("\n=== DUPLICATE PROPERTY IDs ===")
duplicate_ids = df.loc[
    df["PROP_ID"].duplicated(keep=False)
].sort_values("PROP_ID")

if duplicate_ids.empty:
    print("No duplicate IDs found.")
else:
    print(
        duplicate_ids[
            ["PROP_ID", "PRICE", "MIN_PRICE", "MAX_PRICE",
             "PROPERTY_TYPE", "POSTING_DATE", "listing_date"]
        ].to_string(index=False)
    )

# 2. Extreme or sentinel-like price values.
print("\n=== EXTREME PRICE RECORDS ===")
for col in ["MIN_PRICE", "MAX_PRICE"]:
    values = pd.to_numeric(df[col], errors="coerce")
    print(f"\n{col}: values >= 1 billion")
    cols = ["PROP_ID", "PRICE", "MIN_PRICE", "MAX_PRICE",
            "PROPERTY_TYPE", "POSTING_DATE"]
    print(df.loc[values >= 1_000_000_000, cols].head(30).to_string(index=False))

# 3. Extreme price-per-square-foot values.
print("\n=== EXTREME PRICE/SQFT RECORDS ===")
psf = pd.to_numeric(df["PRICE_SQFT"], errors="coerce")
cols = ["PROP_ID", "PRICE", "MIN_PRICE", "MAX_PRICE",
        "PRICE_SQFT", "PRICE_PER_UNIT_AREA",
        "PROPERTY_TYPE", "POSTING_DATE"]

print("PRICE_SQFT >= 100,000:")
print(df.loc[psf >= 100_000, cols].head(30).to_string(index=False))

# 4. Compare area values to help identify possible unit issues.
print("\n=== AREA DISTRIBUTION BY PROPERTY TYPE ===")
for col in ["MIN_AREA_SQFT", "MAX_AREA_SQFT"]:
    print(f"\n{col}")
    print(
        df.groupby("PROPERTY_TYPE", dropna=False)[col]
        .agg(["count", "min", "median", "max"])
        .round(2)
        .to_string()
    )

# 5. Save a compact audit of price and area fields.
Path("audit").mkdir(exist_ok=True)

summary = []
for col in [
    "MIN_PRICE", "MAX_PRICE", "PRICE_SQFT",
    "MIN_AREA_SQFT", "MAX_AREA_SQFT"
]:
    values = pd.to_numeric(df[col], errors="coerce")
    summary.append({
        "column": col,
        "zero_count": int((values == 0).sum()),
        "negative_count": int((values < 0).sum()),
        "at_least_1_billion_count": int(
            (values >= 1_000_000_000).sum()
        ),
        "min": values.min(),
        "median": values.median(),
        "max": values.max()
    })

pd.DataFrame(summary).to_csv(
    "audit/hyderabad_numeric_anomalies.csv", index=False
)

print("\nSaved audit/hyderabad_numeric_anomalies.csv")
