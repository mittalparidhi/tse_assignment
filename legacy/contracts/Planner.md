# PLANNER SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v1.0.0-draft. **Related:** `LLM.md`, `Data.md`, `Agents.md`. The parent contract wins on conflicts. Read this file with `CONTRACT.md` and `LLM.md`; load `Data.md` only when changing data-source rules. This split is deliberate so the active planner context stays below the project’s 8,000-token ceiling.

**Status:** Draft. Request schema, supported natural-language grammar, topology configuration, and coverage-repair policy must be registered in the shared contract/config before implementation is frozen.

## 1. Role and boundary

**Kind:** decision-maker. Model use is optional and is allowed only through the shared `llm_client` under `LLM.md`.

**Job:** convert a user request into a validated `effective_request`; choose a supported execution topology; produce a deterministic `RunPlan`; and respond to an explicit, authorized coverage-repair request. The Planner does not read or transform listing rows, calculate coverage scores, clean data, calculate metrics, select anomaly thresholds, or write the final report.

| Interface | Contract |
|---|---|
| Inputs | Original request; run options; fixed contract constants; verified startup snapshot-integrity result; optional structured coverage-repair request from the Coverage Validator; shared config and supported-schema version. |
| Outputs | `effective_request`, `run_plan`, selected topology, planner trace events, or a structured domain error. |
| May change | Request representation/defaults that are explicitly authorized by this contract; topology and execution-plan metadata. It may not alter the source snapshot, month window, population/metric definitions, or price eligibility. |
| Must preserve | `request_in` exactly as received, including the original natural-language text or structured object. |

## 2. Supported request semantics

The public scope is the frozen source snapshot and the fixed analysis window. The Planner must not silently turn a broad request about this snapshot into a narrower dataset filter.

### 2.1 Defaults

If omitted, the Planner applies these defaults from shared configuration:

- `window_start = "2022-09"` and `window_end = "2023-08"`;
- `scope = "snapshot_default"`, covering both `CITY` labels present in the file (`Hyderabad` and `Secunderabad`), unless a later parent-contract revision authorizes another scope;
- `llm_mode = "off"` unless the run configuration explicitly selects `replay` or `live`;
- `topology = "consolidated"` unless configuration or a valid explicit run option selects an implemented parallel path;
- metric semantics are fixed by `CONTRACT.md`: observed counts use dated records in the window; sale-price metrics use `PREFERENCE == "S"`; unverified `PRICE_SQFT` is not relabeled as verified INR per square foot.

These are defaults, not inferred claims about market coverage. The Planner must not say that the returned counts represent the entire housing market.

### 2.2 Fixed window

A request may omit dates or explicitly name the exact contract window. A request for another start or end month is unsupported. Do not clamp it, replace it with a “nearest” month, or silently accept only the overlapping portion. Return a structured `unsupported_window` error and name the requested and allowed ranges. The 12-month output grid is owned by the parent contract, not by the wording of the user query.

### 2.3 Filter support

Only fields and filter operations registered in a versioned shared request schema are supported. In the current draft, user-controlled row filters are **not enabled**. In particular, the Planner must not silently filter by `CITY`, parsed locality from `location`, `PROPERTY_TYPE`, bedroom count, transaction type, price, or area. A request for such a filter returns `unsupported_filter` and identifies the field. This prevents a model from inventing locality names, treating Secunderabad as out of scope, or using unverified area/transaction fields.

`PREFERENCE == "S"` is a metric eligibility rule, not a request filter: all eligible dated records contribute to `observed_listing_count`, while the sale subset contributes to sale/price metrics as defined in `CONTRACT.md`.

### 2.4 Supported intent

A valid request asks for monthly observed listing counts and/or the contract-defined sale asking-price summaries for the frozen snapshot. The Planner may normalize phrasing such as “monthly listing counts,” “sale price trend,” or “monthly asking prices” to the existing report fields. It must not infer a new statistic, promise a current 2026 market answer, forecast future prices, infer transaction completions, or return unimplemented dimensions. Unsupported intents return a structured error instead of being approximated silently.

## 3. Input modes and parsing

### Structured mode

