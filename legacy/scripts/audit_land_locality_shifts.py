# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from pathlib import Path
import ast
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
MONTHS = ["2023-02", "2023-03", "2023-04"]
SENTINEL = 2147483647


def parse_location(value):
    if not isinstance(value, str) or not value.strip():
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            result = parser(value.strip())
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError, TypeError):
            pass
    return {}


actual_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
if actual_sha != EXPECTED_SHA:
    raise SystemExit(f"STOP: frozen raw checksum mismatch: {actual_sha}")

df = pd.read_csv(RAW, low_memory=False)
required = {
    "POSTING_DATE", "PREFERENCE", "MIN_PRICE", "MAX_PRICE",
    "PROPERTY_TYPE", "location"
}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns: {sorted(missing)}")

ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
utc = pd.to_datetime(ms, unit="ms", utc=True, errors="coerce")
df["month"] = utc.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")

df["min_price"] = pd.to_numeric(df["MIN_PRICE"], errors="coerce")
df["max_price"] = pd.to_numeric(df["MAX_PRICE"], errors="coerce")

loc = df["location"].map(parse_location)
df["locality_name"] = loc.map(
    lambda x: str(x.get("LOCALITY_NAME") or "").strip()
)
df["locality_id"] = loc.map(
    lambda x: str(x.get("LOCALITY_ID") or "").strip()
)

valid = (
    df["PREFERENCE"].astype(str).str.strip().str.upper().eq("S")
    & np.isfinite(df["min_price"])
    & np.isfinite(df["max_price"])
    & df["min_price"].gt(0)
    & df["max_price"].gt(0)
    & df["min_price"].ne(SENTINEL)
    & df["max_price"].ne(SENTINEL)
    & df["min_price"].le(df["max_price"])
    & df["PROPERTY_TYPE"].eq("Residential Land")
    & df["month"].isin(MONTHS)
)
land = df.loc[valid].copy()
land = land[land["locality_name"].ne("")].copy()
land["locality_key"] = land["locality_id"]
land.loc[land["locality_key"].eq(""), "locality_key"] = (
    "NAME:" + land.loc[land["locality_key"].eq(""), "locality_name"]
)

print("Frozen snapshot SHA-256 verified:", actual_sha)
print("Valid sale-price rows for residential land:")
print(land.groupby("month").size().reindex(MONTHS, fill_value=0).to_string())

grouped = land.groupby(
    ["month", "locality_key", "locality_name"], dropna=False
).agg(
    n=("min_price", "size"),
    median_min_inr=("min_price", "median"),
    median_max_inr=("max_price", "median"),
).reset_index()

print("\n=== TOP 12 LOCALITIES WITHIN EACH MONTH ===")
for month in MONTHS:
    part = grouped[grouped["month"] == month].sort_values(
        ["n", "locality_name"], ascending=[False, True]
    )
    total = int(land["month"].eq(month).sum())
    print(f"\n{month}; denominator={total} valid land-sale rows")
    for _, row in part.head(12).iterrows():
        share = 100 * row["n"] / total if total else 0
        print(
            f"{row['locality_name']} [ID {row['locality_key']}]: "
            f"n={int(row['n'])}, share={share:.2f}%, "
            f"median_min=INR {row['median_min_inr']:,.0f}, "
            f"median_max=INR {row['median_max_inr']:,.0f}"
        )

print("\n=== SAME HIGH-VOLUME LOCALITIES ACROSS MONTHS ===")
top_keys = set()
for month in MONTHS:
    part = grouped[grouped["month"] == month].nlargest(8, "n")
    top_keys.update(part["locality_key"].tolist())

candidates = grouped[grouped["locality_key"].isin(top_keys)]
names = (
    candidates.groupby("locality_key")["locality_name"]
    .agg(lambda s: s.iloc[0])
    .to_dict()
)

for key in sorted(top_keys, key=lambda k: names.get(k, "")):
    print(f"\n{names.get(key, '<unknown>')} [ID {key}]")
    for month in MONTHS:
        row = candidates[
            (candidates["locality_key"] == key)
            & (candidates["month"] == month)
        ]
        if row.empty:
            print(f"  {month}: n=0; no median")
        else:
            r = row.iloc[0]
            print(
                f"  {month}: n={int(r['n'])}, "
                f"median_min=INR {r['median_min_inr']:,.0f}, "
                f"median_max=INR {r['median_max_inr']:,.0f}"
            )

print("\nAudit finished. Raw CSV was not modified.")
