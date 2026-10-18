# GLOBAL CONTRACT — Hyderabad Housing-Trends Application

**Contract ID:** TSE-HYD-MT  
**Version:** 1.0.0-draft  
**Authority:** This file is the single source of truth for shared constants, schemas, metric definitions, execution order, failure semantics, and invariants. `Data.md`, `Agents.md`, `Testing.md`, and `LLM.md` are subordinate contracts. They may clarify implementation but must not redefine global rules. If they conflict with this file, the global contract wins and the conflicting subordinate clause must be corrected.

## 1. Purpose and scope

Build a reproducible multi-agent application that reports monthly trends from a frozen, real Hyderabad residential-listing snapshot. The assignment evaluates software behavior through metamorphic testing, not the predictive accuracy of a housing-market model.

The application reports observed records in the supplied snapshot. It does **not** estimate the full Hyderabad housing market, transaction volume, sale completion, inventory, or current 2026 prices. Counts must be described as observed listing-entry records in the snapshot, not census counts or unique properties unless a verified deduplication rule establishes that meaning.

The analysis window is exactly 12 ordered calendar months: `2022-09` through `2023-08`, inclusive. August 2023 is a partial observed month: the latest observed posting date in the raw snapshot is August 26, 2023. Do not extrapolate it to a full month or compare it as if coverage were complete.

## 2. Dataset and provenance

- Raw input: `data/raw/hyderabad.csv`; preserve this frozen source unchanged.
- Derived cleaned data: `data/processed/hyderabad_clean.csv`.
- Audit outputs belong under `audit/`; implementation belongs under `scripts/`; contracts and explanatory documents belong under `docs/`.
- The known raw snapshot has 9,487 rows and 55 columns. `POSTING_DATE` has 9,245 parseable values and 242 missing/invalid values under the current audit. These counts are audit baselines, not constants to hard-code into calculations.
- The source is a scraped 99acres-derived Hyderabad listing sample. Preserve the source attribution and limitations in the report. Do not create synthetic listings or silently augment the snapshot with other datasets.
- Store the raw file's SHA-256 in the run metadata and verify it before execution. If the digest differs from the expected frozen value, fail with `snapshot_integrity_error` unless the operator explicitly updates the snapshot and records a new version.
- Record script/runtime versions and the cleaning-contract version so the run can be reproduced.

## 3. Shared constants and definitions

Define shared constants once in `app/contract.py` (or equivalent) and import them in code/tests; agents must not redefine them.

| Constant | Required value or rule |
|---|---|
| `CONTRACT_VERSION` | `1.0.0-draft` until reviewed and frozen |
| `WINDOW_START` | `2022-09` |
| `WINDOW_END` | `2023-08` |
| `EXPECTED_MONTHS` | Ordered list of all 12 months in the inclusive window |
| `LOCAL_TIMEZONE` | `Asia/Kolkata` |
| `PRICE_SENTINEL` | `2147483647` |
| `COVERAGE_REPAIR_CAP` | 3 retries after the initial attempt |
| `CRITIQUE_REVISION_CAP` | 2 revisions after the initial draft |
| `MR_MIN_BASE_INPUTS` | 30 distinct eligible base inputs per MR |
| `NONDETERMINISTIC_SEEDS` | At least 3 fixed seeds for stochastic/model-dependent tests |
| `CI_LEVEL` | 95% |
| `PRICE_SQFT_REVIEW_THRESHOLD` | 100000; provisional review flag only, not an automatic exclusion rule |

A month is a local calendar month derived from the localized `POSTING_DATE`. A listing-entry record is a raw row with a parseable posting timestamp. A sale listing is a dated row with `PREFERENCE == "S"` based on the available source semantics. A valid price range is a sale listing with finite, positive, non-sentinel lower and upper bounds and `MIN_PRICE <= MAX_PRICE`. The source-reported `PRICE_SQFT` remains unverified until its units and semantics are established.

## 4. Input, output, and public schema

### 4.1 Request

A request may specify the analysis window, optional locality/property filters if those fields are supported and verified, reporting options, execution mode, and seed. The public application must reject unsupported filters instead of silently ignoring them. For this assignment, the default window is fixed to the 12-month contract window; requests must not change it unless a separate contract revision explicitly authorizes variable windows.

