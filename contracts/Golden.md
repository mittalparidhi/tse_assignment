# GOLDEN VECTORS AND REGRESSION ORACLES — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal. Full attribution: CREDITS.md.

**Parent:** `CONTRACT.md` v2.1.0-draft.
**Purpose:** Frozen expected outputs that detect unintended changes to the statistics and the agent pipeline on the real snapshot.
**Status:** Draft. The vectors in `tests/golden/deterministic_baseline.json` were regenerated in Phase 3 for contract v2 (IST months, Price-on-Request exclusion, `MAX_PRICE` validity, new fields).

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

Each stores the 12-month `listing_count`, `price_valid_count` and `coverage_status` series, the ₹/sqft, listing-price, min/max-price and % change series, `is_partial_month`, the sufficient months, rankings, total, yoy move and span.

### 2.2 Pipeline vectors (`pipeline::<label>`, `test_agent_pipeline_unchanged`)

The full agent graph, deterministic mode:

| Label | Criteria | Seed |
|---|---|---|
| `narrow` | `window_end = 2023-08`, `bhk = (3,)`, `localities = ("Gachibowli",)`; forces both loops | 7 |
| `base00` | harness base input 0 | 11 |
| `base05` | harness base input 5 | 23 |

Each stores counts, price-valid counts, ₹/sqft series, rankings, total, yoy move and span, coverage score, relaxations, widening rounds (`widen_rounds`), critique rounds (`critique_rounds`), `coverage_verdict`, `review_status` and rejected-listing count (`n_rejected_outliers`; renamed from the stale `strict_rounds`/`n_rejected_strict`). The pipeline vectors were regenerated when geography widening changed (`narrow` 4,141 → 632 listings).

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
4. Regenerate only with `scripts/regenerate_golden.py --reason "..."`, which writes the new vectors and records old and new totals with the reason in `_corrections`. The Phase 3 regeneration is recorded there (for example `trend::all` total 4,537 → 4,533).

## 5. Acceptance

1. Every vector in §2 exists and passes in deterministic mode.
2. Every stored change since freezing has a `_corrections` entry.
3. The vectors were produced from the snapshot whose hash is in §1.1.
