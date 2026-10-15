# legacy/ — first implementation (reference only)

This folder holds the original agent pipeline that preceded the merge of the
`metamorphic_testing` implementation. It is kept for reference and for porting
its rules into `src/`; it is **not** part of the running application and is not
collected by pytest (`pytest.ini` points at `tests/`).

| Path | What it is |
|---|---|
| `app/` | Criteria agent, retrieval agent, execution graph, anomaly detector, typed schemas |
| `tests/` | Tests for `app/` (plus `.bak` patch backups, ignored by git) |
| `scripts/` | Scripts that import `app/`, the issue 2–5 patch installers, and the v1 cleaning/audit scripts (`clean_hyderabad.py`, `build_processed_snapshot.py`, `finalize_snapshot_audits.py`, `audit_*.py`, `inspect_*.py`) |
| `data/processed/` | v1 cleaned dataset (all 9,487 rows, flagged rather than dropped) and its SHA-256 |
| `audit/` | v1 cleaning audit, snapshot manifest, anomaly investigation, runtime states and test-run logs |
| `contracts/`, `docs/` | v1 contract suite (fixed window; Planner/Scanner/Validator/Anomaly/Diagnostic/Reporter) and v1 design docs, superseded by `contracts/` v2 |
| `examples/`, `*.json` | Example requests and outputs for the criteria/retrieval agents |
| `ISSUE4_INSTALL.md`, `PATCH_INSTRUCTIONS.md`, `README.txt` | Patch instructions for `app/` |

Paths inside this code resolve relative to the old project root, so it does not
run from here unchanged.

The v1 audit evidence in `audit/` (for example the anomaly investigation and the month-concentration audit) remains citable in the report; cite it as v1 evidence.

Rules being carried over into `src/`:

- "Price on Request" rows excluded from price metrics (`app/filtered_execution.py`, `tests/test_price_on_request_exclusion.py`)
- request validation against source-observed values (`app/criteria_agent.py`)
- partial-month labelling of 2023-08 (`app/filtered_execution.py`, `tests/test_reporting_month_identity.py`)
