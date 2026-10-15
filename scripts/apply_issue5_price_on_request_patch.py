from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def add_price_to_required_block(text: str, label: str) -> str:
    """Add PRICE to the sole required-column set without relying on spacing."""
    pattern = re.compile(
        r"(?ms)^(?P<prefix>[ \t]*required[ \t]*=[ \t]*\{)"
        r"(?P<body>.*?)^(?P<suffix>[ \t]*\})"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one required-column set in {label}; found {len(matches)}. "
            "No files have been written."
        )
    match = matches[0]
    body = match.group("body")
    if re.search(r'"PRICE"', body):
        return text
    new_body, count = re.subn(
        r'("PRICE_SQFT"[ \t]*,)',
        r'\1 "PRICE",',
        body,
        count=1,
    )
    if count != 1:
        raise RuntimeError(
            f"Could not find PRICE_SQFT in the required-column set in {label}. "
            "No files have been written."
        )
    replacement = match.group("prefix") + new_body + match.group("suffix")
    return text[:match.start()] + replacement + text[match.end():]


def patch_runtime_eligibility(text: str) -> str:
    if '_price_on_request' in text:
        raise RuntimeError("Runtime price-on-request rule already exists; refusing to apply twice.")
    pattern = re.compile(
        r'(?m)^(?P<i>[ \t]*)in_window\["_valid_price_range"\][ \t]*=[ \t]*\(\n'
        r'(?P<expr>[ \t]*)in_window\["_is_sale"\][ \t]*&[ \t]*valid_min[ \t]*&[ \t]*valid_max[ \t]*&[ \t]*\(min_price[ \t]*<=[ \t]*max_price\)\n'
        r'(?P<close>[ \t]*)\)[ \t]*$'
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one runtime price-range eligibility block; found {len(matches)}. "
            "No files have been written."
        )
    m = matches[0]
    i = m.group("i")
    replacement = (
        f'{i}price_text = in_window["PRICE"].astype("string").fillna("").str.strip()\n'
        f'{i}in_window["_price_on_request"] = price_text.str.contains(\n'
        f'{i}    r"\\bprice\\s+on\\s+request\\b", case=False, regex=True, na=False\n'
        f'{i})\n'
        f'{i}in_window["_valid_price_range"] = (\n'
        f'{i}    in_window["_is_sale"]\n'
        f'{i}    & valid_min\n'
        f'{i}    & valid_max\n'
        f'{i}    & (min_price <= max_price)\n'
        f'{i}    & ~in_window["_price_on_request"]\n'
        f'{i})'
    )
    return text[:m.start()] + replacement + text[m.end():]


def patch_filtered_eligibility(text: str) -> str:
    if '_price_on_request' in text:
        raise RuntimeError("Filtered price-on-request rule already exists; refusing to apply twice.")
    pattern = re.compile(
        r'(?m)^(?P<i>[ \t]*)report_rows\["_min_price_numeric"\][ \t]*=[ \t]*lo\n'
        r'(?P=i)report_rows\["_max_price_numeric"\][ \t]*=[ \t]*hi\n'
        r'(?P=i)report_rows\["_valid_price_range"\][ \t]*=[ \t]*report_rows\["_is_sale"\][ \t]*&[ \t]*valid_lo[ \t]*&[ \t]*valid_hi[ \t]*&[ \t]*lo\.le\(hi\)[ \t]*$'
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one filtered price-range eligibility block; found {len(matches)}. "
            "No files have been written."
        )
    m = matches[0]
    i = m.group("i")
    replacement = (
        f'{i}report_rows["_min_price_numeric"] = lo\n'
        f'{i}report_rows["_max_price_numeric"] = hi\n'
        f'{i}price_text = report_rows["PRICE"].astype("string").fillna("").str.strip()\n'
        f'{i}report_rows["_price_on_request"] = price_text.str.contains(\n'
        f'{i}    r"\\bprice\\s+on\\s+request\\b", case=False, regex=True, na=False\n'
        f'{i})\n'
        f'{i}report_rows["_valid_price_range"] = (\n'
        f'{i}    report_rows["_is_sale"]\n'
        f'{i}    & valid_lo\n'
        f'{i}    & valid_hi\n'
        f'{i}    & lo.le(hi)\n'
        f'{i}    & ~report_rows["_price_on_request"]\n'
        f'{i})'
    )
    return text[:m.start()] + replacement + text[m.end():]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match for {label}; found {count}. No files have been written.")
    return text.replace(old, new, 1)


