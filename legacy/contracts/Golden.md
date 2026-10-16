# GOLDEN VECTORS AND REGRESSION ORACLES — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

**Parent:** `CONTRACT.md` v1.0.0-draft.  
**Purpose:** Define frozen expected outputs that test the Aggregator, Anomaly Detector, and Reporter against the real Hyderabad snapshot.  
**Reference pattern:** `c/Golden.md` from the supplied reference ZIP, adapted to `hyderabad.csv`.  
**Status:** Draft oracle; the source hash and numeric vectors below have been independently recomputed from the supplied CSV, but remain subject to final contract approval.

`CONTRACT.md` owns public schemas and shared constants. `Data.md` owns source parsing and eligibility; `Aggregator.md` owns monthly metrics; `Anomaly.md` owns anomaly rules; `Diagnostic.md` owns explanatory text. This file records expected outputs for regression testing and does not redefine those rules. If a vector disagrees with a parent rule, investigate the implementation or correct the parent through versioned change control; do not silently change the expected value to make a failing test pass.

## 1. Golden-test policy

Golden outputs are regression oracles, not production lookup tables. The implementation must recompute all metrics from the frozen CSV at runtime. It must never substitute these expected numbers for calculations or return them just because the source hash matches.

A golden test answers: *Given this exact snapshot, contract version, eligibility policy, timezone, analysis window, and deterministic configuration, does the application produce the expected structure and results?* It does not answer whether the dataset represents the full Hyderabad housing market or whether an observed pattern has a causal explanation.

### 1.1 Frozen input identity

| Property | Expected value |
|---|---|
| Input file in the working repo | `data/raw/hyderabad.csv` |
| Input filename provided for this audit | `hyderabad.csv` |
| Shape | 9,487 rows × 55 columns |
| SHA-256 | `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` |
| Timestamp field | `POSTING_DATE` |
| Timestamp unit | Unix milliseconds |
| Timezone applied before month extraction | `Asia/Kolkata` |
| Fixed analysis window | `2022-09` through `2023-08`, inclusive |
| Latest posting timestamp | `2023-08-26 10:29:05+05:30` |
| August treatment | Partial observed month; never extrapolate to a full month |

The raw file hash is computed on file bytes. If it differs, fail the frozen-snapshot regression with `snapshot_integrity_error`. A reviewed dataset replacement requires a new snapshot identifier/hash and versioned regeneration of every related golden and metamorphic test. Never change the raw CSV to match this file.

### 1.2 Eligibility assumptions for these vectors

The vectors below use the parent contracts' current draft rules:

1. Parse `POSTING_DATE` as a numeric Unix-millisecond timestamp, convert the instant to `Asia/Kolkata`, and only then derive `YYYY-MM`.
2. Include only valid posting dates in the fixed twelve-month window for monthly aggregates. Rows outside the window or with invalid dates remain in the source/audit but do not enter monthly counts.
3. `observed_listing_count` counts dated source rows in the month. It is not a count of distinct `PROP_ID` values or all market listings.
4. A sale listing has `PREFERENCE == "S"` after the documented string normalization.
5. A valid coherent price range belongs to a sale listing and has finite, positive, non-sentinel `MIN_PRICE` and `MAX_PRICE` values, with `MIN_PRICE <= MAX_PRICE`. Sentinel is `2147483647`.
6. Price-bound medians are computed over the valid coherent sale-price-range subset. Values are in INR; do not convert numeric prices from lakh/crore a second time.
7. Do not use `PRICE_SQFT` for a monetary median, trend, anomaly, or pooled summary while its semantics/units remain unverified. The public `median_price_per_sqft_inr` therefore remains `null` with `metric_status`/metric detail indicating `unverified_metric` as defined by the parent schema.
8. Do not deduplicate by `PROP_ID` alone. The two rows with `PROP_ID = Z70135726` remain preserved unless a separately approved, evidence-based policy changes.

Golden comparisons must use these eligibility rules, not whichever rules happen to be in the current cleaning script. If implementation and contract are inconsistent, fix the implementation or raise a formal contract change.

## 2. Golden vector A — canonical 12-month result

