# GLOBAL CONTRACT — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal. Full attribution: CREDITS.md.

**Contract ID:** TSE-HYD-MT
**Version:** 2.1.0-draft
**Authority:** This file is the single source of truth for shared constants, the output contract, metric definitions, the agent graph, loop policies, failure semantics, and invariants. `Data.md`, the six agent contracts (`Criteria.md`, `Retrieval.md`, `Coverage.md`, `Analysis.md`, `Critique.md`, `Aggregator.md`), `LLM.md`, `Testing.md`, and `Golden.md` are subordinate. They may clarify implementation but must not redefine global rules. If one conflicts with this file, the global contract wins and the subordinate clause must be corrected.

**Design note.** v2.1 aligns this contract with the team's design note (*TSE – Agent Architecture, Hyderabad Refined*): its output contract, coverage rules, critique outcome and filters are adopted, and every deliberate deviation is listed with its evidence in §13.

**Implementation status.** Phases 3 (porting the v1 data and validation rules) and 4 (harness and agent fixes) and the design-note alignment are complete; every clause below describes current behaviour and is backed by code and a test. Open items that need resources this repository cannot provide (the LLM sweep needs Ollama) are listed in `README.md`.

## 1. Purpose and scope

Build a reproducible multi-agent application that reports a 12-month asking-price trend from a frozen, real Hyderabad residential-listing snapshot, and evaluate it with metamorphic relations (MRs). The assignment evaluates software behaviour, not the predictive accuracy of a housing-market model.

The application reports **asking prices of active sale listings of dwellings observed in the snapshot**. It does not estimate the full Hyderabad market, transaction volume, completed sales, inventory, or current prices. Counts are observed listings in a single-point scrape, not a census.

## 2. Dataset and provenance

- Raw input: `data/raw/hyderabad.csv`, 9,487 rows × 55 columns, SHA-256 `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`. Read-only.
- Canonical derived frame: rebuilt in memory from the raw file on every run by `src/loading.py::load_canonical()`. A copy is frozen to `data/snapshot/listings_canonical.csv` with its SHA-256 in `data/snapshot/CHECKSUMS.txt` as a published record; the application does not read it, and a test checks that a rebuilt frame still matches it (`Data.md` §6). Every dropped row is accounted for in `data/snapshot/canonical_reject_log.csv`.
- The v1 cleaned file (`data/processed/hyderabad_clean.csv`) and its cleaning and audit scripts are not part of v2; they are kept for reference under `legacy/`.
- Source: 99acres.com Hyderabad slice via Kaggle (`arvanshul/gurgaon-real-estate-99acres-com`, licence CDLA-Sharing-1.0; the slug is misleading, the dataset covers Gurgaon, Hyderabad, Mumbai and Kolkata). Scraped ≈ 26 Aug 2023.
- Verify the raw SHA-256 before every run. On mismatch, stop with `snapshot_integrity_error`; never update the expected digest automatically.
- `data/`, `results/` and `tests/golden/` are byte-exact artefacts: `.gitattributes` disables line-ending conversion for them.
- Synthetic data (`data/snapshot/listings_synthetic.csv`) exists only as a labelled oracle check for the MR harness. It is never merged with the real snapshot, never used to fill months, and its results are reported separately from the headline results.

## 3. Shared constants

Constants are defined once in code (`src/contract.py`, `src/loading.py`, `src/agents/state.py::GraphConfig`, `src/mr/harness.py`) and imported elsewhere. Agents must not redefine them.

