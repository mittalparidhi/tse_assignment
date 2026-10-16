# AGENTS SUBCONTRACT — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

**Parent:** `CONTRACT.md` v1.0.0-draft  
**Related contracts:** `Data.md`, `Testing.md`, `LLM.md`  
**Status:** Draft; open clarification items are listed in §11.

This file defines each agent's responsibility, interface, mutation boundary, failure behavior, and required tests. It follows the organization of the supplied Chennai reference `c/Agents.md`, but all data rules are adapted to the frozen Hyderabad snapshot. Chennai locality names, historical windows, price fields, thresholds, and golden examples do not apply. The global `CONTRACT.md` is authoritative: if a rule here conflicts with it, correct this subcontract rather than silently redefining the parent.

## 1. Rules shared by all agents

| ID | Rule | Consequence |
|---|---|---|
| A-I/O | Agents receive explicit inputs and return explicit outputs. Only the repository/startup boundary reads files or verifies the snapshot hash. | No hidden filesystem, network, or system-clock access inside business agents. |
| A-PURE | Never mutate the shared cleaned dataframe, request, criteria, or another agent's result in place. | Use immutable models or copies for local transforms. |
| A-NUM | Counts, eligibility, medians, coverage, anomaly flags, status fields, and confidence/statistical results are computed by deterministic code. | LLM text cannot set or revise numbers or test outcomes. |
| A-DATA | Preserve source rows and `source_row_id`. No synthetic listings, inferred dates, silent ID-level deduplication, or invented price values. | Test-only fixtures must remain separate from the real housing snapshot. |
| A-WINDOW | Use the global 12-month window `2022-09` through `2023-08`, inclusive, with `Asia/Kolkata` month derivation. | No agent independently changes the window or derives months from timezone-naive timestamps. |
| A-SCHEMA | Shared constants, output fields, metric rules, statuses, loop caps, and error codes come from `CONTRACT.md` and the shared application contract/config. | Do not scatter duplicate constants across agents. |
| A-ORDER | Results must not depend on input row order, worker completion order, or hash-map iteration. | Stable IDs, fixed month order, deterministic merging, and sorted numeric inputs are required. |
| A-ERR | Known domain failures use the structured error/status convention in the parent contract. Unexpected programming exceptions propagate in development/tests. | Never disguise a bug as an empty successful report. |
| A-TRACE | Every decision that changes control flow, every retry/revision, and every fallback is traced. | Loop counters must reconcile exactly with loop trace events. |

Agents must not infer that the snapshot represents all Hyderabad housing activity. `CITY` currently contains both `Hyderabad` and `Secunderabad`; the default source scope is the frozen file as supplied unless a reviewed parent-contract change explicitly narrows it. The repeated `PROP_ID` `Z70135726` is not sufficient evidence to deduplicate its two rows; follow `Data.md`.

## 2. Agent P — Planner

**Job:** validate a user request and produce a runnable plan. **LLM:** optional, only through `llm_client` and the rules in `LLM.md`.

| Interface | Contract |
|---|---|
| Inputs | User request; global contract/config; verified snapshot metadata and supported filter schema; execution mode; seed; optional coverage-repair request. |
| Outputs | Validated request/criteria, selected topology, planned steps, initial trace events. |
| May change | Plan, validated criteria, topology selection, and allowed soft-filter changes explicitly requested by the coverage controller. |
| Must not change | Raw/cleaned rows, fixed month window, metric eligibility, thresholds, numeric results, or source semantics. |

Responsibilities:
1. Validate required fields, types, supported filters, and requested output options. Reject unknown filters; never silently ignore them.
2. Pin the analysis window to `2022-09`–`2023-08`. Reject a request to change it unless a separately approved parent-contract revision permits variable windows.
3. In structured mode, use the validated request without an LLM. In natural-language mode, request a schema-constrained parse via `llm_client`; validate it in code and use only declared fields.
4. Choose `consolidated` scanning by default. Choose `parallel` only if the parallel path is implemented, its partitioning is deterministic, and the equivalence test in §10 passes. A configuration override may select topology only among implemented paths.
5. Preserve the original request separately from effective criteria. Record any allowed change as a before/after trace entry.
6. For coverage repair, apply only the explicit repair request allowed by the parent/config. A repair may relax configured soft filters; it may not change the time window, source file, sale definition, price-validity rules, or row contents.