**Fixture ID:** `G-HYD-MONTHLY-001`  
**Input:** The complete hash-pinned `hyderabad.csv`; default request; no additional locality/property filters; deterministic calculations; `LLM_MODE=off`.  
**Expected result:** One successful report with exactly twelve ordered monthly records and the aggregate totals in §2.2.

### 2.1 Monthly records

All counts compare by exact integer equality. The price medians compare with the numeric tolerances in §5. These are regression expectations, not values to hard-code into application logic.

| month | observed_listing_count | sale_listing_count | valid_price_range_count | median_min_price_inr | median_max_price_inr | coverage_status | `metric_status` (current parent semantics) |
|---|---:|---:|---:|---:|---:|---|---|
| 2022-09 | 35 | 33 | 33 | 5,800,000.0 | 5,800,000.0 | observed | unverified_metric |
| 2022-10 | 51 | 43 | 43 | 7,700,000.0 | 7,700,000.0 | observed | unverified_metric |
| 2022-11 | 41 | 35 | 35 | 4,999,500.0 | 4,999,500.0 | observed | unverified_metric |
| 2022-12 | 46 | 42 | 42 | 6,351,485.0 | 6,351,485.0 | observed | unverified_metric |
| 2023-01 | 32 | 30 | 30 | 13,500,000.0 | 13,500,000.0 | observed | unverified_metric |
| 2023-02 | 45 | 38 | 38 | 9,150,000.0 | 9,150,000.0 | observed | unverified_metric |
| 2023-03 | 217 | 169 | 169 | 6,500,000.0 | 6,600,000.0 | observed | unverified_metric |
| 2023-04 | 288 | 270 | 270 | 10,235,001.5 | 10,564,500.0 | observed | unverified_metric |
| 2023-05 | 482 | 437 | 433 | 10,600,000.0 | 10,944,000.0 | observed | unverified_metric |
| 2023-06 | 947 | 817 | 801 | 10,000,000.0 | 10,623,200.0 | observed | unverified_metric |
| 2023-07 | 3,447 | 2,808 | 2,776 | 9,255,500.0 | 9,400,000.0 | observed | unverified_metric |
| 2023-08 | 3,531 | 2,911 | 2,885 | 9,452,000.0 | 9,800,000.0 | partial_month | unverified_metric |

For every row, `valid_price_sqft_count` follows the approved source-value quality-count rule. Until unit and semantic verification is completed, `median_price_per_sqft_inr` is `null` and the parent’s coarse record-level `metric_status` is `unverified_metric`. The lower and upper INR price-bound medians are still computed and retained; `unverified_metric` refers to the unresolved `PRICE_SQFT` field and does not invalidate those bound medians.

### 2.2 Aggregate totals and raw-date reconciliation

| Quantity | Expected value |
|---|---:|
| Raw rows | 9,487 |
| Raw columns | 55 |
| Rows with parseable posting timestamps | 9,245 |
| Rows with missing/invalid posting timestamps | 242 |
| Valid-dated rows inside the twelve-month window | 9,162 |
| Valid-dated rows outside the twelve-month window | 83 |
| In-window sale listings (`PREFERENCE == "S"`) | 7,633 |
| In-window valid coherent sale-price ranges | 7,555 |
| In-window sale listings without a valid coherent range | 78 |
| In-window observed rows in July and August combined | 6,978 |
| July/August share of in-window observed rows | 0.7616240995415848 (about 76.1624%) |

The totals must reconcile. Sum of monthly `observed_listing_count` equals 9,162; sum of `sale_listing_count` equals 7,633; sum of `valid_price_range_count` equals 7,555. These relationships must be tested directly instead of inferred from the table being displayed.

### 2.3 Pooled start/end price-bound summary

The summary defined in `Anomaly.md` uses the underlying row-level values, not the twelve monthly medians. The first pool covers September–November 2022; the final pool covers June–August 2023. Both are descriptive snapshot comparisons, not market estimates.

| Series | start-pool n | start median (INR) | end-pool n | end median (INR) | change (%) | direction |
|---|---:|---:|---:|---:|---:|---|
| `MIN_PRICE` / median lower price bound | 111 | 6,000,000.0 | 6,462 | 9,433,486.5 | 57.2247750000 | up |
| `MAX_PRICE` / median upper price bound | 111 | 6,000,000.0 | 6,462 | 9,613,800.5 | 60.2300083333 | up |

