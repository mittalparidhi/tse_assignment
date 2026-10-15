# TESTING SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft. This file defines the MR catalogue, base inputs, seeds, the harness, statistics and diagnosis. Shared values come from the parent.

**Status:** Draft; harness implemented. Statistical unit, M3 and radius inputs change in Phase 4.

## 1. Test layers

| Layer | Where | Oracle |
|---|---|---|
| Unit and contract tests | `tests/test_*.py` | hand-checked fixtures and direct calculation |
| Golden regression | `tests/test_golden.py` | frozen vectors (`Golden.md`) |
| Metamorphic relations | `src/mr/`, `scripts/run_harness.py` | the relation between source and follow-up outputs; no oracle for individual answers |
| Synthetic oracle check | `scripts/make_synthetic.py`, `--synthetic` | known ground truth; labelled and reported separately |

Constructed fixtures are never merged into the real snapshot or reported as observed listings.

## 2. Comparators

- Counts, month order, rankings and `null` placement: exact.
- Floats: `math.isclose` with `REL_TOL = 1e-9` relative and absolute, on unrounded values.
- Every run records MR ID, base input, seed, applicability, violated, a failure detail string, loop counts for both runs, and whether both runs took the same control path.

## 3. Base inputs and seeds

- **36 distinct base inputs** (`src/mr/base_inputs.py`), above the required 30: a strided sample of window end (5 months) × BHK (5 options) × price band (4) × locality set (4), deterministic given the frame. Every input sets a band and ≥ 2 localities so M2 and M3 apply; window ends exclude the last month so D1 applies.
- **[P4]** Add base inputs that use `RADIUS` (centred on the top localities' median coordinates, radius 3–5 km) so the radius algorithm is exercised by the MRs.
- **[P3]** Every base input passes request validation (`Criteria.md` §3).
- **Seeds** `(11, 23, 47)` are used for both source and follow-up runs. Changing them changes the published numbers.
- Repeating a base input with another seed does not create a new base input.

## 4. MR catalogue

`R` is the source report, `R'` the follow-up. Every relation is a statement about `TrendReport` fields only. Implemented in `src/mr/relations.py`.

### Invariance

| ID | Transformation | Relation | Subdomain | Tolerance | Fault exposed |
|---|---|---|---|---|---|
| I1 | permute listing rows | all of `R'` equals `R` | all inputs | counts exact; floats 1e-9 | order-dependent aggregation; unstable tie-break; shards leaking row order |
| I2 | display units ₹→₹ lakh, sq ft→sq m | counts, rankings, % changes identical; `median_psf` scales by the exact unit factor | all inputs; band stays in rupees | 1e-9 | hard-coded units; the D1 sq m confusion; % after rounding |
| I3 | duplicate every listing | counts exactly double; per-month price stats unchanged on already-sufficient months | yoy fields excluded (doubling flips sufficiency for 25–49-listing months) | medians 1e-9; counts exact | silent de-duplication; double counting |
| I4 | bijective relabel of `listing_id` | all of `R'` equals `R` | all inputs | exact | agents keyed on ID hash; shard-by-ID changing the accepted set |
| I5 | display currency ₹ lakh → ₹ crore | as I2, factor 10⁻² | lakh projection of each input (`prepare`) | 1e-9 | hard-coded currency; % after rounding |

### Monotonic

| ID | Transformation | Relation | Subdomain | Tolerance | Fault exposed |
|---|---|---|---|---|---|
| M1 | add ₹500,000 to every price in the densest window month | that month's **[P3]** `median_min_price_inr` and `median_max_price_inr` rise by ₹500,000; other months unchanged; none decreases | band-free projection of each input (`prepare` removes the band from both runs) | \|Δ − X\| ≤ 1e-6·X; others 1e-9 | month bucketing leaks; filters applied after the transform |
| M1raw | as M1 with the band left in place | as M1 | **does not hold** — retained as the documented ill-conceived relation | as M1 | none: listings cross the band, changing the population |
| M2 | widen the price band 25% each side | each month's count ≥ before | inputs with a band | exact inequality | filter inversion; bound off-by-one; stale cached criteria |
| M3 | keep the first half of the locality list | each month's count ≤ before | inputs with ≥ 2 localities; **[P4]** meaningful only once geography widening keeps a locality constraint (`Coverage.md` §3) | exact inequality | leakage between shards; merging a previous criteria set |

### Directional

| ID | Transformation | Relation | Subdomain | Tolerance | Fault exposed |
|---|---|---|---|---|---|
| D1 | shift the window forward one month | the 11 overlapping months' counts and medians match exactly | both windows inside the observed data | counts exact; floats 1e-9 | window off-by-one; bucketing drift; state carried between runs |
| D2 | scale all prices by k = 1.5 (band scaled too) | `median_psf` and price medians scale by exactly k; % changes and rankings unchanged | k such that no listing crosses a bound | 1e-9 | unit mishandling; non-linear aggregation |

M1 and D2 assume no listing crosses a plausibility bound. The harness currently assumes this precondition; **[P4]** it checks it per run and reports how often it binds. Control-flow termination (both loops capped) is tested separately in `tests/test_agents.py` and is not counted as a data MR.

## 5. Control-path stability

Coverage depends on counts, so a transformation that changes counts can change which C1 levers fire, and the two runs then answer different questions. For every run the harness compares the lever sequence (`relax_levers`) and critique rounds of both runs (`same_control_path`). Every relation is reported over all applicable runs and over the stable subdomain; the number of diverged runs is always reported.

## 6. Violation rates and confidence intervals

- Violation rate = violated / applicable. Inapplicable runs are skipped with a reason and excluded from the denominator.
- **95% Wilson score interval**, chosen because rates sit near 0 and 1, where the normal approximation fails.
- **[P4] Statistical unit = base input.** A base input counts as violated if any of its seeds violates. Wilson intervals are computed over the 36 (or more) base inputs, not the 108 runs: in the deterministic sweep the seeds give identical outcomes, so per-run intervals overstate precision (0/108 gives an upper bound of 0.034; 0/36 gives 0.096). The per-run rate and the seed-disagreement count are still reported.
- Report per MR: seed list, base-input count, run count, violations, rate, CI, diverged runs.

## 7. Configurations and outputs

| Tag | Configuration |
|---|---|
| `phaseA_deterministic` | deterministic agents |
| `llm_before_promptfix` / `llm` | LLM mode before/after the prompt-hygiene fixes |
| `before_fix` / `after_fix` | deterministic sweeps before/after the first round of fixes diagnosed in `docs/DIAGNOSIS.md` (per-shard outlier threshold, M1 refinement) |
| `synthetic` | synthetic snapshot, oracle check |

Each `results/<tag>/` holds `base_inputs.csv`, `mr_runs.csv`, `mr_summary.csv`, `headline.txt`, `run_meta.json` (snapshot SHA, seeds, counts, model record) and `trace_example.txt`. **[P4]** All tables are regenerated after the Phase 3 and 4 changes.

## 8. Harness self-tests

| Test | Status |
|---|---|
| Three families represented; ≥ 8 relations; unique IDs; every relation documents subdomain, tolerance, fault | exist (`tests/test_harness.py`) |
| Wilson interval inside [0, 1], non-zero width at 0, contains the estimate, narrows with n, NaN on empty | exist |
| Per-base-input aggregation | **[P4]** |
| A deliberately faulty test double is detected by at least one MR | **[P4]** |

## 9. Diagnosis

For the three most-violated MRs, `docs/DIAGNOSIS.md` gives the failing MR, rate and CI, a reproducible example, the cause with evidence, and its class: agent/aggregation fault, data artefact, ill-conceived MR, or harness bug. Observed causes are distinguished from hypotheses; controlled experiments are in `results/diagnosis/` and `scripts/diagnose.py`.

## 10. Traceability

| This file | Parent |
|---|---|
| §3–6 | §10 items 7–9 |
| §4 | §5 |
| §5 | §7 C1 |