**Failure behavior:** invalid or unsupported requests produce the parent's structured error with the field named. In `off` mode, do not call a model. In `replay` mode, never silently make a live call on a cache miss. Model parsing failures use the deterministic parser/fallback described in `LLM.md`, or the parent-defined error if no valid fallback exists.

## 3. Agent S — Scanner / Data Worker

**Job:** select the rows that satisfy a validated plan. **LLM:** none.

| Interface | Contract |
|---|---|
| Inputs | Immutable `hyderabad_clean.csv` snapshot; validated criteria; optional non-overlapping shard definition. |
| Outputs | Matching row view/copy, stable `source_row_id` values, scan counts, trace metadata. |
| May change | The selected row set only. |

Responsibilities:
1. Use the repository layer to load the cleaned artifact and verify its recorded provenance. Startup integrity verification uses the expected raw hash from `Data.md`/the parent config; agents must not update the expected hash automatically.
2. Select rows only by documented filters. The date window is based on the localized `posting_month`, not `REGISTER_DATE`, `UPDATE_DATE`, display strings, or a timezone-naive conversion.
3. Keep invalid-date rows in the auditable cleaned artifact, but exclude them from month-based analysis. Rows outside the fixed window remain auditable and do not enter the 12-month result.
4. Preserve all source fields and stable row identity; do not deduplicate repeated `PROP_ID` values. The current exact-duplicate policy is defined in `Data.md` and may change only through a reviewed rule change.
5. A zero-row selection is a valid result, not a scanner error. Return an empty selection with a trace event.
6. If parallel scanning is active, partition by a deterministic key, guarantee each eligible `source_row_id` belongs to exactly one shard, and merge in a fixed order. The merged row multiset must equal the consolidated result.

**Must not:** compute medians or anomalies; infer `TRANSACT_TYPE` meanings; convert prices from display lakh/crore strings; filter `PRICE_SQFT` by an unverified threshold as though it were invalid; or change any numeric field. The raw CSV remains read-only.

## 4. Agent G — Aggregator

**Job:** validate selected rows for metric eligibility and create the dense monthly output. **LLM:** none.

| Interface | Contract |
|---|---|
| Inputs | Validated plan; selected rows; canonical expected-month list; metric eligibility rules from `CONTRACT.md` and `Data.md`. |
| Outputs | Exactly 12 monthly records, data-quality denominators, aggregation trace. |
| May change | Computed monthly records and quality counts only. |

Responsibilities:
1. Always emit months in chronological order: `2022-09`, `2022-10`, …, `2023-08`. The output key set must not depend on which rows happen to be present.
2. Compute `observed_listing_count` from rows with valid localized posting dates in the month, with no undocumented property-ID deduplication. Compute `sale_listing_count` only for `PREFERENCE == "S"`.
3. A valid price range requires numeric, finite, strictly positive `MIN_PRICE` and `MAX_PRICE`, neither equal to sentinel `2147483647`, and `MIN_PRICE <= MAX_PRICE`. Use only eligible sale rows for price-bound medians. Retain ineligible rows in observed/sale counts when they otherwise meet those count definitions.
4. Compute `median_min_price_inr` and `median_max_price_inr` from their respective eligible bound values. Use a deterministic median implementation; even-sized subsets use the mean of the two middle sorted values. Do not round before comparison or storage.
5. `PRICE_SQFT` semantics remain unverified. Therefore the published `median_price_per_sqft_inr` is `null` with `metric_status="unverified_metric"` until the parent contract records a verified unit/meaning. A raw quality count may be reported only with an explicit unverified label. Do not derive it from area columns until their scale is verified.
6. Follow the parent's distinction between zero counts and unavailable metrics. Never replace `null` with zero, impute missing prices, interpolate, or carry values forward.
7. Keep month coverage status separate from metric status. The final month is `partial_month` as defined by the parent; an empty month has zero counts and null metrics, not invented observations.
8. Return enough denominators and eligibility counts for the Reporter and tests to reproduce each metric independently.