These results have a highly unequal sample size across pools and include the partial August endpoint. The output must therefore carry the shared caveat that this is a descriptive comparison within a scrape-derived snapshot; it is not a causal estimate, forecast, confidence interval, or claim about the whole market.

## 3. Golden vector B — deterministic anomaly output

**Fixture ID:** `G-HYD-ANOMALY-001`  
**Input:** Vector A's validated monthly records, the exact Aggregator evidence view, and the shared anomaly constants in `CONTRACT.md`/`Anomaly.md`.  
**Expected result:** `anomaly_analysis.status = "ok"`; `rule_version = "1.0.0-draft"`; exactly twelve ordered `monthly_changes` entries; seventeen flags under the current draft thresholds.

### 3.1 Required price-bound jump flags (AN-01)

Both bounds trigger at each month below except March 2023, where the two bounds have different change fractions. Every listed value is a signed fraction, not a percentage integer. Comparison is strict `abs(change_fraction) > 0.12`.

| month | series | expected change fraction |
|---|---|---:|
| 2022-10 | `median_min_price_inr` | 0.3275862068965518 |
| 2022-10 | `median_max_price_inr` | 0.3275862068965518 |
| 2022-11 | `median_min_price_inr` | -0.35071428571428576 |
| 2022-11 | `median_max_price_inr` | -0.35071428571428576 |
| 2022-12 | `median_min_price_inr` | 0.27042404240424034 |
| 2022-12 | `median_max_price_inr` | 0.27042404240424034 |
| 2023-01 | `median_min_price_inr` | 1.12548718921638 |
| 2023-01 | `median_max_price_inr` | 1.12548718921638 |
| 2023-02 | `median_min_price_inr` | -0.3222222222222222 |
| 2023-02 | `median_max_price_inr` | -0.3222222222222222 |
| 2023-03 | `median_min_price_inr` | -0.2896174863387978 |
| 2023-03 | `median_max_price_inr` | -0.2786885245901639 |
| 2023-04 | `median_min_price_inr` | 0.5746156153846154 |
| 2023-04 | `median_max_price_inr` | 0.6006818181818181 |

There must be no AN-01 flags for May, June, July, or August 2023 under the present baseline medians and threshold. There is no flag for September 2022 because it has no predecessor in the requested window.

### 3.2 Required observed-count flags (AN-02/AN-03)

| Rule | Month | Numerator / denominator | Expected value | Expected result |
|---|---|---|---:|---|
| AN-03 observed-count spike | 2023-03 | 217 / 45 | 4.8222222222 | Flag; threshold `>= 2.0` |
| AN-03 observed-count spike | 2023-07 | 3,447 / 947 | 3.6399155227 | Flag; threshold `>= 2.0` |

There must be **no AN-02 count-drop flag** in this snapshot under the registered `<= 0.50` rule. No count ratio is computed for September 2022, and predecessor counts below the minimum eligible denominator are not used.

### 3.3 Required window-level flag (AN-04)

Exactly one `late_window_count_concentration` flag is expected. Its value is:

`(3447 + 3531) / 9162 = 0.7616240995415848`

The threshold is `0.70` with inclusive `>=` comparison. Evidence must include both component counts, the total in-window observed count, and the share. It is a snapshot composition warning; it must mention neither a market surge nor a confirmed scraping cause.

### 3.4 Flag count, ordering, and identity

The expected flag composition is:

| Rule | Expected count |
|---|---:|
| AN-01 lower/upper price-bound jumps | 14 |
| AN-02 observed-count drops | 0 |
| AN-03 observed-count spikes | 2 |
| AN-04 late-window concentration | 1 |
| **Total** | **17** |

Flag IDs must be deterministic and stable, derived from rule ID, month or `window` scope, and series where applicable. Do not generate random UUIDs. Compare the normalized flag tuple `(rule_id, scope, month, series, kind, value, threshold, comparison, reason_code, evidence)` against the oracle. `reason` text must be deterministic under template mode, but prose may change only through a versioned contract/template update. Sorting follows `Anomaly.md`: chronological month, then shared rule order AN-01 through AN-04, then series key; window-level flag ordering must follow the explicitly implemented and tested rule.

