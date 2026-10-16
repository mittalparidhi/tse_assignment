# Reporter Contract — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

**Contract ID:** `TSE-HYD-REPORTER`  
**Contract version:** `1.0.0-draft`  
**Role:** Reporter (final response assembler)  
**Authority:** `CONTRACT.md` is authoritative for shared public fields, status semantics, numerical rules, and failure behavior. This file defines how the Reporter assembles and checks those fields. It must not redefine an upstream metric or silently resolve an open global decision.

## 1. Purpose

The Reporter assembles a single public report from validated outputs produced by the Planner, Scanner/Data Worker, Aggregator, Coverage Validator, Anomaly Detector, and Diagnostic Writer. It exposes the output to the API/UI and creates a stable machine-readable representation suitable for regression testing and downstream rendering.

The Reporter is a **plain deterministic worker**. It is not an analyst, a metric calculator, an anomaly detector, or an LLM agent. It cannot improve a result by changing a number, replacing a `null`, suppressing a flag, or rewriting the status. Its responsibility is to ensure that the independently computed outputs are present, mutually consistent, properly attributed, and serialized under the public contract.

This contract concerns the application's response object. The assignment's separate 10–12-page research/report deliverable may be rendered from validated outputs using a dedicated reporting script, but document layout must not become a second source of computed values. The Reporter must not claim that a PDF or other artifact was created unless the artifact writer confirms success.

## 2. Contract precedence and imports

- Read this file and `CONTRACT.md`; consult `Data.md`, `Aggregator.md`, `Validator.md`, `Anomaly.md`, `Diagnostic.md`, `Golden.md`, `Testing.md`, and `LLM.md` only for the specific fields or invariants they own.
- Import schemas, constants, and enums from the shared contract module (for example `app/contract.py`). Do not duplicate thresholds, required field lists, status values, or loop caps in Reporter code.
- If this contract conflicts with `CONTRACT.md`, follow `CONTRACT.md` and record the conflict for correction. A subordinate contract cannot add a public field without a parent-schema change.
- The Reporter receives normalized upstream objects. It must not reopen `hyderabad.csv`, reload the cleaned dataset, call external services, or reconstruct omitted computations.

## 3. Kind, inputs, outputs, and invariants

**Kind:** worker; pure assembly and validation function.  
**LLM:** none.  
**May compute:** structural checks, schema checks, equality/reconciliation checks, metadata copying, deterministic serialization.  
**May not compute:** prices, counts, medians, price changes, coverage score, flags, pooled statistics, confidence intervals, or explanatory evidence values.

### 3.1 Required inputs

The Reporter receives a `ReportParts` (or equivalent typed object) containing:

1. the validated request as received and the validated/effective criteria selected by the Planner;
2. the Aggregator's twelve monthly records and any approved summary object;
3. the Coverage Validator's final outcome/status and `coverage_score`;
4. the Anomaly Detector's complete `anomaly_analysis` object;
5. the Diagnostic Writer's ordered diagnostic list;
6. data-quality counts from the audited cleaning/aggregation pipeline;
7. the complete trace emitted by the orchestrator and individual agents;
8. run configuration and versions: contract version, logic version, frozen snapshot SHA-256, seed, LLM mode, selected topology, scanner count if relevant, and loop-enable flags/counters.

Every input must have already passed its owning agent's validation. A missing required component is not permission to fabricate a replacement.

### 3.2 Successful output

The Reporter returns exactly one object matching the current public `TrendReport` schema in `CONTRACT.md`. It preserves registered field names and types, including the twelve `records`, the `anomaly_analysis`, ordered `diagnostics`, data-quality information, run metadata, `trace`, `status`, and `error` field (null on success where required by schema).

The Reporter must not add speculative fields such as market forecasts, unique-property counts, confidence claims, causes, or unverified price-per-square-foot interpretations. It must not remove a schema field just because its value is `null` or its array is empty.

### 3.3 Core invariants