def main() -> int:
    targets = {
        "runtime": ROOT / "scripts" / "build_runtime_state.py",
        "filtered": ROOT / "app" / "filtered_execution.py",
        "golden": ROOT / "tests" / "test_hyderabad_golden.py",
    }
    for name, path in targets.items():
        if not path.is_file():
            raise FileNotFoundError(f"Required {name} file not found: {path}")

    # Prepare and validate every change in memory before touching any files.
    runtime = targets["runtime"].read_text(encoding="utf-8")
    filtered = targets["filtered"].read_text(encoding="utf-8")
    golden = targets["golden"].read_text(encoding="utf-8")

    runtime = add_price_to_required_block(runtime, "scripts/build_runtime_state.py")
    runtime = patch_runtime_eligibility(runtime)

    filtered = add_price_to_required_block(filtered, "app/filtered_execution.py")
    filtered = patch_filtered_eligibility(filtered)

    expected_updates = {
        '("2022-11", 41, 35, 35, 4999500.0, 4999500.0, "observed"),':
        '("2022-11", 41, 35, 34, 5249750.0, 5249750.0, "observed"),',
        '("2023-04", 288, 270, 270, 10235001.5, 10564500.0, "observed"),':
        '("2023-04", 288, 270, 269, 10200003.0, 10509000.0, "observed"),',
        '("2023-05", 482, 437, 433, 10600000.0, 10944000.0, "observed"),':
        '("2023-05", 482, 437, 430, 10488800.0, 10806000.0, "observed"),',
        '("2023-07", 3447, 2808, 2776, 9255500.0, 9400000.0, "observed"),':
        '("2023-07", 3447, 2808, 2775, 9261000.0, 9400000.0, "observed"),',
        '("2023-08", 3531, 2911, 2885, 9452000.0, 9800000.0, "partial_month"),':
        '("2023-08", 3531, 2911, 2884, 9476000.0, 9800000.0, "partial_month"),',
    }
    for old, new in expected_updates.items():
        golden = replace_once(golden, old, new, f"golden vector {old[:13]}")
    golden = replace_once(
        golden,
        '            sum(r["valid_price_range_count"] for r in records), 7555\n',
        '            sum(r["valid_price_range_count"] for r in records), 7548\n',
        "golden aggregate valid-price-range total",
    )

    regression_path = ROOT / "tests" / "test_price_on_request_exclusion.py"
    regression_content = '''"""Regression tests for textual Price on Request values with numeric bounds."""

from scripts import build_runtime_state as runtime


def test_price_on_request_rows_are_excluded_from_runtime_price_ranges():
    request = runtime.AnalysisRequest()
    plan = runtime._plan(request)
    scan = runtime._scan_snapshot(plan, None)
    in_window = scan["in_window"]

    candidates = in_window.loc[
        in_window["_is_sale"] & in_window["_price_on_request"]
    ]
    assert len(candidates) == 7
    assert not candidates["_valid_price_range"].any()

    aggregate = runtime._aggregate_months(plan, scan)
    assert aggregate["in_window_valid_ranges"] == 7548
    assert aggregate["data_quality"]["in_window_sale_rows_without_valid_coherent_range"] == 85

    by_month = {r["month"]: r for r in aggregate["monthly_records"]}
    expected_counts = {
        "2022-11": 34,
        "2023-04": 269,
        "2023-05": 430,
        "2023-07": 2775,
        "2023-08": 2884,
    }
    for month, expected in expected_counts.items():
        assert by_month[month]["valid_price_range_count"] == expected


def test_price_on_request_rows_remain_in_listing_and_sale_counts():
    request = runtime.AnalysisRequest()
    plan = runtime._plan(request)
    scan = runtime._scan_snapshot(plan, None)
    aggregate = runtime._aggregate_months(plan, scan)

    assert aggregate["in_window_count"] == 9162
    assert aggregate["in_window_sales"] == 7633
'''
    if regression_path.exists():
        existing = regression_path.read_text(encoding="utf-8")
        if existing.strip() != regression_content.strip():
            raise RuntimeError(
                f"{regression_path} already exists with different contents; "
                "refusing to overwrite it. No files have been written."
            )

    # Safety backups and writes occur only after all replacements validated.
    for name, path in targets.items():
        backup = path.with_name(path.name + ".issue5.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
    targets["runtime"].write_text(runtime, encoding="utf-8", newline="\n")
    targets["filtered"].write_text(filtered, encoding="utf-8", newline="\n")
    targets["golden"].write_text(golden, encoding="utf-8", newline="\n")
    if not regression_path.exists():
        regression_path.write_text(regression_content, encoding="utf-8", newline="\n")

    print("Issue 5 patch applied successfully.")
    print("Updated runtime aggregation, filtered aggregation, golden values, and regression tests.")
    print("Backups use the suffix .issue5.bak.")
    print("Next: run python .\\scripts\\build_runtime_state.py and python -m pytest -q")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Issue 5 patch NOT applied: {exc}", file=sys.stderr)
        raise SystemExit(1)