**Must not:** call an LLM, make anomaly judgments, revise filters, widen coverage, write explanations, or drop source rows. Missing required columns are schema failures, not silently substituted columns.

## 5. Agent V — Coverage Validator

**Job:** decide whether monthly data coverage is sufficient to proceed or a permitted repair is justified. **LLM:** none by default; any model-assisted choice requires a parent-contract change and must not control numeric thresholds.

| Interface | Contract |
|---|---|
| Inputs | Aggregated monthly records and denominators; original and effective criteria; configured coverage rule; retry counter; loop-enabled option. |
| Outputs | Coverage result/score; accept, stop, or explicit repair request; trace events. |
| May change | Control flow and a documented request to relax eligible soft filters. |

Responsibilities:
1. Calculate coverage only from the formula and threshold defined in shared config. Record the formula, denominator (12 months), observed score, required threshold, and decision.
2. Coverage measures presence/availability within this snapshot; it does **not** establish representativeness of Hyderabad's market or that scraped monthly counts are complete.
3. Request a repair only when coverage fails, a permitted soft filter exists, loops are enabled, and the retry cap has not been reached. Do not retry if no meaningful allowed repair remains.
4. Repairs may relax only soft filters explicitly marked repairable in the request schema/config. Never widen the analysis window, synthesize observations, change price eligibility, rewrite source values, or silently change Hyderabad/Secunderabad scope.
5. Stop as soon as coverage passes, loops are disabled, no permitted repair remains, or the configured cap is reached. At exhaustion, preserve the actual low score and return the status required by the parent contract.
6. The current global draft does not yet specify the exact coverage formula/acceptance threshold or the canonical names of repairable soft filters. Do not invent constants in this agent. These must be set in `app/contract.py` and reflected in the parent contract before the production repair decision is considered frozen. A controlled test fixture may force retry/stop branches solely to test termination.

**Loop accounting:** the initial scan is not a retry. There may be at most `COVERAGE_REPAIR_CAP` retries after it. Each actual retry emits exactly one `kind="loop"` event with loop name `coverage_repair`, attempt number, before/after coverage, action, reason, cap, and outcome. Disabled/skipped decisions use non-loop trace events and do not increment the counter.

## 6. Agent A — Anomaly Detector

**Job:** compute versioned numeric anomaly flags from validated monthly outputs. **LLM:** none.

| Interface | Contract |
|---|---|
| Inputs | Validated 12-month records, metric denominators, and anomaly rules/thresholds from shared config. |
| Outputs | Ordered anomaly-flag list plus detector status and evidence. |
| May change | Anomaly outputs only. |

Responsibilities:
1. Execute only rules with stable IDs, documented inputs, thresholds, eligibility/preconditions, comparison direction, and missing/zero-baseline behavior.
2. Each flag contains at least `rule_id`, `month`, `metric`, `observed_value`, `baseline_or_comparator`, `threshold`, `denominator`, and a deterministic reason code. Preserve full precision in machine fields.
3. If a required metric is `null`, a denominator is inadequate, the comparison baseline is absent/zero, or the rule's precondition fails, skip the rule for that month and record the reason. Do not coerce unavailable values to zero.
4. Findings describe a pattern in the provided scrape sample. Do not infer causes (e.g. a scraping change) without independent evidence and do not present an anomaly as proof of a market event.
5. The current global draft requires explicit versioned rules but does not yet establish numeric anomaly thresholds. The implementation must source these from shared config / an approved parent decision. It must not invent numeric thresholds locally. If no rules are configured, return no flags and an explicit `not_configured` status rather than silently claiming the data is anomaly-free.

**Must not:** call the LLM, modify counts/medians/statuses, read rows outside the analysis window, or use the unverified `PRICE_SQFT` as an INR/sq-ft metric.

## 7. Agent D — Diagnostic Writer and Critique/Revision Gate

**Job:** explain already-computed flags and apply the bounded quality-review loop to explanatory text. **LLM:** optional, via `llm_client` only.

