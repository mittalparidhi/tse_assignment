# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
import pandas as pd

path = "data/raw/hyderabad.csv"
df = pd.read_csv(path, nrows=10, low_memory=False)

print("=== ALL CANONICAL SNAPSHOT COLUMNS ===")
for col in df.columns:
    print(col)

print("\n=== DATE-RELATED COLUMNS ===")
matches = [
    col for col in df.columns
    if any(term in col.upper() for term in [
        "DATE", "REGISTER", "LISTING", "POST", "CREAT", "PUBLISH", "UPDATE"
    ])
]

if not matches:
    print("No date-related column names found.")
else:
    for col in matches:
        print(f"\n{col}:")
        print(df[col].dropna().astype(str).head(5).to_list())

print("\n=== SNAPSHOT CHECK ===")
print("Columns:", len(df.columns))
