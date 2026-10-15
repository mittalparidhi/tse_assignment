# ANOMALY SUBCONTRACT — Hyderabad Housing-Trends Application

**Contract ID:** `TSE-HYD-MT-ANOM`  
**Version:** `1.0.0-draft`  
**Parent:** `CONTRACT.md` v`1.0.0-draft`  
**Reference pattern:** `c/Anomaly.md` from the supplied reference ZIP, adapted to Hyderabad's listing-entry snapshot and verified numeric fields.  
**Status:** Draft. The rules below are deterministic screening heuristics for the assignment, not statistically calibrated market indicators.

`CONTRACT.md` is authoritative for shared constants, public schemas, metric eligibility, the fixed window, error semantics, and the agent graph. `Data.md` controls source-field interpretation. `Aggregator.md` controls monthly counts and price-bound medians. If any rule conflicts, update the parent contract first; do not resolve a conflict locally.

## 1. Role and responsibility

**Kind:** deterministic worker.  
**LLM:** none. The Anomaly Detector must not call a language model, prompt service, embedding service, external API, or network resource.  
**Job:** calculate adjacent-month changes, detect configured changes in the observed snapshot, create a concise descriptive comparison between the beginning and end of the window, and return auditable anomaly evidence.

| Interface | Contract |
|---|---|
| **Inputs** | The exact 12 ordered monthly records from Aggregator; the row-level eligible coherent sale-price-range evidence used by Aggregator for pooled summaries; shared anomaly constants; rule/config version. |
| **Outputs** | An `anomaly_analysis` object conforming to `CONTRACT.md`; an ordered list of flags; per-month change values; pooled start/end descriptive summaries; one completion trace event. |
| **May change** | Only its newly constructed anomaly result and its own trace event. |
| **Must not change** | Monthly counts, medians, statuses, input rows, request criteria, coverage decisions, shared constants, snapshot, or data-quality flags owned by another agent. |

The component identifies unusual **values in the supplied scrape snapshot**. It does not determine whether a change occurred in the whole Hyderabad housing market. A flag is evidence that a configured numerical rule was met; it is not proof of fraud, a scraping failure, a market event, or a causal mechanism.

## 2. Required inputs and preconditions

### 2.1 Monthly records

The monthly input must contain exactly one record for each month in `EXPECTED_MONTHS`, in chronological order. Required fields are:

- `month`;
- `observed_listing_count`;
- `sale_listing_count`;
- `valid_price_range_count`;
- `median_min_price_inr`;
- `median_max_price_inr`;
- `coverage_status` and `metric_status`.

`median_price_per_sqft_inr` may be present in the record schema, but it must remain `null` while `PRICE_SQFT` units and semantics are unresolved. It must not be used for deltas, flags, pooled summaries, or evidence until `CONTRACT.md` and `Data.md` are revised with source-supported verification.

Counts must be nonnegative integers, with `valid_price_range_count <= sale_listing_count <= observed_listing_count`. Price-bound medians must be finite and positive when a valid price range exists and null when the Aggregator's status rules require null. An input that violates these invariants is inconsistent; do not treat the inconsistency as a domain anomaly.

### 2.2 Eligible rows for pooled summaries

For the start/end summary, receive an internal evidence view containing only rows in the same eligible coherent sale-price-range subset used by Aggregator. At minimum it contains `source_row_id`, `posting_month`, `MIN_PRICE`, and `MAX_PRICE`. It is an internal calculation input, not a new public dataset. Do not rebuild or relax the eligibility rule independently.

The view must retain row identity, contain no repeated `source_row_id`, and use the same snapshot, local month derivation, and fixed analysis window as the monthly records. It is acceptable for the view to be empty. If the view is not supplied, malformed, or cannot be tied to the same aggregation run, do not fabricate a summary or derive one from monthly medians; return a structured input error or a summary-unavailable reason according to the parent error policy.

### 2.3 Scope

The only allowed window is September 2022 through August 2023, inclusive. The first month has no predecessor and must never receive an adjacent-month change or a predecessor-based flag. August 2023 is a partial observed month. State this in summary caveats; do not extrapolate its counts to a full month.

## 3. Shared constants and rule semantics

Import all thresholds from `app/contract.py` or the one approved shared configuration module. Never retype literal thresholds in the implementation, prompt, or tests. The draft values in `CONTRACT.md` are:

| Constant | Draft value | Use |
|---|---:|---|
| `ANOMALY_MIN_BUCKET_N` | `5` | Minimum count of eligible coherent price ranges in both adjacent months before a price-bound change is assessed; for count ratios, the predecessor month must have at least this many observed rows. |
| `PRICE_BOUND_CHANGE_THRESHOLD` | `0.12` | A price-bound median change is flagged only when its absolute fractional change is strictly greater than 12%. |
| `OBSERVED_COUNT_DROP_RATIO` | `0.50` | A snapshot-count drop is flagged when the current observed count is less than or equal to 50% of the prior month's count. |
| `OBSERVED_COUNT_SPIKE_RATIO` | `2.00` | A snapshot-count spike is flagged when the current observed count is greater than or equal to twice the prior month's count. |
| `LATE_WINDOW_COUNT_SHARE_THRESHOLD` | `0.70` | A concentration flag is emitted when the final two months account for at least 70% of all observed records in the 12-month window. |
| `SUMMARY_FLAT_BAND_PCT` | `1.0` | Start/end price-bound summaries are `flat` when the computed percentage change lies inclusively between -1% and +1%. |
| `ANOMALY_RULES_VERSION` | `1.0.0-draft` | Version attached to every anomaly result. |

These values are transparent operational heuristics selected for reproducible testing. They are not learned from a representative housing population, are not calibrated p-values, and must not be described as statistically significant. If a threshold changes, update `CONTRACT.md`, this file, configuration, golden tests, and the version together.

## 4. Adjacent-month calculations

Return a `monthly_changes` entry for each of the 12 months, including the first month. All change values are finite numbers or `null`; no value may be NaN, infinity, a formatted currency string, or a rounded value substituted for the calculation.

### 4.1 Price-bound median change

For each month `t` after the first month, calculate independently for `median_min_price_inr` and `median_max_price_inr`:

`change_fraction[t] = current_month_median / previous_month_median - 1`

Calculate only when both the previous and current `valid_price_range_count >= ANOMALY_MIN_BUCKET_N`, and both corresponding medians are finite and strictly positive. Otherwise return `null` for that series at month `t`. The first month always has null changes.

The input price medians must come directly from Aggregator. Do not recompute a median from monthly medians, use a midpoint, convert INR again, or use `PRICE_SQFT`. Negative changes are valid values. `0.12` represents a 12% increase; `-0.12` represents a 12% decrease.

### 4.2 Observed listing-count ratio

For each month after the first, calculate:

`observed_count_ratio[t] = observed_listing_count[t] / observed_listing_count[t-1]`

Compute the ratio only when the predecessor's `observed_listing_count >= ANOMALY_MIN_BUCKET_N` and is greater than zero. If the predecessor does not meet the condition, use `null`. A current count of zero is valid and produces a zero ratio when the predecessor is eligible.

This ratio describes observed rows in the frozen snapshot. It is not a rate of all new listings in the city and must not be called a market-growth rate.

### 4.3 Window concentration

Calculate `late_window_count_share` as:

`(observed_listing_count[2023-07] + observed_listing_count[2023-08]) / sum(observed_listing_count over EXPECTED_MONTHS)`

If the denominator is zero, use `null` and emit no concentration flag. Otherwise retain the exact fraction and compare it to `LATE_WINDOW_COUNT_SHARE_THRESHOLD`. This is a window-level sample-composition warning. Because August is partial and the dataset is scrape-derived, it must not be interpreted as a market surge.

## 5. Flag rules

Only the following configured rules may emit flags in version `1.0.0-draft`. Thresholds use the shared constants above.

### AN-01 — Price-bound median jump

For each month after the first and for each of `median_min_price_inr` and `median_max_price_inr`, emit a `price_bound_jump` flag when the corresponding `change_fraction` is not null and `abs(change_fraction) > PRICE_BOUND_CHANGE_THRESHOLD`.

- **Comparison:** strict `>`; exactly +0.12 or -0.12 does not trigger.
- **Value:** signed fractional change, not percent units. For example, `0.25` means a 25% increase.
- **Series:** explicitly identify `median_min_price_inr` or `median_max_price_inr`.
- **Required evidence:** current/previous medians, current/previous valid-range counts, and computed change fraction.
- **Interpretation:** a large change in the observed price-bound median; not proof that the market price moved by that amount.

Emit a separate flag for each bound series that qualifies. Do not merge distinct series into a single flag that loses their evidence. Do not emit flags when either month fails the minimum bucket rule.

### AN-02 — Observed snapshot count drop

