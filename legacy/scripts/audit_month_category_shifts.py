from pathlib import Path
import hashlib
import pandas as pd

root = Path(__file__).resolve().parents[1]
raw = root / "data" / "raw" / "hyderabad.csv"
expected = "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"

actual = hashlib.sha256(raw.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"STOP: raw checksum mismatch: {actual}")

df = pd.read_csv(raw, low_memory=False)
ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
dt = pd.to_datetime(ms, unit="ms", utc=True, errors="coerce")
df["month"] = dt.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")

months = ["2023-06", "2023-07", "2023-08"]
columns = ["PREFERENCE", "PROPERTY_TYPE", "CITY", "BEDROOM_NUM"]
focus = df[df["month"].isin(months)].copy()

print("Frozen raw SHA-256 verified:", actual)
print("Category percentages are within each month's observed rows.")

for col in columns:
    if col not in focus.columns:
        print(f"\nSKIPPED {col}: column not present")
        continue

    temp = focus[["month", col]].copy()
    temp["category"] = temp[col].fillna("<MISSING>").astype(str)
    counts = (
        temp.groupby(["month", "category"])
        .size()
        .rename("count")
        .reset_index()
    )
    counts["percent"] = counts["count"] / counts.groupby("month")["count"].transform("sum") * 100

    print(f"\n=== {col} ===")
    table = counts.pivot(index="category", columns="month", values="percent")
    count_table = counts.pivot(index="category", columns="month", values="count")
    table = table.reindex(columns=months)
    count_table = count_table.reindex(columns=months)

    for category in table.index:
        print(f"\n{category}")
        for month in months:
            n = count_table.loc[category, month]
            pct = table.loc[category, month]
            n_text = "0" if pd.isna(n) else str(int(n))
            pct_text = "0.00" if pd.isna(pct) else f"{pct:.2f}"
            print(f"  {month}: n={n_text}, share={pct_text}%")

print("\nAudit finished. Raw dataset was not modified.")
