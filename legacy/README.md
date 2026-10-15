# legacy/ — first implementation (reference only)

This folder holds the original agent pipeline that preceded the merge of the
`metamorphic_testing` implementation. It is kept for reference and for porting
its rules into `src/`; it is **not** part of the running application and is not
collected by pytest (`pytest.ini` points at `tests/`).

| Path | What it is |
|---|---|
| `app/` | Criteria agent, retrieval agent, execution graph, anomaly detector, typed schemas |
| `tests/` | Tests for `app/` (plus `.bak` patch backups, ignored by git) |
| `scripts/` | Scripts that import `app/`, and the issue 2–5 patch installers |
| `examples/`, `*.json` | Example requests and outputs for the criteria/retrieval agents |
| `ISSUE4_INSTALL.md`, `PATCH_INSTRUCTIONS.md`, `README.txt` | Patch instructions for `app/` |

Paths inside this code resolve relative to the old project root, so it does not
run from here unchanged.

Rules being carried over into `src/`:

- "Price on Request" rows excluded from price metrics (`app/filtered_execution.py`, `tests/test_price_on_request_exclusion.py`)
- request validation against source-observed values (`app/criteria_agent.py`)
- partial-month labelling of 2023-08 (`app/filtered_execution.py`, `tests/test_reporting_month_identity.py`)
