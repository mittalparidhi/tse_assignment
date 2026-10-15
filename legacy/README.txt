Issue 5 revised patch v3: Exclude Price on Request rows from price-bound metrics

This patch uses whitespace-tolerant matching for the project's existing aggregation code.
It adds PRICE to the required source columns, excludes textual "Price on Request" rows
from valid price-range counts and MIN_PRICE/MAX_PRICE medians in both main and filtered
aggregation, updates affected monthly golden counts/medians, and adds regression tests.
It does not modify either CSV dataset.

PowerShell steps from the project root:
1. Extract this ZIP into C:\Users\parid\Desktop\assignment_tse (merge folders).
2. Run: python .\scripts\apply_issue5_price_on_request_patch.py
3. Only if it reports success, run: python .\scripts\build_runtime_state.py
4. Then run: python -m pytest -q

The installer validates all replacement points in memory before it writes any target files.
It creates .issue5.bak backups of the three modified existing files. If the installer fails,
stop and share the exact error; it should not have changed the target source files.
