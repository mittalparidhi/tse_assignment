# ANALYSIS AGENT SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft. **Related:** `Critique.md`, `Data.md`, `LLM.md`. The parent wins on conflicts.

**Status:** Draft; implemented. New output fields are added in Phase 3; rejection accounting is fixed in Phase 4.

## 1. Role and boundary

**Kind:** computation. **LLM:** optional, grey-zone review only (§4). **Code:** `src/agents/nodes.py::analysis_agent`; statistics in `src/trend.py::compute_trend`.

**Job:** compute the `TrendReport` from the retrieved listings. On a critique complaint, recompute with contextual outliers removed **only in the flagged months**.

| Interface | Contract |
|---|---|
| Inputs | `raw_listings`, effective spec, `critique_complaint`, `flagged_months`, `config`, `seed`, `llm` |
| Outputs | `trend_stats` (a `TrendReport`), `n_rejected_outliers`, one trace entry |
| May change | Which retrieved listings are excluded from the statistics, within flagged months only |
| Must preserve | Listing values; listings in unflagged months; the window and units |

## 2. Statistics (all deterministic Python)

Computed by `compute_trend` exactly as defined in `CONTRACT.md` §5:

- Per month: `n_active`, `median_psf`, `p25_psf`, `p75_psf`, **[P3]** `median_min_price_inr`, `median_max_price_inr` (replacing `median_price`), `median_age_on_site_days`, `month_is_sufficient`, **[P3]** `is_partial_month`.
- Report: `locality_rankings` (≥ 5 listings, top 10, median ₹/sqft descending, name tie-break, stable sort), `yoy_median_psf_pct` and `yoy_span_months` (first vs last sufficient month), `n_listings_total`.
- Display scaling: price × currency factor; ₹/sqft × (currency factor ÷ area factor). Percentages are computed from unrounded values.
- Empty months: count 0, statistics `null`. No imputation, interpolation or carry-forward.
- Medians and percentiles use numpy; an even count's median is the mean of the two middle values.

A model never computes, rounds or revises any of these numbers.

## 3. Targeted recomputation (loop C2 target)

Runs only when `critique_complaint` is set and `flagged_months` is non-empty. For each flagged month, separately (`group_outliers_by_month = True`):

| Rule | Reject a listing when |
|---|---|
| Contextual outlier | robust z-score of log ₹/sqft (median and MAD within the month, scaled by 0.6745) has absolute value `> robust_z_threshold` (3.5) |
| Area disagreement | `area_sqft` differs from `area_sqm_raw × 10.7639104` by more than `cross_field_tolerance` (1%) |
| Price disagreement | `price_inr` differs from `price_display_inr` by more than 1% |

A comparison with a missing restatement is skipped, not treated as a disagreement. The z-score uses the median and MAD, so a single extreme value cannot set its own threshold. Setting `group_outliers_by_month = False` reproduces the original per-shard fault and exists only to keep the root-cause analysis reproducible.

The robust threshold is relative, so the filter is not shift-invariant: adding a constant to one month's prices changes ₹/sqft by a different amount per listing and can change which listings are rejected. This is the documented cause of MR M1's residual violations (`docs/DIAGNOSIS.md`).

## 4. LLM grey-zone review (LLM mode only)

- Candidates: listings in flagged months with `2.0 < |z| <= 3.5`. At most `max_review_months` (3) months, chosen by candidate count then month name; at most 12 listings per month.
- The prompt presents listings **by position, never by ID**, sorted on every displayed field (a total order), de-duplicated on displayed content; a verdict applies to every row with that content. Each constraint was forced by a failing MR (`LLM.md` §4).
- The model may only add listings to the rejection set. It cannot un-reject arithmetic rejections, change values or touch unflagged months.

## 5. Accounting

- **[P4]** `n_rejected_outliers` equals the number rejected in the current computation. Because each recomputation starts again from `raw_listings` with the cumulative flagged months, adding round totals double-counts; the current code does so when more than one round runs.
- Provenance records seed, agent mode, query mode, loop counts, relaxations, coverage score, rejected count, flagged months, `n_no_coordinate` and LLM accounting; **[P3]** also `contract_version` and `snapshot_sha256`.

## 6. Must not

Reject listings outside flagged months; add or modify listings; compute any statistic with a model; or read files or the network.

## 7. Tests

| Test | Status |
|---|---|
| C2 changes the answer, so it is not decorative (`test_cycle2_changes_the_answer_so_it_is_not_decorative`) | exists |
| Robust z unmoved by an extreme outlier (`test_robust_z_is_unmoved_by_an_extreme_outlier`) | exists |
| Statistics identical in both modes (`test_statistics_are_identical_in_both_modes`) | exists |
| Median, sufficiency, empty months, yoy span, ranking ties, units (`tests/test_trend.py`) | exists |
| Golden series unchanged (`tests/test_golden.py`) | exists; regenerated in Phase 3 |
| `median_min_price_inr` / `median_max_price_inr` / `is_partial_month` | **[P3]** |
| `n_rejected_outliers` not double-counted across rounds | **[P4]** |

## 8. Traceability

| This file | Parent |
|---|---|
| §2 Statistics | §5 |
| §3 Recomputation | §7 C2 |
| §4 LLM | §8, `LLM.md` |
| §5 Accounting | §5.2 provenance, §9 |
