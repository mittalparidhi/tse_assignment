# Hyderabad Housing-Trends Contract Suite — Consistency Audit

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

**Audit target:** Hyderabad contract suite draft v9 preparation  
**Reference:** the user-provided `c.zip` containing 12 contract files under `c/`  
**Data:** the frozen `hyderabad.csv` snapshot  
**Status:** cross-contract consistency pass completed; contracts remain drafts pending the open items below.

## 1. Scope and method

The reference package was inspected file by file. Its 11 named contracts (`Agents.md`, `Aggregator.md`, `Anomaly.md`, `Data.md`, `Diagnostic.md`, `Golden.md`, `LLM.md`, `Planner.md`, `Reporter.md`, `Testing.md`, and `Validator.md`) were mapped to the corresponding Hyderabad subcontracts. Reference `_common.md` rules were consolidated into the authoritative Hyderabad `CONTRACT.md` and shared-agent rules in `Agents.md`; the Hyderabad suite therefore contains a global parent contract plus 11 named subcontracts. The suite README is an additional navigation document, not one of the 12 contract documents.

The pass examined shared schemas, status/coverage policy, metric eligibility, fixed-window/timezone semantics, error codes, trace events, loop accounting, golden outputs, anomaly conditions, LLM boundaries and testing assumptions. An independent Python check recomputed the Hyderabad monthly golden values and anomaly counts from the hash-pinned CSV. This is a contract/data-baseline check, not an end-to-end application test: no complete application implementation was included in this contract suite.

## 2. Reference-file mapping

| Reference contract | Hyderabad equivalent | Adaptation notes |
|---|---|---|
| `c/Agents.md` | `Agents.md` | Retains agent boundaries, allowed/forbidden actions, failure behavior, trace rules, and tests for Planner, Scanner, Aggregator, Validator, Anomaly, Diagnostic, and Reporter roles. |
| `c/Aggregator.md` | `Aggregator.md` | Replaces the reference dataset's fields with Hyderabad posting dates, `PREFERENCE`, and numeric price bounds. |
| `c/Anomaly.md` | `Anomaly.md` | Uses four deterministic snapshot-screening rule families and source-evidence-linked price-bound series. |
| `c/Data.md` | `Data.md` | Defines the frozen CSV, timestamp conversion, audit populations, source-row identity, price eligibility, and unresolved field semantics. |
| `c/Diagnostic.md` | `Diagnostic.md` | One evidence-bounded explanation per anomaly flag; template fallback remains available. |
| `c/Golden.md` | `Golden.md` | Freezes twelve monthly records, data-quality reconciliations, pooled summaries, anomaly flags, and report-shape expectations. |
| `c/LLM.md` | `LLM.md` | Defines `off`/`replay`/`live`, replay keys, shared client, retry limits, and numeric independence. |
| `c/Planner.md` | `Planner.md` | Uses a fixed 12-month Hyderabad window and disables user filters/production repairs unless later approved. |
| `c/Reporter.md` | `Reporter.md` | Assembles the public schema without changing upstream metric or flag values. |
| `c/Testing.md` | `Testing.md` | Defines 9 primary data MRs, an optional partition-equivalence MR, a separate bounded-loop control-flow test, confidence intervals, seeds, and reproduction outputs. |
| `c/Validator.md` | `Validator.md` | Validates the complete 12-month grid and price-bound coverage separately from structural integrity. |
| `c/_common.md` | `CONTRACT.md` shared rules (especially §§3–4, 9, 11–13) plus `Agents.md` §1 | Common invariants, the canonical trace schema, loop accounting, and coverage-loop rules are consolidated rather than copied into every subcontract. |

The Hyderabad parent adds a globally authoritative report schema and source-specific rules, which the reference suite delegates across `CONTRACT.md` and `_common.md`.

## 3. Cross-contract conflicts resolved