For month `t`, emit `observed_count_drop` when the ratio is defined and `observed_count_ratio[t] <= OBSERVED_COUNT_DROP_RATIO`.

- **Comparison:** inclusive `<=`; a ratio exactly 0.50 triggers.
- **Value:** current/prior observed row count ratio.
- **Required evidence:** previous and current observed counts, the ratio, and the threshold.
- **Interpretation:** an abrupt drop in records present in the frozen sample. The agent must not claim a true fall in housing supply or listing activity.

### AN-03 — Observed snapshot count spike

For month `t`, emit `observed_count_spike` when the ratio is defined and `observed_count_ratio[t] >= OBSERVED_COUNT_SPIKE_RATIO`.

- **Comparison:** inclusive `>=`; a ratio exactly 2.00 triggers.
- **Value:** current/prior observed row count ratio.
- **Required evidence:** previous and current observed counts, the ratio, and the threshold.
- **Interpretation:** a sharp increase in observed snapshot rows. Collection or sampling behavior is a possible explanation, but it must remain a hypothesis unless separate evidence confirms it.

A month cannot receive both a drop and spike flag under the configured thresholds. No flag is generated for the first month, undefined ratios, or a predecessor below the configured minimum.

### AN-04 — Late-window count concentration

Emit one window-level `late_window_count_concentration` flag when `late_window_count_share >= LATE_WINDOW_COUNT_SHARE_THRESHOLD`.

- **Scope:** `window`; `month` is `null`.
- **Value:** the fraction of observed in-window rows contributed by July and August 2023 combined.
- **Required evidence:** July count, August count, total in-window count, and exact share.
- **Interpretation:** the month distribution is highly concentrated in the final two observed months. This is a sample-coverage caution, not a market trend claim.

If the final two months have no observations or the total is zero, the share is null and this rule does not emit a flag. The agent must not reclassify an empty month as a market shutdown.

## 6. Start/end pooled summary

Provide a descriptive summary for each verified price-bound field, `median_min_price_inr` and `median_max_price_inr`. Do not produce a `price_per_sqft` summary while its semantics or units are unverified.

- **Start pool:** eligible coherent sale-price-range rows whose `posting_month` is one of the first three months: `2022-09`, `2022-10`, `2022-11`.
- **End pool:** eligible coherent sale-price-range rows whose `posting_month` is one of the last three months: `2023-06`, `2023-07`, `2023-08`.
- **Start/end values:** the median of the underlying row-level `MIN_PRICE` or `MAX_PRICE` values within each pool. Never calculate the summary as the average or median of monthly medians.
- **Minimum evidence:** both pools must contain at least `ANOMALY_MIN_BUCKET_N` eligible rows for that metric. Otherwise, that metric's `start`, `end`, and `change_pct` are `null`, and its summary status states `insufficient_rows`.
- **Change:** `change_pct = (end_median / start_median - 1) * 100`, provided both medians are finite and positive.
- **Direction:** `up` if `change_pct > SUMMARY_FLAT_BAND_PCT`; `down` if `change_pct < -SUMMARY_FLAT_BAND_PCT`; otherwise `flat`, including either exact boundary.
- **Denominators:** include `n_start` and `n_end`. These count eligible source rows, not distinct properties.

The final three-month pool includes partial August and the two months with the highest row volume. Label the comparison `descriptive_snapshot_comparison`; include a caveat that the sampling distribution and partial final month prevent a market-wide trend inference. A valid summary is not a forecast, confidence interval, causal estimate, or statistical significance result.

For reproducibility, the current frozen snapshot provides these regression baselines under the current timestamp and coherent-price-range rules:

| Summary metric | Start pool n | Start median (INR) | End pool n | End median (INR) | Change (%) |
|---|---:|---:|---:|---:|---:|
| `MIN_PRICE` | 111 | 6,000,000 | 6,462 | 9,433,486.5 | 57.224775 |
| `MAX_PRICE` | 111 | 6,000,000 | 6,462 | 9,613,800.5 | 60.2300083333 |

These are regression values, not production constants. Recompute them from the frozen snapshot; never hard-code them into the anomaly calculation.

## 7. Flag and result schema

The parent public schema must include `anomaly_analysis` as an object alongside the twelve monthly records and run metadata. The `anomaly_analysis` object contains:

- `status`: `ok`, `not_configured`, or `insufficient_data`;
- `rule_version`: `ANOMALY_RULES_VERSION`;
- `monthly_changes`: exactly twelve objects in canonical month order;
- `flags`: deterministically ordered list of zero or more flags;
- `summary`: start/end pooled comparisons and explicit availability/status for each bound metric;
- `caveats`: stable machine-readable caveat codes, including partial-August and snapshot-sample limitations.

Each `monthly_changes` object contains `month`, `median_min_price_change_fraction`, `median_max_price_change_fraction`, and `observed_count_ratio`. Nulls must be represented as JSON `null`.

Each flag must contain:

`flag_id`, `rule_id`, `scope`, `month`, `series`, `kind`, `value`, `threshold`, `comparison`, `reason_code`, `reason`, and `evidence`.

- `flag_id` is stable and deterministic for the same rule and scope, e.g. a slug made from rule ID, month/window key, and series; do not use a random UUID.
- `scope` is `month` or `window`.
- `month` is a valid `YYYY-MM` for monthly flags and `null` for window-level flags.
- `series` identifies the exact metric that triggered the rule.
- `value` and `threshold` are finite numeric values in the units documented for the rule.
- `comparison` is one of `>`, `>=`, `<=`; store the comparison actually used.
- `reason_code` is a stable code. `reason` is a deterministic template that explains the configured rule and does not invent a cause.
- `evidence` is structured numeric evidence with the prior/current values or numerator/denominator used by the rule.

Order flags first by earliest month (window-level flags use a defined `window` position), then by the shared rule order `AN-01`, `AN-02`, `AN-03`, `AN-04`, then by series key. The exact ordering must be implemented once and tested; input row order must not affect it.

## 8. Missingness, status, and failure behavior

- If all required thresholds are configured and valid and input schemas pass, set `status="ok"`, even if no flag is triggered. An empty flag list means rules ran and none triggered; it does not prove the data is clean. Set `status="insufficient_data"` if the monthly schema is valid but every month has `observed_listing_count == 0`, so no count or price rule can yield a meaningful observation.
- If anomaly constants are unavailable, invalid, or differ from the registered version, do not silently apply local defaults. Return `status="not_configured"` only if the parent explicitly permits a no-rules result; otherwise return the registered configuration error.
- If one or more price changes cannot be calculated because of low counts/null medians, keep those values null and record the relevant reason/status in the monthly-change object. The count ratio or window share may still be evaluated independently.
- If required monthly records are missing, duplicated, out of order, or fail count/median invariants, return a structured parent-defined input error. Do not emit plausible flags from inconsistent inputs.
- Unexpected programming errors must propagate in tests/development; do not catch them and return an empty flag list.
- If a flag evidence value is non-finite or cannot be reconciled with its input metrics, fail validation rather than serializing NaN/Infinity.
- A flag threshold is not an exclusion rule. Anomaly detection cannot remove rows, relabel prices as invalid, or alter the coverage score.

## 9. Purity, determinism, and forbidden actions

The Anomaly Detector must:

1. Be a pure function of the monthly records, eligible row evidence, and versioned shared constants.
2. Produce the same result regardless of DataFrame row order, input mapping order, locale, current date/time, process ID, or LLM mode.
3. Preserve full numeric precision in machine-readable fields; presentation text must not be used as the numeric source.
4. Use only the twelve contracted months; it must not inspect records outside the window.
5. Keep `PRICE_SQFT` out of analysis until its semantics and units are verified.
6. Leave all inputs unchanged and never access raw files, network resources, or the system clock.
7. Use deterministic reason templates and rule IDs; no LLM-generated anomaly reason is permitted in this component.
8. Expose enough evidence for an independent test oracle to recompute each flag.

It must not infer that a spike or drop was caused by scraping changes, deduplicate repeated `PROP_ID`, classify individual listings as fraudulent, use a z-score or learned detector not approved in the parent contract, forecast prices, create missing rows, interpolate medians, use price-per-square-foot values as if verified, or claim statistical significance from rule thresholds.

## 10. Frozen-snapshot regression expectations

Using the supplied file with SHA-256 `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`, canonical `Asia/Kolkata` months, the fixed 12-month window, `PREFERENCE == "S"`, and valid coherent INR price bounds:

- In-window observed records: `9,162`.
- In-window sale records: `7,633`.
- In-window valid coherent price ranges: `7,555`.
- The last two months have `3,447 + 3,531 = 6,978` observed rows, or approximately `0.7616241` of the in-window total.
- Under the draft `0.70` concentration threshold, AN-04 must trigger once.
- Under the draft `2.00` spike-ratio threshold, AN-03 is expected in March 2023 (217 / 45 ≈ `4.8222222`) and July 2023 (3,447 / 947 ≈ `3.6399155`).
- Under the draft `0.50` drop-ratio threshold, no observed-count drop is expected in the current monthly baseline.
- Under the draft `0.12` absolute median-change threshold, AN-01 is expected for both bounds in October 2022, November 2022, December 2022, January 2023, February 2023, March 2023, and April 2023. No price-bound jump is expected in May–August 2023 under the listed baseline values. The baseline therefore produces 14 price-bound jump flags, 2 count-spike flags, no count-drop flags, and 1 concentration flag (17 flags total).

These expected flags are software regression expectations, not judgments that the source represents true market behavior. If a result differs, first check the snapshot hash, timezone conversion, month grid, Aggregator output, and shared constants; do not update the expected output merely to make a test pass.

## 11. Required tests

1. **Schema:** exactly twelve ordered month-change objects; all required keys and status values present.
2. **First month:** all adjacent change fields null; no predecessor-based flag.
3. **Price-change direction:** positive, negative, and zero changes are calculated correctly for both price-bound medians.
4. **Price threshold boundary:** exactly +0.12 and -0.12 do not flag; values strictly outside either boundary flag.
5. **Price denominator eligibility:** a missing median, non-finite median, nonpositive median, or either adjacent valid-range count below five yields null and no price-jump flag.
6. **Count-drop boundaries:** exactly 0.50 flags; a value above 0.50 does not.
7. **Count-spike boundaries:** exactly 2.00 flags; a value below 2.00 does not.
8. **Predecessor floor:** if previous observed count is below five or zero, current/prior ratio is null and no count-spike/drop flag is emitted.
9. **Count ratio semantics:** current count zero is allowed when the predecessor is eligible and results in ratio zero/drop flag.
10. **Concentration boundary:** exactly 0.70 flags; a value below 0.70 does not; zero total produces null/no flag.
11. **Summary pooling:** summary medians match a hand-calculated median of eligible row-level values; a fixture with different monthly sample sizes verifies the implementation does not median or average the monthly medians.
12. **Summary missingness:** when either start or end pool has fewer than five eligible rows, its summary metric is null with `insufficient_rows` status.
13. **`PRICE_SQFT` protection:** no change, flag, or summary is produced from that column while it remains unverified.
14. **Regression baseline:** the real snapshot has the counts, pooled summaries, concentration flag, spike flags, and price-bound jump months listed in §10.
15. **Row-order invariance:** shuffle eligible rows and monthly input mappings; values and ordered flags remain identical.
16. **Input immutability:** no monthly input field or row evidence is mutated.
17. **No model dependency:** mocked LLM client receives zero calls; `off`, `replay`, and `live` modes cannot change anomaly values.
18. **Failure behavior:** bad schemas, impossible month values, invalid thresholds, and inconsistent evidence produce the agreed error behavior, not a successful empty flag result.
19. **Serialization:** no NaN/Infinity; every numeric value and threshold can be parsed as finite JSON numeric data; flags have deterministic IDs/order.
20. **Evidence reconciliation:** independently recompute every flag's ratio/change/share from evidence and verify that it meets the recorded comparison exactly.
21. **Window limits:** adding a row outside the fixed window cannot change monthly flags, summary pools, or concentration denominator after the Scanner's fixed-window eligibility is applied.
22. **No causal overclaim:** deterministic reason templates include no claim that an observed count or median change was caused by a specific event.

## 12. Parent-contract changes and change control

Before implementation is frozen, keep `CONTRACT.md` consistent with this subcontract by registering the constants in §3, defining the `anomaly_analysis` public object and flag schema in §7, and identifying the version in report metadata. `Aggregator.md` must expose the exact row-level eligible price-range evidence used for the pooled summary without making that private evidence an extra public dataset. `Agents.md` and `Testing.md` must use the same rule IDs and boundaries.

Any change to rule IDs, thresholds, eligibility, start/end pools, flag schema, reason codes, or comparison boundaries requires an `ANOMALY_RULES_VERSION` change, updates to the global contract and shared configuration, and regenerated golden/MR tests. Keep raw data and long traces outside this contract. This file must remain below the individual 8,000-token contract limit; do not expand it merely to fill the budget.

*End of Anomaly subcontract. Draft for `CONTRACT.md` v`1.0.0-draft`.*
