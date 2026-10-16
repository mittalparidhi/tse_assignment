# Metamorphic Testing of a Multi-Agent Housing-Trends Application

**TSE Assignment — Final Report**
Market: Hyderabad / Secunderabad (the brief's optional Indian-metro route)

**How to read the results.** The headline results are the **contract-v2
sweeps** (`contracts/CONTRACT.md` v2.1.0-draft): a deterministic sweep (§7.1)
and the same sweep with the local model switched on (§7.2), each over twelve
relations, 72 base inputs and three seeds. Earlier sweeps, run before the two
team implementations were merged, are kept with their diagnoses in
`docs/DIAGNOSIS.md` and quoted here only where they explain a v2 result.

---

## 1. Introduction

This report describes a six-agent application that reads a frozen snapshot of
Hyderabad residential listings and reports how asking prices moved over twelve
months, and the metamorphic suite built to find faults in it without knowing
the correct answer to any query.

Given "3 BHK in Gachibowli, ₹80 lakh to ₹4 crore, the twelve months to August
2023", nobody can say what the correct median price per square foot was.
Metamorphic testing replaces that missing oracle with relations between runs:
reordering the input must not move the trend, duplicating every listing must
double the counts and leave the medians alone, scaling prices by *k* must scale
the medians by *k*. A violated relation exposes a fault without knowing any
single right answer.

**What the relations found.**

- **Genuine agent faults, each fixed and re-measured:** geography widening that
  broke locality-set inclusion (M3, 9/36 → 0/36); a listing review that cut its
  batch before removing duplicates (I3 in LLM mode, 8/72 → 0/72); before the
  merge, an outlier threshold computed per *(worker, month)* (I3 and I4 on all
  108 runs) and four prompts that leaked information a judgment must not
  depend on.
- **An unsound relation:** adding a constant to prices while a price band stays
  in place changes the selected population (`M1raw`, kept as the
  counter-example).
- **A limit of the architecture:** a model judge whose verdict changes which
  listings are counted cannot satisfy relations that change what it is shown
  (D1, D2, part of M1).
- **A threat to the headline:** the reported year-on-year move depends on the
  sufficiency threshold, and at the contract's threshold it has the opposite
  sign to the official index (§9).

## 2. Data source

| | |
|---|---|
| Dataset | 99acres.com residential listings, Hyderabad slice |
| Origin | Kaggle `arvanshul/gurgaon-real-estate-99acres-com`, titled *"Indian Real Estate – 99acres.com"*; despite the slug it covers Gurgaon, Hyderabad, Mumbai and Kolkata (verified on the dataset page) |
| Licence | Community Data License Agreement – Sharing – v1.0 |
| Scrape date | ≈ 26 August 2023 (latest `POSTING_DATE`) |
| Raw size | 9,487 rows × 55 columns |
| Integrity | SHA-256 `9e81698322606c86…`, checked on every load |

The raw file is never modified; `verify_snapshot()` aborts if the checksum
changes. Months are calendar months in `Asia/Kolkata` (UTC would move 18
listings into the previous month). Full provenance: `data/SOURCE.md`.

**Population.** Sale listings of dwellings with a parseable `POSTING_DATE`:

```
raw rows                         9487
sale only (PREFERENCE=S)         7927   -1560
dwellings only                   5085   -2842
parseable POSTING_DATE (IST)     4975    -110
canonical listings               4975   (4574 with a usable price and area)
```

Listings without a usable price stay in the frame, flagged: they count in
`listing_count` but not in the price statistics (§3).

**Defects found and how they are handled** (evidence in `contracts/Data.md`):

| Defect | Evidence | Handling |
|---|---|---|
| `MIN_AREA_SQFT` holds **square metres** | `AREA` string ÷ column = **10.7639** at both the 5th and 95th percentile (3,531 rows) | area parsed from the display string |
| int32 sentinel and zero prices | `MIN_PRICE`/`MAX_PRICE` = 2,147,483,647 on 5 rows, 0 on 75 | not price-valid |
| sale, rent and PG mixed | `PREFERENCE` S 7,927, R 1,467, P 93 | sale only |
| `BEDROOM_NUM` missing on 29.7% | 2,806 of the 2,814 are `Residential Land` | dwellings only |
| "Price on Request" | 87 raw rows carry placeholder bounds | not price-valid |
| area-entry errors in the tail | a 27 sqft "villa" at ₹2.15 crore | **kept**, for cycle 2 to catch (§4.2) |

The square-metre column is the consequential one: trusting the name would
inflate every price-per-area figure 10.76×, and the ratio being identical at
both tails is what separates mislabelling from noise.

**The snapshot's own limit.** It is a single scrape, so older months hold only
listings still live on the scrape date: **96.4% of the window's listings fall
in its final six months**. §9 shows this dominates the study's uncertainty. A
**synthetic snapshot** with uniform monthly depth is built alongside; it is the
only place with a genuine oracle.

## 3. The output contract

Fixed before any relation was written, because "the trend is unchanged" cannot
be falsified until "the trend" is a named set of numbers (`src/contract.py`,
`TrendReport`):

| Field | Meaning |
|---|---|
| `window_months` | exactly twelve months, ascending |
| `monthly[]` | per month: `listing_count` (all matching listings), `price_valid_count`, `median_listing_price_inr` (median of (MIN + MAX) / 2), `median_price_per_sqft_inr`, `coverage_status` (ADEQUATE ≥ 30 usable listings / LIMITED / NO_DATA_IN_SNAPSHOT); extensions: min/max-price medians, ₹/sqft quartiles, `median_age_on_site_days`, `month_is_sufficient` (n ≥ 50), `is_partial_month` |
| `locality_rankings[]` | localities by median ₹/sqft, with explicit `rank` |
| `yoy_median_psf_pct`, `yoy_span_months` | move between the first and last **sufficient** month, and how many months that spans |
| `currency_unit`, `area_unit` | display units, carried so unit invariance is observable |
| `criteria`, `provenance` | the slice described; seeds, loop counts, verdicts, LLM accounting |

Three choices exist so that relations mean something. **Medians, not means**:
the price tail is contaminated, and a mean would fail every invariance relation
for reasons unrelated to the agents. **Counts separate from prices**: duplication
doubles counts and leaves medians fixed, and a fused statistic would hide
exactly what the relations test. **The span of the "year-on-year" move is
reported**: it runs between sufficient months, often far fewer than twelve. A
missing median is `null`, never zero, and August 2023 is flagged partial.
`median_age_on_site_days` is right-censored and length-biased, so it is not
called days on market and no relation asserts on it.

## 4. Agent architecture

Six agents over a shared LangGraph state. The graph carries two cycles, both
real conditional edges:

```
                 ┌────────────────────────────────────────┐
                 │                                        │ cycle 1
                 v                                        │ coverage < target
      CriteriaAgent ──> RetrievalDispatch ──> Retrieval_0..3
                                │                    │
                                └──> RetrievalMerge ──> CoverageAgent
                                                            │ proceed
                                                            v
                        ┌──── cycle 2 ────┐          AnalysisAgent
                        │  complaint +    │                │
                        │  flagged months v                v
                        └──────────── CritiqueAgent ──> AggregatorAgent ──> report
```

| Agent | Reads | Writes |
|---|---|---|
| **Criteria** | request | `filter_spec`, `query_mode` |
| **Retrieval** ×4 | `filter_spec`, `query_mode`, round | shard of matching listings |
| **Coverage** | merged listings | `coverage_score`, ACCEPT / RETRY / LIMITED, `widened_filter_spec` |
| **Analysis** | listings, `critique_complaint` | `trend_stats` |
| **Critique** | `trend_stats` | APPROVED / REJECTED / NEEDS_REVIEW, flagged months |
| **Aggregator** | `trend_stats`, coverage | `final_report`, narrative |

### 4.1 The three required control-flow properties

**(a) Feedback loop.** Cycle 2, Critique → Analysis: a rejection names the
months at fault, and Analysis recomputes only those, rejecting outliers by a
robust z-score on log ₹/sqft. At most one recomputation; a problem still open
after it is reported as NEEDS_REVIEW.

**(b) Conditional, iterative step.** Cycle 1, Coverage → Retrieval:
`coverage_score` is the share of the twelve months with at least 30 usable
listings. Below the target (0.5) Coverage widens one criterion — geography,
then BHK, then price band, each at most once, at most two retries — and
retrieval runs again; if the target cannot be reached it proceeds with
**LIMITED** coverage and reports the gap. Geography widening keeps the locality
constraint: each selected locality adds its own nearest neighbours, which
preserves set inclusion (§8.4). Both cycles are capped, so the graph
terminates.

**(c) Genuine dependency.** Criteria sets `query_mode`, and Retrieval runs a
**different algorithm** for each: exact locality matching, or a haversine
radius search that excludes listings without coordinates (5.3% of those with
a usable price).

**Several cooperating agents.** Retrieval fans out to four parallel nodes, each
scanning the shard given by a stable `sha256(seed:listing_id)`; a merge node
reassembles them in canonical order. A test checks the answer is identical with
1, 2, 4 and 8 agents.

### 4.2 Why the loops are necessary rather than decorative

**Cycle 1 is forced by the data.** "3 BHK in Gachibowli" matches 120 listings,
and only **two** months have 30 usable ones. Without the loop the system
returns mostly empty months or silently answers a broader question. With it,
coverage goes **0.167 → 0.250 → 0.333** as Gachibowli gains its 15 nearest
localities and then BHK widens to 2–4 (120 → 432 → 696 listings), and the
report states what was relaxed. A linear pipeline cannot do this: the decision
to widen depends on an aggregate that exists only after retrieval. The run then
stops at **LIMITED**: the whole snapshot could cover at most 7 months for this
query, and the report says so instead of answering for the whole metro, which
is what the pre-merge geography lever did.

**Cycle 2 is forced by the area-entry errors.** A 400 sqft villa at ₹8.3 crore
is plausible alone and suspicious only against its month, so no blanket filter
catches it, and validating every listing on every run would discard legitimate
luxury stock. Escalating only for months whose aggregate looks wrong is why the
complaint carries flagged months. On the query above, cycle 2 rejects **17
listings**, moves **4 monthly medians** (up to 11.6%) and changes the reported
move from **−4.45% to −0.70%**; on the whole metro it rejects 132 and moves the
headline from −6.41% to −7.74%.

### 4.3 Execution trace: both cycles firing

Abridged from `results/v2_deterministic/trace_example.txt` ("3 BHK in
Gachibowli", seed 7):

```
 7. RetrievalMerge   agents=4  round=0  listings=120
 8. CoverageAgent    coverage=0.1667  covered=2 of 7 attainable  verdict=RETRY    + 15 neighbouring localities (cycle 1)
14. RetrievalMerge   agents=4  round=1  listings=432
15. CoverageAgent    coverage=0.25    covered=3 of 7             verdict=RETRY    BHK [3] -> [2, 3, 4] (cycle 1)
21. RetrievalMerge   agents=4  round=2  listings=696
22. CoverageAgent    coverage=0.3333  covered=4 of 7             verdict=LIMITED  decision=PROCEED
23. AnalysisAgent    mode=full  listings=696  move_pct=-4.45
24. CritiqueAgent    flagged 5 months  verdict=REJECTED -> recompute flagged months (cycle 2)
25. AnalysisAgent    mode=targeted recomputation  rejected=17  move_pct=-0.70
26. CritiqueAgent    flagged 2 months, none new  verdict=APPROVED
```

Cycle 1 fires twice and cycle 2 once, and the answer changes at step 25.

### 4.4 Where the local model sits

In LLM mode, agents delegate judgment to Qwen2.5-3B-Instruct (Q4_K_M) through
Ollama: Analysis asks which **grey-zone** listings (robust |z| between 2.0 and
3.5) their own description contradicts; Critique asks which months look
implausible; Aggregator writes the summary when there is a price change;
Criteria can choose `query_mode` for a free-text request. **Every statistic
stays deterministic Python**: the model supplies judgment and wording, never
arithmetic. Temperature is 0 and the harness seed reaches the model on every
call; a probe of 20 identical requests returned 20 identical replies, so an
unchanged prompt means an unchanged judgment.

The team's design note is adopted in contract v2.1; its ten deliberate
deviations — for example months from `POSTING_DATE` rather than
`REGISTER_DATE__U`, which leaves 4 instead of 7 months coverable — are listed
with evidence in `contracts/CONTRACT.md` §13.

## 5. The metamorphic relation catalogue

Twelve relations across the three families (the minimum is eight), each a
statement about `TrendReport` fields only. For every relation: the relation
and why it should hold, the subdomain, the tolerance, and the fault a
violation would expose. Floats are compared with `math.isclose` on unrounded
values; counts exactly. Full definitions and the mapping to the design note's
MR1–MR8: `contracts/Testing.md` §4.

### 5.1 Invariance

| ID | Transformation | Relation, and why it should hold | Subdomain | Tolerance | Fault exposed |
|----|---------------|----------------------------------|-----------|-----------|---------------|
| **I1** | permute the listing rows | every field unchanged: a trend is a property of the set of listings, not their order | all inputs | counts exact; floats 1e-9 | order-dependent aggregation; unstable tie-breaks; shards leaking row order |
| **I2** | display ₹ → ₹ lakh, sqft → sq m | counts, statuses, rankings, % changes identical; ₹/sqft scales by the unit factor: units are presentation | all inputs; band kept in rupees | 1e-9 | hard-coded units; the square-metre confusion; rounding before percentages |
| **I3** | duplicate every listing | counts exactly double; per-month medians unchanged: repeating every value does not move a median | year-on-year fields excluded (doubling makes 25–49-listing months sufficient) | medians 1e-9; counts exact 2× | silent de-duplication; double counting; per-row judgments |
| **I4** | bijectively relabel listing IDs | every field unchanged: an identifier says nothing about price | all inputs | exact | logic keyed on IDs (shard hashing, prompts) |
| **I5** | display ₹ lakh → ₹ crore | as I2, factor 10⁻²: the brief's Indian-metro case, "converting ₹ crore ↔ ₹ lakh … must not move the trend or the rankings" | lakh projection of each input | 1e-9 | hard-coded currency; rounding before percentages |

### 5.2 Monotonic

| ID | Transformation | Relation, and why it should hold | Subdomain | Tolerance | Fault exposed |
|----|---------------|----------------------------------|-----------|-----------|---------------|
| **M1** | add ₹500,000 to both price bounds in the densest month | that month's price medians rise by ₹500,000; other months and all counts unchanged: a shift moves a median by the shift | **band-free projection**, so the shift cannot change which listings are selected | \|Δ − X\| ≤ 1e-6·X; others 1e-9 | month-bucketing leaks; filters applied after the transform |
| **M1raw** | as M1, price band left in place | as M1 — **does not hold**: kept as the documented counter-example (§8.1) | none | as M1 | none; the relation itself is unsound |
| **M2** | widen the price band 25% each side | each month's `listing_count` ≥ before: a superset filter cannot select fewer | inputs with a band | exact inequality | filter inversion; off-by-one on bounds; stale cached criteria |
| **M3** | keep the first half of the locality list | each month's `listing_count` ≤ before: a subset of places cannot hold more listings | inputs with ≥ 2 localities | exact inequality | leakage between shards; widening that breaks set inclusion (found, §8.4) |
| **M4** | halve the search radius | each month's `listing_count` ≤ before: a smaller disc is contained in the larger | radius inputs | exact inequality | wrong distance formula; unlocated rows leaking into a radius query |

### 5.3 Directional

| ID | Transformation | Relation, and why it should hold | Subdomain | Tolerance | Fault exposed |
|----|---------------|----------------------------------|-----------|-----------|---------------|
| **D1** | shift the window forward one month | the eleven overlapping months' counts, statuses and medians match: a month's statistics cannot depend on which window contains it | both windows inside the data | counts exact; floats 1e-9 | window off-by-one; bucketing drift; state carried between runs |
| **D2** | scale all prices (and the band) by k = 1.5 | every price median scales by exactly k; % changes, rankings and counts unchanged: medians are scale-equivariant, and scaling the band keeps the population fixed | all inputs | 1e-9 | unit mishandling; non-linear aggregation |

**Stated in advance.** M2, M3 and M4 change listing counts, which can change
which cycle-1 levers fire and so the population for the whole window; they are
also reported over the **control-path-stable subdomain**, where both runs took
the same path. Cycle 2's relative outlier filter can also change the analysed
population, so every run records how many listings it rejected in each run.

## 6. Statistical protocol

- **72 distinct base inputs**: 36 locality inputs (strided over window end,
  BHK, price band and locality set) and 36 radius inputs (centres at the six
  deepest localities, 3–5 km). Each relation runs on the inputs in its
  subdomain: at least 36 for every relation.
- **k = 3 fixed, recorded seeds `[11, 23, 47]`**, used for source and
  follow-up alike: **2,592 checks per sweep**, each two full pipeline runs.
- **The base input is the unit.** A base input counts as violated if any seed
  violates. Its three seeds are repeated measurements of one input, not
  independent samples, so intervals over runs would overstate precision (0/108
  runs gives an upper bound of 0.034; 0/36 inputs, 0.096). The per-run rate and
  the number of inputs whose seeds disagreed are also recorded.
- **95% Wilson score intervals**, because rates sit at or near 0 and 1, where
  the normal approximation leaves [0, 1] or collapses to zero width. 0/72 gives
  **[0.000, 0.051]**.
- **Stopping rule.** A zero-violation relation is bounded at 0.051 (0.096 for
  the 36-input relations), enough to say it fails on fewer than one input in
  ten; every non-zero rate has an interval clearly separated from zero. The
  sweeps were therefore not extended.

## 7. Results

### 7.1 The deterministic sweep

`results/v2_deterministic/`, rebuilt by `python scripts/headline_table.py --v2`
from the per-run records. Unit = base input.

| MR | Family | Bases | Rate | 95% CI | Stable-path rate |
|----|--------|------:|-----:|--------|-----------------:|
| I1–I5 | invariance | 72 | **0.000** | [0.000, 0.051] | 0.000 |
| M1 | monotonic | 72 | **0.194** | [0.120, 0.300] | 0.194 |
| M2 | monotonic | 72 | **0.000** | [0.000, 0.051] | 0.000 |
| M3 | monotonic | 36 | **0.000** | [0.000, 0.096] | 0.000 |
| M4 | monotonic | 36 | **0.000** | [0.000, 0.096] | 0.000 |
| M1raw | monotonic | 71 | **0.718** | [0.605, 0.810] | 0.718 |
| D1, D2 | directional | 72 | **0.000** | [0.000, 0.051] | 0.000 |

Seeds disagreed on no base input; the cycle-1 path diverged in 42 of 2,592
runs. M1raw has 71 inputs because one (`base10`) has no listing inside its
window once the band is kept. Before M3's fix the same sweep gave M3 0.250 and
M2 0.028 (`results/v2_before_m3fix/`); the sweep before the design-note
alignment is `results/v2_before_note_alignment/`. On the **synthetic snapshot**
M2 (0.028) and M3 (0.111) fail only on runs whose control path diverged, and
are 0.000 on the stable subdomain.

### 7.2 The LLM sweep

`results/v2_llm/`: the same inputs, seeds and relations with the model agents
on (`qwen2.5:3b-instruct-q4_K_M`, Ollama 0.40.4, weights digest `357c53fb…`,
Kaggle T4). *Before fix* is `results/v2_llm_before_reviewfix/`, the same sweep
before the I3 fault of §8.4 was fixed.

| MR | Bases | Deterministic | Before fix | **LLM** | 95% CI | Seeds disagree |
|----|------:|--------------:|-----------:|--------:|--------|---------------:|
| I1, I2, I4, I5 | 72 | 0.000 | 0.000 | **0.000** | [0.000, 0.051] | 0 |
| I3 | 72 | 0.000 | 0.111 | **0.000** | [0.000, 0.051] | 0 |
| M1 | 72 | 0.194 | 0.375 | **0.375** | [0.272, 0.490] | 5 |
| M2 | 72 | 0.000 | 0.000 | **0.000** | [0.000, 0.051] | 0 |
| M3, M4 | 36 | 0.000 | 0.000 | **0.000** | [0.000, 0.096] | 0 |
| M1raw | 71 | 0.718 | 0.746 | **0.746** | [0.634, 0.833] | 1 |
| D1 | 72 | 0.000 | 0.069 | **0.069** | [0.030, 0.152] | 0 |
| D2 | 72 | 0.000 | 0.278 | **0.264** | [0.176, 0.376] | 2 |

The cycle-1 path diverged in 43 runs (stable-path rates differ only for D1,
0.070, and D2, 0.268). Seeds now disagree on 8 (relation, input) pairs, because the
seed reaches the model. The fallback rate — requests whose reply was unusable, so the
deterministic rule was used — is **0.0383** over 17,164 model requests.
Every violating M1, D1 and D2 run took the same control path in both runs, and
in 128 of those 143 runs cycle 2 rejected a different number of listings: the
model's listing review is where it changes the answer.

The sweep **replays without a GPU**: `python scripts/replay_llm_sweep.py`
answers every model request from the committed reply cache, treats a missing
reply as an error, and reproduces all 2,592 run records exactly.

| | Deterministic | LLM |
|---|---|---|
| runs / base inputs | 2,592 / 72 | 2,592 / 72 |
| elapsed (s) | 1,037 (Windows laptop) | 1,596 (Kaggle T4) |
| coverage verdict | all 72 inputs LIMITED | — |

## 8. Root-cause analysis

The three most-violated relations of the final system — the LLM sweep — are
**M1raw (0.746)**, **M1 (0.375)** and **D2 (0.264)**. Each is attributed below
to one of the brief's four causes; §8.4 lists the faults the other relations
found. The full experiment log, including every pre-v2 diagnosis, is
`docs/DIAGNOSIS.md`.

### 8.1 M1raw, 0.746 — an ill-conceived relation

**Symptom.** 53 of 71 inputs; typically `median_listing_price_inr moved
750,000.00, expected 500,000.00`, and in 24 runs a month's `listing_count`
itself changed.

**Evidence with no agents involved.** Applying the criteria directly to the
frame, before and after adding ₹500,000 to the shifted month:

| Input | Band (₹ lakh) | Listings before → after | Median before | after | Moved |
|---|---|---|---:|---:|---:|
| base00 | 40–150 | 2 → 1 | 14,377,250 | 14,500,000 | **+122,750** |
| base01 | 80–400 | 15 → 16 | 18,000,000 | 16,877,250 | **−1,122,750** |
| base09 | 40–150 | 15 → 14 | 8,253,000 | 8,051,500 | **−201,500** |
| base05 | 50–200 | 11 → 11 | 14,000,000 | 14,500,000 | +500,000 |

On `base01` the median **fell by ₹1.12 million** after every price in the month
rose by ₹500,000. The band is applied after the shift, so listings cross its
edges and the follow-up selects a different population; where no listing
crosses (`base05`) the relation holds exactly. No agent takes part, so this is
neither an agent fault nor a harness bug.

**Control.** D2 also transforms every price and holds at 0.000
deterministically, for one reason: it scales the band with the data.

**Verdict: ill-conceived MR.** Kept deliberately as the counter-example; M1,
declared on the band-free projection, replaces it. Its rate barely moves
between the deterministic (0.718) and LLM (0.746) sweeps, as an unsound
relation's should.

### 8.2 M1, 0.375 — two causes, measured separately

**Symptom.** 27 of 72 inputs, e.g. `2023-03: median_listing_price_inr moved
750,000.00, expected 500,000.00`. The shift is applied to both price bounds,
no band is in play, and every violating run took the same control path.

**Cause 1 — the outlier filter is not shift-invariant (14 inputs, a data
artifact).** The deterministic sweep fails on 14 inputs, and the LLM sweep on
all 14 of them. In every one of those violations cycle 2 rejected a different
number of listings in the follow-up run; no input failed with the rejected
count unchanged. Adding ₹500,000 to price changes ₹/sqft by a different amount
per listing (₹1,000 at 500 sq ft, ₹100 at 5,000 sq ft), so the month's median
and MAD of log ₹/sqft move and the relative threshold admits a different set.
Two controls confirm it: with cycle 2 disabled M1 does not fail (0 of 15 runs
pre-v2, the same inputs failing 15 of 15 with it on), and on the synthetic
snapshot, whose listings sit away from the threshold, M1 is 0.000. The
relation is sound for the statistics; it fails through where real listings sit
relative to a relative threshold. **Verdict: data artifact.**

**Cause 2 — the model judges different prices (13 inputs).** The other 13
inputs fail only with the model on; in 25 of their 31 violating runs the
rejected count changed. The listing review shows the model each listing's price
and ₹/sqft, so a shifted month is a different question and the model can
answer it differently. This is D2's mechanism (§8.3). **Verdict: ill-conceived
for an LLM-judged pipeline.**

### 8.3 D2, 0.264 — the model is shown different prices

**Symptom.** 19 of 72 inputs, e.g. `2023-03: median psf 10000.0 did not scale
by 1.5 (got 14267.1)` — almost, but not exactly, ×1.5.

**Evidence.** D2 holds on all 72 inputs deterministically, so the statistics
are scale-equivariant and the relation is sound for them. With the model, every
violating run kept the same control path, and in 49 of 55 the number of rejected
listings changed. Because the model is deterministic (§4.4), an unchanged
prompt cannot produce a changed judgment; a prompt-sensitivity measurement on
the pre-v2 system (`scripts/prompt_sensitivity.py`) found that D2 changes the
review prompt on **every** input — more review prompts than any other relation
— because every displayed price and ₹/sqft is multiplied by 1.5. Whether a
description corroborates a price is a judgment *about* the price, so the
model's verdict legitimately changes, a different set is rejected, and the
median scales by k only up to that difference.

**Prediction, then confirmation.** Before the pre-v2 prompt fixes, D2 was
predicted to stay violated because its prompt difference is irreducible, while
the identity leak behind I4 was predicted to vanish. Afterwards I4 fell from
0.630 to 0.000 while D2 stayed violated, 0.556 → 0.593 (per run). D1 (0.069 in v2) has the same
cause: shifting the window changes which months the review covers and the
twelve-row table the critique reads.

**Verdict: ill-conceived MR for this architecture.** The relation holds for a
pipeline whose selection does not depend on what an LLM judge is shown; this
one deliberately lets the judge change which listings are counted. Stated
generally: *a judge whose verdict changes the data selected creates a feedback
path, and what it is shown decides which relations break.* We kept that design
because invariance relations — renaming or duplicating a listing must not
change the trend — admit no exception, while D1, D2 and M1 change data the
judgment is legitimately about.

### 8.4 Other faults the relations found

| Relation | Symptom | Cause, evidence | Category | Status |
|---|---|---|---|---|
| **M3** (v2) | 9/36: `2022-12: locality subset gave MORE listings (3 -> 4)` | geography widened around the *selection's* centre, so a subset and its superset widened around different points; on `base03` the subset gained five localities the superset did not | **genuine agent fault** | fixed: each locality widens around itself, skipping selected ones, which provably keeps widen(A) ⊆ widen(B); M3 0/36, M2 2/72 → 0/72 |
| **I3** (v2 LLM) | 8/72: `price_valid_count 141 -> 283, expected exactly 2x` | the review cut each month's grey zone to its 12 highest-₹/sqft rows **before** removing duplicates; on `base23` the model saw 10 distinct listings in the source run and 8 after duplication, and a verdict reached only the twins inside the cut (283 = 2 × 141 + 1) | **genuine agent fault** | fixed and re-run on Kaggle: I3 0/72, D2 20 → 19, nothing else changed; it also closes the pre-v2 residual (0.176) |
| narrative (v2 LLM) | 58 of 72 model summaries rejected | with no price change the model copied the facts block (49); the faithfulness guard rejected the radius it had been given (9) | model limitation; **genuine agent fault** | guard fixed; no model summary without a change. No relation compares the narrative |
| **I3, I4** (pre-v2) | 108/108 runs | outlier threshold computed per *(worker, month)*: 184 listings at 1–4 agents, 185 at 8 | **genuine agent fault** | fixed; replicated on v2 (`results/v2_diagnosis/`) |
| **I4, I3, I2, I1** (pre-v2 LLM) | I4 0.630, I3 0.417, I2 0.028 | prompts carried listing IDs, display units, duplicated rows and an incomplete sort order | **genuine agent faults** | fixed by four prompt-hygiene rules |
| **M3** (pre-v2) | 0.000 | could not fail: geography widening sent every run to the whole metro | **harness/design blind spot** | became testable, then found the fault above |
| control-path report | M3's stable subdomain empty | signature compared human-readable notes containing criteria values | **harness bug** | fixed |

All four of the brief's categories occur. Two of the findings concern our own
instrumentation, which is the reason every relation's rate is reported with the
rejected counts and control paths that explain it.

## 9. Threats to validity

**The headline depends on the sufficiency threshold.** The year-on-year move
runs from the first sufficient month, early months hold 21–35 listings, and
their medians are noise. Whole metro, statistics only
(`scripts/threshold_sensitivity.py`):

| n ≥ | sufficient months | first | headline |
|-----|-------------------|-------|----------|
| 10–25 | 12 | 2022-09 | +87.18% |
| 30 | 7 | 2022-10 | +18.35% |
| **40–60** | **6** | **2023-03** | **−6.41%** |
| 75–150 | 5 | 2023-04 | +8.32% |
| 200–300 | 4 | 2023-05 | +3.87% |

A 93.6-point spread, and the sign flips. **External cross-check:** NHB RESIDEX
(*Press Release July–September 2023*, HPI at market price, based on asking
prices) reports Hyderabad at **+6.8%**. At n ≥ 75 our snapshot gives +8.32%,
the same sign and within 1.5 points; at the contract's n ≥ 50 it gives −6.41%,
the **wrong sign**. We report −6.41% because that is what the contract fixed in
advance — changing the threshold after seeing the index would fit the contract
to the answer — and state that n ≥ 50 was a poor choice. It is one overlapping
data point, not a series (`results/residex/cross_check.md`).

**Other threats.**

- **Single-point scrape, asking prices.** Older months hold only listings still
  live in August 2023 (survivorship), and the prices are asking prices.
- **Narrow queries end below the coverage target.** Keeping the locality
  constraint means no locality base input reaches 0.5 coverage, so many moves
  span two or three sufficient months; the report states it.
- **Relations stated over projections.** M1's band-free projection, I5's lakh
  projection and M2–M4's stable subdomain are reported with how often each
  excluded case occurs.
- **The LLM sweep ran on one machine.** It replays exactly from its cached
  replies, but a fresh run on other hardware may get slightly different replies
  even at temperature 0. The pre-v2 LLM sweeps used another population and
  per-run intervals; their rates are not compared with v2.
- **The model's role is limited by design.** It judges grey-zone listings and
  months and writes some summaries; 3.8% of its requests ended in the
  deterministic rule because the reply was unusable.
- **No PIN codes.** The dataset has no postal column; locality and radius are
  the geographic filters.
- **The synthetic snapshot is our own construction** and has no coordinates, so
  it cannot exercise radius search or geography widening.
- **The diagnosis rests on our own instrumentation**, which was wrong twice
  (§8.4); errors of the same kind would be equally hard for us to see.

## 10. Reflection

The brief asks which aspects an LLM could have produced without running the
system.

**Producible from the text alone: the shape of nearly everything.** Extending
the brief's eight example relations to twelve is routine. The architecture —
planner, parallel retrievers, coverage check, analyser, critic, reporter, a
feedback edge and a conditional retry — is a known pattern, and a model will
justify why its loops are not decorative. The statistical protocol is
standard. A model could also write a confident root-cause story for any results
table, which is exactly the danger.

**Requiring execution: every number, and every surprise.** No reading reveals
that `MIN_AREA_SQFT` holds square metres; that came from a ratio pinned at
10.7639 across both tails. Nor that our own cycles were once dead — the code
compiled, the tests passed, and LangGraph silently discarded updates to
undeclared state keys, visible only in a trace where the coverage agent said
retry and nothing retried. The per-worker threshold showed up as 185 listings
at eight workers against 184 at four; M1raw's flaw as a median *falling*
₹1,122,750 under a uniform increase; the review fault as 10 distinct listings
becoming 8 when the data was duplicated; the threshold problem as a sign flip
against an official index.

**The sharpest version.** We were wrong three times about why M1 failed, and
every wrong answer was articulate. A relation passed 108 runs while the property
it claimed did not hold. A fix that made M3 testable introduced a fault M3 then
found. A model drafted every one of these changes, including the wrong ones;
running the system is what decided which were right — which, in a project about
testing without an oracle, is the subject matter. The use of AI throughout is
recorded in `AI_USE.md`.

---

## Appendix — reproducing this report

```bash
pip install -r requirements.txt
python scripts/headline_table.py --v2 --check                  # §7.1 from the run records, checked against this report
python scripts/headline_table.py --v2 --tag v2_llm --check     # §7.2 likewise
python scripts/replay_llm_sweep.py                             # §7.2 replayed offline, no GPU
python scripts/run_harness.py --tag v2_deterministic           # §7.1 from scratch, ~20-50 min
python scripts/run_harness.py --tag v2_synthetic --synthetic   # synthetic control
python scripts/run_harness.py --tag v2_llm --llm               # §7.2 from scratch: Ollama + the model
python scripts/threshold_sensitivity.py                        # §9 table
python -m pytest                                               # 154 tests
python scripts/verify_claims.py                                # re-derive the quoted figures
python scripts/run_checks.py --replay                          # all of the checks, logged to audit/test_logs/
```

Result sets: `results/v2_deterministic/`, `results/v2_llm/`,
`results/v2_llm_before_reviewfix/`, `results/v2_before_m3fix/`,
`results/v2_before_note_alignment/`, `results/v2_synthetic/`,
`results/v2_diagnosis/`, `results/v2_sensitivity/`; pre-v2 sets and their
diagnoses are described in `docs/DIAGNOSIS.md`. Shipped with them: the frozen
snapshot and its checksum, the seeds `[11, 23, 47]`, and the model reply cache
in `data/llm_cache/`. Contracts for every agent: `contracts/` (v2.1.0-draft).
Every issue found, with how it was caught and fixed: `docs/ISSUE_LOG.md`.
