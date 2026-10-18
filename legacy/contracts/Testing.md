# TESTING SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v1.0.0-draft. This file defines oracle, metamorphic testing, sample eligibility, and reporting. Shared values come from the global contract.

## 1. Test boundary and oracle

Call the application core directly for unit and metamorphic tests; test the API separately for request/response schema. Use an independent oracle with hand-checked fixtures and straightforward calculations, not the application's helper functions.

The frozen real snapshot is the main subject. Small constructed test fixtures may be used to exercise edge cases and control flow, but must be labeled as test fixtures and never merged into the housing snapshot or reported as observed listings.

## 2. Comparator rules

- Counts, month order, statuses, null placement, and schemas: exact equality.
- INR medians: compare with `math.isclose` using a documented absolute/relative tolerance suitable for floating-point representation; do not round before comparison.
- Invariance MRs: output fields expected to remain invariant must be equal within the metric tolerance.
- Directional MRs: assert the direction only on eligible subdomains and state whether equality is allowed.
- Each result records MR/input ID, seed, eligibility, expected/observed relation, pass/fail/skip, tolerance, and failure details.

## 3. Base-input requirements and seeds

- At least 8 distinct MRs across invariance, monotonicity, and directional families.
- At least 30 distinct eligible base inputs per MR. Reusing the same base input with different seeds does not make it a distinct base input.
- Inputs that do not meet the MR precondition are recorded as skipped with a reason, not counted as passes.
- For any nondeterministic/model-dependent behavior, use at least 3 fixed seeds and report repetitions by seed. Keep the data/metric oracle deterministic.
- Freeze the input IDs, transformations, seeds, and expected relation before evaluating the implementation.

## 4. Required metamorphic relation catalogue

Each relation must be documented with: ID, family, transformation, relation expected, preconditions/subdomain, fields checked, tolerance, targeted fault, skip rule, and number of eligible base inputs.

### MR1 — Row-order invariance (invariance)
**Transform:** permute row order without changing row contents.  
**Expected:** all monthly counts, medians, statuses, and flags remain equal; ordering of the final month grid remains chronological.  
**Subdomain:** any valid base input with stable row IDs.  
**Tolerance:** exact for counts/statuses; configured numeric tolerance for medians.  
**Targets:** order-dependent aggregation, unstable grouping, nondeterministic tie handling.

### MR2 — Irrelevant-column invariance (invariance)
**Transform:** add or alter a column that is not used by the analysis.  
**Expected:** report metrics and flags are unchanged.  
**Subdomain:** extra column is not a supported filter or declared metric input.  
**Tolerance:** exact/numeric comparator as above.  
**Targets:** accidental dependency on unrelated fields, schema-coupling bugs.

### MR4 — Invalid-date exclusion (invariance on monthly metrics)
**Transform:** append a row whose `POSTING_DATE` is missing or invalid.  
**Expected:** all 12 monthly counts and metrics remain unchanged; invalid-date quality count increases by one.  
**Subdomain:** added row has no valid posting date.  
**Tolerance:** exact.  
**Targets:** invalid-date leakage into monthly aggregation, silent row loss.

### MR5 — Sale-subset isolation (invariance on sale-price metrics)
**Transform:** append a dated non-sale row with extreme but syntactically valid price fields.  
**Expected:** observed listing count increases by one in that month; sale count and sale-price medians remain unchanged.  
**Subdomain:** source classification `PREFERENCE != "S"` and a valid month.  
**Tolerance:** exact counts; numeric median tolerance.  
**Targets:** mixing sale/rent/other preferences into sale-price analysis.

### MR6 — Monotonic observed count (monotonicity)
**Transform:** append one new valid dated row inside the fixed window.  
**Expected:** that month's observed count increases by one, unless the row is an exact duplicate removed by the declared rule; other months' counts are unchanged.  
**Subdomain:** unique eligible row, valid timestamp, in-window month.  
**Tolerance:** exact.  
**Targets:** wrong month assignment, accidental global filtering, incorrect count aggregation.