## 4. Golden vector C — report envelope and diagnostic alignment

The full report also includes run metadata, trace, data-quality counters, and diagnostics. The exact run ID, timestamp, elapsed time, trace attempt details, `logic_version`, and LLM provider metadata are not fixed literals; tests validate their types and constraints. `snapshot_sha256`, window, timezone, contract version, counts, schemas, anomaly results, and loop-cap invariants are deterministic under the same input/configuration.

### 4.1 Abbreviated expected response

The following is a schema illustration, not a complete fixture and not a replacement for the full JSON fixture emitted by the test suite:

```json
{
  "status": "ok",
  "error": null,
  "contract_version": "1.0.0-draft",
  "snapshot_sha256": "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a",
  "window_start": "2022-09",
  "window_end": "2023-08",
  "timezone": "Asia/Kolkata",
  "records": [
    {
      "month": "2022-09",
      "observed_listing_count": 35,
      "sale_listing_count": 33,
      "valid_price_range_count": 33,
      "median_min_price_inr": 5800000.0,
      "median_max_price_inr": 5800000.0,
      "median_price_per_sqft_inr": null,
      "coverage_status": "observed"
    },
    {
      "month": "2023-08",
      "observed_listing_count": 3531,
      "sale_listing_count": 2911,
      "valid_price_range_count": 2885,
      "median_min_price_inr": 9452000.0,
      "median_max_price_inr": 9800000.0,
      "median_price_per_sqft_inr": null,
      "coverage_status": "partial_month"
    }
  ],
  "anomaly_analysis": {
    "status": "ok",
    "rule_version": "1.0.0-draft",
    "flags": "17 expected flags; see §3"
  },
  "diagnostics": "exactly one {flag_id, text, source} object per flag, same order",
  "data_quality": {
    "raw_rows": 9487,
    "raw_columns": 55,
    "invalid_or_missing_posting_dates": 242,
    "in_window_observed_rows": 9162,
    "in_window_sale_rows": 7633,
    "in_window_valid_price_ranges": 7555
  }
}
```

In an actual JSON fixture, `records` must contain all twelve monthly records, `anomaly_analysis.flags` must be the full array rather than the explanatory string shown above, and `diagnostics` must be an array rather than a descriptive placeholder. The excerpt omits non-deterministic metadata fields only to keep the contract readable. Use the full schema in `CONTRACT.md` for validation.

### 4.2 Diagnostic equality policy

With `LLM_MODE=off`, each diagnostic must use `source="template"`; the text must satisfy the rule-specific template contract, refer to the exact flag, and avoid causal claims. If template wording is pinned as an exact fixture, update its template version when wording changes. With `replay`, compare cached response identity and validated schema. With `live`, do not require identical prose across runs; instead assert exact flag alignment, length/content policy, valid source labels, and immutable numeric results. No flags means `diagnostics=[]` and zero diagnostic model calls.

## 5. Comparison tolerances

- **Schemas, required fields, month order, row counts, sale counts, valid-range counts, statuses, null placement, flag count, flag IDs, rule IDs, comparisons, and diagnostic-to-flag order:** exact equality.
- **INR price medians:** absolute tolerance `0.01` INR and relative tolerance `1e-10`, unless a stricter exact numeric representation is possible. Tolerance is for binary floating-point representation only; it is not permission to round away meaningful differences.
- **Fractions, ratios, concentration share, and percentage changes:** absolute tolerance `1e-9`, relative tolerance `1e-10`.
- **Null / unavailable values:** exact JSON `null`, never zero, empty string, NaN, or Infinity.
- **Integers:** exact equality; never compare counts with a tolerance.
- **Human-readable diagnostics:** apply §4.2 rather than numerical tolerance.

Serialize machine-readable numbers as JSON numbers, not currency strings or comma-formatted text. Human-facing formatting must not mutate the numerical fields used by the oracle.

## 6. Required secondary tests