| Constant | Value | Defined in |
|---|---|---|
| `CONTRACT_VERSION` | `2.1.0-draft` | `src/contract.py` |
| `EXPECTED_SHA256` | raw digest above | `src/loading.py` |
| `INT32_SENTINEL` | `2147483647` | `src/loading.py` |
| `LOCAL_TIMEZONE` | `Asia/Kolkata` | `src/loading.py` |
| `LATEST_POSTING` | `2023-08-26 10:29:05+05:30` (defines the partial month and the age-on-site reference) | `src/loading.py` |
| `DEFAULT_WINDOW_END` | `2023-08` | `src/contract.py` (also `PARTIAL_MONTH`) |
| `WINDOW_LENGTH` | 12 months | `src/trend.py::month_window` |
| `ADEQUATE_N` / `adequate_n` | 30 usable price-and-area records: a month is `ADEQUATE` (design note §4.3) | `src/contract.py`, `GraphConfig` |
| `MIN_SUFFICIENT_N` | 50 price-valid listings: months the headline move is measured between (§13 D-3) | `src/contract.py` |
| `coverage_target` | 0.50 (share of window months that are `ADEQUATE`) | `GraphConfig` |
| `max_retry_rounds` | 2 (loop C1; design note §4.3.4) | `GraphConfig` |
| `max_critique_rounds` | 1 (loop C2) | `GraphConfig` |
| `n_retrieval_agents` | 4 | `GraphConfig` |
| `robust_z_threshold` | 3.5 | `GraphConfig` |
| `jump_threshold_pct` | 25.0 | `GraphConfig` |
| `cross_field_tolerance` | 0.01 | `GraphConfig` |
| `SEEDS` | `(11, 23, 47)` | `src/mr/harness.py` |
| `MIN_BASE_INPUTS` | 36 (brief requires ≥ 30) | `src/mr/base_inputs.py` |
| `REL_TOL` | `1e-9` | `src/mr/relations.py` |
| `CI_LEVEL` | 95%, Wilson score | `src/mr/harness.py` |

## 4. Population and month rules

### 4.1 Canonical population and price validity

A raw row is a **canonical listing** if (drop cascade, `canonical_reject_log.csv`):

1. `PREFERENCE == "S"` (sale; rent and PG excluded — §13 D-2).
2. `PROPERTY_TYPE` is a dwelling type listed in `Data.md` (land and plots excluded).
3. `POSTING_DATE` parses as Unix milliseconds (§13 D-1).

A canonical listing is **price-valid** (`price_valid`) if all hold; otherwise it is kept, flagged, and counted in `listing_count` but not in any price statistic (`canonical_price_validity.csv`):

4. `PRICE` text is not "Price on Request".
5. `MIN_PRICE` is numeric, finite, `> 0` and `!= INT32_SENTINEL`; `MAX_PRICE` satisfies the same, and `MIN_PRICE <= MAX_PRICE`.
6. Area parses from the `AREA` display string in sq ft and is `> 0` (never from `MIN_AREA_SQFT`, which holds square metres; `Data.md` D1).

The representative asking price is `(MIN_PRICE + MAX_PRICE) / 2` (design note §2). Measured: 4,975 canonical listings, 4,574 price-valid; every price-valid listing has `MIN_PRICE == MAX_PRICE`. Raw rows are never modified.

### 4.2 Month assignment

Parse `POSTING_DATE` as Unix milliseconds, convert the instant to `Asia/Kolkata`, then derive `month = YYYY-MM`. Do not derive the month from UTC. (Measured: 18 canonical rows change month between UTC and IST.)

### 4.3 Window

A report covers exactly 12 consecutive calendar months ending at `window_end` (inclusive). `window_end` is movable; the default is `2023-08`. Months with no listings are still reported (count 0, statistics `null`). `2023-08` is a partial month (last posting 26 Aug) and is flagged `is_partial_month = true`; it is never extrapolated.

### 4.4 Identity

`listing_id` is unique within the canonical frame. It is derived from `PROP_ID` plus the raw row position, because `PROP_ID` alone is not unique (one ID appears on two rows). Both rows are kept; a repeated `PROP_ID` is not evidence of a duplicate listing.

## 5. Output contract

Every MR is a statement about these fields and nothing else. Defined in `src/contract.py`.

### 5.1 `MonthStat` (one per window month, in order)

| Field | Definition |
|---|---|
The first six rows are the design note's output contract (§2); the rest are extensions.