1. **One authoritative metric/status policy.** `CONTRACT.md` now owns monthly record fields, `coverage_status` precedence, `metric_status` precedence, coverage score and final status mapping. `Aggregator.md`, `Validator.md`, `Golden.md`, and `Reporter.md` defer to the parent rather than offering competing interpretations.
2. **Coverage is not representativeness.** `coverage_score = covered_months / 12.0`, where a month is price-covered if it has at least one valid coherent sale-price range and finite lower/upper medians. The unverified `PRICE_SQFT` field does not reduce price-bound coverage. A structurally valid report with a price-bound gap is `partial`, not a synthetic repair or a false success.
3. **One public monthly schema.** Every non-error response has twelve ordered monthly records, including `valid_price_sqft_count` as an explicitly unverified quality count and `median_price_per_sqft_inr = null` until semantics are verified. The golden monthly table now includes all required record fields.
4. **One exact trace schema.** Every trace event has exactly `{i, agent, kind, loop, msg, data}`. Trace indices are zero-based and consecutive. Only actual feedback firings have `kind="loop"`; skipped, disabled, rejected, and exhausted-loop decisions do not increment loop counters. LLM retries are separate non-loop events.
5. **One public error envelope and registry.** Errors use `error={"code", "message"}`; there is no separate top-level `error_code`. The inconsistent draft name `E_DIAGNOSTIC_INPUT` was normalized to `diagnostic_input_error` and references updated. Validator reason codes are explicitly marked as internal trace reasons, not public error codes.
6. **Deterministic report identity.** `Reporter.md` now follows the parent `run_id` fingerprint rule: append the final Reporter event, then hash canonical report content excluding `run_id`. It does not copy an arbitrary upstream ID. An absent seed is exactly `null`.
7. **Consistent provenance/reconciliation.** The source hash, Unix-millisecond timestamp handling, `Asia/Kolkata` month derivation, fixed window, quality counts, and duplicated-ID handling are reflected across `CONTRACT.md`, `Data.md`, `Golden.md`, `Aggregator.md`, and README.
8. **Sale eligibility is explicit.** `PREFERENCE` is trimmed as text and then compared exactly with uppercase `S`; the undocumented `TRANSACT_TYPE` codes are not used as a replacement.
9. **Replay policy is consistent.** Replay never silently makes a live request. A missing required Planner interpretation can yield `replay_miss` if no unambiguous deterministic grammar fallback exists; a missing optional diagnostic answer uses the deterministic template.
10. **Metamorphic relations have clear subdomains.** MR9 removes every valid-date in-window row in the selected month for its empty-month fixture; it does not incorrectly imply that a month is empty merely because it has no price-eligible rows. CF1 is kept separate from data MRs.
11. **Disabled features are not overstated.** No production filter-widening repair is permitted until a versioned repair table exists. Parallel execution is not claimed unless implemented, configured, and tested for partition/merge equivalence.
12. **Pooled summary uses row-level values.** The start/end price-bound summaries use eligible row-level price ranges, not an average or median of monthly medians; the relevant contracts and golden vector agree.

## 4. Verification against `hyderabad.csv`

The validation script recomputed the monthly golden vector and anomaly rules from the supplied snapshot. Results:

| Check | Recomputed result | Outcome |
|---|---:|---|
| Raw dimensions | 9,487 rows × 55 columns | Match |
| SHA-256 | `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` | Match |
| Valid localized posting timestamps | 9,245 | Match |
| Missing/invalid posting timestamps | 242 | Match |
| Valid-date rows outside `2022-09`–`2023-08` | 83 | Match |
| In-window observed rows | 9,162 | Match |
| In-window sale rows (`PREFERENCE == "S"`) | 7,633 | Match |
| In-window valid coherent sale price ranges | 7,555 | Match |
| In-window sale rows without a valid coherent range | 78 | Match |
| Exact full-row duplicate rows detected/removed | 0 / 0 | Match |
| Repeated `PROP_ID` group/rows | 1 / 2 | Match; preserve both rows |
| Monthly golden rows compared | 12 | No mismatches |
| Monthly sums (observed / sale / coherent ranges) | 9,162 / 7,633 / 7,555 | Reconciled |
| Anomaly flags under current draft thresholds | 17 | 14 AN-01, 0 AN-02, 2 AN-03, 1 AN-04 |
| July–August observed-row share | 0.7616240995 (about 76.16%) | Match |

