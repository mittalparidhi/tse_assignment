

# Global Contract: Hyderabad Housing-Trends Application



**Contract version:** 0.1  

**Dataset:** Frozen Hyderabad residential-listing snapshot  

**Status:** Initial specification; unit and field-semantic checks remain pending



## 1. Purpose and scope



The application summarizes observed residential-listing postings in the Hyderabad dataset. It reports monthly posting counts and asking-price statistics for the available historical snapshot.



The dataset is a scraped listing sample, not a complete census of Hyderabad's housing market. Results must be described as statistics over observed records. The application must not interpret changes in observed counts as direct evidence of market-wide supply changes or price appreciation.



The original file at `data/raw/hyderabad.csv` is immutable. Cleaning and analysis must use reproducible derived data.



## 2. Dataset and date semantics



The raw dataset contains 9,487 rows and 55 columns. The observed `POSTING_DATE` range is May 2022 through August 2023, with 9,245 valid timestamps in the initial audit.



`POSTING_DATE` is the primary listing-entry timestamp. It is recorded as Unix milliseconds. Convert it to a timestamp, interpret it in the `Asia/Kolkata` timezone, and derive the calendar month from that localized timestamp. The canonical pipeline must use this rule consistently and regenerate monthly counts accordingly.



Rows with missing or invalid posting timestamps cannot be assigned to a calendar month. Exclude them from monthly aggregates and report their number in data-quality metadata.



The default analysis window is September 2022 through August 2023, inclusive. It contains exactly 12 calendar months and is anchored to the available snapshot, not to the current date.



The snapshot's latest observed posting date is August 26, 2023. Mark August 2023 as a partial snapshot month. Do not assume that earlier months are complete representations of the underlying market.



## 3. Output contract



Every successful analysis returns exactly 12 monthly records, ordered chronologically from `2022-09` through `2023-08`.



Each record contains:



\- `month`: calendar month in `YYYY-MM` format.

\- `observed_listing_count`: number of eligible, dated listing rows in the month after documented exact-row deduplication.

\- `sale_listing_count`: number of those rows for which `PREFERENCE == "S"`.

\- `valid_price_range_count`: number of sale listings with valid, coherent numeric price bounds.

\- `median_min_price_inr`: median of valid lower price bounds, in INR.

\- `median_max_price_inr`: median of valid upper price bounds, in INR.

\- `valid_price_sqft_count`: number of sale listings with usable `PRICE_SQFT` values.

\- `median_price_per_sqft_inr`: median source-reported price-per-square-foot value, in INR per square foot, only after the field's units and semantics have been verified.

\- `coverage_status`: whether the month is within the snapshot's observed coverage and whether it is a partial month.

\- `metric_status`: whether the relevant metrics are available.



Price metrics must be numeric or `null`. Never output `NaN`, positive infinity, or negative infinity as JSON numbers.



Price ranges must not silently be replaced by their midpoint. The lower and upper price statistics are distinct metrics.



## 4. Currency and price validity



The numeric `MIN_PRICE` and `MAX_PRICE` fields are treated as INR, subject to validation against source semantics and displayed examples. Do not convert displayed lakh/crore strings again when using numeric fields that are already represented in rupees.



A numeric price bound is individually valid only if it is finite, strictly positive, and not the known sentinel value `2147483647`.



A coherent price range requires both bounds to be individually valid and `MIN_PRICE <= MAX_PRICE`. Report the count of valid coherent ranges. Calculate the lower-bound and upper-bound medians from coherent ranges only.



Records with `Price on Request`, zero-valued bounds, sentinel values, non-numeric values, or incoherent bounds must not enter the valid coherent-range subset. Retain these records in the processed dataset with explicit quality flags wherever possible.



A property ID repeated in multiple rows is not, by itself, proof of a duplicate. Remove exact full-row duplicates deterministically if present; flag repeated IDs whose rows differ, and preserve them until a documented rule resolves the discrepancy.



## 5. Price-per-square-foot validity



`PRICE_SQFT` is a source-provided metric. Its meaning and unit must be checked before it is reported as INR per square foot. Do not recompute it from area columns until their units are verified.



A candidate numeric `PRICE_SQFT` value must be finite and strictly positive. Zero, missing, and non-numeric values are unusable.



Flag values greater than or equal to 100,000 for anomaly review. This is a provisional investigation threshold, not proof that a listing is erroneous. Do not silently discard such values from the entire dataset. Document the primary metric's inclusion rule and perform a sensitivity analysis before finalizing any exclusion threshold.



