# AGGREGATOR SUBCONTRACT — Hyderabad Housing-Trends Application

**Contract ID:** `TSE-HYD-MT-AGG`  
**Version:** `1.0.0-draft`  
**Parent:** `CONTRACT.md` v`1.0.0-draft`  
**Reference pattern:** `c/Aggregator.md` from the supplied 12-file reference ZIP, adapted to the Hyderabad snapshot.  
**Status:** Draft for implementation and review.

The global `CONTRACT.md` controls shared constants, the public monthly schema, eligibility definitions, statuses, and failure semantics. `Data.md` controls source-preservation and field interpretation. This file specifies how the Aggregator applies those rules. If a conflict is found, do not silently choose a new rule: record the conflict and update the parent contract first.

## 1. Role and responsibility

**Kind:** deterministic worker.  
**LLM:** none; no prompt, model call, embedding call, network request, or probabilistic calculation is permitted.  
**Job:** validate the row-level inputs needed for aggregation, calculate monthly counts and eligible price-bound medians, emit the dense twelve-month output grid, and preserve the distinctions between a zero count and a metric that cannot be calculated.

| Interface | Contract |
|---|---|
| **Inputs** | Processed snapshot rows from the Scanner/Data Worker; the shared expected-month list; shared eligibility constants; metric-verification state for `PRICE_SQFT`; relevant run metadata. |
| **Outputs** | Exactly 12 monthly records using the parent schema, plus aggregation evidence needed by the orchestrator/trace. A domain input failure returns the parent-defined structured error. |
| **May change** | Its newly constructed output records and its own trace event only. |
| **Must not change** | Raw or processed input rows, source columns, request criteria, shared constants, eligibility policy, coverage decision, anomaly flags, diagnostics, or report metadata owned by other agents. |

The Aggregator computes descriptive statistics from the frozen sample. It does not decide whether the sample represents the full Hyderabad housing market, infer completed transactions, estimate missing listings, forecast prices, or assert that month-to-month changes are market-wide changes.

## 2. Required inputs and preconditions

The caller must supply the processed rows and derived date fields produced by the versioned cleaning pipeline. The Aggregator must not reinterpret source semantics or independently replace the canonical timestamp pipeline.

### 2.1 Required fields

At minimum, the row table must provide:

- `source_row_id`: stable, unique identity for the original source-row position. It is for traceability and detection of duplicated delivery, not property-level deduplication.
- `posting_month`: canonical `YYYY-MM` derived from `POSTING_DATE` after conversion from Unix milliseconds to `Asia/Kolkata`; missing or invalid dates remain null/invalid.
- `PREFERENCE`: source value used for the sale subset. Only the exact value `S` is treated as sale for sale-price metrics.
- `MIN_PRICE` and `MAX_PRICE`: numeric price-bound candidates, in INR subject to the source qualification in `Data.md`.
- `PRICE_SQFT`: unverified source-provided field, preserved for quality counts only until its semantics and unit are approved.

Other original source columns may be present. The Aggregator ignores columns that are irrelevant to these calculations. It must not mutate the incoming table or rely on the order of its rows.

If a required column is absent, return `E_SCHEMA` (or the exact globally registered equivalent) with the missing column names. If `source_row_id` repeats in the same merged input, return a structured duplicate-delivery error; do not silently deduplicate. If a `posting_month` value is malformed, treat that row as not month-eligible and expose the issue to data-quality/orchestrator metadata rather than assigning it to an invented month. Whether malformed derived month values are a recoverable data-quality issue or a hard schema error must follow the shared schema policy; this draft's default is: null/invalid month is excluded from month records, while an impossible non-null value such as `2023-13` raises `E_INVALID_MONTH`.

### 2.2 Frozen scope and analysis window

