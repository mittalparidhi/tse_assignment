from pathlib import Path
import hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hyderabad.csv"
EXPECTED_SHA = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)

actual_sha = hashlib.sha256(RAW.read_bytes()).hexdigest()
print("=== FROZEN SNAPSHOT CHECK ===")
print("SHA-256:", actual_sha)

if actual_sha != EXPECTED_SHA:
    raise SystemExit("STOP: raw snapshot checksum does not match the frozen baseline.")

df = pd.read_csv(RAW, low_memory=False)
required = {"POSTING_DATE", "PROP_ID", "PREFERENCE"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing required columns: {sorted(missing)}")

posting_ms = pd.to_numeric(df["POSTING_DATE"], errors="coerce")
posting_utc = pd.to_datetime(posting_ms, unit="ms", utc=True, errors="coerce")
df["posting_date"] = posting_utc.dt.tz_convert("Asia/Kolkata")
df["month"] = df["posting_date"].dt.strftime("%Y-%m")
df["day"] = df["posting_date"].dt.strftime("%Y-%m-%d")

focus = df[df["month"].isin(["2023-06", "2023-07", "2023-08"])].copy()

print("\n=== ROW COUNTS ===")
print("Raw rows:", len(df))
print("Rows with valid posting dates:", int(df["posting_date"].notna().sum()))
print("\nJune-August counts:")
print(focus.groupby("month", dropna=False).size().to_string())

print("\n=== DAILY COUNTS: JULY-AUGUST ===")
daily = (
    focus[focus["month"].isin(["2023-07", "2023-08"])]
    .groupby(["month", "day"])
    .size()
    .rename("rows")
    .reset_index()
)
for month in ["2023-07", "2023-08"]:
    part = daily[daily["month"] == month].sort_values(
        ["rows", "day"], ascending=[False, True]
    )
    print(f"\n{month}: busiest posting dates")
    print(part.head(15).to_string(index=False))
    print("Distinct posting dates:", int(part["day"].nunique()))
    print("Median rows per date:", float(part["rows"].median()) if len(part) else 0)

print("\n=== WEEKLY COUNTS: JULY-AUGUST ===")
weekly_source = focus[
    focus["month"].isin(["2023-07", "2023-08"])
    & focus["posting_date"].notna()
].copy()
weekly_source["week_start"] = (
    weekly_source["posting_date"].dt.strftime("%Y-%m-%d")
)
weekly_source["week_start"] = pd.to_datetime(weekly_source["week_start"])
weekly_source["week_start"] = (
    weekly_source["week_start"]
    - pd.to_timedelta(weekly_source["week_start"].dt.weekday, unit="D")
)
print(
    weekly_source.groupby(["month", "week_start"])
    .size()
    .rename("rows")
    .to_string()
)

print("\n=== CATEGORY DISTRIBUTIONS ===")
candidate_columns = [
    c for c in df.columns
    if any(term in c.upper() for term in [
        "LOCALITY", "CITY", "PROPERTY_TYPE", "PROP_TYPE",
        "PREFERENCE", "BEDROOM", "BHK", "PROPERTY_CATEGORY"
    ])
]
print("Candidate columns:", candidate_columns)

for col in candidate_columns:
    print(f"\n{col}:")
    values = focus[focus["month"].isin(["2023-06", "2023-07", "2023-08"])][col]
    print(values.fillna("<MISSING>").astype(str).value_counts().head(12).to_string())

print("\n=== PROPERTY ID REPETITION ===")
for month in ["2023-06", "2023-07", "2023-08"]:
    part = focus[focus["month"] == month]
    ids = part["PROP_ID"].dropna().astype(str)
    print(
        f"{month}: rows={len(part)}, non-null IDs={len(ids)}, "
        f"unique IDs={ids.nunique()}, repeated-ID rows={int(ids.duplicated(keep=False).sum())}"
    )
    repeated = ids[ids.duplicated(keep=False)].value_counts().head(10)
    if not repeated.empty:
        print("Most repeated IDs:")
        print(repeated.to_string())

print("\nAudit complete. The raw CSV was only read, not modified.")
