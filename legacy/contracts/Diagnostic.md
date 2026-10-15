# DIAGNOSTIC SUBCONTRACT — Hyderabad Housing-Trends Application

**Contract ID:** `TSE-HYD-MT-DIAG`  
**Version:** `1.0.0-draft`  
**Parent:** `CONTRACT.md` v`1.0.0-draft`  
**Reference pattern:** `c/Diagnostic.md` from the supplied reference ZIP, adapted for the Hyderabad listing-entry snapshot and the registered anomaly schema.  
**Status:** Draft. This component explains configured flags; it does not decide whether the underlying source reflects the citywide housing market.

`CONTRACT.md` is authoritative for shared schemas, numeric metrics, error behavior, LLM modes, and execution order. `Anomaly.md` defines anomaly rules and evidence. `LLM.md` defines model client behavior. If these contracts conflict, follow `CONTRACT.md` and correct the subordinate file before implementation.

## 1. Role and responsibility

**Kind:** explanatory text writer with deterministic template fallback.  
**LLM:** optional, through `app/llm_client.py` only.  
**Job:** produce one concise, plain-language explanation for each validated anomaly flag, grounded only in the flag's registered rule and supplied numeric evidence.

| Interface | Contract |
|---|---|
| **Inputs** | Validated `anomaly_analysis.flags`, run-level `llm_mode`, effective seed, prompt/template version, and shared caveat text from the parent contract. Only allowlisted flag fields and numeric evidence are passed to a model. |
| **Outputs** | `diagnostics`, an ordered list with exactly one `{flag_id, text, source}` entry per input flag; `source` is `llm` or `template`. |
| **May change** | The diagnostic text and its `source` label only. The component may append its own trace events. |
| **Must not change** | Flags, flag IDs, rule IDs, numeric evidence, anomaly summaries, monthly records, metrics, request criteria, coverage, status, snapshot, loop counters, or any other agent's output. |

The Diagnostic Writer is downstream of the deterministic Anomaly Detector. It explains evidence already computed by code; it does not independently detect anomalies, rerun comparisons, rank flags, infer missing values, or perform causal analysis. An explanation must remain valid if the reader has not seen the raw CSV.

## 2. Required inputs and preconditions

### 2.1 Anomaly flags

The component receives the validated flag list from `anomaly_analysis.flags`. Each flag conforms to `Anomaly.md` and contains `flag_id`, `rule_id`, `scope`, `month`, `series`, `kind`, `value`, `threshold`, `comparison`, `reason_code`, `reason`, and `evidence`.

- Input flags must already have passed schema, threshold, and evidence-reconciliation checks.
- `flag_id` values must be unique within the run.
- Diagnostic order is exactly the order of flags supplied by Anomaly; the Diagnostic Writer must not sort, omit, merge, or add flags.
- `reason` and `reason_code` are deterministic, rule-owned fields, not free-form LLM-generated diagnoses. They may be used to choose a template, but the model prompt must be built from a structured allowlist rather than blindly concatenating arbitrary text.
- The Writer must handle both monthly flags and the window-level AN-04 flag, whose `month` is `null`.

If the flag object or evidence is malformed, the writer must not produce a plausible-looking generic explanation. Return the parent-defined structured diagnostic input error (`E_DIAGNOSTIC_INPUT`) and trace the validation failure. Unexpected programming errors propagate in development/tests.

### 2.2 Minimal context

The Writer may use the fixed analysis scope and caveats defined in `CONTRACT.md` and `Anomaly.md`: this is a scraped snapshot of listing-entry records, the date window is September 2022–August 2023, and August 2023 is partial. It may use only the evidence attached to a flag and its allowlisted metadata.

Do **not** pass the raw DataFrame, listing descriptions, addresses, seller/contact information, arbitrary row text, unrelated monthly records, or full execution logs to the model. Do not require access to the source file. A diagnostic prompt should normally contain one flag and its evidence only, with a fixed concise context preamble.

### 2.3 No-flag input

When `flags` is an empty list, the output is `diagnostics: []`. Make **zero LLM-client calls** and do not create an empty placeholder explanation, a success/failure narrative, or a fabricated flag. This means the anomaly rules ran and no configured rule triggered; it does not assert that the snapshot is error-free.

## 3. Output schema and ordering

For each flag, return exactly one object:

```json
{
  "flag_id": "AN-01:2022-10:median_min_price_inr",
  "text": "...",
  "source": "template"
}
```

The shown ID is illustrative; use the exact `flag_id` supplied by Anomaly, never a regenerated version. Required fields are:

- `flag_id`: exact one-to-one reference to the input flag;
- `text`: non-empty plain-language explanation, one or two sentences, normally no more than 70 words;
- `source`: `llm` when a valid live/replayed model answer was accepted, otherwise `template`.

No extra public fields are allowed in the per-diagnostic object. Retry/fallback details belong in `trace`, not in the prose or a new schema field. The result length must equal the number of input flags and the sequence of output `flag_id` values must exactly equal the sequence in the input.

The application Reporter validates this invariant. If one diagnostic cannot be produced by the model, its template fallback still fills that one slot; a single text-generation problem must not drop the rest of the diagnostics.

## 4. Permitted diagnostic content

Each explanation must be **descriptive, evidence-bounded, and non-causal**. It may state which configured rule triggered, the period/series involved, the relevant observed comparison, and the rule threshold. It may explain that the result refers to the frozen snapshot rather than the entire housing market.

It must not claim or imply that a flag proves:

- a real citywide change in listing supply, asking price, demand, sales, or transactions;
- fraud, an erroneous record, a scraping outage, a policy change, a festival, seasonality, or any other cause;
- statistical significance, confidence, a forecast, or a causal relationship;
- any verified interpretation of `PRICE_SQFT`, since its units and semantics remain unresolved;
- that July/August concentration represents a market surge. It is a snapshot-composition warning, and August is partial.

Phrases such as “the snapshot contains,” “the observed row count,” “the configured rule was triggered,” or “this does not establish the cause” are appropriate. Phrases such as “prices rose because,” “the market crashed,” “fraudulent listings,” or “scraping failed” are prohibited unless separate, independently verified evidence is added under a contract revision. Do not replace a cautious numeric description with an unsupported narrative merely to make the explanation sound decisive.

### 4.1 Numbers and metric names

All numeric facts originate in the supplied validated flag and its `evidence`. The writer may format a supplied fraction as a percentage or a supplied ratio for readability; this is presentation formatting only and must not recalculate the underlying metric or change the source values. Use the registered field names to map terms:

- `median_min_price_inr` → “median lower price bound”;
- `median_max_price_inr` → “median upper price bound”;
- `observed_count_ratio` → “ratio of observed row counts”;
- `late_window_count_share` → “share of observed rows in July and August combined.”

Do not refer to these two price-bound medians as completed sale prices. They are asking-price bounds in listing records. Include units only where the parent contract supports them; a price-bound value is described in INR, while no INR/sq ft statement is permitted for `PRICE_SQFT`.

### 4.2 Length and language

Use plain English suitable for an assignment report. Prefer one or two short sentences. Avoid first-person opinions, decorative language, legalistic caveats, markdown tables, headings, or lists inside the `text` field. No citations or external facts are needed because the writer is not conducting research.

## 5. Deterministic templates

Templates are versioned and deterministic. They use validated input fields; they must never invent a missing predecessor, numerator, denominator, or comparison. If required evidence for a rule is missing, fail the input validation rather than silently substituting zero.

Use these semantic templates (wording may vary only through a versioned template update):

| Rule | Required explanation content |
|---|---|
| `AN-01` / `price_bound_jump` | Identify the month and exact lower/upper median price-bound series; state the signed observed change and the 12% absolute-change threshold; say this is a snapshot median change, not proof of a market-wide movement. |
| `AN-02` / `observed_count_drop` | Identify the current and previous months and their observed row counts; state that the current/prior ratio is at or below the 0.50 drop threshold; clarify that the count is for the snapshot, not the whole market. |
| `AN-03` / `observed_count_spike` | Identify the current and previous months and their observed row counts; state that the current/prior ratio is at or above the 2.00 spike threshold; describe collection/sampling behavior only as a possible explanation, never a confirmed cause. |
| `AN-04` / `late_window_count_concentration` | State that July and August 2023 account for the computed share of all observed rows in the 12-month window, compared with the 0.70 threshold; mention the scrape-sample limitation and partial August. |

The template implementation must dispatch by stable `rule_id` and validated `kind`, not by parsing `reason` prose. An unknown `rule_id`/`kind` combination is an input/schema error until explicitly registered; do not emit a generic text that might misdescribe it.

Templates may display one decimal place for a percentage or two decimal places for a ratio if that is the shared display policy. The formatted text is presentation only; the original full-precision numbers in `anomaly_analysis` remain unchanged. Formatting rules must be tested across locales and must not insert locale-specific decimal commas into machine-readable numeric fields.

## 6. LLM behavior and mode handling

