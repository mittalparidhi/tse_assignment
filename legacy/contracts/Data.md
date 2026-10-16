# DATA SUBCONTRACT — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

**Parent:** `CONTRACT.md` v1.0.0-draft  
**Status:** Draft; dataset fingerprint is known, but several source-field semantics remain unresolved.  
**Scope:** Source freeze, date conversion, row preservation, price eligibility, audit evidence, and reproducibility. This file clarifies data rules; the parent contract controls public schemas, metrics, analysis window, and loop limits. In a conflict, update this file rather than silently changing the parent contract.

## 1. Source and frozen input

| Item | Contract value |
|---|---|
| Raw path | `data/raw/hyderabad.csv` |
| Source rows / columns | 9,487 / 55 |
| SHA-256 | `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` |
| Source lineage | 99acres-derived listing scrape; repository and field-description wiki are cited in project documentation |
| Mutability | Read-only after snapshot freeze |

The hash above was computed from the supplied `hyderabad.csv` bytes. The matching copy inside `archive (3).zip` has the same hash. The source repository is `https://github.com/arv-anshul/99acres-scrape`; the field-description wiki is `https://github-wiki-see.page/m/arv-anshul/99acres-scrape/wiki/SRP-Data-Description`. Do not claim a licence unless the repository licence is checked and cited.

This is a scraped listing sample, not a full market census. Preserve its original records; do not add synthetic listings, merge external datasets into the snapshot, or describe observed row counts as total Hyderabad inventory or completed transactions. The `CITY` field includes 8,762 rows labelled `Hyderabad` and 725 labelled `Secunderabad`. No city filter may be applied silently. The parent contract must explicitly choose a strict `CITY == "Hyderabad"` scope if that is required; otherwise the frozen-source baseline includes both labels and reports the mix.

## 2. Timestamp conversion and canonical month grid

`POSTING_DATE` is documented as Unix milliseconds. Parse values numerically with explicit millisecond units, treating missing, nonnumeric, non-finite, or out-of-range values as invalid. Interpret a valid value as an absolute instant, convert it to `Asia/Kolkata`, and only then derive `posting_month = YYYY-MM`. Do not derive months from a timezone-naive UTC timestamp. Preserve the original `POSTING_DATE` value.

Rows with invalid dates remain in the cleaned file and data-quality counts but cannot contribute to monthly aggregates. Do not infer their dates from `REGISTER_DATE`, `UPDATE_DATE`, or another field. Rows with valid dates outside the analysis window also remain auditable but do not contribute to the parent contract's twelve monthly records.

The canonical conversion yields 9,245 valid local timestamps and 242 missing/invalid timestamps. Valid timestamps range from `2022-05-17 23:01:45+05:30` to `2023-08-26 10:29:05+05:30`. The required analysis window is `2022-09` through `2023-08`; August 2023 is partial. The monthly baseline below counts all retained rows with valid posting dates, before filtering to sale records or valid prices.

| Month | Observed rows | Month | Observed rows |
|---|---:|---|---:|
| 2022-09 | 35 | 2023-03 | 217 |
| 2022-10 | 51 | 2023-04 | 288 |
| 2022-11 | 41 | 2023-05 | 482 |
| 2022-12 | 46 | 2023-06 | 947 |
| 2023-01 | 32 | 2023-07 | 3,447 |
| 2023-02 | 45 | 2023-08 | 3,531 |

There are 9,162 valid-date rows in the twelve-month window. July and August contribute 6,978 rows (about 76.2% of that window); this concentration may reflect scrape/collection behavior and must not be presented as proof of a market-wide surge. The existing date audit must be regenerated with the timezone rule above before its month-level output is treated as canonical.

## 3. Cleaning and identity rules

Cleaning must be implemented by a versioned script, not improvised inside agents. Each run writes a summary table with rule ID, rows inspected, rows flagged or changed, and output path. Never overwrite the raw file.

| Rule | Required action |
|---|---|
| D1 — Preserve identity | Add a stable `source_row_id` based on raw row position before transformation. Keep all 55 raw fields unchanged in meaning; append derived fields and flags rather than overwriting source values. |
| D2 — Date quality | Add localized timestamp, `posting_month`, and a date status. Invalid dates are retained but excluded from monthly aggregates. |
| D3 — Exact duplicates | Current audit finds 0 fully identical rows. Do not remove any rows unless a documented full-row equality rule detects them and the removal count is logged. |
| D4 — Repeated property ID | `PROP_ID = Z70135726` occurs twice. The two rows match in the inspected identifiers, date, and price fields but differ in `PRIMARY_TAGS` (`['FEATURED']` versus `[]`). Preserve both and emit an ID-collision audit; a repeated ID alone does not authorize deduplication. |
| D5 — Sale scope | Use `PREFERENCE == "S"` for sale-price metrics. Counts in the raw snapshot are S=7,927, R=1,467, P=93. Retain non-S rows for general observed-row counts unless the parent contract explicitly defines a different population. Do not infer the meaning of `R` or `P` beyond verified source documentation. |
| D6 — Transaction code | `TRANSACT_TYPE` values are 1.0=7,340, 2.0=571, missing=1,576. Their code meanings are not verified here; do not use these codes as substitutes for `PREFERENCE`. |
| D7 — Numeric price bounds | Treat `MIN_PRICE` and `MAX_PRICE` as candidate INR values. A bound is eligible only if numeric, finite, strictly positive, and not sentinel `2147483647`; a range also requires both bounds eligible and `MIN_PRICE <= MAX_PRICE`. Never parse `PRICE` display text and convert the numeric fields a second time. |
| D8 — Preserve price failures | Retain rows with zero, sentinel, incoherent, or otherwise ineligible bounds. Add mutually interpretable reason flags such as `non_positive_price`, `price_sentinel`, `inverted_price_range`, and `invalid_price_bound`; do not replace them with zero, a midpoint, or an estimate. |
| D9 — Price per square foot | `PRICE_SQFT` is source-provided but its precise semantics and units are not verified. There are 75 zero values, 8,915 positive values below 100,000, and 497 values at or above 100,000. The 100,000 threshold is a review flag only, not proof of invalidity. Preserve values and emit a review flag; do not assert an INR/sq-ft metric until its meaning is verified. |
| D10 — Area fields | Preserve `MIN_AREA_SQFT` and `MAX_AREA_SQFT`; do not recompute price per square foot from them until unit/scale semantics are verified. Although their names contain `SQFT`, their distribution warrants a source check. |