| Field | Definition |
|---|---|
| `month` | `YYYY-MM` |
| `listing_count` | canonical listings in the month matching the criteria, **including** those without a valid price or area and those cycle 2 rejected |
| `price_valid_count` | of those, the price-valid listings not rejected by cycle 2: the common eligible set for both medians |
| `median_listing_price_inr` | median representative price `(MIN_PRICE + MAX_PRICE) / 2`, in display currency |
| `median_price_per_sqft_inr` | median representative price ÷ parsed area, in display units |
| `coverage_status` | `ADEQUATE` if `price_valid_count >= ADEQUATE_N`; `NO_DATA_IN_SNAPSHOT` if `listing_count == 0`; otherwise `LIMITED` |
| `median_min_price_inr`, `median_max_price_inr` | *extension* — medians of each bound (contract v2 decision 7; equal to the listing price on this snapshot) |
| `p25_psf`, `p75_psf` | *extension* — quartiles of price per sqft (numpy linear interpolation) |
| `median_age_on_site_days` | *extension* — median (latest posting − posting date); right-censored and length-biased; no MR asserts on it |
| `month_is_sufficient` | *extension* — `price_valid_count >= MIN_SUFFICIENT_N`; the months the headline move spans |
| `is_partial_month` | *extension* — `true` for the month containing `LATEST_POSTING` |

A statistic that cannot be computed is `null`, never zero. Medians use the mean of the two middle values for even counts.

### 5.2 `TrendReport`

| Field | Definition |
|---|---|
| `window_months` | exactly 12 months, ascending |
| `monthly` | 12 `MonthStat`, aligned with `window_months` |
| `locality_rankings` | localities with ≥ 5 listings in the window, ranked by median ₹/sqft descending, ties broken by name; top 10 |
| `yoy_median_psf_pct` | *extension* — % change in `median_price_per_sqft_inr` between the first and last **sufficient** month; `null` if fewer than two |
| `yoy_span_months` | months spanned by that comparison (may be < 12) |
| `n_listings_total` | sum of `listing_count` |
| `n_price_valid_total` | sum of `price_valid_count` |
| `currency_unit` | `INR`, `INR_LAKH` or `INR_CRORE` |
| `area_unit` | `SQFT` or `SQM` |
| `criteria` | the effective (possibly widened) criteria |
| `provenance` | seed, agent mode, query mode, loop counts, relaxations, coverage score, rejected count, flagged months, LLM accounting, `contract_version`, `snapshot_sha256` (of the snapshot the frame was derived from), `coverage_verdict` (`ACCEPT`/`LIMITED`), `review_status` (`APPROVED`/`NEEDS_REVIEW`) |

Construction fails with a contract violation if the window is not 12 months, rows are misaligned, or `yoy_median_psf_pct` is non-finite.

### 5.3 Units

Price-band criteria are always in rupees. Display units only scale reported levels: ₹ lakh = ₹ × 1e-5, ₹ crore = ₹ × 1e-7, sq m = sq ft × 1/10.7639104. Percentages, counts and rankings are unit-independent.

### 5.4 Errors

Domain errors at the request boundary return `{"status": "error", "error_code": ..., "message": ...}` with a stable code (`Criteria.md` §4). Unexpected programming exceptions propagate; they are never disguised as a successful report.

## 6. Multi-agent architecture

Six agents over a shared `TrendState` (`src/agents/state.py`), compiled as a LangGraph `StateGraph` (`src/agents/graph.py`):

```
CriteriaAgent → RetrievalDispatch → Retrieval_0..3 (parallel) → RetrievalMerge → CoverageAgent
CoverageAgent --(insufficient, C1)--> RetrievalDispatch
CoverageAgent --(sufficient / cap)--> AnalysisAgent → CritiqueAgent
CritiqueAgent --(rejected, C2)--> AnalysisAgent
CritiqueAgent --(approved / cap)--> AggregatorAgent → END
```