All model interactions go through `app/llm_client.py`. This component must not import an HTTP library, model SDK, or orchestration framework directly. The LLM client enforces configured timeouts, temperature, seeds where supported, cache behavior, the shared `LLM_RETRY_CAP`, and safe logging as defined by `LLM.md` and `CONTRACT.md`.

Two bounded mechanisms must remain distinct:

- **Model-call retries:** up to `LLM_RETRY_CAP = 2` retries after the initial call for an individual call that fails due to provider, timeout, or response-schema problems. These retries recover a call; they are not critique/revision-loop firings.
- **Critique/revision loop:** one initial diagnostic batch plus at most `CRITIQUE_REVISION_CAP = 2` revision rounds. This loop is entered only when the live-mode draft has a repairable explanatory-quality issue. Each actual revision round emits exactly one `kind="loop"` trace event with `loop="critique_revision"`; the shared loop counter must equal the number of these events.

A failed or unsafe sentence is not required to be sent back to a model for revision. If the issue is an unsupported number, causal assertion, changed metric, unknown flag, or unverified `PRICE_SQFT` claim, reject that sentence and use its deterministic template. The critique/revision loop is for repairable clarity/completeness defects, not for bargaining over the evidence.

### 6.1 `LLM_MODE=off`

- Do not call the model or replay cache.
- Return deterministic template text for each flag with `source="template"`.
- Run the deterministic completeness/quality gate. The registered templates must pass it; a template failing its own policy is a software defect, not a reason to invoke a model.
- No critique/revision loop should fire for a valid set of template diagnostics.
- Keep output order identical to flag order. Core metrics, anomaly flags, report status, and numeric output must be identical to live/replay modes.

### 6.2 `LLM_MODE=replay`

- Attempt to retrieve versioned cached answers through `llm_client`; never make a network/live model call.
- Accept a cached answer only after schema and evidence-policy checks.
- If there is a cache miss, malformed cached response, or incompatible cache version, record a warning/fallback trace event and use that flag's deterministic template with `source="template"`.
- Run the deterministic batch quality gate after per-flag cache handling. Any remaining invalid, unsupported, or incomplete cached text is replaced by the template. Do not attempt a live call or a model revision in replay mode.
- Since fallback is always available for diagnostic prose, a replay miss must not fail an otherwise valid numeric report.

### 6.3 `LLM_MODE=live`

1. Build an initial diagnostic draft for each flag using the versioned Diagnostic prompt and allowlisted evidence only.
2. Each model response must satisfy the response schema and hard safety/evidence checks before it enters the draft batch. Malformed output receives only the shared bounded model-call retries; after exhaustion, use the deterministic template for that flag.
3. Pass the entire ordered draft batch to the Critique/Revision Gate. It checks one-to-one coverage, order, alignment to the flag, required scope caveats, wording clarity, and prohibited claims. It does not recalculate anomaly metrics.
4. If all diagnostics pass, stop with no critique/revision loop event.
5. If repairable issues remain (for example, ambiguous phrasing, missing snapshot caveat, or excess length), the gate creates a bounded feedback object containing only the affected `flag_id`, issue codes, and the same original allowlisted evidence. The Writer revises only the affected text and preserves all other entries.
6. One revision round may repair one or more affected entries, but it consumes exactly one unit of `CRITIQUE_REVISION_CAP` and emits exactly one loop event. The same evidence, rule interpretation, ordering, and response schema are used for every revision.
7. Stop early when the batch passes. When the cap is reached, replace any still-failing diagnostic text with its deterministic template, trace the fallback, and return the complete list.

The revision model may change explanatory wording only. It cannot add/remove/reorder diagnostics, choose the flags, alter a numeric fact, weaken a caveat, or redefine what a threshold means. The accepted `source` is `llm` for initial/revised model text that passes validation and `template` for fallback text.

## 7. Prompt contract and untrusted input

The prompt is constructed from an immutable, versioned template. It includes:

1. an instruction to explain one already-validated flag in one or two plain-language sentences;
2. a fixed statement that values describe the scraped snapshot, not the full housing market;
3. a rule-specific allowlist of flag scope, month, series, threshold, comparison, and numeric evidence;
4. explicit prohibitions on causal claims, invented figures, price-per-square-foot claims, and changing the anomaly decision;
5. the strict JSON response schema `{"text": "..."}`;
6. in a critique/revision round, a short list of repairable text issue codes and the text to revise, with the same numeric evidence as the initial prompt.