The output window is fixed to the ordered list from `2022-09` through `2023-08`, inclusive. Import `EXPECTED_MONTHS`, `WINDOW_START`, `WINDOW_END`, `LOCAL_TIMEZONE`, and sentinel constants from shared configuration; do not redeclare them in this agent.

The default row population includes the frozen source's supported scope, which contains both `CITY == "Hyderabad"` and `CITY == "Secunderabad"`. The Aggregator must not silently filter either label. If a future, explicitly approved request schema adds a population filter, the Scanner applies it and the Aggregator aggregates only those returned rows; the Aggregator must not invent filters of its own.

Only rows whose canonical `posting_month` is one of the 12 expected months contribute to monthly records. Missing/invalid dates and valid dates outside the window remain in the source/processed artifact and data-quality audit, but do not contribute to any of the twelve monthly counts or medians. The Aggregator must not infer a missing month from `REGISTER_DATE`, `UPDATE_DATE`, a display string, or any other field.

## 3. Population and denominator rules

All metrics must be calculated from explicit, documented row subsets. These subsets are not interchangeable.

### A-01 — Observed listing-entry count

For month `m`, `observed_listing_count` is the number of input rows with a valid canonical `posting_month == m` after the Scanner has applied only authorized population/request scope.

- Count source rows; do not count distinct `PROP_ID`, `SPID`, description, or address.
- Do not automatically deduplicate repeated property identifiers. The two source rows with `PROP_ID = Z70135726` remain separate records under the current evidence-based policy.
- A row with an invalid price still contributes to `observed_listing_count` if its month is valid.
- A row with `PREFERENCE` equal to `R`, `P`, missing, or another value still contributes to observed count; those values are simply not sale rows.
- Rows without a valid month or outside the fixed window do not contribute to this monthly value.

### A-02 — Sale listing count

For month `m`, `sale_listing_count` is the number of observed rows in month `m` for which `PREFERENCE` is exactly the string `S` after safe normalization approved by the cleaning contract. In the current frozen data, `PREFERENCE == "S"` is the documented sale-price scope.

Do not infer that `TRANSACT_TYPE` codes mean sale/rent, and do not replace the `PREFERENCE` rule with an unverified field. Do not count `R` or `P` as sale rows. Do not require a valid price for a row to count as a sale listing.

### A-03 — Valid coherent price-range count

A sale row is eligible for price-bound aggregation only when **both** `MIN_PRICE` and `MAX_PRICE` are valid and the range is coherent. The eligible count for month `m` is `valid_price_range_count`.

A bound is valid only when all are true:

1. It can be interpreted as a numeric scalar under the shared parsing rule; booleans are not numeric prices.
2. It is finite (`NaN`, positive infinity, and negative infinity are invalid).
3. It is strictly greater than zero.
4. It is not the sentinel `2147483647`.

A row's coherent range must additionally satisfy `MIN_PRICE <= MAX_PRICE`. Both bounds must pass independently. A range with one missing bound, one sentinel, a zero, a negative value, a nonnumeric value, or an inverted order is ineligible for both price-bound medians.

Do not parse the display `PRICE` text and convert numeric bound columns a second time. Do not infer a missing bound from the other bound. Keep invalid rows in observed/sale counts and audit their eligibility reason outside the median subset.

### A-04 — Price-per-square-foot quality count

`PRICE_SQFT` semantics and units are not yet verified. Until that source check is complete, the Aggregator must not emit a `median_price_per_sqft_inr` from this field or label any such number INR/sq ft.

If the parent-schema field `valid_price_sqft_count` is emitted while the metric remains unverified, treat it only as a **quality count**, not as proof of metric validity. For this draft, the quality count is the number of sale rows in the month with a finite, strictly positive numeric `PRICE_SQFT` value. It excludes missing, nonnumeric, non-finite, zero, and negative values; it does not exclude a value solely because it is at or above the provisional `PRICE_SQFT_REVIEW_THRESHOLD = 100000`.