No current rule authorizes removal of the 242 invalid-date rows, the 78 invalid coherent-price-range rows, or the repeated-ID pair from the stored cleaned snapshot. Eligibility filters apply to metrics, not blanket row deletion.

## 4. Snapshot and metric denominators

`data/processed/hyderabad_clean.csv` is a derived, reproducible artifact. It must preserve all 9,487 raw rows and all original columns; add `source_row_id`, local posting datetime/month, and explicit data-quality flags. If the implementation later introduces a justified row-removal policy, it requires a parent-contract version change and a before/after audit. The raw file and its hash remain unchanged.

With the canonical timezone rule and current parent-contract eligibility rules, the twelve-month window has 9,162 observed rows, 7,633 rows with `PREFERENCE == "S"`, and 7,555 sale rows with a valid coherent numeric price range. These values are audit baselines, not constants to hard-code into calculations. Monthly output counts and medians must be recomputed from the snapshot on every run. The 78 invalid price ranges in this window are all sale rows; they remain in observed and sale counts but not in price-bound medians.

Define denominators explicitly:

- `observed_listing_count`: valid localized posting date in the month; no undocumented property-ID deduplication.
- `sale_listing_count`: observed rows whose `PREFERENCE` is exactly `S`.
- `valid_price_range_count`: sale rows with two eligible bounds and `MIN_PRICE <= MAX_PRICE`.
- `valid_price_sqft_count`: publish as a verified-metric denominator only after the field's semantics are checked; before then it may be shown only as a raw quality statistic clearly marked unverified.

Missing monthly rows and missing metrics follow the parent contract: always emit all twelve months; count zero means no eligible observed rows, while a metric that cannot be computed is `null`. Never fill missing prices, invent records, carry values forward, or interpolate.

## 5. Data boundaries and startup integrity

1. The raw snapshot is read-only. All cleaning creates a separate processed artifact.
2. Application agents consume the processed snapshot and explicit criteria. They must not perform hidden file/network/clock reads to change data semantics.
3. Do not change row order in a way that alters results. A stable `source_row_id` must permit every flag, eligibility decision, and diagnostic to be traced back to the source row.
4. At run start, calculate the raw SHA-256 and compare it with the frozen digest above. On mismatch, stop with `snapshot_integrity_error`; do not silently regenerate the expected hash.
5. Log the raw hash, contract version, cleaning-script version, timezone, input/output row counts, and the summary/audit artifact paths. Do not log credentials or unnecessary full listing descriptions.
6. Source-field ambiguities (`TRANSACT_TYPE`, `PRICE_SQFT`, area units, and city scope) remain explicit unresolved items until backed by source documentation or a recorded project decision.

## 6. Reproducibility checks

| Check | Required result |
|---|---|
| R1 — Raw integrity | SHA-256 equals `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`. |
| R2 — Row/column count | 9,487 rows and 55 source columns before appended derived fields. |
| R3 — Timestamp audit | 9,245 valid localized timestamps; 242 missing/invalid; observed span and monthly counts agree with §2. |
| R4 — Twelve-month grid | Exactly the ordered months `2022-09` … `2023-08`, with 9,162 observed rows across the window before sale/price filters. |
| R5 — Sale and price subset | 7,633 sale rows and 7,555 sale rows with valid coherent price ranges in the window under the rules in §3. |
| R6 — Duplicate audit | 0 exact duplicate rows; the two rows for `Z70135726` remain present and are reported as a repeated ID. |
| R7 — Repeatability | Re-running the cleaning script on the same raw hash/config produces identical processed bytes or a documented canonical serialization and the same counts/flags. |
| R8 — No source mutation | Raw SHA-256 before and after cleaning is identical. |

If any baseline changes, first determine whether the source, timezone logic, or cleaning rule changed. Update this contract and its parent version only for an intentional, reviewed change; do not modify expected values just to make a test pass.

## 7. Traceability to the parent contract

| This subcontract | Parent contract |
|---|---|
| Source, freeze, and hash | §§2, 11, 12 |
| Month conversion and partial-month caveat | §§1, 3, 5, 7 |
| Sale/price eligibility and denominators | §§3, 4, 6, 7 |
| Row identity and duplicate policy | §§4, 6.3, 11 |
| Source-field ambiguity and output caveats | §§1, 4.3, 6.2, 7 |
| Reproducibility and error behavior | §§10–12 |

**Change rule:** This subcontract is reviewed alongside `CONTRACT.md`. Shared schema, window, error-code, or metric-policy changes are made in the parent first; this file then records source-specific evidence and implementation assertions.