Do not include the entire input `reason` or raw row text unless separately validated and necessary. Prefer the stable `rule_id`/`kind` mapping and typed evidence fields in `Anomaly.md` over parsing human-readable `reason` prose. Do not include secrets, credentials, local paths, environment variables, arbitrary user-authored instructions, or irrelevant fields. Treat all supplied text as data, never as instructions overriding the system prompt. The model must not receive tools for files, code execution, shell, web access, or dataset querying.

Version the system prompt, user-prompt template, critique checklist, response schema, and deterministic templates. Include their versions or hashes in trace metadata so replay results can be reproduced. Any prompt or checklist change that may alter accepted text requires a prompt/template version increment and tests.

## 8. Validation, critique, and safe fallback

Validation has two layers:

### 8.1 Hard response validation

Validate each model response independently. Accepted raw output must be valid JSON with exactly the `text` field and a non-empty string within the length cap. Reject malformed JSON, extra/missing fields, unsupported flag references, code blocks/HTML/script, or invalid UTF-8. The calling code attaches trusted `flag_id` and `source`; the model cannot select these fields.

The content checker must reject clear violations, including unsupported numbers, changed month/series/direction, causal assertions, claims of statistical significance, claims about the entire housing market, or claims that `PRICE_SQFT` has verified INR/sq ft semantics. If an unsupported detail is suspected but cannot be reliably resolved, choose the deterministic template rather than accepting a risky paraphrase. Do not attempt to repair a hard safety violation through a revision prompt.

### 8.2 Critique/Revision Gate

The gate checks the complete ordered list against the original flags and this contract. At minimum it verifies:

- output count and `flag_id` order are exactly aligned with the flag list;
- every text refers to the right month/window, series, and rule type;
- the number/direction/threshold stated in the prose matches the supplied evidence and is not a changed metric;
- the text does not assert a cause, market-wide implication, forecast, statistical significance, or verified `PRICE_SQFT` result;
- AN-04 mentions the late-window concentration/sample-composition limitation and partial August where relevant;
- text is concise, understandable, and does not exceed the word/sentence cap;
- no output is missing, duplicated, or associated with the wrong flag.

Classify findings as:

- `hard_reject`: unsupported numeric fact, causal claim, invalid schema, rule/series/month mismatch, forbidden `PRICE_SQFT` assertion, or unsafe content. Use the template immediately for that flag; do not ask the model to negotiate the fact.
- `repairable_text`: clarity, completeness, length, or omission of a required caveat where the text contains no hard violation. These findings may enter the live-mode critique/revision loop.
- `pass`: all checks succeed.

Feedback contains issue codes, never a new numeric interpretation. Do not pass a vague prompt such as “make it better”; identify the repairable requirement and preserve the original evidence. If the deterministic template itself fails the gate, return `E_DIAGNOSTIC_INPUT` or propagate the programming defect as appropriate; do not invent a generic sentence.

## 9. Trace and metadata

Trace events use the parent trace schema and stable diagnostic event names. At minimum record:

- one diagnostic completion event with the number of input flags and output diagnostics;
- one warning per malformed/invalid model attempt, including attempt number and non-sensitive failure category;
- a fallback event for each diagnostic that uses template text after a live/replay failure or critique-cap exhaustion;
- model/cache mode, prompt version, critique-checklist version, seed, provider/model logical identifier, cache hit/miss, model-call attempts, revision-round count, and fallback source where applicable;
- exactly one `kind="loop"` event for every actual critique/revision round, using `loop="critique_revision"`, the attempt/cap, issue codes, affected flag IDs, and the outcome.

The shared `loop_counters.critique_revision` equals the number of `kind="loop"` events with `loop="critique_revision"` and cannot exceed `CRITIQUE_REVISION_CAP`. A model-call retry is a warning/attempt trace, not a loop event. Template fallback alone is not a revision unless a revision round actually occurred. Critique/revision events are separate from coverage-repair events.

Trace entries must not contain API keys, credentials, full raw listing content, or unbounded prompt dumps. Log `flag_id` and a safe error/issue code, not private request contents. `source="template"` is the public result indicator; detailed fallback reasons remain in trace metadata.

## 10. Failure behavior