1. Validate the incoming object against the versioned request schema.
2. Reject unknown fields, invalid types, out-of-window dates, unsupported filters, invalid `llm_mode`, or unsupported topology names.
3. Fill only documented defaults in §2.1.
4. Do not call an LLM.

### Natural-language mode

1. Preserve the original text in `request_in` and calculate a stable request/input hash for tracing or replay lookup. Do not include the entire dataset or raw listing rows in a model prompt.
2. In `off` mode, use only the deterministic grammar implemented and tested by the project. If the request falls outside it, return a parse/unsupported-intent error; do not make a live call.
3. In `replay` mode, use only a matching versioned cached result. Cache keys must include parser/prompt version, normalized request hash, model/config identity where relevant, and seed. A cache miss is explicit; it never falls through to live mode.
4. In `live` mode, the LLM may propose only the request-schema fields. Validate the response exactly as for structured input. Ignore or reject unknown fields, unsupported filters, changed windows, inferred dataset facts, and extra prose that attempts to change system policy.
5. If model parsing fails, use the deterministic fallback only if it can parse the request unambiguously. Otherwise return an explicit error. Record fallback use as a `warning` trace event.

Model output is untrusted input. It is not authority to change contract constants, data semantics, metric eligibility, loop caps, or tool permissions.

## 4. Run plan and topology

The `RunPlan` is metadata for orchestration, not a copy of the dataset. It records at minimum: contract/schema version; fixed window; timezone; scope; required output metrics; selected topology; partition policy if any; `llm_mode`; seed where applicable; and the reasons for any non-default choice.

### Topology decision

1. Default to `consolidated` so the application works without parallel execution support.
2. A valid `force_topology` option may select `consolidated` or `parallel` only if that implementation is enabled in shared config.
3. If `parallel` is requested but unavailable, return `topology_unavailable`; do not simulate parallel execution while labelling the trace as parallel.
4. If both paths are implemented, partition assignment and merge order must be deterministic and disjoint. Every source-row identity may contribute at most once. Parallel and consolidated paths must yield equivalent month records, metrics, statuses, and flags within parent-defined tolerances.
5. A topology choice must not alter the fixed window, input population, row-level eligibility, metric definitions, or data-quality accounting. Do not select topology based on an LLM’s opinion of the results.

The current parent contract does not freeze a parallel partition scheme. Before implementing parallel mode, register the partition key, treatment of invalid-date/out-of-window rows for quality metadata, overlap check, merge order, and equivalence test in shared configuration or the parent contract. Until then, consolidated mode is the compliant default.

## 5. Coverage-repair feedback

The Planner may receive a repair request only from the Coverage Validator, with a stable issue code, measured coverage evidence, requested action, current attempt, and cap. It must independently check whether the proposed action is allowed by the versioned repair table; the Validator cannot authorize an otherwise forbidden change.

**Current draft limitation:** `CONTRACT.md` defines a cap of three retries after the initial attempt, but the coverage formula/acceptance threshold and repairable soft-filter set are not yet approved. Because user-controlled filters are currently disabled, there is no authorized filter-widening action in this draft. The Planner must not invent one. Until the shared coverage policy is approved, record the repair as unavailable, keep the effective request unchanged, and let the orchestrator stop with the low-coverage/partial status defined in the parent contract.

Once a versioned repair table is approved:

1. Accept only actions listed in that table, applied to the named supported soft field.
2. Never change `window_start`, `window_end`, timezone, snapshot, sale eligibility, price validity rules, `PRICE_SQFT` status, or global output schema.
3. Apply one repair pass atomically. If any part is not permitted, make no partial changes and return a repair-not-allowed decision.
4. Revalidate the resulting request against the same schema and recompute topology deterministically.
5. A repair is one retry, regardless of how many fields the approved table changes in that pass. The initial attempt is not a retry; no more than `COVERAGE_REPAIR_CAP` retries may occur.
6. A retry is triggered only by an explicit validator feedback event. The Planner cannot create repeated retries on its own or reset the attempt counter.

Each actual retry emits exactly one `kind="loop"` trace event. Skipped, disabled, unauthorized, and exhausted-loop decisions are not loop firings and must not increment the retry counter. Required shared trace field names must be frozen in the parent contract before implementation.