### 4.2 Monthly record

Every successful analysis returns exactly 12 records, one per expected month, ordered chronologically. Each record contains:

- `month`: `YYYY-MM`.
- `observed_listing_count`: number of eligible rows with valid localized posting dates in the month after only the documented exact-row duplicate policy.
- `sale_listing_count`: number of those rows with `PREFERENCE == "S"`.
- `valid_price_range_count`: number of sale rows with valid coherent numeric bounds.
- `median_min_price_inr`: median of eligible `MIN_PRICE` values, in INR.
- `median_max_price_inr`: median of eligible `MAX_PRICE` values, in INR.
- `valid_price_sqft_count`: number of eligible source-reported `PRICE_SQFT` values under the verified metric rule; while units remain unverified, expose the count as a quality statistic and do not label the metric INR/sqft.
- `median_price_per_sqft_inr`: median only after units and semantics have been verified; otherwise `null` and status `unverified_metric`.
- `coverage_status`: one of `observed`, `no_listings`, `partial_month`.
- `metric_status`: one of `ok`, `no_sale_listings`, `no_valid_prices`, `unverified_metric`, `no_listings`.

The August 2023 record must be marked `partial_month`. `observed_listing_count = 0` means the snapshot has zero eligible dated rows for that month; it does not mean the real market had no listings. A metric that cannot be computed must be `null`, never fabricated as zero.

### 4.3 Report metadata

The report includes `contract_version`, `snapshot_sha256`, `run_id`, `window_start`, `window_end`, `timezone`, `seed`, `llm_mode`, `logic_version`, `coverage_score`, `topology`, `loop_counters`, `trace`, `data_quality`, and `status`. `data_quality` includes counts of raw rows, rows with invalid/missing dates, sale rows, valid/invalid price bounds, `PRICE_SQFT` values accepted for metric use, review flags, and any preserved duplicate-ID cases. No metadata field may imply complete market coverage.

### 4.4 Error response

Expected domain errors return a structured error with `status="error"`, a stable `error_code`, a short explanation, and trace metadata. Unexpected programming exceptions must propagate in development/tests; they must not be caught and disguised as successful reports.

## 5. Timestamp and month rules

`POSTING_DATE` is a Unix timestamp in milliseconds. Parse it using explicit millisecond units, reject missing/non-finite/unparseable values, convert the resulting instant to `Asia/Kolkata`, and only then derive `YYYY-MM`. Do not derive the month from a naive UTC timestamp. Regenerate canonical monthly counts after applying this rule; prior audit counts produced with a different timezone handling are not automatically the canonical result.

Rows without valid posting dates cannot be assigned to a month. Preserve them in the cleaned data with an explicit date-quality flag, but exclude them from all monthly counts and monthly price aggregates. Report their count in metadata. Do not infer a posting date from other columns.

## 6. Price and numeric eligibility

### 6.1 Price bounds

Treat numeric `MIN_PRICE` and `MAX_PRICE` as candidate INR values, subject to source validation. Do not convert numeric fields from lakh/crore again merely because the display string uses those units. A bound is individually valid only if numeric, finite, strictly positive, and not equal to `2147483647`. A valid range additionally requires both bounds valid and `MIN_PRICE <= MAX_PRICE`.

`Price on Request`, zero values, sentinel values, nonnumeric values, missing bounds, and inverted ranges are ineligible for median price-bound calculations. Retain their rows and annotate the reason; do not silently drop the entire listing from observed counts or sale counts. Do not replace unavailable prices with zero, a midpoint, a neighbouring month value, or a model-generated estimate.

### 6.2 Price per square foot

Do not recompute price per square foot from `MIN_AREA_SQFT` or `MAX_AREA_SQFT` until area units and semantics are verified. The current data has suspiciously small area values and `PRICE_SQFT` has extreme values. The provisional `100000` threshold is a review flag only: flag values at or above it for audit, but do not automatically remove them from the data or valid subset solely on this threshold. The final metric eligibility rule must be documented in `Data.md`, backed by a source-semantic check or explicitly marked unresolved. If unresolved, report the metric as unverified rather than asserting INR/sqft.

