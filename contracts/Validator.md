# Agent V — Coverage Validator Subcontract

**Parent:** `CONTRACT.md` v1.0.0-draft  
**Related contracts:** `Agents.md`, `Data.md`, `Planner.md`, `LLM.md`, `Testing.md`  
**Status:** Draft. This contract defines the coverage calculation and decision protocol. Production filter-repair behavior remains disabled until the parent contract defines an approved soft-filter schema and repair table.  
**Authority:** The global contract controls shared schemas, fixed-window semantics, metric eligibility, and retry caps. If this file conflicts with the parent, the parent wins and this file must be revised.

## 1. Job and boundary

The Coverage Validator (V) independently checks whether the Aggregator's twelve-month output is structurally sound, calculates the price-range metric-coverage score, identifies whether an observed coverage shortfall is eligible for an approved repair, and returns an explicit decision to the orchestrator.

V is deterministic and makes no LLM call. It does not calculate or repair housing metrics, change the source population, reinterpret columns, modify criteria, or create data. Its only control-flow effect is to accept the result, request one approved coverage repair through the Planner/orchestrator, or continue with an explicit partial-coverage status when no repair is permitted or the retry cap is reached.

V distinguishes three concepts that must not be conflated:

1. **Grid integrity:** whether the output has exactly one well-formed record for every expected month.
2. **Metric coverage:** whether eligible numeric price ranges exist to support monthly price-bound medians.
3. **Market representativeness:** not measured by this validator. A high score does not mean the scrape represents all Hyderabad listings or transactions.

Missing source data is not itself proof of a software defect. A valid `no_listings` or `no_valid_prices` record is preserved and reported; it must not be converted into a fictional observation to improve the score.

## 2. Inputs and outputs

| Item | Contract |
|---|---|
| Inputs | Aggregated 12-month records; the exact expected-month list; `data_quality`; original and effective criteria/plan metadata; enabled-loop flag; current coverage-repair attempt count; shared constants and schema version. |
| Outputs | `grid_integrity`, `coverage_months`, `coverage_score`, month-level coverage diagnostics, a decision (`accept`, `partial`, `repair_request`, or `fail`), reason code, and any authorized repair request. |
| Mutations allowed | Validator decision metadata and an authorized feedback request only. |
| Mutations forbidden | Source or processed rows, aggregate counts/medians, statuses owned by Aggregator, month window, eligibility rules, criteria, thresholds, or trace history. |
| LLM | None. No validator-specific prompt, replay key, or network call is allowed. |

The validator reads shared values from the application contract/configuration. It must not scatter copies of the month window, retry cap, sentinel value, or status vocabulary into agent-local constants.

## 3. Structural grid validation

### V-01 — Expected month set

The expected ordered month list is the twelve months from `2022-09` through `2023-08`, inclusive. It must be imported from the shared contract, not generated from the current clock. Exactly 12 monthly records are required on a normal aggregation result.

### V-02 — Uniqueness and order

Each expected month must appear exactly once. The records must be ordered chronologically. Duplicate month keys, unexpected month keys, missing keys, malformed `YYYY-MM` values, or records in a different order fail grid integrity. V reports the precise defect; it does not silently sort, deduplicate, or synthesize a replacement record.

### V-03 — Required field checks

For every monthly record, V checks that the parent-required fields are present and have the declared types. Counts must be nonnegative integers (booleans do not count as integers for this check). Metric values must be finite numbers or `null`; NaN and positive/negative infinity are invalid public values. Status fields must use the allowed vocabulary from `CONTRACT.md`.

### V-04 — Count and status consistency

V checks, but does not recompute, the following invariants:

- `sale_listing_count <= observed_listing_count`.
- `valid_price_range_count <= sale_listing_count`.
- `observed_listing_count == 0` must correspond to `coverage_status="no_listings"`, with numeric price medians null and `metric_status="no_listings"`.
- If `sale_listing_count == 0` but observed rows exist, `metric_status` must be `no_sale_listings` and price-bound medians must be null.
- If sale rows exist but `valid_price_range_count == 0`, price-bound medians must be null and `metric_status="no_valid_prices"`.
- If `valid_price_range_count > 0`, both median price-bound fields must be finite and strictly positive, with `median_min_price_inr <= median_max_price_inr`.
- `median_price_per_sqft_inr` must remain null with `metric_status`/quality metadata indicating `unverified_metric` until `Data.md` and the parent contract explicitly verify source semantics and units.
- August 2023 is marked `coverage_status="partial_month"` even if it has many rows; this status does not change counts or medians.

These are consistency checks. V must not repair inconsistent values itself. It sends a structured validation issue to the orchestrator and the Aggregator if a deterministic rebuild is permitted; otherwise it returns `fail`.

## 4. Metric coverage calculation

### V-05 — Definition

In this draft, the global metadata field `coverage_score` means **monthly price-bound metric coverage**, not the proportion of the real-world market observed and not structural grid integrity.

A month is **price-covered** when all of the following are true:

1. It is one of the twelve expected months and has exactly one structurally valid monthly record.
2. `valid_price_range_count >= 1`.
3. `median_min_price_inr` and `median_max_price_inr` are both finite, strictly positive, and ordered (`median_min_price_inr <= median_max_price_inr`).
4. `metric_status` is `ok` rather than `no_listings`, `no_sale_listings`, `no_valid_prices`, or `unverified_metric`.

Let `coverage_months` be the number of price-covered months. Then:

`coverage_score = coverage_months / 12`

The score is a finite float in `[0.0, 1.0]`. The decision must use the integer `coverage_months` and the associated month-level evidence; do not branch on a rounded display value. Display rounding, if any, happens only in the report.

This score describes availability of monthly median price-bound statistics within the frozen sample. It is not a measure of market representativeness, collection completeness, listing uniqueness, or confidence in the median. The report must retain `observed_listing_count`, `sale_listing_count`, and `valid_price_range_count` so a reader can inspect denominators. Since `PRICE_SQFT` remains unverified, it is not part of this score.

### V-06 — Structural integrity versus score

Structural integrity and metric coverage are separate outputs. `grid_integrity=false` is a validation defect; `coverage_score<1.0` can be a legitimate data outcome. A structurally valid report with one or more months lacking valid prices is not automatically malformed. The report may be `partial` while preserving all twelve monthly records and correct null semantics.

### V-07 — No hidden minimum sample threshold

The score requires at least one eligible price range in a month because that is sufficient to calculate a median; it does not claim that the median is statistically stable. V must not introduce an unstated minimum of 5, 30, or another number of rows per month. If the project later adopts a minimum-per-month policy, the threshold, rationale, and affected status must be added to `CONTRACT.md`, `Testing.md`, and shared config in a coordinated revision.

## 5. Decision protocol

V returns exactly one of these decisions:

| Decision | Condition | Required behavior |
|---|---|---|
| `accept` | Grid integrity passes and all 12 months are price-covered (`coverage_months == 12`). | Continue to anomaly detection and diagnostics. |
| `partial` | Grid integrity passes but one or more months are not price-covered and no permitted repair can run or the repair cap is exhausted. | Continue only if the parent status policy permits partial results; preserve null metrics and describe the coverage shortfall. |
| `repair_request` | Coverage is below 12 covered months, loops are enabled, the deficit is attributable to a currently configured repairable soft filter, the shared repair policy authorizes the proposed change, and retries remain. | Send one typed request to the Planner/orchestrator; do not mutate effective criteria locally. |
| `fail` | Grid/schema/status invariants fail and cannot be corrected by the approved deterministic rebuild path, or required validation evidence is missing/corrupt. | Return a structured error/failed run; never disguise invalid data as a valid partial result. |

A raw-data limitation is not a repairable software issue. If a month has no eligible price range because the source itself has no valid prices, V records that fact and returns `partial` unless a separately configured and approved soft filter demonstrably excluded otherwise eligible rows. The Validator must not change sale eligibility, relax price validity, remove outliers, expand the date window, or use other months to fill a missing median.

## 6. Coverage-repair policy and loop accounting

### V-08 — Current draft behavior

The parent sets `COVERAGE_REPAIR_CAP = 3` retries after the initial attempt. The current Planner contract says user-controlled filters are disabled and no repairable soft-filter table is approved. Consequently, **no production filter-widening action is currently authorized**. In the current configuration, a low score must result in `partial` and a clear reason such as `no_authorized_repair`, not an improvised retry.

The loop code and trace schema may be tested using a controlled fixture whose repairable filter and repair action are explicitly declared by test configuration. The fixture must not alter or add records to the frozen Hyderabad snapshot, and its outcomes must not be reported as data findings.

### V-09 — When a repair policy is approved

After the parent contract contains an explicit versioned repair table, V may request a repair only when every condition below holds:

1. `coverage_months < 12`.
2. `loops_enabled` is true.
3. `attempts < COVERAGE_REPAIR_CAP`.
4. At least one approved soft filter is present in the original validated criteria.
5. The diagnostic supports that the soft filter caused an avoidable loss of price-covered months, rather than a source-data or metric-validity problem.
6. The specific repair action is listed in the shared repair table.

The request includes the stable issue code, before-coverage evidence, affected months, approved field/action identifier, attempt number, cap, and reason. The Planner revalidates the action and applies it atomically. V does not send arbitrary replacement criteria or numeric thresholds.

A repair must never change the fixed twelve-month window, timezone, snapshot, sale definition, price-bound eligibility, sentinel rule, metric formula, or output schema. A repair that would change any hard constraint is rejected before another scan.

### V-10 — Attempt counts

The initial execution is attempt 0, not a retry. Actual retry attempts are numbered 1 through 3. Every actual coverage repair produces exactly one `kind="loop"` event with `loop="coverage_repair"`. No loop event is written for acceptance, a repair proposal rejected by policy, disabled loops, no configured soft filters, a source-data limitation, or a cap-exhausted decision. Those cases use a `decision` or `warning` event as appropriate.

After each approved retry, the pipeline must re-run the affected scan and aggregation, then return to V with the updated records. The process stops immediately when score reaches 1.0 or no authorized retry remains. The final `loop_counters.coverage_repair` must equal the number of trace events with `kind="loop"` and `loop="coverage_repair"`.