| Situation | Required result |
|---|---|
| No anomaly flags | `diagnostics=[]`; zero model calls and zero critique/revision firings. |
| `LLM_MODE=off` | Template result for every flag; no model call; no revision loop if templates pass. |
| Valid replay entry | Accept only after hard validation and batch gate; no network call. |
| Replay miss/invalid entry | No live call; template for that flag and warning/fallback trace. |
| Live provider timeout/error | Shared bounded retries, then template for the affected flag; continue with remaining flags. |
| Invalid JSON/schema or hard evidence/safety violation | Bounded call retries only for malformed/provider failures; hard content violations immediately use template. Do not send hard violations through the critique loop. |
| Repairable live text issue | Enter at most `CRITIQUE_REVISION_CAP` revision rounds; stop early on pass, otherwise template unresolved entries at cap. |
| Unknown flag rule or malformed evidence | `E_DIAGNOSTIC_INPUT`; do not fabricate an explanation. |
| Unexpected programming exception | Propagate in development/tests; never disguise it as a valid fallback. |

The Diagnostic Writer must not change `anomaly_analysis.status`, global report `status`, metrics, coverage score, flags, or any numeric field. Optional explanation failures are recoverable when validated template input exists. If the input flag evidence is malformed, no safe template exists and the parent error path applies.

## 11. Required tests

1. **One-to-one mapping:** every flag has exactly one diagnostic; no diagnostic exists without a flag.
2. **Flag identity:** returned `flag_id` sequence exactly matches input order, including multiple AN-01 series for one month and window-level AN-04.
3. **No flags:** empty flags produce an empty list and zero client calls/revision events in all modes.
4. **Off mode:** templates are deterministic; no cache/provider call and no revision loop occur.
5. **Replay hit:** valid cached response is accepted and never uses the network.
6. **Replay miss:** template fallback is logged; no live request or revision loop occurs.
7. **Live valid output:** source is attached by code; a passing batch fires no critique loop.
8. **Malformed JSON/schema:** shared retries are bounded, then template; provider retries are not counted as critique-loop firings.
9. **Provider timeout/unavailable:** bounded attempts then per-flag template; other diagnostics still complete.
10. **Unknown rule/kind or malformed evidence:** `E_DIAGNOSTIC_INPUT`, not a generic explanation.
11. **Evidence use:** any text numbers correspond to supplied values/thresholds/evidence under the display formatter; no unsupported number is accepted.
12. **Direction accuracy:** positive and negative AN-01 changes have correct direction and correct lower/upper series.
13. **Count-drop/spike accuracy:** AN-02 describes lower observed row counts and AN-03 describes higher observed row counts, without a market-wide claim.
14. **Window concentration:** AN-04 mentions July/August concentration and the partial/scraped-snapshot caveat.
15. **Causal guard:** a model claim of cause, fraud, statistical significance, or a citywide market event is rejected and replaced with a template.
16. **`PRICE_SQFT` guard:** no diagnostic asserts INR/sq ft while that field remains unverified.
17. **Numeric immutability:** hashing the anomaly object before/after Writer execution gives identical results.
18. **Mode invariance:** modes may change diagnostic text/source and trace metadata, not flags, metrics, statuses, or order.
19. **Seed/replay trace:** seed, prompt/checklist version, cache status, retry count, revision count, and fallback source are recorded without secrets.
20. **Fallback isolation:** one flag's invalid response does not discard valid diagnostics for other flags.
21. **Template determinism:** same flag/template version yields identical text across row order, locale, and process runs.
22. **Critique happy path:** a repairable missing-caveat/clarity issue produces one revision event and then passes without touching evidence.
23. **Critique cap:** a fixture that remains repairable through all rounds produces exactly `CRITIQUE_REVISION_CAP` loop events, then templates unresolved items; no extra iteration occurs.
24. **Hard-reject separation:** an unsupported number or causal claim uses template immediately and does not consume a critique revision.
25. **Counter reconciliation:** `loop_counters.critique_revision` equals the revision-loop event count and is independent of model-call retry count and coverage-repair count.
26. **Unexpected defect:** a programming exception is not converted to an empty/valid diagnostic result.

## 12. Parent-contract changes and change control

`CONTRACT.md` defines the public `diagnostics` field as an ordered array of `{flag_id, text, source}` objects and registers `LLM_RETRY_CAP` and `CRITIQUE_REVISION_CAP` in shared configuration. `LLM.md` declares the same call retry cap, diagnostic schema, and fallback behavior. `Anomaly.md` preserves stable rule identifiers and typed evidence keys for templates. `Agents.md` owns the role/topology of the Critique/Revision Gate; this file owns the text-quality rules, allowed feedback, and per-flag fallback.

Any change to diagnostic schema, evidence allowlist, template wording rules, critique checks, retry behavior, or fallback policy requires a version update and regenerated tests. Diagnostic prose does not require changing the anomaly-rule version unless the numeric rule or flag schema changes.

*End of Diagnostic subcontract. Draft for `CONTRACT.md` v`1.0.0-draft`.*
