# GOLDEN VECTORS AND REGRESSION ORACLES — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft.
**Purpose:** Frozen expected outputs that detect unintended changes to the statistics and the agent pipeline on the real snapshot.
**Status:** Draft. The vectors exist in `tests/golden/deterministic_baseline.json`; their **values are regenerated in Phase 3**, because the IST month rule, the Price-on-Request exclusion and the `MAX_PRICE` validity rule all change the population.

`CONTRACT.md` owns the output contract; `Data.md` owns the population; `Analysis.md` owns the statistics. This file records expected outputs and the rules for changing them. It does not redefine those rules.

## 1. Golden-test policy

Golden outputs are regression oracles, not lookup tables. The application recomputes everything from the snapshot at run time and must never return a stored value because the hash matches.

A golden test answers: *given this snapshot, contract version, population rules, window and deterministic configuration, are the outputs exactly what they were?* It does not say whether the numbers are correct; correctness is checked by unit tests and MRs.

### 1.1 Frozen input identity

| Property | Value |
|---|---|
| Raw file | `data/raw/hyderabad.csv`, SHA-256 `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` |
| Canonical frame | `data/snapshot/listings_canonical.csv`, SHA-256 in `data/snapshot/CHECKSUMS.txt` |
| Agent mode | `DETERMINISTIC` |
| Config | `GraphConfig()` defaults (`CONTRACT.md` §3) |
| Seeds | per pipeline vector, fixed in `tests/test_golden.py` (§2.2) |

If the raw hash differs, the golden tests fail with `snapshot_integrity_error`; never edit the raw file to match.

## 2. Vectors

### 2.1 Trend vectors (`trend::<label>`, `test_trend_computation_unchanged`)

`compute_trend` on the full canonical frame, no agents:

| Label | Criteria |
|---|---|
| `all` | `window_end = 2023-08` |
| `bhk3` | `window_end = 2023-08`, `bhk = (3,)` |
| `banded` | `window_end = 2023-07`, a price band |
| `lakh` | `window_end = 2023-08`, `currency_unit = INR_LAKH` |

Each stores the 12-month count, ₹/sqft, price and % change series, the sufficient months, rankings, total, yoy move and span. **[P3]** Each also stores `median_min_price_inr`, `median_max_price_inr` and `is_partial_month` per month.

### 2.2 Pipeline vectors (`pipeline::<label>`, `test_agent_pipeline_unchanged`)

The full agent graph, deterministic mode:

| Label | Criteria | Seed |
|---|---|---|
| `narrow` | `window_end = 2023-08`, `bhk = (3,)`, `localities = ("Gachibowli",)`; forces both loops | 7 |
| `base00` | harness base input 0 | 11 |
| `base05` | harness base input 5 | 23 |

Each stores counts, ₹/sqft series, rankings, total, yoy move and span, coverage score, relaxations, widening rounds (`widen_rounds`), critique rounds and rejected-listing count. **[P4]** The last two are stored under the stale names `strict_rounds` and `n_rejected_strict` (from the removed "STRICT mode"); rename them to `critique_rounds` and `n_rejected_outliers`. **[P4]** `base00`/`base05` change when radius base inputs are added or geography widening changes; regenerate them in the same commit.

### 2.3 Corrections log

`_corrections` in the JSON records every intentional change to a stored value: the key, old and new values, and the reason. An existing entry (`pipeline::base00.widen_rounds` 3 → 2) documents a counting fix that left every statistic byte-identical.

## 3. Comparison rules

| Field kind | Rule |
|---|---|
| Counts, rankings, month lists, loop counts, relaxation lists | exact |
| Floats | relative 1e-9 |
| `null` | must stay `null` |

## 4. Changing a vector

1. Identify the cause: snapshot, population rule, statistic, agent logic, or config.
2. A change is allowed only for an intentional, reviewed contract change. Record it in `_corrections` with the reason, and bump the parent version if a rule changed.
3. Never update a value only to make a failing test pass. A golden failure after a refactor is a regression until proven otherwise.
4. **[P3]** The Phase 3 regeneration is one such change: record the old and new totals and which rule caused each difference (IST months, Price on Request, `MAX_PRICE` validity).

## 5. Acceptance

1. Every vector in §2 exists and passes in deterministic mode.
2. Every stored change since freezing has a `_corrections` entry.
3. The vectors were produced from the snapshot whose hash is in §1.1.