A value at or above that threshold may have a separate review flag in data-quality output, but the Aggregator must not turn the review threshold into an exclusion rule. Because units are unresolved, the count must be described as a raw quality statistic. The count must not affect coverage score, sale counts, valid price-range counts, or price-bound medians.

## 4. Aggregation algorithm

The implementation must be a pure deterministic calculation given the same input rows, shared contract/configuration, and metric-verification state.

For each `month` in `EXPECTED_MONTHS`, in order:

1. Select rows whose canonical `posting_month` equals that month.
2. Compute `observed_listing_count` from all selected rows.
3. Compute `sale_listing_count` from selected rows with `PREFERENCE == "S"`.
4. From those sale rows, construct the eligible coherent price-range subset using A-03.
5. Compute `valid_price_range_count` as the number of rows in that subset.
6. Compute `median_min_price_inr` as the sample median of `MIN_PRICE` from that **same coherent subset**.
7. Compute `median_max_price_inr` as the sample median of `MAX_PRICE` from that **same coherent subset**.
8. Compute the `PRICE_SQFT` quality count under A-04. Until semantics are verified, set `median_price_per_sqft_inr = null` and preserve the unverified status.
9. Assign `coverage_status` and `metric_status` under §5.
10. Emit one record even if the month has no eligible rows; do not omit sparse or empty months.

The `ALL` population, if used internally by the application, must pool rows before computing medians. It must not average or take the median of monthly medians, and it must not reconstruct a pooled median from locality/month medians. This contract's public schema is one record per month; no extra locality/property dimension may be added unless the parent schema is revised.

### 4.1 Median semantics

Use deterministic numeric operations such as `numpy.median` over the eligible values, with the library/runtime version recorded for reproducibility. Sorting values before calculating the median is permitted and is recommended for transparent oracle checks.

- Odd number of eligible values: use the middle sorted value.
- Even number of eligible values: use the arithmetic mean of the two middle sorted values, matching the standard NumPy/pandas median definition.
- One eligible range: both medians equal that row's lower and upper bound respectively.
- Zero eligible ranges: both bound medians are `null`.
- Preserve the full internal numeric result. Do not round medians for aggregation or store formatted values such as `"₹1.02 Cr"` in machine-readable numeric fields.
- No midpoint of each listing's price band is calculated by this contract. The two bound medians are separate statistics over the lower bounds and upper bounds of the same eligible rows.

For example, when the eligible lower-bound values are `[10, 20, 30, 40]`, the lower-bound median is `25`; the Aggregator must not select `20` or `30` alone, and must not average lower- and upper-bound medians together. This is a unit-test illustration only, not an addition to the source dataset.

### 4.2 Deterministic ordering and purity

Output order is exactly `EXPECTED_MONTHS` order, ascending from `2022-09` to `2023-08`. Results must not depend on input row order, DataFrame index labels, parallel shard completion order, dictionary iteration order, or LLM availability.

The Aggregator must not use random sampling, the system clock, web access, live model calls, or mutable global state. It must not modify shared DataFrames in place. Any temporary numeric coercion or eligibility mask is local to the calculation. The same input must produce equivalent record values, statuses, and order on every run under the same pinned runtime/dependencies.

## 5. Null and status semantics

A count of zero and a null metric have different meanings. Zero is used only for a measured count with no qualifying rows. A metric is `null` when it cannot be calculated from its eligible subset.

### 5.1 `coverage_status`

| Condition | Value |
|---|---|
| No valid observed rows for the month | `no_listings` |
| One or more observed rows, month is `2023-08` | `partial_month` |
| One or more observed rows in any other expected month | `observed` |

The fixed Hyderabad snapshot has observations in August 2023, and its latest posting is August 26, 2023; therefore that record is `partial_month`, not a complete-month measurement. The parent contract should retain this partial-month caveat. If a future test fixture has zero August rows, the global contract's statements “August must be `partial_month`” and “zero observed rows means `no_listings`” require an explicit precedence decision; do not conceal that edge-case conflict.