Area fields with uncertain or inconsistent units must not be used to derive new price metrics until the unit question is resolved.



## 6. Missing-month and missing-metric semantics



The output always contains all 12 months, even if one or more months have no eligible observations.



\- `no_listings`: `observed_listing_count = 0`; price metrics are `null`.

\- `no_sale_listings`: postings exist, but no sale-preference listings are available; sale-price metrics are `null`.

\- `no_valid_prices`: sale listings exist, but no valid coherent price ranges are available; price-bound medians are `null`.

\- `ok`: the relevant metric has eligible observations and can be calculated.



Keep `coverage_status` separate from `metric_status`. A month can have usable metrics while still being a partial snapshot month.



Do not fill missing prices with zero, carry values forward, interpolate, or invent listings. Zero means a measured count of zero; `null` means that a metric cannot be calculated from eligible observations.



## 7. Deterministic calculations



All data parsing, filtering, grouping, numeric calculations, and validation are performed in Python. An LLM must not determine row eligibility or supply numeric metrics.



Use fixed parsing rules, fixed month boundaries, explicit validity predicates, and documented aggregation functions. Use medians for the specified price statistics. Do not round intermediate values; round only for display or serialization when required by the output schema.



Sort monthly records by calendar month. For stochastic diagnostics or bootstrap intervals, define and record fixed seeds, resampling counts, and quantile methods. Identical inputs, configuration, and software environment must produce identical outputs.



All data-quality exclusions, flags, and row counts must be auditable.



## 8. Balancing and sampling



The primary analysis uses all eligible observed records; it must not downsample months merely to make monthly counts equal.



A month-stratified sample may be used for sensitivity analysis only. Record its seed, sampling rule, per-month sample size, and comparison with the full-sample results. Sampling or weighting must not be presented as a correction for unknown data-collection bias.



## 9. Multi-agent workflow and bounded loops



The orchestrator must enforce finite retry limits. Initial configuration:



\- **Coverage-repair loop:** at most 3 retries after the initial attempt.

\- **Critique/revision loop:** at most 2 revisions after the initial draft.



Every retry must have a reason and a machine-readable trace entry. Stop early when the condition is satisfied. When the limit is reached, stop the loop and report `max_attempts_exceeded` or an appropriate explicit failure status. Never loop indefinitely.



The numerical calculation component must be deterministic. The LLM may explain anomalies, suggest diagnostics, or draft narrative summaries, but it cannot override programmatic validation or numeric results.



## 10. Contract validation



A valid output must satisfy all of the following:



1\. Exactly 12 monthly records are returned in chronological order.

2\. The records cover September 2022 through August 2023.

3\. Counts are non-negative integers.

4\. Price metrics are finite numeric values or `null`.

5\. Missing-month and missing-price statuses follow Section 6.

6\. Price metrics use only the documented valid subsets.

7\. Repeated property IDs and anomalies are handled according to the documented policy.

8\. A repeated run with the same input and configuration gives the same deterministic metrics.

9\. Every bounded loop terminates within its configured limit.

10\. The output records the dataset snapshot/version, contract version, and relevant configuration.



Any violation is a contract-validation failure and must be logged with a reason.



## 11. Known limitations and open checks



The snapshot is concentrated heavily in July and August 2023, so collection or sampling bias may affect interpretation. Monthly counts describe records observed in this dataset, not all market listings.



Before treating this contract as final, verify:

\- The exact semantics of `TRANSACT_TYPE` codes.

\- The unit consistency of `MIN_AREA_SQFT` and `MAX_AREA_SQFT`.

\- The documented units and plausibility of `PRICE_SQFT`.

\- The repeated `PROP_ID` records and exact-row duplicate policy.

\- The final validity and sensitivity rules used for price metrics.



Any change to these rules must update the contract version and related tests.


## Context Budget Policy

- Target maximum context budget for the global contract and its directly included contract context: approximately 7,500 tokens.
- Treat 7,500 tokens as the working ceiling, not a target that must be filled.
- Preserve all mandatory requirements, field definitions, metric semantics, validation rules, and bounded-loop policies when revising the contract.
- Prefer concise, unambiguous rules over repeated explanations.
- Do not include raw datasets, long execution logs, or full code listings in the contract.
- Keep implementation details and experimental results in separate project files, referencing them from the contract where necessary.
- Before a major contract revision, estimate its token count and verify that the contract context remains within the budget.