- **Numeric immutability:** all numeric outputs are copied from their authoritative upstream result. The Reporter must not recalculate, round, clamp, normalize, infer, or overwrite them.
- **Trace immutability:** trace event order and content are preserved except for deterministic schema validation. The Reporter may append one documented final-assembly event only if the shared trace contract explicitly permits it; do not mutate earlier events.
- **Diagnostic alignment:** diagnostic `flag_id` sequence exactly matches the anomaly flag sequence, one diagnostic per flag.
- **Month grid:** on an accepted successful result, there are exactly 12 monthly records in chronological order from `2022-09` to `2023-08`.
- **Snapshot identity:** output hash equals the hash verified at run start; never recalculate it from a modified or cleaned file and present it as the raw snapshot hash.
- **No missing-value repair:** `null` remains `null`; unavailable values are not converted to zero, empty strings, “N/A”, or estimates in JSON.
- **No hidden data:** the Reporter does not expose raw rows, credentials, API keys, full private prompts, or sensitive provider headers.

## 4. Public response assembly

### 4.1 Contract-owned fields

The Reporter copies or references the following fields exactly as defined in `CONTRACT.md`:

| Field | Source of truth | Reporter behavior |
|---|---|---|
| `status` | Final orchestrator/Validator outcome under global status rules | Copy; never infer status from a count or flag |
| `error` / `error_code` fields | Shared error schema | Copy a validated error, or use the registered success representation |
| `contract_version` | Shared constant | Copy the imported constant |
| `snapshot_sha256` | Startup integrity check | Copy the verified raw-file hash |
| `run_id` | Shared run-identity policy | Copy the upstream run identifier; do not invent wall-clock IDs |
| `window_start`, `window_end` | Validated request/global fixed window | Copy the effective window; reject mismatch |
| `timezone` | `LOCAL_TIMEZONE` | Copy `Asia/Kolkata` |
| `seed` | Run configuration | Copy; if no seed applies, use the schema's explicit null/value convention |
| `llm_mode` | Run configuration | Copy `off`, `replay`, or `live` as validated |
| `logic_version` | Build/configuration metadata | Copy supplied version; do not derive it from free-form text |
| `coverage_score` | Coverage Validator | Copy without recomputation |
| `topology` | Planner's selected topology | Copy the actual path used, not the desired path |
| `loop_counters` | Orchestrator trace bookkeeping | Validate against trace, then expose |
| `trace` | Orchestrator | Preserve events and consecutive indices |
| `data_quality` | Audited data/aggregation pipeline | Copy counts and flags with their documented names |
| `records` | Aggregator | Copy all 12 records; do not recompute them |
| `anomaly_analysis` | Anomaly Detector | Copy after structural reconciliation only |
| `diagnostics` | Diagnostic Writer and its gate | Copy in exactly the original flag order |

The precise top-level nesting is owned by `CONTRACT.md`. If a local implementation currently groups some of these under `metadata`, it must map consistently to the registered schema; Reporter must not emit both nested and top-level duplicate copies unless the schema requires both.

### 4.2 Request and effective criteria

If the public schema registers `criteria_in`, it must preserve the request values as received, before repair or normalization. If it registers `effective_criteria`, it must reflect the validated criteria actually used by the Scanner/Data Worker. They are distinct fields and must not overwrite each other. Any applied coverage repair must be visible through the final effective criteria and the L1 trace; it must never be disguised as the original user request.

If a future public schema includes `price_unit`, copy it from the validated effective criteria. Do not independently infer a unit from display strings or field names. Until such a field is formally registered in `CONTRACT.md`, do not add it ad hoc.

### 4.3 Partial final month

The response covers September 2022 through August 2023. August 2023 must remain `coverage_status="partial_month"`, because the latest observed posting date is August 26, 2023. The Reporter must preserve that status and the shared scrape-sample caveat. It must not fill missing days, extrapolate counts, seasonally adjust values, or relabel August as a complete month.

A separate `partial_last_month` metadata flag may be emitted only if it is registered in the current public schema. If present, it must be `true` for the contracted window and must agree with the August record. The Reporter must not derive a conflicting independent interpretation.

## 5. Metadata and trace integrity

### 5.1 Required metadata

For the public fields registered in `CONTRACT.md`, preserve:

- the contract version and code/logic version;
- the exact frozen raw snapshot SHA-256;
- the effective window and timezone;
- the execution seed and LLM mode;
- the selected topology and applicable worker/scanner count;
- whether each feedback loop was enabled;
- the two loop counters for coverage repair and critique/revision;
- the quality counts needed to interpret the report.

A metadata value must describe what actually ran, not what was intended. For example, set the topology to `consolidated` if only consolidated execution occurred. If parallel execution is not implemented, do not claim multiple scanners.

### 5.2 Loop counters

`loop_counters.coverage_repair` and `loop_counters.critique_revision` must exactly equal the count of trace events with `kind="loop"` and the matching registered loop name. Model-call retries are not loop firings and must not inflate either value. Conversely, any actual feedback-loop firing must have one corresponding loop event and counter increment.

If the trace contains an unknown loop name or malformed loop event, fail report validation rather than silently dropping the event or coercing the counter. The Reporter must not edit the trace to make the counter pass.

### 5.3 Trace shape

Use the shared trace schema from `CONTRACT.md`/the trace owner. Under the current schema, each event has stable fields for its zero-based index `i`, `agent`, `kind`, `loop`, `msg`, and `data`. The `i` values must be the consecutive sequence `0, 1, ..., n-1`. Each agent and event kind must belong to the registered enum. Do not reorder the trace alphabetically or by agent; temporal execution order is meaningful.

The final response must expose the runtime trace needed to show the actual feedback loop firing. A trace containing only an idealized graph or a claimed loop count without the event is not sufficient. Keep private prompt text and secrets out of trace payloads.

## 6. Determinism and JSON serialization

### 6.1 Deterministic modes

With `LLM_MODE=off` and `LLM_MODE=replay`, the same frozen raw snapshot, canonical request, contract/logic versions, seed, options, and replay-cache contents must produce byte-identical serialized report JSON. This guarantee applies to the response payload; external console logs and timing measurements are outside it.

Achieve this by using a fixed schema/key order, stable list order, stable flag/diagnostic order, a canonical request/config representation, deterministic `run_id` behavior under the shared run-identity policy, and no wall-clock timestamp or elapsed-time value in the deterministic payload unless a global schema revision explicitly changes this guarantee. Do not use random UUIDs, unordered-set iteration, machine-specific absolute paths, or locale-dependent formatting in the serialized body.

`live` LLM prose is not expected to be byte-identical. However, all numerical data, monthly records, anomaly flags, flag order, quality counters, statuses, loop caps, and diagnostic-to-flag alignment must be checked against the same invariants. Live text may vary only within the policy in `Diagnostic.md`.

### 6.2 Numeric representation

Do not round numbers during assembly or serialization. Use the project's documented JSON serializer and its shortest-round-trip numeric representation, preserving values that round-trip to the same binary number. Presentation rounding belongs only in a rendered UI or final document layer and must not overwrite the machine-readable report.

Never encode a number as a formatted string in a numeric field. Do not use locale-based decimal separators, digit grouping, currency symbols, or percent signs in machine-readable numbers. A display layer may show a price as INR lakh/crore if that display convention is separately documented, but the numeric JSON fields remain rupee values.

### 6.3 Time fields

The current global schema does not authorize the Reporter to read the clock to add runtime timestamps or elapsed-duration fields to the public response. If operational timing is required later, record it in an external execution log or introduce it through a versioned schema change that explicitly relaxes the byte-identical deterministic-payload invariant. Never add wall-clock fields silently.

## 7. Error handling

The Reporter validates upstream results before returning success. There are two failure classes:

1. **Expected domain failure:** an upstream agent/orchestrator supplies a registered error. Reporter emits the error response required by the global schema and preserves the trace and diagnostic error context permitted by that schema.
2. **Report assembly/schema defect:** required fields are missing, months are duplicated/reordered, counters disagree with the trace, diagnostics do not align with flags, the snapshot hash is not verified, or a numeric field has an invalid type. Reporter must not return a successful report. Use the registered report-schema error code if one exists; otherwise propagate a typed assembly exception to the orchestrator so the global error handler can emit a valid failure response.

Unexpected programming exceptions must not be hidden behind a fabricated successful report. During development and tests, preserve the exception or fail loudly with the original cause. Do not broadly catch every exception and convert it into an empty result.