### 5.2 `metric_status`

Apply the following first-matching precedence for the current parent schema:

| Condition | Value | Bound medians |
|---|---|---|
| `observed_listing_count == 0` | `no_listings` | Both `null` |
| Observed rows exist but `sale_listing_count == 0` | `no_sale_listings` | Both `null` |
| Sale rows exist but `valid_price_range_count == 0` | `no_valid_prices` | Both `null` |
| At least one valid price range exists but `PRICE_SQFT` remains unverified | `unverified_metric` | Compute and retain both valid price-bound medians; `median_price_per_sqft_inr` stays `null` |
| Valid price ranges exist and any metric designated required by the parent is verified | `ok` | Compute the eligible parent-defined metrics |

The `metric_status` is a coarse record-level field in the current public schema. Therefore `metric_status = "unverified_metric"` refers to the unresolved price-per-square-foot field; it **does not invalidate or erase** the independently valid `median_min_price_inr` and `median_max_price_inr`. If per-metric statuses are added later, that is a parent-schema change.

Keep `coverage_status` and `metric_status` separate. Do not convert nulls to zeros, forward-fill, interpolate, use a neighbouring month, create a fake row, or use a language model to repair missing numerical values.

## 6. Required output schema and invariants

Emit exactly the monthly record fields specified in `CONTRACT.md` §4.2; do not add new public fields without a parent-contract revision. At minimum, every record contains:

`month`, `observed_listing_count`, `sale_listing_count`, `valid_price_range_count`, `median_min_price_inr`, `median_max_price_inr`, `valid_price_sqft_count`, `median_price_per_sqft_inr`, `coverage_status`, `metric_status`.

Every successful aggregation must satisfy all of the following:

1. There are exactly 12 records and the month keys equal `EXPECTED_MONTHS` in order, each appearing exactly once.
2. All count fields are nonnegative integers; booleans are not accepted as integers.
3. `0 <= valid_price_range_count <= sale_listing_count <= observed_listing_count` for every month.
4. Where count is zero under the status rules, affected medians are `null`; no empty median is encoded as `0`, `NaN`, infinity, or a string.
5. When `valid_price_range_count > 0`, both price-bound medians are finite numeric values and satisfy `median_min_price_inr <= median_max_price_inr`.
6. `median_price_per_sqft_inr` is `null` while `PRICE_SQFT` semantics/units are unverified, regardless of how many finite positive source values exist.
7. `valid_price_sqft_count` is a quality statistic while unverified and must not be treated as eligibility evidence for any price-bound metric or the coverage validator.
8. Status labels belong to the enumerations in the parent contract and follow §5. The parent/reporting layer must not rewrite statuses to make coverage appear complete.
9. A numeric output contains a finite machine-readable number or `null`; no formatted currency strings, Python `NaN`, `Infinity`, or JSON non-standard numeric values.
10. Input records and raw/processed files are unchanged after aggregation.

If any output invariant fails because of an unexpected programming defect, propagate the exception in tests/development rather than converting it into a plausible successful report. Expected malformed input is handled using the shared structured error contract.

## 7. Snapshot baseline for regression checks

The following are **regression oracles computed from the supplied frozen `hyderabad.csv`** using the current canonical timestamp and price-bound rules. They are not constants to hard-code into production logic. The test suite should recompute these values from the pinned snapshot and compare them with this table; a mismatch requires checking the source hash, timezone conversion, cleaning version, and eligibility rules before changing the baseline.