| Agent | Contract | Reads | Writes |
|---|---|---|---|
| Criteria | `Criteria.md` | `filter_spec`, `user_query` | `filter_spec`, `query_mode` |
| Retrieval ×4 | `Retrieval.md` | `filter_spec` / `widened_filter_spec`, `frame`, `seed`, `retry_count` | `retrieval_report`, `raw_listings`, `n_no_coordinate` |
| Coverage | `Coverage.md` | `raw_listings`, effective spec | `coverage_score`, `coverage_verdict`, `widened_filter_spec`, `retry_count`, `relaxations`, `relax_levers` |
| Analysis | `Analysis.md` | `raw_listings`, `critique_complaint`, `flagged_months` | `trend_stats`, `n_rejected_outliers` |
| Critique | `Critique.md` | `trend_stats`, `raw_listings` | `critique_verdict`, `critique_complaint`, `flagged_months`, `critique_rounds` |
| Aggregator | `Aggregator.md` | `trend_stats` | `final_report`, `narrative` |

The brief's three control-flow requirements:

- **(a) Feedback loop:** C2, Critique → Analysis, carrying named flagged months for targeted recomputation.
- **(b) Conditional/iterative control:** C1, Coverage decides from `coverage_score` whether to widen and re-run retrieval or proceed.
- **(c) Genuine dependency:** Criteria sets `query_mode`; Retrieval then runs a different algorithm (locality set membership vs haversine radius search).

## 7. Loop policies

### C1 — Coverage widening

- `coverage_score = ADEQUATE months / 12` (≥ `ADEQUATE_N` usable price-and-area records). Verdict `ACCEPT` when `coverage_score >= coverage_target`.
- Otherwise widen one lever per round, each lever at most once, in the design note's order: geography, BHK (±1), price band (×0.75 / ×1.25). Geography widening doubles the radius, or adds each selected locality's own depth-doubling neighbourhood (`Coverage.md` §3); it never removes the locality constraint and it preserves set inclusion (a subset widens to a subset). A narrow query can therefore end below the coverage target with its levers exhausted: the answer stays about the place asked for.
- At most `max_retry_rounds` (2) retries. Stop early when no lever applies, or when the slice already covers every month the **whole snapshot** can cover — further widening cannot add historical records (design note §4.3.4). Below target the verdict is `LIMITED` and the gap is reported, never filled. Every relaxation is recorded in `relaxations` and shown to the user.

### C2 — Critique recomputation

- At most `max_critique_rounds` rounds. A round fires only when the critique flags months not already flagged.
- The critique checks named invariants first (`price_valid_count <= listing_count`; a median exists iff `price_valid_count > 0`; medians positive; `coverage_status` agrees with the counts), then jumps and contextual outliers. A complaint names the invariant and the months.
- Recomputation may reject listings only within flagged months, by the rules in `Analysis.md`. A rejected listing loses its price (`price_valid`), not its place in `listing_count`. Nothing is added and no value is changed.
- The critique evaluates the post-rejection listings, and `n_rejected_outliers` reports the current round's rejections (not a running sum).
- If the critique still finds a new problem after its last permitted round, the report is labelled `NEEDS_REVIEW` (`provenance.review_status`, and the summary says so), never silently approved.

Both loops terminate by construction. Loop counts are recorded in `provenance` and every iteration appears in `trace`.

## 8. Determinism and model boundaries

- Every statistic is computed by deterministic Python (`src/trend.py`). No model computes or revises a number.
- `agent_mode = DETERMINISTIC` is the default and requires no network or model. `agent_mode = LLM` is optional; its permitted judgments are limited by `LLM.md`.
- Identical frame, criteria, config and seed produce an identical `TrendReport`.
- No hidden network, file or clock reads inside agents; the snapshot is loaded and verified once at startup.

## 9. Trace and reproducibility

- `trace` records each agent step with `step`, `agent` and decision details, including every loop iteration and its reason.
- One-command reproduction of the headline table: `python scripts/headline_table.py --check` (from committed records) or `python scripts/run_harness.py --tag <tag>` (full re-run).
- `NOTEBOOK.md` records what was tried; `AI_USE.md` records AI assistance, including where it was wrong.

## 10. Acceptance criteria