### MR7 — Monotonic sale count (monotonicity)
**Transform:** append one unique valid sale row in a chosen month.  
**Expected:** that month's sale count increases by one; other months' sale counts are unchanged. Price medians may change, so this MR does not assert median invariance.  
**Subdomain:** valid localized date, `PREFERENCE == "S"`, unique row under dedup policy.  
**Tolerance:** exact counts.  
**Targets:** sale classification/count errors.

### MR8 — Lower-bound directional relation (directional)
**Transform:** increase `MIN_PRICE` for one eligible sale row while keeping it finite, positive, below/equal to its valid upper bound, and leaving all other rows fixed.  
**Expected:** that month's median lower bound cannot decrease. Upper-bound median and counts remain unchanged.  
**Subdomain:** valid coherent price range after transformation; ensure transformation does not cross sentinel or eligibility boundaries.  
**Tolerance:** median comparator; count exact.  
**Targets:** wrong-column median, filtering errors, directionally incorrect aggregation.

### MR9 — Upper-bound directional relation (directional)
**Transform:** increase `MAX_PRICE` for one eligible sale row while maintaining `MAX_PRICE >= MIN_PRICE` and validity.  
**Expected:** that month's median upper bound cannot decrease. Lower-bound median and counts remain unchanged.  
**Subdomain:** valid coherent ranges before and after transformation.  
**Tolerance:** median comparator; count exact.  
**Targets:** swapped price bounds, incorrect median field, eligibility bugs.

### MR11 — Month-grid invariance (invariance)
**Transform:** remove all eligible rows for one month in a test fixture while keeping the global window fixed.  
**Expected:** response still contains all 12 months; that month has count zero, null metrics, and `no_listings` statuses; all other months are unchanged.  
**Subdomain:** fixture permits an empty month without changing the fixed window.  
**Tolerance:** exact.  
**Targets:** sparse output grids, fabricated interpolation, missing-month crashes.

### MR12 — Partition equivalence (invariance)
**Transform:** execute the same eligible rows through consolidated scanning and non-overlapping partitioned scanning, then merge.  
**Expected:** records, counts, medians, flags, and status match within tolerance; no duplicated row IDs.  
**Subdomain:** both topologies are implemented and partition coverage is complete.  
**Tolerance:** exact counts/statuses; numeric tolerance for medians.  
**Targets:** shard overlap, missing partitions, nondeterministic merge logic. Skip if only consolidated mode is implemented.

### MR13 — Bounded-loop termination (control-flow relation)
**Transform:** provide a controlled validator fixture that continues requesting repair until the cap is reached.  
**Expected:** the initial attempt plus no more than the configured retry cap occur; the final trace records exhaustion and no infinite loop occurs.  
**Subdomain:** deterministic test fixture only; it is not a housing record.  
**Tolerance:** exact attempt/event counts.  
**Targets:** off-by-one cap errors, hidden retries, missing stop conditions.

Use at least eight data MRs, with all three families represented. Skip optional partition equivalence if only consolidated mode exists. Keep bounded-loop termination as a control-flow test; do not count it as a data MR if the rubric distinguishes them.

## 5. Violation rates and confidence intervals

For each MR, report eligible base-input count `n`, pass count, fail count, skip count, violation rate `fail / (pass + fail)`, and a 95% confidence interval. Do not include skipped cases in the denominator. State the interval method; Wilson score intervals are recommended for binomial proportions, including small samples. For seeded repetitions, report per-seed results and a pooled result with the dependence caveat; repeated seeds on the same base input are not independent base inputs.

Include MR/input ID, seed, expected/observed values, and a reproducible case for failures.

## 6. Harness self-tests

The harness itself must test:
- a known passing invariance case;
- a known violating case using a deliberately faulty test double;
- skip/precondition handling;
- exact count and schema comparisons;
- numeric tolerance behavior;
- deterministic seed enumeration;
- Wilson interval implementation against a hand-checkable example;
- output CSV/JSON schema and denominator reconciliation.

## 7. Results and diagnosis

Report top three violation categories by evidence-supported frequency and impact. For each: show failing MR IDs, denominator, violation rate and 95% CI, a reproducible example, likely code-level cause supported by trace, and a proposed fix. Distinguish observed cause from hypothesis. Do not claim statistical significance without a defined comparison procedure.