### 7.1 Global error-shape rule

Where the global error schema specifies `status="error"`, `records=[]`, `summary=null`, and `coverage_score=0`, follow it exactly; retain the trace and registered error `{code, message}`/`error_code` fields as prescribed by the currently frozen schema. The Reporter does not retain apparently valid partial numeric records in fields that the error schema requires to be empty. If the schema version has not yet settled a difference between `error` and `error_code`, raise the schema conflict for a global revision rather than emitting both forms ad hoc.

An optional diagnostic-text failure is not a report-level error if `Diagnostic.md` successfully supplies a template fallback. A numeric pipeline, snapshot-integrity, or required-schema failure cannot be concealed as a text fallback.

## 8. Data-quality reconciliation

Reporter performs validation, not recomputation. It checks identities that can be verified from the supplied results:

- total of monthly `observed_listing_count` equals the Aggregator's in-window dated-row total;
- total of monthly `sale_listing_count` equals the corresponding in-window sale total;
- total of monthly `valid_price_range_count` equals the eligible coherent sale-price-range total;
- `valid_price_range_count <= sale_listing_count <= observed_listing_count` in each month;
- count fields are nonnegative integers, not booleans or floating-point approximations;
- medians are finite numbers or `null` under the registered metric status;
- `median_min_price_inr <= median_max_price_inr` whenever both are non-null and calculated over the same eligible rows;
- unverified `PRICE_SQFT` semantics imply `median_price_per_sqft_inr=null` and the registered unverified status; no Reporter-layer value is allowed to replace it;
- raw input hash, date-quality count, and source-row totals match the upstream audit metadata and the current golden fixture;
- all 12 months are present once, with the correct partial-month marker for August.

The Reporter must not “repair” a mismatch by changing the monthly records, editing `data_quality`, dropping a month, or forcing an aggregate total. It raises or returns the registered validation error and exposes enough trace information to diagnose the inconsistent agent output.

## 9. UI and final-report rendering boundary

If the application has a UI or generates a separate assignment report, it consumes the validated machine-readable response as read-only input.

- Table cells and charts must use the existing report values; no independent metric calculation in UI code.
- Display `null` explicitly as unavailable/unverified, not as zero.
- Label money as INR; price bounds are listing asking-price bounds, not completed transaction prices.
- Show the fixed reporting window and mark August 2023 as partial.
- Include a concise snapshot-coverage caveat: this is a scrape-derived sample and row concentrations can reflect sampling/collection behavior.
- Do not describe observed listing counts as market-wide inventory, completed transactions, or unique properties.
- Do not describe the anomaly flags as causal claims or statistical significance findings.
- Include the execution trace/loop example and contract/logic/snapshot versioning in the 10–12-page assignment report where the report rubric requires them; cite the frozen data source as documented in `Data.md`.
- Keep the reflection about LLM assistance and non-LLM reproducible behavior in the report artifact, not as a model-generated inference embedded into numeric fields.

Rendered presentation may format a value for a human reader, but the source numeric values and statuses remain accessible for audit. The document renderer must also make clear when a figure is absent because a metric is unresolved or its eligible denominator is zero.

## 10. Prohibited behavior

The Reporter must never:

1. calculate or adjust an aggregate, median, change fraction, anomaly threshold, flag, coverage score, or confidence interval;
2. call an LLM, web API, database, or source URL;
3. infer a cause for a flag or relabel the scrape snapshot as the whole market;
4. change the request to match the result or hide changes made by the coverage-repair loop;
5. infer or change `PREFERENCE`, `TRANSACT_TYPE`, area units, or `PRICE_SQFT` semantics;
6. replace `null` by zero or suppress data-quality evidence;
7. modify raw/cleaned data or deduplicate repeated property IDs;
8. insert random run IDs, wall-clock timestamps, elapsed-time values, or machine-specific paths into deterministic JSON;
9. remove or reorder diagnostics/flags/trace events to make output look cleaner;
10. claim a file, chart, or report was written before its writer confirms the exact artifact path and successful completion.

## 11. Acceptance tests

At minimum, automate the following tests using the shared fixtures and contract constants:

| ID | Scenario | Expected behavior |
|---|---|---|
| REP-01 | Valid full-snapshot report | Required schema valid; exactly 12 ordered monthly records |
| REP-02 | Month order duplicate/missing | Reject report; do not sort/fill silently |
| REP-03 | `records` medians altered between Aggregator and Reporter | Reporter detects mismatch only if authoritative duplicated evidence is provided; never rewrites medians |
| REP-04 | Count reconciliation mismatch | Reject/fail report assembly |
| REP-05 | `valid_price_range_count > sale_listing_count` | Reject/fail report assembly |
| REP-06 | Unverified `PRICE_SQFT` but non-null median | Reject/fail report assembly |
| REP-07 | August month marked complete | Reject/fail report assembly |
| REP-08 | Diagnostic missing/extra/reordered flag IDs | Reject/fail report assembly |
| REP-09 | `loop_counters` disagree with loop trace events | Reject; never edit trace to agree |
| REP-10 | Trace indices have a gap/duplicate | Reject/fail report assembly |
| REP-11 | Error status | Match exact shared error shape and preserve trace |
| REP-12 | No anomaly flags | `diagnostics=[]`; no call inferred or fabricated |
| REP-13 | Repeated `PROP_ID` | Reporter does not deduplicate or alter row counts |
| REP-14 | Same input/configuration in `off` mode twice | Byte-identical response JSON |
| REP-15 | Same input/configuration and same replay cache | Byte-identical response JSON |
| REP-16 | Different machine locale | JSON numbers/order remain unchanged |
| REP-17 | Seed/configuration metadata | Values match the actual run context |
| REP-18 | Snapshot SHA-256 mismatch | Return registered snapshot-integrity error; no success report |
| REP-19 | LLM diagnostic fallback | Complete report still succeeds if all numeric/upstream checks pass |
| REP-20 | UI/display rounding | Machine-readable response remains full precision and unchanged |
| REP-21 | Missing timing fields | No timestamp/elapsed time is inserted by Reporter under the current deterministic schema |
| REP-22 | Artifact writer returns failure | No success claim or fabricated path in the report |
| REP-23 | Trace contains actual feedback loop firing | Trace event and loop counter agree, and are visible in response/report trace |
| REP-24 | Error schema has `summary=null`, empty records, zero coverage | Exact error response follows global schema; no partial numeric body is substituted |

Test fixtures may include isolated in-memory inputs for invalid schema, empty subsets, malformed traces, or diagnostic mismatches. They must not be appended to the frozen CSV or described as real listings.

## 12. Open schema decisions and change control

The current draft suite contains a few schema decisions that must be reconciled centrally before implementation freezes:

1. Whether public error schema uses `error: {code, message}` or `error_code` plus another message field.
2. Whether partial/nonfatal coverage maps to a public `status="partial"` or another registered status; Reporter must copy the Validator/orchestrator decision and cannot decide this locally.
3. Whether `run_id` is a deterministic fingerprint or an opaque operational identifier. Byte-identical `off`/`replay` payloads require deterministic run identity.
4. Whether `summary`, `criteria_in`, `effective_criteria`, `price_unit`, `partial_last_month`, `n_scanners`, and `loops_enabled` are registered top-level fields, nested metadata, or not part of the public response. Do not emit inconsistent duplicate forms.
5. Whether timestamps/elapsed-duration data belong in a separate operational log instead of the deterministic report body.

Resolve these in `CONTRACT.md`, update `Golden.md`, update the corresponding schemas/tests, and increment the shared contract version. Until that occurs, the rule is to follow the current global schema and fail visibly on a contradiction; do not invent a private Reporter convention.

## 13. Definition of done

The Reporter contract is implemented when its schema tests pass; all report numbers and flags remain identical to authoritative upstream outputs; the 12-month grid and August partial label are preserved; metadata accurately reflects the actual run; loop counters reconcile with the ordered trace; diagnostics align one-to-one with flags; errors follow the global response shape; and repeated `off`/`replay` runs produce byte-identical machine-readable JSON for the same frozen inputs and configuration. The Reporter has no LLM dependency and no permission to modify data or calculations.