| Interface | Contract |
|---|---|
| Inputs | Anomaly flags; corresponding computed evidence; `llm_mode`; seed; approved prompt/schema; critique checklist. |
| Outputs | One diagnostic per flag, `source` (`llm` or `template`), validation result, revision count, trace. |
| May change | Explanatory text and its provenance/validation metadata only. |

Responsibilities:
1. Emit exactly one explanation for each flag and none when no flags exist. If there are no flags, do not call the model.
2. In `off` mode, use deterministic templates. In `replay`, use only a matching stored response; a cache miss must never trigger an unannounced live request. In `live`, call only through `llm_client` with configured timeouts and bounded retries.
3. Supply the model only evidence already computed in code. Require structured output, reject unknown fields, validate that the response refers only to supplied flags and evidence, and discard any proposed numbers, new flags, metric changes, unverified causes, or unsupported claims.
4. The critique gate checks completeness, alignment to the supplied flag, uncertainty, required sampling/partial-month caveats where relevant, and forbidden causal assertions. A critique can request clearer language or a missing caveat, not changed metrics or flags.
5. Allow one initial draft plus at most `CRITIQUE_REVISION_CAP` revisions. Every revision is schema-checked against the same fixed evidence. Stop on first valid draft. On exhaustion, retain the last valid draft or use a deterministic template and record the outcome according to `LLM.md`.
6. Record model/provider and identifier, mode, seed where applicable, prompt/template version, cache status, attempt count, validation outcome, and fallback source. Never log credentials or unnecessary listing text.

**Must not:** add/remove flags, change status, choose thresholds, calculate values, mutate monthly records, or execute model-supplied code, commands, paths, SQL, or instructions.

**Loop accounting:** one initial draft plus at most `CRITIQUE_REVISION_CAP` revisions. Each actual revision emits exactly one `kind="loop"` event with loop name `critique_revision`, attempt, reason, validation issue, outcome, and cap. A template fallback is not itself a revision unless a revision was actually attempted.

## 8. Agent R — Reporter

**Job:** assemble and validate the final report. **LLM:** none. **Numeric mutation:** forbidden.

**Inputs:** plan/effective criteria, 12 monthly records, data-quality metadata, anomaly flags, diagnostics, coverage decision, loop counters, trace, snapshot/contract/version metadata.  
**Outputs:** response conforming to the global report/error schema.  
**May change:** presentation assembly and metadata only; it may not recalculate or revise numeric results.

Responsibilities:
1. Validate exactly 12 ordered month records; required fields and types; valid status values; nonnegative integer counts; finite numeric metrics or `null`; and `null`/status consistency.
2. Confirm that `valid_price_range_count` does not exceed `sale_listing_count`, and `sale_listing_count` does not exceed `observed_listing_count`. Check that denominators and anomaly evidence reconcile to the numeric results.
3. Include snapshot hash, contract/logic version, timezone, window, run mode, seed if relevant, topology, coverage decision/score, loop counters, trace, data-quality flags, fallback/model metadata, and caveats required by `CONTRACT.md`.
4. Mark August 2023 as partial. Explain that monthly row counts are observed listing-entry records from a scraped sample, not census counts or completed transactions. Do not call unverified `PRICE_SQFT` verified INR/sq-ft.
5. Verify loop counters against the number of corresponding `kind="loop"` events. Trace event indices, if used by the implementation, are unique and ordered without gaps.
6. Serialize deterministically in `off` and `replay` modes where the parent contract requires reproducibility: stable field order, stable month order, no wall-clock fields in deterministic output, and no rounding introduced solely for display in machine data.
7. On a domain error, emit the parent-defined error shape and preserve available trace/diagnostics. Do not turn a failed or partial run into `status="ok"` merely because a report can be rendered.

## 9. Required graph and runtime trace

Required main path:

`Planner → Scanner → Aggregator → Coverage Validator`

If coverage repair is permitted and needed:

`Coverage Validator → Planner/selection step → Scanner → Aggregator → Coverage Validator`

After coverage acceptance or bounded stop:

`Aggregator → Anomaly Detector → Diagnostic Writer ⇄ Critique/Revision Gate → Reporter`