| Month | Observed rows | Sale rows | Valid coherent price ranges | Median minimum price (INR) | Median maximum price (INR) |
|---|---:|---:|---:|---:|---:|
| 2022-09 | 35 | 33 | 33 | 5,800,000 | 5,800,000 |
| 2022-10 | 51 | 43 | 43 | 7,700,000 | 7,700,000 |
| 2022-11 | 41 | 35 | 35 | 4,999,500 | 4,999,500 |
| 2022-12 | 46 | 42 | 42 | 6,351,485 | 6,351,485 |
| 2023-01 | 32 | 30 | 30 | 13,500,000 | 13,500,000 |
| 2023-02 | 45 | 38 | 38 | 9,150,000 | 9,150,000 |
| 2023-03 | 217 | 169 | 169 | 6,500,000 | 6,600,000 |
| 2023-04 | 288 | 270 | 270 | 10,235,001.5 | 10,564,500 |
| 2023-05 | 482 | 437 | 433 | 10,600,000 | 10,944,000 |
| 2023-06 | 947 | 817 | 801 | 10,000,000 | 10,623,200 |
| 2023-07 | 3,447 | 2,808 | 2,776 | 9,255,500 | 9,400,000 |
| 2023-08 | 3,531 | 2,911 | 2,885 | 9,452,000 | 9,800,000 |
| **Window total** | **9,162** | **7,633** | **7,555** | — | — |

These are sample-derived values, not market-wide estimates. The concentration of records in July/August may reflect source collection behavior; the Aggregator must not add causal language or interpret medians as completed-transaction prices. August is partial. The 78 sale rows in the window that do not satisfy coherent bound eligibility remain counted as sale listings but are excluded from price-bound medians.

## 8. Trace and observability

The Aggregator emits a completion step through the shared trace schema. It should record, at minimum, the fixed window, number of input rows considered, number of rows eligible for the window, excluded invalid/out-of-window row counts if supplied or safely computed, count of months emitted, aggregation logic version, and result status. Use only shared trace field names once ratified in `CONTRACT.md`; do not create an agent-specific incompatible trace shape.

Trace data must not contain every listing row, full listing descriptions, credentials, or unnecessary raw strings. The monthly output itself remains the authoritative numeric record; the trace explains execution and diagnostics, not an alternative set of metrics.

The Aggregator does not compute `coverage_score`, select retries, widen filters, decide pass/partial/fail, or increment a coverage-repair counter. Those responsibilities belong to the Coverage Validator/orchestrator. It must return the same aggregation result whether loops are enabled or disabled.

## 9. Error behavior and forbidden actions

| Condition | Required behavior |
|---|---|
| Missing required column | Structured `E_SCHEMA` or globally registered equivalent; name missing fields. |
| Impossible non-null `posting_month` such as `2023-13` | Structured invalid-month error; do not coerce to a neighbouring month. |
| Repeated `source_row_id` in merged input | Structured duplicate-delivery error; do not drop one copy silently. |
| Repeated `PROP_ID` with distinct `source_row_id` | Preserve both rows and count both under current policy. |
| Sale row has invalid price bounds | Retain in observed/sale count; exclude from valid coherent subset. |
| No valid price ranges for a month | Emit the month with count `0` and null medians, using §5 status rules. |
| `PRICE_SQFT` threshold breach or unresolved units | Flag/describe quality state; do not silently exclude or report verified INR/sq ft. |
| Unexpected programming exception | Propagate in development/tests; do not disguise as success. |

**The Aggregator must not:** call an LLM; access the network or system clock; modify any input data; remove rows because of `PROP_ID`; convert price strings a second time; infer `TRANSACT_TYPE` meanings; invent a zero or median for an empty subset; use unverified `PRICE_SQFT` as a verified metric; round values before calculations; calculate the coverage score; choose anomaly thresholds; write explanations that assert causal market events; or silently change the month window or sale definition.

## 10. Required tests

The Aggregator contract is not complete until these tests exist and run as part of the reproducible suite:

1. **Dense grid:** a successful result always contains all 12 exact month keys in canonical order, even when an internal test fixture has no rows in a month.
2. **Canonical snapshot counts:** the observed, sale, valid-range, and median oracle table in §7 matches recomputation from the raw-hash-pinned snapshot.
3. **Timezone boundary:** timestamps around a UTC/local month boundary are assigned according to `Asia/Kolkata`, not a naive UTC month.
4. **Independent denominators:** invalid price rows remain in observed/sale counts but not `valid_price_range_count`; rent/other preference rows remain observed but not sale.
5. **Sale selector:** only exact `PREFERENCE == "S"` rows contribute to sale-price metrics; `TRANSACT_TYPE` does not override this selector.
6. **Price validity boundaries:** accept finite positive lower/upper values not equal to the sentinel when `MIN_PRICE <= MAX_PRICE`; reject zero, negative, null, nonnumeric, NaN, infinity, sentinel, and inverted ranges.
7. **Coherent-subset rule:** both medians use the identical valid-range row subset; do not use separate lower/upper denominators or calculate per-row range midpoints.
8. **Median semantics:** test one value, odd count, even count, repeated values, and a half-unit midpoint (for example, median of `[10, 20, 30, 40]` is `25`).
9. **Row-order invariance:** shuffling input rows or changing DataFrame index labels does not change metrics/statuses/order.
10. **Missingness:** no listings, no sale rows, and no coherent price ranges produce the parent-defined count, null, and status values; no forward fill/interpolation is permitted.
11. **Unverified `PRICE_SQFT`:** its median remains null; its positive-finite quality count does not change the price-bound coverage score or eligibility.
12. **Review-threshold safety:** values exactly at and above `100000` may be flagged for review but are not excluded only because of the threshold.
13. **No implicit deduplication:** distinct source row IDs that share `PROP_ID` both contribute; duplicated source-row delivery produces an explicit error.
14. **Input immutability:** input values, input row count, and raw source hash do not change during aggregation.
15. **No model dependency:** tests confirm no LLM client is invoked and results are the same with model mode `off`, `replay`, or `live` because this worker does not consult LLM mode.
16. **Counts and finite values:** all count inequalities, null rules, finite-number requirements, and status enumerations in §6 are property-tested.
17. **Window limits:** rows with invalid month or months before September 2022/after August 2023 cannot appear in the dense grid or affect its monthly metrics; their data-quality accounting remains upstream/auditable.
18. **No per-month minimum invented:** one valid coherent price range is enough to calculate a numeric median; the Aggregator must not add a minimum sample threshold unless the parent contract is revised.
19. **Trace:** one aggregation completion event is emitted for a successful run; the trace has no row-level payload leakage and is consistent with the returned record count.

Small hand-calculated unit-test fixtures are permitted for testing formulas and failure cases; they are test fixtures only and must never be appended to, or reported as observations in, `hyderabad.csv`.

## 11. Parent decisions and change control

The following items require a parent-contract decision before this subcontract is frozen:

1. **Global status precedence:** `CONTRACT.md` defines `unverified_metric` for unresolved `PRICE_SQFT`, while also allowing valid price-bound medians. This subcontract clarifies that the bound medians remain present, but the parent should confirm the record-level status policy or adopt per-metric statuses in a versioned schema change.
2. **Empty August edge case:** the frozen snapshot contains August records, so `partial_month` is unambiguous for this data. The parent should decide precedence if a future fixture has zero August rows (`no_listings` versus `partial_month`).
3. **Error registry:** register the exact invalid-month and duplicate-source-row-delivery error codes centrally rather than leaving local aliases.
4. **Price-per-square-foot semantics:** keep the metric null/unverified until source evidence and area units are verified; a threshold alone is not verification.

Changes to the fixed window, schema, source population, `PREFERENCE` sale rule, sentinel rule, denominator definitions, rounding, or status precedence require a versioned parent-contract change and corresponding golden/MR updates. The raw dataset must remain unchanged.

*End of Aggregator subcontract. Draft for `CONTRACT.md` v`1.0.0-draft`.*
