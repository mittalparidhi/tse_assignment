import json
import hashlib
from pathlib import Path
import pandas as pd

root = Path.cwd()
raw = root / "data" / "raw" / "hyderabad.csv"
report_path = root / "audit" / "filtered_runtime_state.json"

expected_sha = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)
actual_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
print("=== CHECKSUM ===")
print("Raw SHA-256:", actual_sha)
if actual_sha != expected_sha:
    raise SystemExit("STOP: frozen snapshot checksum mismatch")

report = json.loads(report_path.read_text(encoding="utf-8"))
print("Report snapshot_sha256:", repr(report.get("snapshot_sha256")))
runtime_state = report.get("runtime_state") or {}
if isinstance(runtime_state, dict):
    print("Nested runtime snapshot_sha256:", repr(runtime_state.get("snapshot_sha256")))
print("Report status:", report.get("status"))
print("Coverage score:", report.get("coverage_score"))

ids = [
    "Q69255364", "J70257340", "V70657016", "Z60331450",
    "T65066010", "L69228804", "E69995518", "M70698488",
    "X70270432", "S70312078", "S70310604", "L70308592",
    "Q70297544", "C70802468", "F70780388", "S70772186",
    "I70910350", "P70832368", "E70803372", "I70371884",
    "F70100324", "U70323056", "O70865844", "D70085386",
]

df = pd.read_csv(raw, low_memory=False)
selected = df[df["PROP_ID"].astype(str).isin(ids)].copy()
print("\n=== SELECTED ROW DATE RECONCILIATION ===")
print("Expected IDs:", len(ids))
print("Matched raw rows:", len(selected))

posting_ms = pd.to_numeric(selected["POSTING_DATE"], errors="coerce")
posting_utc = pd.to_datetime(
    posting_ms, unit="ms", utc=True, errors="coerce"
)
selected["posting_month"] = (
    posting_utc.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m")
)
selected["registration_date"] = pd.to_datetime(
    selected["REGISTER_DATE__U"], errors="coerce"
)
selected["registration_month"] = (
    selected["registration_date"].dt.strftime("%Y-%m")
)
selected["posting_in_reporting_window"] = selected["posting_month"].between(
    "2022-09", "2023-08"
)

print(
    selected[
        ["PROP_ID", "REGISTER_DATE__U", "registration_month",
         "POSTING_DATE", "posting_month", "posting_in_reporting_window"]
    ].sort_values(["posting_month", "PROP_ID"], na_position="first")
    .to_string(index=False)
)

print("\n=== RECONCILIATION TOTALS ===")
print("Rows with invalid posting date:", int(posting_utc.isna().sum()))
print(
    "Rows outside reporting window or with invalid posting date:",
    int((~selected["posting_in_reporting_window"].fillna(False)).sum())
)
print("Rows in reporting window:", int(selected["posting_in_reporting_window"].sum()))
print("Monthly observed count sum:", sum(
    int(row.get("observed_listing_count", 0))
    for row in report.get("monthly_records", [])
))