## 6. Trace requirements

Every Planner event records the original request identifier/hash, parser mode, schema version, action/decision, reason, outcome, and any relevant attempt number. Record the `effective_request` separately from immutable `request_in`; never overwrite the original request for logging convenience.

Trace events should distinguish:

- `step`: request received, schema validation, defaults applied, or plan assembled;
- `decision`: accepted/rejected request, chosen topology, or repair permitted/skipped;
- `warning`: deterministic fallback used, optional model unavailable, or non-default configuration;
- `error`: a structured domain failure;
- `loop`: an actual coverage repair retry only.

Never log API credentials, full prompts containing secrets, or full listing descriptions. If the shared trace schema changes, update `CONTRACT.md` and all agent contracts together.

## 7. Failure behavior

Error names below are proposed stable codes; add them to the global error registry before freezing implementation.

| Condition | Required behavior |
|---|---|
| Unknown request field or malformed structured request | `invalid_request`; identify the field and expected form. |
| Requested window differs from `2022-09`–`2023-08` | `unsupported_window`; do not clamp or silently change it. |
| Unsupported city/locality/property/price/area filter | `unsupported_filter`; do not ignore it. |
| Request intent cannot be parsed unambiguously | `request_unparseable`; no guessed criteria. |
| Replay key not found | `replay_miss`; never make a live request. |
| Parallel requested but not configured | `topology_unavailable`; do not mislabel execution. |
| Coverage-repair rule missing or action unauthorized | record repair unavailable; leave request unchanged and stop/continue only as the parent coverage contract defines. |
| Snapshot hash failed at startup | orchestrator returns `snapshot_integrity_error` before Planner runs. |
| Unexpected programming exception | propagate during tests/development; do not hide it as a domain error. |

## 8. Must not

The Planner must not read/filter/count rows; calculate coverage, counts, medians, confidence intervals, or anomaly thresholds; infer source-field semantics; deduplicate records; expand the fixed month window; invent localities or property facts; mutate the snapshot; weaken metric eligibility; call the model outside `llm_client`; execute model-suggested code; or claim that an unsupported filter was applied.

## 9. Required tests

1. Structured valid request fills defaults without an LLM call.
2. Explicit fixed window is accepted; earlier/later window is rejected unchanged with the expected code.
3. Unknown fields and unsupported city/locality/property/price/area filters are rejected, not ignored.
4. All documented intent phrases map to the same fixed report schema; unsupported forecasting/current-market intent is rejected.
5. `off` mode makes zero network/model calls; replay hit uses the cached validated result; replay miss makes no live call; live parsing goes only through `llm_client`.
6. Malformed model output, unknown fields, prompt-injection-like request text, and model-suggested metric/schema changes cannot alter contract constants or data rules.
7. Original request text/object remains byte-/value-equivalent in `request_in` after parsing, fallback, and repair.
8. Default topology is consolidated. Requested parallel topology fails explicitly when unavailable; when both modes are implemented, a fixture verifies disjoint partitions and output equivalence.
9. An unauthorized or unconfigured repair leaves criteria unchanged; configured repairs are atomic, revalidated, and stop after the shared cap.
10. Actual retry count equals `kind="loop"` repair events; skipped/disabled decisions do not increment it.
11. Snapshot-integrity failure prevents Planner invocation; unexpected coding exceptions are not disguised as successful runs.

## 10. Parent-contract decisions required before freeze

- Add the exact request and `RunPlan` schemas, supported intents, and error-code registry to `CONTRACT.md` or `app/contract.py`.
- Decide whether any user-controlled filters will be supported. If so, define each field, canonical values, comparison semantics, and whether it is hard or repairable.
- Define the coverage score, pass threshold, and authorized repair table before implementing coverage repair.
- Register the parallel partition strategy and `force_topology` semantics before claiming parallel support.
- Define the canonical trace event/counter schema once and import it across modules.

**Version:** Draft `Planner.md` for parent `CONTRACT.md` v1.0.0-draft. Any change to request fields, window semantics, topology policy, repair authority, error codes, or trace schema requires coordinated parent, planner, and test updates.
