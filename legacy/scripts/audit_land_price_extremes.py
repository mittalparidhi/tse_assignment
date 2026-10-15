from pathlib import Path
import hashlib
import numpy as np
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

for col in ["MIN_PRICE", "MAX_PRICE"]:
    df[col + "_NUM"] = pd.to_numeric(df[col], errors="coerce")

months = ["2023-02", "2023-03", "2023-04"]
valid = (
    df["PREFERENCE"].astype(str).str.strip().str.upper().eq("S")
    & df["PROPERTY_TYPE"].eq("Residential Land")
    & df["month"].isin(months)
    & np.isfinite(df["MIN_PRICE_NUM"])
    & np.isfinite(df["MAX_PRICE_NUM"])
    & df["MIN_PRICE_NUM"].gt(0)
    & df["MAX_PRICE_NUM"].gt(0)
    & df["MIN_PRICE_NUM"].ne(2147483647)
    & df["MAX_PRICE_NUM"].ne(2147483647)
    & df["MIN_PRICE_NUM"].le(df["MAX_PRICE_NUM"])
)

land = df.loc[valid].copy()

print("Frozen snapshot checksum verified:", actual)
print("Valid land-sale rows examined:", len(land))

columns = [
    "month", "PROP_ID", "CITY", "MIN_PRICE_NUM", "MAX_PRICE_NUM",
    "AREA", "SECONDARY_AREA", "location"
]
columns = [c for c in columns if c in land.columns]

print("\n=== 15 HIGHEST REPORTED MAXIMUM PRICES ===")
top = land.sort_values("MAX_PRICE_NUM", ascending=False).head(15)
print(top[columns].to_string(index=False, max_colwidth=100))

print("\n=== 10 LOWEST REPORTED MINIMUM PRICES ===")
bottom = land.sort_values("MIN_PRICE_NUM", ascending=True).head(10)
print(bottom[columns].to_string(index=False, max_colwidth=100))

print("\nAudit finished. No records were modified or removed.")
