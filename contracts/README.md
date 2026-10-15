# Hyderabad Contract Suite (v2.0.0-draft)

## Authority and reading order

1. `CONTRACT.md` — authoritative shared rules, constants, output contract, graph and loop policies.
2. The active agent contract: `Criteria.md`, `Retrieval.md`, `Coverage.md`, `Analysis.md`, `Critique.md` or `Aggregator.md`.
3. Only the support contract needed for the task: `Data.md` (source semantics and population), `LLM.md` (model behaviour), `Testing.md` (MR catalogue and statistics), `Golden.md` (regression oracles).

If a subordinate file conflicts with `CONTRACT.md`, the global contract wins.

## Files

| File | Covers | Code |
|---|---|---|
| `CONTRACT.md` | Global rules, constants, `TrendReport`, graph, loops, acceptance | `src/contract.py`, `src/agents/graph.py` |
| `Data.md` | Snapshot, defects D1–D7, filter cascade, identity | `src/loading.py` |
| `Criteria.md` | Request validation, `query_mode` | `src/agents/nodes.py::criteria_agent`, `src/validation.py` |
| `Retrieval.md` | Sharded scan, exact-locality vs radius | `make_retrieval_agent`, `retrieval_dispatch`, `retrieval_merge` |
| `Coverage.md` | Coverage score, widening, loop C1 | `coverage_agent` |
| `Analysis.md` | Statistics, targeted outlier rejection | `analysis_agent`, `src/trend.py` |
| `Critique.md` | Month flagging, loop C2 | `critique_agent` |
| `Aggregator.md` | Final report and narrative | `aggregator_agent` |
| `LLM.md` | Model use, seeds, cache, fallbacks | `src/llm.py` |
| `Testing.md` | MR catalogue, harness, statistics | `src/mr/`, `scripts/run_harness.py` |
| `Golden.md` | Regression vectors | `tests/golden/`, `tests/test_golden.py` |

The v1 suite (fixed window, Planner/Scanner/Validator/Anomaly/Diagnostic/Reporter agents) is preserved unchanged in `legacy/contracts/`. `CONTRACT.md` §11 lists every change from v1 and why.

## Implementation status tags

Phases 3 and 4 are complete and their **[P3]**/**[P4]** tags have been removed: every clause describes current behaviour, backed by code and a test.

## Context-budget policy

The 8,000-token limit applies to each contract file individually. Keep each under about 7,500 tokens. When preparing a model prompt, load `CONTRACT.md` and only the subcontracts the task needs; do not include raw CSV rows, long logs or full code listings.

## Verified source facts

- Raw file `data/raw/hyderabad.csv`: 9,487 rows × 55 columns, SHA-256 `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`.
- `POSTING_DATE` is Unix milliseconds; the latest is `2023-08-26 10:29:05+05:30`, so August 2023 is partial.
- `MIN_AREA_SQFT` holds square metres (ratio to the `AREA` string is 10.7639 at p5 and p95).
- `CITY` contains Hyderabad and Secunderabad; both are in scope.
- There is no PIN-code column; locality is the geographic filter.

## Open items

- **The LLM sweeps predate contract v2.** `results/llm_before_promptfix/` and `results/llm/` were produced on Kaggle with the earlier code and population (4,578 rows, UTC months, whole-metro geography widening, per-run intervals). Re-running them needs Ollama with `qwen2.5:3b-instruct-q4_K_M` (`notebooks/kaggle_llm_sweep.ipynb`, or `python scripts/run_harness.py --tag v2_llm --llm`). Until then, report them as pre-v2 results and do not mix them with the v2 deterministic rates.
- Whether a strict replay mode (cache miss = error, no network) is required for the LLM sweep (`LLM.md` §6).

Resolved in Phase 4: M3 is kept, and is meaningful now that geography widening keeps a locality constraint (`Coverage.md` §3); the radius base inputs are defined in `Testing.md` §3.