## 7. Trace contract

Every V decision emits a trace event with at least:

- `agent="coverage_validator"`
- `kind` (`decision`, `warning`, `error`, or `loop` only for an actual retry)
- stable `reason_code`
- `coverage_months`, `expected_months=12`, and full-precision `coverage_score`
- `grid_integrity` and a machine-readable list of failed invariants, if any
- `decision` (`accept`, `partial`, `repair_request`, or `fail`)
- `attempt` and `cap` where loop-related
- `repair_action` or `null`
- deterministic outcome and next stage

Trace must not include full CSV rows, lengthy descriptions, secrets, API credentials, or a model-generated explanation. Human-readable reasons are produced from deterministic templates and are secondary to the machine-readable fields.

Recommended stable reason codes include `coverage_complete`, `metric_coverage_partial`, `no_authorized_repair`, `loops_disabled`, `repair_cap_reached`, `repair_not_allowed`, `grid_missing_month`, `grid_duplicate_month`, `grid_unexpected_month`, `invalid_metric_value`, `status_count_inconsistent`, and `required_validation_evidence_missing`. Add any promoted code to the shared registry before freezing.

## 8. Failure and skip behavior

| Condition | Required result |
|---|---|
| All 12 months valid and price-covered | `accept`; proceed. |
| Grid valid, one or more months lack eligible prices, no repairable criteria | `partial`; keep all months and null metrics as specified. |
| Coverage below complete and loops are disabled | `partial`; trace `loops_disabled`; no loop counter increase. |
| Coverage below complete and no approved soft filter exists | `partial`; trace `no_authorized_repair`; no loop counter increase. |
| Coverage below complete and cap is reached | `partial`; trace `repair_cap_reached`; no additional attempt. |
| Proposed action is missing from the versioned repair table | Reject action; `partial` or `fail` according to whether the existing output is structurally valid; never apply a nearby action. |
| Missing, duplicated, unordered, or unexpected month keys | `fail` unless the parent-approved deterministic rebuild path succeeds; do not fill months from guesses. |
| NaN/infinite public metric or incompatible count/status pair | `fail` or deterministic rebuild; never coerce to zero. |
| Validator exception caused by a programming defect | Propagate during tests/development; do not convert to successful `partial`. |

## 9. Must not

V must not call an LLM; read or mutate the raw CSV; recompute medians or counts; alter metric eligibility; convert price units; decide that a `PRICE_SQFT` value is valid INR/sqft while semantics remain unresolved; remove records; impute or interpolate metrics; change the fixed month window; expand a query beyond the frozen snapshot; invent soft filters or repair thresholds; hide partial coverage; or claim that the sample measures total Hyderabad market inventory.

## 10. Required tests

1. Exactly 12 unique ordered months pass the grid check.
2. Missing, duplicated, out-of-order, malformed, or unexpected month keys are detected with distinct issue codes.
3. Each allowed `coverage_status` and `metric_status` combination is checked against count and null semantics.
4. Negative counts, bool-as-count, NaN, infinity, nonnumeric metrics, inverted medians, and impossible count inequalities fail validation.
5. `no_listings`, `no_sale_listings`, and `no_valid_prices` months remain valid records with correct nulls; none is silently converted to zero-priced data.
6. Each of 0 through 12 price-covered months gives the exact integer `coverage_months` and score `coverage_months / 12` within floating-point tolerance; decisions branch on the integer.
7. `PRICE_SQFT` being unverified never increases or decreases the price-bound coverage score.
8. Coverage below 12 without an authorized soft filter returns `partial` and generates no loop event.
9. Disabled, rejected, skipped, and cap-exhausted paths do not increment retry counters.
10. A controlled fixture reaches the repair feedback edge and stops after at most the configured cap; the actual raw snapshot hash and rows remain unchanged.
11. If a configured repair succeeds, the pipeline re-aggregates, revalidates, and stops immediately when full price coverage is achieved.
12. The final loop counter equals the number of matching loop trace events exactly.
13. Run the validator twice on identical aggregate records and config; all validation outputs, decisions, and deterministic trace fields are identical.
14. Report wording says sample/observed coverage, never full-market coverage.

## 11. Parent-contract decisions required before freeze

- Add `coverage_score = coverage_months / 12` and the month-level definition from §4–5 to `CONTRACT.md` as the authoritative public definition.
- Confirm whether `partial` is a successful report status or a nonzero exit/result status, and align `CONTRACT.md`, `Agents.md`, and `Reporter.md` accordingly.
- Define the canonical trace schema and error/reason-code registry in shared config.
- Keep coverage repair disabled until supported soft filters and atomic repair actions are listed in the parent contract. If no user filters are added, retain the bounded loop as a controlled orchestration path for testing but do not fabricate real-data repairs.
- Add the score formula, decision cases, null/status combinations, and loop tests to `Testing.md` and the independent oracle.

**Version note:** Draft `Validator.md` for `CONTRACT.md` v1.0.0-draft. The formula above is an explicit proposed definition, not an already verified property of the source file. Promote it into the parent contract before declaring the contracts and implementation frozen.
