# Credits: Paridhi Mittal. Full attribution: CREDITS.md.

import pandas as pd
from pathlib import Path

DATA = Path("data/raw/hyderabad.csv")
OUT = Path("audit")

OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(DATA, low_memory=False)

print("=== DATASET SUMMARY ===")
print("Rows:", len(df))
print("Columns:", len(df.columns))
print("Column names:", df.columns.tolist())

# Parse the documented posting timestamp.
df["listing_date"] = pd.to_datetime(
    df["POSTING_DATE"],
    unit="ms",
    errors="coerce"
)

valid = df.dropna(subset=["listing_date"]).copy()
valid["listing_month"] = (
    valid["listing_date"].dt.to_period("M").astype(str)
)

print("\n=== DATE AUDIT ===")
print("Valid posting dates:", len(valid))
print("Missing/invalid posting dates:", df["listing_date"].isna().sum())
print("Earliest posting date:", valid["listing_date"].min())
print("Latest posting date:", valid["listing_date"].max())

monthly = (
    valid.groupby("listing_month")
    .size()
    .rename("listing_count")
    .reset_index()
)

print("\n=== MONTHLY LISTING COUNTS ===")
print(monthly.to_string(index=False))

monthly.to_csv(
    OUT / "hyderabad_monthly_counts.csv",
    index=False,
    lineterminator="\n",
)

# Explicitly check consecutive calendar months.
periods = pd.PeriodIndex(monthly["listing_month"], freq="M")
expected = pd.period_range(periods.min(), periods.max(), freq="M")
missing_months = expected.difference(periods)

print("\nObserved months:", len(periods))
print("Missing calendar months:", list(map(str, missing_months)))

# Column-level missingness report.
missingness = pd.DataFrame({
    "column": df.columns,
    "missing_count": df.isna().sum().values,
    "missing_percent": (df.isna().mean().values * 100).round(2)
})

missingness.to_csv(OUT / "hyderabad_missingness.csv", index=False, lineterminator="\n")

print("\nReports saved under:", OUT)
