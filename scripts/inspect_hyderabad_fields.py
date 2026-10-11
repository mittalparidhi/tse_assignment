
import pandas as pd
from pathlib import Path

df = pd.read_csv("data/raw/hyderabad.csv", low_memory=False)

print("=== PROPERTY ID ===")
print("Missing PROP_ID:", df["PROP_ID"].isna().sum())
print("Duplicate PROP_ID rows:", df["PROP_ID"].duplicated().sum())

print("\n=== PREFERENCE ===")
print(df["PREFERENCE"].value_counts(dropna=False).to_string())

print("\n=== TRANSACTION TYPE ===")
print(df["TRANSACT_TYPE"].value_counts(dropna=False).head(20).to_string())

print("\n=== PROPERTY TYPE ===")
print(df["PROPERTY_TYPE"].value_counts(dropna=False).head(20).to_string())

print("\n=== PRICE EXAMPLES ===")
print(df["PRICE"].value_counts(dropna=False).head(30).to_string())

print("\n=== PRICE / AREA FIELD SUMMARY ===")
for col in [
    "MIN_PRICE", "MAX_PRICE", "PRICE_SQFT",
    "PRICE_PER_UNIT_AREA", "MIN_AREA_SQFT", "MAX_AREA_SQFT"
]:
    s = pd.to_numeric(df[col], errors="coerce")
    print(f"\n{col}")
    print("Valid numeric values:", s.notna().sum())
    print("Missing/non-numeric:", s.isna().sum())
    print("Zero values:", (s == 0).sum())
    print("Negative values:", (s < 0).sum())
    print("Min:", s.min())
    print("Median:", s.median())
    print("Max:", s.max())

print("\n=== SAMPLE ROWS ===")
print(
    df[[
        "PROP_ID", "PREFERENCE", "PROPERTY_TYPE",
        "TRANSACT_TYPE", "PRICE", "MIN_PRICE", "MAX_PRICE",
        "PRICE_SQFT", "MIN_AREA_SQFT", "MAX_AREA_SQFT",
        "POSTING_DATE"
    ]].head(12).to_string(index=False)
)