### 6.3 Duplicates and identifiers

Remove a row automatically only if it is an exact duplicate under the declared full-row duplicate rule. A repeated `PROP_ID` alone is not sufficient proof of a duplicate listing. The known repeated ID `Z70135726` appears twice and needs comparison across all columns; preserve both until an evidence-based rule is selected and recorded. Keep `source_row_id` or another stable row reference so every exclusion and flag can be traced to the raw snapshot.

### 6.4 Numeric calculations

Use deterministic Python numeric operations and documented pandas/numpy behavior for counts and medians. LLMs must not calculate or revise numerical metrics. Preserve sufficient precision in internal calculations; apply presentation rounding only at the reporting boundary. Every metric must be computed from its explicitly defined eligible subset, and the report must expose its denominator/count.

## 7. Missingness and monthly aggregation

The output grid always contains all 12 expected months, even when no eligible rows exist for a month.

- If a month has no eligible dated rows: `observed_listing_count=0`, numeric metrics are `null`, `coverage_status="no_listings"`, and `metric_status="no_listings"`.
- If rows exist but no sale rows exist: counts reflect observed rows, `sale_listing_count=0`, price metrics are `null`, and `metric_status="no_sale_listings"`.
- If sale rows exist but no valid price ranges exist: `valid_price_range_count=0`, price-bound medians are `null`, and `metric_status="no_valid_prices"`.
- If price-per-square-foot semantics are not verified: its median is `null` and its status is `unverified_metric`, even if raw numeric values exist.
- Otherwise, use `metric_status="ok"` for metrics whose eligibility conditions are satisfied.

Do not fill missing metrics with zero, forward-fill, interpolate, or invent listings. Keep `coverage_status` separate from `metric_status`. Because this is a scraped sample and the monthly distribution is highly uneven, all reporting must state that monthly counts can reflect scrape/collection behavior as well as posting activity.

## 8. Multi-agent architecture and execution graph

The workflow must be genuinely nonlinear and traceable. Implement the following logical roles; these may be separate modules or agents, but their contracts must remain testable independently.

1. **Planner**: validates the request, selects the fixed window, chooses the execution topology, and creates a run plan. It may not alter data or calculate report metrics.
2. **Scanner/Data worker**: reads only the frozen, cleaned snapshot and applies the supported filters. If parallel scanning is implemented, shard results must be merged deterministically and produce the same result as consolidated scanning.
3. **Aggregator**: validates eligible rows and computes the dense 12-month grid and deterministic medians. It does not call an LLM.
4. **Coverage Validator**: evaluates data/metric coverage and either accepts the result or requests a bounded repair/widening action. It may not fabricate data or change the fixed window.
5. **Anomaly Detector**: computes deterministic flags from defined counts/medians and explicit thresholds. Every flag includes a rule ID and supporting numeric evidence.
6. **Diagnostic Writer**: produces a plain-language explanation for each flag. If an LLM is enabled, it may explain only evidence supplied in the prompt; it cannot alter flags, metrics, or status.
7. **Reporter**: validates the final schema, assembles metadata, loop counters, trace, caveats, and status. It cannot change numeric results.

Required graph:

`Planner → Scanner/Data Worker → Aggregator → Coverage Validator`

The Coverage Validator has a feedback edge to the Planner or filter-selection step when a permitted repair can improve coverage. After acceptance: `Aggregator → Anomaly Detector → Diagnostic Writer → Reporter`. The trace must make the feedback edge, each attempt, and termination reason visible. A loop must not be represented as an unbounded conceptual arrow; its cap is enforced in code.

If parallel and consolidated paths are implemented, topology selection must be deterministic from documented request/data conditions. Both paths must preserve row identity, not double-count overlaps, and agree within the contract tolerance.

## 9. Loop policies and stop conditions