The monthly price-per-square-foot quality counts are recomputed only as finite, positive source-value counts over sale rows. They are **not** treated as verified INR/sq-ft observations. `median_price_per_sqft_inr` remains null in the golden table. The late-window concentration and count/price-bound changes are snapshot diagnostics; they do not establish causes or market-wide changes.

The verification command used was `python /mnt/data/validate_suite_baselines.py`. It reported `baseline_issues=[]`. This validates the static golden baseline and anomaly-count expectations; it does **not** demonstrate that the eventual app, loop traces, full metamorphic harness, or report renderer has been implemented or passed end-to-end tests.

## 5. Real remaining decisions before implementation freeze

These are intentionally left open because the source does not support guessing them:

- **Typed request implementation:** register exact typed `AnalysisRequest` and internal `RunPlan` schemas plus a deterministic natural-language intent grammar/test corpus in shared code/config. The parent public report schema and public error registry are already defined.
- **Source semantics:** independently verify `PRICE_SQFT` meaning/units, area-field units/scales, and `TRANSACT_TYPE` meanings. Until then, do not call price-per-square-foot a verified INR metric or use transaction-type codes as sale labels.
- **Price-source confirmation:** the numeric `MIN_PRICE`/`MAX_PRICE` columns are treated as candidate INR values under the current documented source mapping; final source-semantic confirmation should be recorded with evidence before release.
- **Coverage repair:** production repair remains disabled. Do not add soft filters or alter eligibility rules just to attain full coverage. Keep the bounded loop covered by controlled test fixtures until a versioned repair table is approved.
- **Parallel topology:** do not advertise/return `parallel` until a deterministic partitioning and merging strategy is implemented and the MR10 partition-equivalence tests pass.
- **Anomaly threshold approval:** 5-row bucket floor, 12% price-bound shift, 0.50 drop ratio, 2.00 spike ratio, and 70% late-window share are reproducible draft heuristics. They need project approval/calibration; they are not statistical significance thresholds.
- **Assignment artifacts and empirical run:** implement the app and MR harness, run at least 30 distinct eligible bases per required data MR, use at least three fixed seeds for any model-dependent tests, produce confidence intervals and top-three evidence-backed diagnoses, and complete `NOTEBOOK.md`, `AI_USE.md`, one-command reproduction, runtime traces, and the 10–12 page report.

## 6. Per-contract budget check

The longest current file is `CONTRACT.md` at about 4,757 whitespace-delimited words; the other contracts are shorter (most are about 1,800–3,900 words). No target-model tokenizer was available for an exact token count during this pass, so the counts below are word counts and the sub-8,000-token claim remains a conservative estimate, not a measured tokenizer result. None of the documents was padded to approach the budget.

| File | Approx. word count |
|---|---:|
| `CONTRACT.md` | 4,757 |
| `Agents.md` | 3,420 |
| `Aggregator.md` | 3,886 |
| `Anomaly.md` | 3,543 |
| `Data.md` | 1,805 |
| `Diagnostic.md` | 3,736 |
| `Golden.md` | 3,155 |
| `LLM.md` | 2,172 |
| `Planner.md` | 2,200 |
| `Reporter.md` | 3,499 |
| `Testing.md` | 2,542 |
| `Validator.md` | 2,569 |

**Audit result:** the main cross-contract conflicts identified in this pass have been standardized, and the static golden baseline check passed with no mismatches. The suite is coherent enough to guide implementation, but should remain marked **draft** until the source-semantic checks and implementation-level tests above are completed.