The full snapshot vector is the primary golden oracle. Also test the following behavior using isolated in-memory unit fixtures where necessary. Such fixtures are test-only objects, not appended to `hyderabad.csv`, must not be reported as listings, and are not substitutes for real data.

1. **Dense month grid:** output has exactly the twelve expected months in order even if a test fixture has a month with no eligible rows.
2. **Empty input:** counts are zero; unavailable medians are null; statuses follow parent precedence; anomaly status is `insufficient_data`; no fabricated diagnostic flags are returned.
3. **Missing/invalid timestamp:** row is preserved in data-quality accounting but excluded from all monthly counts.
4. **Timezone boundary:** a timestamp close to a UTC month boundary is assigned to the local `Asia/Kolkata` month, not the UTC month.
5. **Sentinel and invalid bounds:** `2147483647`, zero, non-finite, missing, nonnumeric, and inverted bounds do not enter the valid price-range subset.
6. **Sale filter:** a row outside `PREFERENCE == "S"` cannot enter the sale-price-bound medians, even if its bounds are numeric.
7. **Property-ID repeat:** repeating `PROP_ID` alone must not remove a row.
8. **Input row order:** permutation of in-memory rows does not alter aggregates, normalized flags, pooled summary, or diagnostic ordering. For end-to-end runs, the raw byte hash check still applies to the frozen file.
9. **Numeric precision:** even-sized medians preserve half-unit results such as `10,235,001.5` INR.
10. **Threshold boundaries:** AN-01 exactly at ±0.12 does not trigger; AN-02 exactly 0.50 does trigger; AN-03 exactly 2.00 triggers; AN-04 exactly 0.70 triggers.
11. **Insufficient predecessor:** no adjacent change or count-ratio flag is derived where the predecessor lacks the configured minimum evidence.
12. **No unverified metric use:** changing raw `PRICE_SQFT` values alone does not affect the current price-bound golden metrics or anomaly flags.
13. **Partial final month:** August remains `partial_month`; no projection or full-month correction is applied.
14. **No hidden model dependency:** `LLM_MODE=off` produces the same numeric records, summaries, and flags without API keys or network access.
15. **Retry/loop invariants:** coverage and critique loops terminate within their shared caps and expose their actual counts in trace/metadata.

## 7. Baseline update and change control

A golden mismatch is a diagnostic signal, not authorization to rewrite the expected value. On failure, compare in this order:

1. verify raw file SHA-256 and row/column count;
2. verify timestamp parsing unit, timezone localization, and month window;
3. verify sale eligibility, sentinel handling, coherent price-range filter, and duplicate policy;
4. verify formulas, median method, null/status precedence, threshold operators, rule ordering, and rounding;
5. inspect code changes and runtime/dependency versions;
6. only then decide whether a source-supported, approved contract change is warranted.

A legitimate baseline update requires a recorded reason, reviewer approval, the source/contract/rule version it follows, a before/after diff, regeneration of the full oracle from code independent of the application under test, and updated regression plus metamorphic tests. Never update goldens automatically during CI, and never loosen tolerances solely to make a known defect pass.

Changing any of the following requires explicit review and coordinated updates to `CONTRACT.md`, the responsible subcontract, test fixtures, and version metadata: frozen source hash, fixed date window, timezone, `PREFERENCE` sale rule, sentinel or numeric eligibility rule, duplicate behavior, median formula, null/status semantics, output schema, anomaly threshold/comparison, flag ID/order contract, or numeric tolerance.

## 8. Golden acceptance criteria

The golden suite passes only when all of the following hold:

- the frozen input hash matches the expected SHA-256;
- twelve monthly records are returned in canonical order;
- all exact count totals and numeric medians match §2;
- pooled summary values and denominators match §2.3;
- anomaly changes and exactly seventeen flags match §3;
- the final month is labeled partial and the `PRICE_SQFT` median remains unverified/null;
- every diagnostic aligns one-to-one with a flag and cannot modify numeric output;
- all statuses, nulls, schema, metadata, and bounded-loop invariants pass;
- no production calculation reads a golden table in place of recomputing from the snapshot.

The golden vectors describe a specific frozen scraped snapshot. They are regression anchors for software correctness, not evidence of complete coverage, price prediction accuracy, or market-wide causal change.