The critique/revision gate may be implemented inside the Diagnostic Writer/orchestrator rather than as a separate process, but its decision and feedback edge must be visible. The graph must be a real execution graph, not merely a diagram; both loops must be capped in code. Trace events must identify agent, event kind, attempt, action, outcome/status, and reason. Include a runtime trace showing one feedback-edge execution and one no-retry execution. If the frozen data does not naturally trigger coverage repair, use a separate controlled test fixture; never add fake listings to the real snapshot.

## 10. Minimum agent-level tests

| Agent | Required tests |
|---|---|
| Planner | Fixed window enforced; unknown filter rejected; request preserved; `off` makes no model call; invalid/model-unparseable requests follow documented fallback/error behavior. |
| Scanner | Date conversion/filtering respects the localized month; source rows and IDs are preserved; empty selection is valid; input data unchanged; repeated IDs are not implicitly removed. |
| Aggregator | Exactly 12 months in order; correct independent denominators; coherent price-range eligibility; known hand-calculated medians; correct zero/null/status behavior; `PRICE_SQFT` remains unverified until approved. |
| Coverage Validator | Formula/threshold come from config; pass, fail, disabled, no-soft-filter, early-stop, and cap-exhaustion paths; exact retry limit; counters equal loop events. |
| Anomaly Detector | Each configured rule's positive, negative, boundary, null, and low-denominator cases; stable rule IDs; deterministic outputs; no unsupported-cause claims. |
| Diagnostic Writer | No flags means no model call; `off` uses templates; valid/invalid model response, timeout, replay miss, fallback, and revision-cap behavior; numeric records cannot be altered by output. |
| Reporter | Schema/status validation; denominator inequalities; partial-August caveat; trace/counter reconciliation; stable output in deterministic modes; error path retains trace. |
| Whole graph | Coverage feedback edge reached in a controlled fixture; critique/revision edge reached; both stop at caps; consolidated/parallel equivalence if both modes ship; raw snapshot remains unchanged. |

Use the independent oracle and MR rules in `Testing.md`. The bounded-loop termination test is a control-flow test and must not be counted as a data metamorphic relation if the rubric treats those categories separately.

## 11. Parent-contract clarifications required before freezing

| Item | Current limitation | Required action |
|---|---|---|
| Coverage acceptance | `CONTRACT.md` defines the repair cap but not the exact coverage score formula or acceptance threshold. | Add the formula/threshold to shared config and the parent contract before production behavior is frozen. |
| Repairable filters | The supported filter set and which filters are soft/repairable are not fully specified. | Declare them in the request schema/parent contract; never assume a filter can be relaxed. |
| Anomaly thresholds | Parent requires explicit rules but does not list a complete rule catalogue or threshold constants. | Approve/version the rule catalogue and thresholds before interpreting empty flags as a clean bill of health. |
| City scope | Source contains both `Hyderabad` and `Secunderabad`. | Keep supplied-file scope by default; narrow it only after a documented decision. |
| Trace/counter schema | Parent requires trace and exact accounting but does not yet freeze all field names. | Define shared event/counter models once and import them across agents. |

## 12. Traceability and change control

| Agent contract | Parent authority |
|---|---|
| Shared invariants and errors | `CONTRACT.md` §§3, 4.4, 10–11 |
| Planner/scanner | `CONTRACT.md` §§4–5, 8–10; `Data.md` |
| Aggregator/statuses | `CONTRACT.md` §§4–7; `Data.md` |
| Coverage repair and caps | `CONTRACT.md` §9 |
| Anomaly evidence | `CONTRACT.md` §§8, 10; `Testing.md` |
| LLM diagnostics/revision | `CONTRACT.md` §10; `LLM.md` |
| Report schema/reproducibility | `CONTRACT.md` §§4, 11–12 |

Change the global contract first when changing shared schemas, metrics, fixed window, eligibility, thresholds, loop caps, or error semantics. Then update this file and affected tests. Keep the contract suite within the parent context budget; do not paste raw CSV rows, source code, or full logs into contracts.

*Version: draft for `CONTRACT.md` v1.0.0-draft.*