### L1 — Coverage repair loop
- Initial attempt plus at most `COVERAGE_REPAIR_CAP` retries.
- Every retry requires a named issue, a permitted repair, and a trace event containing attempt number, before/after coverage, action, and outcome.
- A repair may change only supported soft filters or partitioning. It must not change the frozen snapshot, month window, eligibility definitions, or numeric values.
- Stop immediately when the validator accepts coverage or when no permitted repair remains.
- On exhaustion, return a structured partial/error result with `max_attempts_exceeded`; never loop indefinitely.

### L2 — Critique/revision loop
- One initial draft plus at most `CRITIQUE_REVISION_CAP` revisions.
- The critique can request clearer explanation or missing caveats, not changes to calculated metrics.
- Revisions must be validated against the same schema and numeric evidence.
- Stop early when the critique passes; otherwise report `max_attempts_exceeded` and preserve the last valid draft or use deterministic fallback text.

Loop counters in the report equal the number of corresponding loop trace events. No hidden retries are allowed outside these counters.

## 10. Determinism, model boundaries, and failures

- Core data cleaning, filtering, aggregation, coverage scoring, anomaly detection, metric comparison, and schema validation are deterministic and independent of LLM availability.
- Model use is optional and limited to query interpretation or explanatory text. Model output is untrusted until schema and evidence checks pass.
- Support a no-model/off mode with deterministic rule/template behavior so the full application and test suite run without API keys or network access.
- Record model/provider, model identifier, temperature, seed, prompt/template version, cache status, retry count, and fallback source whenever applicable. Never log secrets.
- For stochastic/model-dependent tests, use at least three fixed seeds and repeat each eligible base input as required by `Testing.md`.
- Network/model failures must use bounded retries and deterministic fallback or explicit error status. They must not silently alter data or numeric outputs.

## 11. Trace and reproducibility

Each trace event includes a stable event type, agent/role, step/attempt number, input or criteria summary, action, outcome/status, and reason. Do not log sensitive credentials or full raw rows. Trace events must expose feedback-loop entry, retries, early stop, exhaustion, fallback, and final report assembly.

Provide one command reproducing cleaning, audits, golden outputs, and MR summaries. Document setup in `NOTEBOOK.md`; record AI-assisted tasks and manual checks in `AI_USE.md`. Version-control the snapshot, contracts, code, config, and expected outputs; exclude temporary files.

## 12. Acceptance criteria

A release is contract-compliant only if all are true:

1. Raw snapshot integrity is checked and the raw file is unchanged.
2. Canonical timestamp parsing uses milliseconds and `Asia/Kolkata`.
3. Every successful response contains exactly 12 chronologically ordered months from `2022-09` to `2023-08`.
4. All metrics follow the eligibility rules and have explicit counts/statuses; unresolved `PRICE_SQFT` semantics are not mislabeled as verified.
5. Invalid rows remain auditable, and duplicate-ID policy is evidence-based.
6. Numeric calculations are deterministic and independent of LLM calls.
7. Both loops terminate within their caps and record their traces/counters.
8. At least 8 valid metamorphic relations cover invariance, monotonicity, and directional behavior; each includes a subdomain, tolerance, targeted fault, and eligibility/skip rule.
9. Each MR has at least 30 distinct eligible base inputs. Any nondeterministic/model-dependent MR uses at least 3 fixed seeds.
10. Violation rates and 95% confidence intervals are reported with denominators and skips; the statistical method is stated.
11. The top three violations are diagnosed with evidence, not speculation.
12. The design note explains graph topology, feedback loops, agent dependencies, and a runtime trace.
13. The report is 10–12 pages and explicitly states the snapshot’s sampling and partial-month limitations.
14. One-command reproduction, `NOTEBOOK.md`, `AI_USE.md`, audit outputs, MR catalogue, harness results, and source files are included.

## 13. Change control and context budget

This file and its directly loaded subordinate contracts together have a working context ceiling of approximately 7,500 tokens and must remain below 8,000 tokens. This is a ceiling, not a target to fill. Keep code, raw data, logs, and long result tables outside contract text. Store each requirement in one authoritative location and link to it from other documents. Any change to shared constants, schemas, metric eligibility, loop caps, or MR semantics requires a version change and updated tests. Unresolved source semantics must be marked as unresolved; do not replace uncertainty with an assumption.
