# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from pathlib import Path
import ast
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"

EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
MONTHS = ["2023-06", "2023-07", "2023-08"]


def parse_location(value):
    """Parse a location dictionary stored as text; never execute the text."""
    if not isinstance(value, str) or not value.strip():
        return {}

    text = value.strip()

    for parser in (json.loads, ast.literal_eval):
        try:
            result = parser(text)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            pass

    return {}


actual_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
if actual_sha != EXPECTED_SHA:
    raise SystemExit(
        f"STOP: frozen raw checksum mismatch. Actual SHA-256: {actual_sha}"
    )

df = pd.read_csv(RAW, low_memory=False)

required = {"POSTING_DATE", "location", "CITY"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns: {sorted(missing)}")

posting_ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
posting_utc = pd.to_datetime(
    posting_ms, unit="ms", utc=True, errors="coerce"
)
df["posting_date"] = posting_utc.dt.tz_convert("Asia/Kolkata")
df["month"] = df["posting_date"].dt.strftime("%Y-%m")

parsed = df["location"].map(parse_location)
df["locality_name"] = parsed.map(
    lambda x: str(x.get("LOCALITY_NAME") or "").strip()
)
df["locality_id"] = parsed.map(
    lambda x: str(x.get("LOCALITY_ID") or "").strip()
)
df["location_city_name"] = parsed.map(
    lambda x: str(x.get("CITY_NAME") or "").strip()
)

focus = df[df["month"].isin(MONTHS)].copy()
known = focus[focus["locality_name"] != ""].copy()

print("=== SNAPSHOT INTEGRITY ===")
print("SHA-256:", actual_sha)
print("Raw rows:", len(df))
print("Audit rows:", len(focus))
print("Location strings parsed:", int(parsed.map(bool).sum()), "/", len(df))
print(
    "Audit rows with locality name:",
    len(known), "/", len(focus)
)

print("\n=== LOCALITY COVERAGE BY MONTH ===")
for month in MONTHS:
    part = focus[focus["month"] == month]
    named = part[part["locality_name"] != ""]
    ids = named.loc[named["locality_id"] != "", "locality_id"]

    print(
        f"{month}: rows={len(part)}, "
        f"named_locality_rows={len(named)}, "
        f"missing_locality_rows={len(part) - len(named)}, "
        f"distinct_locality_names={named['locality_name'].nunique()}, "
        f"distinct_locality_ids={ids.nunique()}"
    )

print("\n=== TOP 12 LOCALITIES WITHIN EACH MONTH ===")
for month in MONTHS:
    part = known[known["month"] == month]
    counts = part["locality_name"].value_counts()
    total = len(focus[focus["month"] == month])

    print(f"\n{month} (share denominator = all rows in month)")
    for locality, count in counts.head(12).items():
        print(
            f"{locality}: rows={count}, "
            f"share={count / total * 100:.2f}%"
        )

print("\n=== SAME LOCALITIES ACROSS MONTHS ===")
top_localities = known["locality_name"].value_counts().head(15).index

for locality in top_localities:
    values = []
    for month in MONTHS:
        month_rows = len(focus[focus["month"] == month])
        count = int(
            (
                (known["month"] == month)
                & (known["locality_name"] == locality)
            ).sum()
        )
        share = count / month_rows * 100 if month_rows else 0
        values.append(f"{month}: {count} ({share:.2f}%)")

    print(f"{locality} | " + " | ".join(values))

print("\nAudit finished. The raw CSV was read only; no records were changed.")