1. Raw snapshot integrity is verified and the raw file is unchanged.
2. Months are derived in `Asia/Kolkata` from millisecond timestamps.
3. Every report has exactly 12 ordered months; the partial month is flagged.
4. The canonical population follows §4.1 and every exclusion is counted.
5. Statistics are deterministic, `null` where undefined, and independent of LLM calls.
6. Both loops terminate within their caps, and a committed trace shows each firing.
7. At least 8 MRs cover invariance, monotonic and directional families; each states transformation, relation, subdomain, tolerance and the fault it exposes (`Testing.md`).
8. Each MR has ≥ 30 distinct base inputs and k ≥ 3 recorded seeds; violation rates and Wilson 95% CIs are computed over base inputs.
9. The three most-violated MRs are diagnosed with evidence (`docs/DIAGNOSIS.md`).
10. One-command reproduction, `NOTEBOOK.md`, `AI_USE.md`, the frozen snapshot and committed results are present.

## 11. Changes from v1.0.0-draft

| # | v1 rule | v2 rule | Why |
|---|---|---|---|
| 1 | Fixed window 2022-09 → 2023-08 | Movable `window_end`, default 2023-08 | The window-shift MR requires it |
| 2 | August labelled `partial_month` | `is_partial_month` flag kept | Retained from v1 |
| 3 | All dated rows counted; sale subset for prices | Sale dwellings only | Prices per sq ft are only comparable for dwellings; rent/PG/land are different markets |
| 4 | `Asia/Kolkata` | Kept | Retained from v1; implementation was UTC |
| 5 | Price on Request excluded from prices | Excluded from the population | Retained from v1 |
| 6 | Sentinel excluded | Kept, plus zero prices | Retained |
| 7 | `MIN_PRICE` and `MAX_PRICE` medians | Kept; ₹/sqft from `MIN_PRICE` | Retained from v1; ₹/sqft needs one price |
| 8 | `PRICE_SQFT` unverified, no ₹/sqft | ₹/sqft = `MIN_PRICE` / parsed area | Area unit verified (`Data.md` D1) |
| 9 | Hyderabad + Secunderabad | Kept | Retained |
| 10 | Repeated `PROP_ID` kept | Kept, with a unique `listing_id` | Retained; uniqueness needed by retrieval and MR I4 |
| 11 | No synthetic data | Labelled oracle check only | Separate from headline results |
| 12–15 | `median_min/max_price_inr`, status fields | `MonthStat` / `TrendReport` above | One output surface for all MRs |
| 16–18 | No user filters | Validated filters (`Criteria.md`) | Criteria are the base inputs MRs perturb |
| 19 | Planner, Scanner, Validator, Anomaly, Diagnostic, Reporter | Criteria, Retrieval, Coverage, Analysis, Critique, Aggregator | Matches the implementation |
| 20 | Coverage repair disabled | C1 with three levers, cap 3 | Brief requirement (b) |
| 21 | Critique revision cap 2 | Cap 1 | Measured: 2/16 violations at two rounds, 0/16 at one |
| 22 | — | Geography widening keeps a locality constraint (nearest localities until depth doubles) | Otherwise every run collapsed to the whole metro and MR M3 was vacuous |
| 23 | Model modes off/replay/live | `DETERMINISTIC` / `LLM` with response cache | Matches the implementation |
| 24 | CI over runs | CI over base inputs | Seeds are not independent samples |

## 13. Deviations from the design note, with evidence

The design note (*TSE – Agent Architecture, Hyderabad Refined*) is adopted in v2.1 — output contract, coverage threshold and verdicts, retry cap and lever order, NEEDS_REVIEW, city and locality-ID filters, `GEO_RADIUS`, the range-overlap price band, `data/SOURCE.md`. These are the deliberate differences:

| # | Design note | This contract | Evidence |
|---|---|---|---|
| D-1 | Months from `REGISTER_DATE__U` | Months from `POSTING_DATE` (IST) | The note's monthly counts reproduce exactly on the raw file (0, 2, 0, 1, 0, 5, 20, 65, 145, 770, 4,024, 4,455), confirming its reading. But `REGISTER_DATE__U` equals `POSTING_DATE` on 3,753 rows and is **later** on 5,389 (by up to 70+ days), so it is a refresh date, not the listing date. On price-valid listings it leaves 4 of 12 months `ADEQUATE` (0, 2, 0, 0, 0, 2, 8, 28, 82, 373, 1,981, 2,098); `POSTING_DATE` gives 7 (25, 35, 27, 29, 22, 23, 61, 159, 309, 544, 1,711, 1,588), so the trend and the month-comparing MRs have something to compare. Cost: `POSTING_DATE` is missing on 242 raw rows (110 sale dwellings), which are excluded. The v1 implementation made the same choice. |
| D-2 | All listings; property type is a user filter | Sale (`PREFERENCE == "S"`) dwellings only | Rent (1,467 rows) and PG (93) carry monthly rents in `MIN_PRICE`/`MAX_PRICE`, not asking prices; land (2,806 of the 2,814 rows without a BHK) has no built-up area for price per sqft. Mixing them would make the medians meaningless. Property type remains a user filter within dwellings. |
| D-3 | No headline field; one threshold (30) | Extension `yoy_median_psf_pct` between months with ≥ 50 price-valid listings; `ADEQUATE` at 30 as in the note | At 30 the headline uses 2022-10 (35 listings) as its first month and reads +18.35%; at 50 it reads −6.41%; the external RESIDEX index reads +6.8% (`REPORT.md` §9). The headline is an extension, so its threshold is kept separate from the note's coverage threshold and reported with its sensitivity. |
| D-4 | Up to two critique recomputations | One (`max_critique_rounds = 1`), plus `NEEDS_REVIEW` | Measured on the count-monotonicity relation: 2/16 violations with two rounds, 0/16 with one (`GraphConfig` note): the flagged set grows between rounds and the relative threshold is not idempotent. `NEEDS_REVIEW` keeps the cap visible; no harness base input ends `NEEDS_REVIEW`. |
| D-5 | One Retrieval agent | Four parallel Retrieval agents | The brief asks for "several cooperating agents each scan listings". The answer is independent of the agent count (tested at 1, 2, 4, 8). |
| D-6 | LLM only for request parsing and explanations | Optional LLM mode also judges grey-zone listings and suspect months | Off by default; the headline sweep runs deterministic, as the note requires. The pre-v2 LLM sweeps show the cost of a judge that changes which listings count (`REPORT.md` §8), which is the note's reason for the restriction. |
| D-7 | Eight MRs (MR1–MR8) | Twelve (I1–I5, M1–M4, M1raw, D1, D2) | Superset; mapping in `Testing.md` §4. MR2 is tested as a display-unit change with the band kept in rupees (I2, I5) rather than rescaling the filter bounds; MR8's tolerance is 1e-9, stricter than the note's 1e-6. |
| D-8 | Audit the repeated `PROP_ID` with a tie-break rule | Keep both rows, each with a unique `listing_id` | The two rows differ only in `PRIMARY_TAGS`; keeping both needs no tie-break and matches the note's "unique canonical_row_id to each retained row". |
| D-9 | "Hyderabad by default, Secunderabad … explicitly included" | Both cities by default; `cities` filter selects either | The note's scope is the "Hyderabad–Secunderabad metro"; reading the default as both keeps 438 Secunderabad listings (395 price-valid) in the metro trend. Either city alone is one filter away. |
| D-10 | `start_month` and `end_month` | `window_end`; the start is 11 months earlier | The window is always 12 calendar months (note §1–2), so the start is determined by the end. |

## 12. Change control and context budget

Each contract file stays below 8,000 tokens; this is a ceiling, not a target. Keep code, raw data and long result tables out of contract text. Any change to constants, schemas, the population, loop caps or MR semantics requires a version change here first, then the subordinate contract, then tests. Unresolved source semantics are marked as open decisions, never replaced by an assumption.
