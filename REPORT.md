# Metamorphic Testing of a Multi-Agent Housing-Trends Application

**TSE Assignment — Final Report**
Market: Hyderabad / Secunderabad (the brief's optional Indian-metro route)

---

## 1. Introduction

This report describes a six-agent application that reads a frozen snapshot of
Hyderabad residential listings and reports how asking prices moved over twelve
months, and the metamorphic suite built to find faults in it without knowing
the correct answer to any query.

The difficulty is the absence of an oracle. Given "3 BHK in Gachibowli, ₹80
lakh to ₹4 crore, the twelve months to August 2023", nobody can say what the
correct median price per square foot was. Metamorphic testing sidesteps this:
transform an input in a known way, re-run, and ask whether the two outputs
relate as the property demands. Reordering the input must not move the trend;
duplicating every listing must double the counts and leave medians alone;
scaling prices by *k* must scale medians by *k* and leave percentage changes
untouched. A violated relation exposes a fault with no oracle in sight.

Four results frame what follows.

**The relations found a real fault.** Two invariance relations were violated on
**all 108 runs** each: the agent validating listings computed its outlier
threshold per *(worker, month)* group rather than per month, so renaming
listing identifiers — changing no price, area or date — moved monthly counts.
No individual output looked wrong.

**One relation was itself unsound.** A monotonicity relation was violated at
0.787 with the system blameless: adding a constant to prices while a price-band
criterion stayed in place changed which listings the band selected. The brief's
guidance — an MR is a hypothesis, not an axiom — applied literally.

**A synthetic control exposed a fault the real data hid** (§8.7): the adaptive
feedback loop breaks the invariance properties the relations assert, and the
real snapshot masked it through a quirk of its shape.

**Adding a local model broke relations the deterministic system satisfied** —
not through randomness (a determinism probe returned 20/20 identical replies)
but because the prompts carried information a judgment must not depend on. One
measurement predicts every one of those violations (§8.1), and §8.7 states the
general result: **an LLM judge that reads the output statistics and whose
verdict changes which data is selected creates a feedback path no relation
about those statistics can survive.**

## 2. Data source

| | |
|---|---|
| Dataset | 99acres.com residential listings, Hyderabad slice |
| Origin | Kaggle — `arvanshul/gurgaon-real-estate-99acres-com`, titled *"Indian Real Estate – 99acres.com"*. Despite the slug, it is a multi-city archive: "properties of **Gurgaon, Hyderabad, Mumbai, Kolkata**". Verified on the dataset page. |
| Licence | Community Data License Agreement – Sharing – v1.0 (`cdla.io/sharing-1-0/`), verified on the same page |
| Scrape date | ≈ 26 August 2023 (latest `POSTING_DATE`) |
| Raw size | 9,487 rows × 55 columns, 14 MB |
| Integrity | SHA-256 `9e81698322606c86…`, re-verified on every load |

The raw file is never modified, and `verify_snapshot()` aborts if the checksum
moves, so a changed input cannot be mistaken for a code change. The snapshot,
the seeds `[11, 23, 47]` and the pinned model digest are the three artifacts
that make a sweep reproducible.

### 2.1 Five defects, each verified rather than assumed

| ID | Defect | Evidence | Handling |
|----|--------|----------|----------|
| **D1** | `MIN_AREA_SQFT` is **square metres despite its name** | ratio of the `AREA` display string to that column is **10.7639 at both the 5th and 95th percentile** over 3,531 rows — a constant, not a distribution | area parsed from the display string |
| **D2** | int32 sentinel in the price fields | `MIN_PRICE`/`MAX_PRICE` reach exactly 2,147,483,647 (= 2³¹−1) on 5 rows; 75 rows carry zero | both dropped |
| **D3** | sale, rent and PG mixed | `PREFERENCE`: S=7,927, R=1,467, P=93 | sale only |
| **D4** | `BEDROOM_NUM` missing on 29.7% | **2,806 of the 2,814 are `Residential Land`**; where both exist, heading-derived BHK agrees on 6,041 rows and conflicts on **0** | restricted to dwellings |
| **D5** | area-entry errors in the tail | a **27 sqft "villa" at ₹2.15 crore** (₹796,296/sqft) and a 285,599 sqft one | **deliberately retained** — see §4.3 |

**D1 is the most consequential**: had the column name been trusted, every
price-per-area figure here would be inflated 10.76×, and the ratio being
*identical* at both tails is what distinguishes mislabelling from noise.
**D4 is structural inapplicability**, not missing data — plots have no
bedrooms — so restricting to dwellings removes it and makes price-per-built-area
commensurable.

Filter cascade, every drop counted:

```
raw rows                                            9487
sale only (PREFERENCE=S)                            7927   -1560
dwellings only                                      5085   -2842
parseable POSTING_DATE                              4975    -110
price not zero/sentinel                             4917     -58
parseable AREA (sqft)                               4578    -339
plausibility bounds DEFERRED to Analysis             4578      -0
canonical listings                                  4578
```

### 2.2 The threat this snapshot carries

It is a **single-point scrape**: older months contain only listings still live
on the scrape date, so the series is survivorship-biased. Monthly depth in the
September 2022 – August 2023 window, after cleaning:

```
2022-09   24    2022-12   29    2023-03   58    2023-06   541
2022-10   34    2023-01   21    2023-04  158    2023-07  1689
2022-11   25    2023-02   23    2023-05  304    2023-08  1557
```

**96.5% of the window's listings fall in its final six months**, and the thin
months' medians swing from ₹4,104 to ₹8,567/sqft on 21–34 listings. §9 shows
this is not a footnote but the dominant limitation of the whole study.

A **synthetic snapshot** with uniform monthly depth is built alongside the real
one. It is not a substitute: it is the only place in the project with a genuine
oracle, which is what makes two of the brief's four root-cause categories
distinguishable at all (§8.4).

---

## 3. The output contract

Fixed before any relation was written, because "the trend is unchanged" cannot
be falsified until "the trend" is a named, finite set of numbers. Defined in
`src/contract.py` as `TrendReport`:

| Field | Meaning |
|---|---|
| `window_months` | exactly twelve months, ascending |
| `monthly[]` | per month: `n_active`, `median_psf`, `median_price`, `p25_psf`, `p75_psf`, `median_age_on_site_days`, `month_is_sufficient` |
| `locality_rankings[]` | localities by median ₹/sqft, with explicit `rank` |
| `yoy_median_psf_pct` | move between the first and last **sufficient** month |
| `yoy_span_months` | how many months that actually spans |
| `n_listings_total` | listings in the window after criteria |
| `currency_unit`, `area_unit` | display units, carried so unit-invariance is observable |
| `criteria`, `provenance` | the slice described; seeds, loop counts, LLM accounting, trace |

Five decisions exist specifically so that relations mean something.

**Median, not mean.** The price tail is heavy and contaminated by D5; a mean
would make every invariance relation fail for reasons unconnected to the
agents. This is also why no violation in our results was attributable to a data
artifact until the LLM was introduced.

**Counts reported separately from prices.** Duplication doubles counts and
leaves medians fixed; widening a band raises counts and may move medians. A
statistic fusing the two would hide precisely the faults the relations target.

**`yoy_span_months` is reported.** An early version named the field "yoy" while
measuring between the first and last *sufficient* months — six on this
snapshot, not twelve. A field called "year-on-year" that silently measures half
a year would let the window-shift relation assert on an undefined quantity.

**`month_is_sufficient` exists at all** (n ≥ 50). Without it the system can
publish a median computed from 21 listings with no flag.

**`median_age_on_site_days` is not called "days on market."** It is
`scrape_date − posting_date` for listings live at the scrape — median 37 days
(p10 6, p90 108). It is **right-censored**, since every listing is still live,
and **length-biased**, since slow listings accumulate in a snapshot while fast
ones exit, so it overstates typical time-to-sale. It is a secondary statistic
and **no relation asserts on it.** Reporting it as days-on-market would be a
false claim about what was measured.

---

## 4. Agent architecture

Six agents over a shared state, following the Reads/Writes contract of the
project design note. The graph is not a linear pipeline: it carries two cycles,
both real LangGraph conditional edges.

```
                 ┌────────────────────────────────────────┐
                 │                                        │ cycle 1
                 v                                        │ coverage < target
      CriteriaAgent ──> RetrievalDispatch ──> Retrieval_0..3
                                │                    │
                                └──> RetrievalMerge ──> CoverageAgent
                                                            │ sufficient
                                                            v
                        ┌──── cycle 2 ────┐          AnalysisAgent
                        │  complaint +    │                │
                        │  flagged months v                v
                        └──────────── CritiqueAgent ──> AggregatorAgent ──> report
```

| Agent | Reads | Writes |
|---|---|---|
| **Criteria** | `user_query` | `filter_spec`, `query_mode` |
| **Retrieval** ×4 | `filter_spec`, `query_mode`, `retry_count` | `retrieval_report` |
| **Coverage / Confidence** | `raw_listings`, `filter_spec` | `coverage_score`, `coverage_verdict`, `widened_filter_spec` |
| **Analysis** | `raw_listings`, `critique_complaint` | `trend_stats` |
| **Critique / Validation** | `trend_stats` | `critique_verdict`, `critique_complaint` |
| **Aggregator / Report** | `trend_stats`, `coverage_score` | `final_report`, `narrative` |

### 4.1 The three required control-flow properties

**(a) Feedback loop — a downstream agent sends work upstream.** Cycle 2,
Critique → Analysis: a rejection carries a *specific complaint* naming the
months at fault, and Analysis recomputes only those. The payload is surgical,
not a blanket re-run.

**(b) Conditional / iterative control step.** Cycle 1, Coverage → Retrieval:
the Coverage agent computes `coverage_score = sufficient_months / 12` plus
geographic spread, then proceeds or widens the binding criterion and re-runs
retrieval. Both cycles are capped, so termination is guaranteed.

**(c) Genuine dependency — one agent's output changes what another *does*.**
The Criteria agent sets **`query_mode`** and the Retrieval agents execute a
**different algorithm**: exact locality matching, or great-circle (haversine)
radius search. One is a set-membership test, the other a distance computation —
not the same algorithm over different rows. 94.7% of the frame carries usable
coordinates; unlocated rows are *excluded* from a radius query, since a radius
query is a claim about geography.

### 4.2 Several cooperating retrieval agents

The brief asks for "several cooperating agents each scan listings against a set
of user-specified criteria." Retrieval is therefore fanned out into **four
parallel graph nodes**, each scanning its own shard, assigned by a stable
`sha256(seed:listing_id)` hash, with a merge node reassembling the result in
canonical order. A test asserts the answer is identical across 1, 2, 4 and 8
agents — a property that did **not** hold before §8.1's fix.

### 4.3 Why the loops are necessary rather than decorative

**Cycle 1 is forced by the data.** "3 BHK in Gachibowli over twelve months"
matches 111 listings, of which **one month** reaches the sufficiency threshold.
Without the loop the system returns mostly empty months, or silently
over-broadens and answers a different question. The loop makes an unanswerable
query answerable **while recording which constraint it relaxed** — information
the user needs to read the number at all. Measured: coverage goes **0.083 →
0.167 → 0.500**. A linear pipeline cannot do this: the decision to widen
depends on an aggregate that exists only after retrieval.

**Cycle 2 is forced by defect D5.** A 400 sqft villa at ₹8.3 crore is
individually plausible and suspicious only in aggregate, so it survives any
blanket filter; validating everything on every run is wasteful and discards
legitimate luxury stock. Escalating only for months whose aggregate looks wrong
is why the complaint carries flagged months.

This cycle was nearly ornamental. The loader originally removed the D5
contamination up front — hygiene that deleted the very thing the cycle exists
to catch. On the bounded frame the cross-field checks found **zero
disagreements in 4,504 rows**. With it retained, the cycle shifts **7 of 12
monthly medians** (up to **+5.50%**), **changes the locality ranking order**,
rejects **125 listings** and moves the headline from **−10.9% to −13.6%**.

### 4.4 Execution trace: both cycles firing

Abridged from `results/llm/trace_example.txt`:

```
 2. Retrieval_0..3   mode=EXACT_LOCALITY  retrieved=111 total
 3. CoverageAgent    coverage=0.0833  decision=WIDEN and re-retrieve (cycle 1)
 4. CriteriaAgent    RELAXED  lever=2  BHK [3] -> [2, 3, 4]
 8. CoverageAgent    coverage=0.1667  decision=WIDEN and re-retrieve (cycle 1)
 9. CriteriaAgent    RELAXED  lever=3  locality filter dropped
13. CoverageAgent    coverage=0.5000  verdict=SUFFICIENT  decision=PROCEED
14. AnalysisAgent    mode=full  listings=4266  move_pct=-10.9
15. CritiqueAgent    REJECT -> recompute flagged months (cycle 2)
16. AnalysisAgent    mode=targeted recomputation  rejected=125  listings=4141
17. CritiqueAgent    APPROVE
18. AggregatorAgent  llm_calls=7  llm_fallback_rate=0.0
```

Cycle 1 fires twice, cycle 2 once, and the answer changes materially at step 16.

### 4.5 Where the local model sits

In LLM mode four agents delegate judgment to Qwen2.5-3B-Instruct (Q4_K_M) via
Ollama: Criteria chooses `query_mode`; Analysis reviews the **grey zone**
(robust |z| between 2.0 and 3.5) by reading descriptions; Critique judges which
months look implausible; Aggregator writes the summary.

**Every statistic stays deterministic Python in both modes.** The model
supplies judgment and language, never arithmetic.

Four **prompt-hygiene constraints** are design rules, not implementation
details — each forced by a relation that failed without it (§8.5):

1. listings are presented **by position, never by identifier**
2. the review batch is sorted on **every displayed field** (a total order)
3. the batch is **deduplicated on content**, and a verdict applies to every row
   carrying that content
4. the critique table is rendered in **canonical units** with **counts
   withheld**

Temperature is 0 and the harness seed reaches the model on every call. A
determinism probe — 20 repeats, same prompt, same seed — returned **20/20
identical replies**, which is what makes those four constraints *sufficient*:
identical prompt plus deterministic decoding implies identical judgment.

---

## 5. The metamorphic relation catalogue

Eleven relations across the three required families (eight is the minimum):
five invariance, four monotonic, two directional. Every one is a statement
about `TrendReport` fields and nothing else.

### 5.1 Invariance

| ID | Transformation | Relation | Subdomain | Tolerance |
|----|---------------|----------|-----------|-----------|
| **I1** | permute the listing rows | every reported field unchanged | all criteria sets | counts exact; floats rel. 1e-9 |
| **I2** | change display units (₹→₹ lakh, sqft→sq.m) | percentage changes, rankings and counts identical; medians scale by the unit factor | all criteria sets | rel. 1e-9 |
| **I3** | duplicate every listing | per-month medians and quartiles unchanged; counts exactly double | months already sufficient; yoy fields excluded | medians rel. 1e-9; counts exactly 2× |
| **I4** | bijectively relabel listing IDs | every reported field unchanged | all criteria sets | exact |
| **I5** | convert **₹ lakh → ₹ crore** | as I2 | the lakh-denominated projection | rel. 1e-9 |

I5 exists because the brief singles it out for the Indian-metro variant:
*"converting ₹ crore ↔ ₹ lakh … must not move the trend or the rankings."*

I3 is deliberately scoped. Doubling flips `month_is_sufficient` for any month
holding 25–49 listings, which changes *which* months the headline spans — so
the yoy fields legitimately move and are excluded by design, not convenience.

### 5.2 Monotonic

| ID | Transformation | Relation | Subdomain |
|----|---------------|----------|-----------|
| **M1** | add ₹500,000 to every price in one month | that month's median price rises by ≈X; others unchanged; no month decreases | the **band-free projection** of each base input |
| **M1raw** | as M1, band left in place | as M1 | **none — retained counter-example** |
| **M2** | widen the price band (superset) | each month's count ≥ the original | criteria setting a band, **conditioned on control-path stability** |
| **M3** | restrict to a locality subset | each month's count ≤ the all-locality count | ≥2 localities, **conditioned on control-path stability** |

`M1raw` is not a passing check and is not meant to be: it is the documented
unsound relation, kept measurable because a counter-example still being
measured is stronger evidence than one deleted.

### 5.3 Directional

| ID | Transformation | Relation | Subdomain |
|----|---------------|----------|-----------|
| **D1** | shift the window forward one month | the eleven overlapping months match the previous run | both windows inside the data range |
| **D2** | scale all prices by k = 1.5 | medians scale by exactly k; percentage changes and ranking order invariant | k keeping the population fixed; the band is scaled alongside |

### 5.4 Boundary interactions, stated in advance

M1 and D2 both transform prices while the criteria may impose a price band. A
large enough shift or scale moves listings across that boundary, **changing the
selected population**, at which point the relation genuinely does not hold.
This is a relation-design trap, not a system fault. D2 handles it by scaling
the band alongside the data; M1 required two attempts (§8.2).

M2 and M3 are **conditional** because coverage depends on listing counts, so a
transformation that changes counts can change how many relaxation rounds fire —
and therefore the population for the whole window. Measured on the synthetic
snapshot: a locality *subset* returned **85 → 331** listings.

---

## 6. Statistical protocol

The system can be non-deterministic — shard assignment, relaxation order and
(in LLM mode) the model's sampling are all seeded — so each relation is checked
statistically rather than once.

- **36 distinct base inputs per relation**, above the required 30, varying
  window end, BHK, locality breadth and price band. Every input satisfies every
  relation's applicability precondition, so all eleven are evaluated on all 36.
- **k = 3 fixed, recorded seeds `[11, 23, 47]`**, applied to source and
  follow-up alike.
- **1,188 checks per sweep** (11 × 36 × 3), each comprising two full pipeline
  runs. Three sweeps were run: deterministic, LLM pre-fix, LLM post-fix.
- Per relation: base-input count, run count, violation count, violation rate
  and a **95% Wilson score interval**.

**Wilson rather than the normal approximation.** Rates here sit at or near 0
and 1 — five relations at exactly zero, one at 0.806. The normal interval
leaves [0, 1] in that regime and collapses to zero width at p̂ = 0, asserting
certainty from 108 observations. Wilson behaves: 0/108 gives
**[0.000, 0.034]**.

**Generating the base inputs needed care.** A first sweep left M2 with 24
applicable inputs, M3 with 27 and D1 with exactly 30, since those relations need
a band, ≥2 localities and shiftable window room; cycling the option lists by one
index also degenerated onto a single varying dimension. The generator now takes
a strided sample of the full cross product, every option carrying a band and ≥2
localities.

**Stopping rule.** The brief asks us to stop when the interval supports the
conclusion. At 108 runs a zero-violation relation is bounded at 0.034, enough
to claim the property holds; the non-zero rates have intervals clearly
separated from zero. We therefore did not extend the sweep. The same criterion
applied to the LLM fallback rate, which converged to **0.0874** with a 95%
interval of width 0.012 over 14,209 calls.

---

## 7. Results

### 7.1 Headline: three configurations

| MR | Family | Transformation | Deterministic | LLM pre-fix | LLM post-fix | 95% CI (post-fix) |
|----|--------|----------------|---------------|-------------|--------------|-------------------|
| I1 | inva. | reorder listings | 0.000 | 0.000 | 0.000 | [0.000, 0.034] |
| I2 | inva. | change display units | 0.000 | 0.028 | 0.000 | [0.000, 0.034] |
| **I3** | inva. | duplicate every listing (2x) | 0.000 | 0.417 | **0.176** | [0.116, 0.258] |
| I4 | inva. | relabel listing ids | 0.000 | 0.630 | 0.000 | [0.000, 0.034] |
| I5 | inva. | convert the display currency from lakh to crore | 0.000 | 0.000 | 0.000 | [0.000, 0.034] |
| **M1** | mono. | add Rs 500,000 to every price in one month | 0.139 | 0.222 | **0.333** | [0.252, 0.427] |
| **M2** | mono. | widen the price band (superset) | 0.000 | 0.111 | **0.111** | [0.065, 0.184] |
| M3 | mono. | restrict to a locality subset | 0.000 | 0.000 | 0.000 | [0.000, 0.034] |
| **M1raw** | mono. | add Rs 500,000 to one month, band left in place | 0.861 | 0.852 | **0.806** | [0.721, 0.869] |
| **D1** | dire. | shift the window forward one month | 0.000 | 0.222 | **0.667** | [0.573, 0.748] |
| **D2** | dire. | scale all prices by k=1.5 | 0.000 | 0.556 | **0.593** | [0.498, 0.681] |

### 7.2 Run metadata

| | Deterministic | LLM pre-fix | LLM post-fix |
|---|---|---|---|
| runs | 1188 | 1188 | 1188 |
| elapsed (s) | 354.67 | 4137 | 2340 |
| LLM calls | — | 14,210 | 14,209 |
| cache hits | — | 10,556 | 12,329 |
| fallback rate | — | 0.0645 | 0.0874 |
| C1 path diverged | 0 | 0 | 0 |

### 7.3 Violations by family, excluding the retained counter-example

| Family | Deterministic | LLM pre-fix | LLM post-fix |
|---|---|---|---|
| invariance | 0 | 116 | 19 |
| monotonic | 15 | 36 | 48 |
| directional | 0 | 84 | 136 |
| **total** | **15** | **236** | **203** |

### 7.4 Reading the tables

**Deterministically, every relation holds except M1's residual** — fifteen
violations in 1,188 checks, all on M1 (§8.6).

**The model broke three invariance relations** (relabelling 0.630, duplication
0.417, units 0.028), and the determinism probe rules out randomness, so these
were *systematic*. **The fixes recovered two exactly and one partially** — I4
and I2 to 0.000, I3 to 0.176, invariance violations **116 → 19** — and **made
two others worse** (D1 0.222 → 0.667, M1 0.222 → 0.333). Totals fell 236 → 203
but the distribution shifted from invariance to directional; §8.7 argues the
choice.

**`M1raw` behaves as designed** at 0.806–0.861 in all three configurations,
which is what a genuinely unsound relation should look like.

**Control-path divergence is zero in all three sweeps**, so no result is
confounded by the relaxation path. That is not a given: on synthetic data it
diverges in 99 of 1,188 runs, which is §8.7.

---

## 8. Root-cause analysis

The brief requires each top violation to be attributed, with evidence, to one
of: a genuine agent fault, a data artifact, an ill-conceived MR, or a harness
bug. All four occur.

**The three most-violated relations in the shipped configuration** are
**M1raw (0.806)**, **D1 (0.667)** and **D2 (0.593)**, diagnosed in §§8.2–8.4.
Because the shipped configuration is the product of two rounds of fixes, the
relations that were most violated *before* those fixes — I4, I3 and M1 — are
diagnosed too (§§8.5–8.6): their faults are real, were found by the relations,
and their repair is what produced the current numbers.

### 8.1 One measurement bounds what the model can break

The determinism probe returned **20/20 identical replies** at temperature 0
with a fixed seed. So for a model agent, *identical prompt ⟹ identical
judgment*. Whether a relation can survive the LLM therefore reduces to a
question with a yes/no answer: **does the transformation change any prompt that
influences which listings are selected?**

Measured directly, with no inference, over the whole catalogue
(`scripts/prompt_sensitivity.py`, all 36 base inputs):

| MR | selection prompts differ | review | critique | LLM post-fix rate |
|----|--------------------------|--------|----------|-------------------|
| I1 reorder | **0 / 36** | 0 | 0 | **0.000** |
| I4 relabel | **0 / 36** | 0 | 0 | **0.000** |
| M3 subset | **0 / 36** | 0 | 0 | **0.000** |
| I2 units | 2 / 36 | 0 | 4 | **0.000** |
| I5 crore | 4 / 36 | 0 | 4 | **0.000** |
| I3 duplicate | 19 / 36 | 27 | 0 | 0.176 |
| M2 widen band | 36 / 36 | 88 | 72 | 0.111 |
| M1 add ₹X | 36 / 36 | 37 | 72 | 0.333 |
| D2 scale prices | 36 / 36 | 107 | 72 | 0.593 |
| D1 window shift | 36 / 36 | 76 | 72 | 0.667 |
| M1raw | 36 / 36 | 29 | 72 | 0.806 |

**The implication runs one way, and only the deductive direction is sound.**
Prompt invariance is *sufficient* for the relation to hold: I1, I4 and M3
perturb no selection prompt on any of the 36 inputs, and all three sit at
0.000. That is not a statistical finding but a proof — given the determinism
probe, an identical prompt cannot yield a different judgment, so the relation
*cannot* break through the model.

**The converse is false**, and reading it as a biconditional is the error an
earlier draft of this report made (AI_USE.md §3.12). I2 and I5 perturb a
selection prompt on 2 and 4 inputs respectively and still hold at 0.000: a
perturbed prompt only *enables* a violation, it does not cause one, because the
perturbation still has to change a judgment that changes which listings are
counted. The same asymmetry holds within a single relation — §8.5 reports it
per-cell for I3, where 0 of 51 identical-prompt cells violated but only 19 of
57 differing-prompt cells did. Nor is the relationship monotone: M2 perturbs
every input yet scores 0.111, below I3's 0.176 on 19.

The measurement is therefore a **bound**, not an explanation. It partitions the
catalogue into relations the model provably cannot break and relations it
*might*, and the rest of §8 does the work of finding out which of the latter it
actually did.

It also splits the violations into two kinds, which is what the rest of §8 is
about:

- **prompts differ because the prompt leaked information the judgment is not
  about** — identity, display units, duplicate rows. These are **faults**, and
  fixing them moved I4, I2 and I1 into the top block (§8.5).
- **prompts differ because the transformation genuinely changed what the
  judgment is about** — the prices, the window, the listing set. These are
  **unsound relations** for this architecture (§§8.3–8.4), and no prompt
  hygiene can repair them.

### 8.2 M1raw, 0.806 — an ill-conceived relation, by design

`M1raw` adds ₹500,000 to one month's prices while leaving the price-band
criterion in place. **Evidence with no agents involved** — computing medians
directly on the frame:

| base input | band (₹ lakh) | n | before | after | moved |
|------------|---------------|---|--------|-------|-------|
| base00 | 40–150 | 2 | 14,377,250 | 14,500,000 | **+122,750** |
| base01 | 80–400 | 15 | 18,000,000 | 16,877,250 | **−1,122,750** |
| base09 | 40–150 | 15 | 8,253,000 | 8,051,500 | **−201,500** |

On `base01` the median **fell by ₹1.12M** after every price rose by ₹500k. No
agent participates, so the cause is neither an agent fault nor a harness bug:
the band is applied *after* the shift, so the follow-up selects a different
population. One crossing listing dominates, because these sliced months hold
1–15 listings.

**The control that confirms it.** D2 scales all prices and holds at 0.000
*deterministically* — same class of transformation, and it holds for exactly
one reason: D2 scales the band alongside the data.

**Verdict: ill-conceived MR.** Retained deliberately at 0.806 as the documented
counter-example; the refined form (M1, declared on the band-free projection)
replaces it. Its rate is near-identical in all three configurations, which is
what a genuinely unsound relation should look like.

### 8.3 D1, 0.667 — an unsound relation for an LLM-judged pipeline

**Symptom.** All 72 violations are of one form:

```
2022-09: count 22 != 23 across the shifted window
```

The eleven overlapping months should match between a window and the same window
shifted one month. They differ by one or two listings.

**Mechanism.** D1 replaces one month of the window with another, so the
Critique agent's twelve-row median table is a *different table*
(§8.1: 12 of 6 critique prompts differ) and the Analysis review sees a
different listing set (15 of 6). The model therefore flags a different set of
months, different listings are rejected, and the overlap moves.

**Why this is not a prompt-hygiene fault.** The information that changes is the
information the judgment is *about*. A critique agent asked "which months look
anomalous relative to their neighbours" must see the months; a window shift
changes the neighbours. Withholding the window would not make the judgment
better-posed, it would make it impossible.

**Confirmed by configuration, not by sampling.** D1 holds at **0.000
deterministically** and at **0.222** with the pre-fix prompts, rising to 0.667
once counts were withheld from the critique (§8.7). All three rates come from
the same relation on the same data; only what the judge reads changed.

**Verdict: ill-conceived MR for this architecture.** The relation is sound for a
pipeline whose selection is independent of the aggregate, which the
deterministic configuration is and the LLM configuration is not. Stating it
without that condition was our error, not the system's.

### 8.4 D2, 0.593 — the same cause, and the cleanest demonstration of it

**Symptom.** 57 of 60 violations read:

```
2023-04: median psf 7,364 did not scale by 1.5 (got 7,361)
```

Medians scale by *almost* exactly k.

**Mechanism.** Scaling every price by 1.5 changes every price and every ₹/sqft
the review prompt displays — the largest prompt perturbation of any relation
(18 of 6 review prompts differ, §8.1). The model's judgment about whether a
listing's description corroborates its price legitimately changes when the
price changes, so a different set is rejected and the median scales by k only
up to that difference.

**This relation is the control for the whole of §8.1.** D2 was *predicted* to
remain violated after the prompt fixes, before the second sweep was run,
precisely because its prompt difference is irreducible. It came back 0.556 →
0.593 while I4 collapsed 0.630 → 0.000. A diagnosis that correctly predicts
which violations will *persist* is stronger evidence than one that only
explains those that disappear.

**Verdict: ill-conceived MR for this architecture**, same category as D1.
Deterministically D2 holds at 0.000, so the relation is sound; it is the
combination of an exact-arithmetic claim with a judge that reads prices that is
not.

### 8.5 I4, I3, I2, I1 — genuine agent faults, now fixed

These were the most-violated relations before the fixes, and all four causes
were leaks of information the judgment is not about:

| Cause | Affects | Pre | Post |
|-------|---------|-----|------|
| **listing IDs printed in the review prompt** | I4, I3 | 0.630 | **0.000** |
| **critique table rendered in display units** | I2 | 0.028 | **0.000** |
| **top-N taken from a duplicated set** (returns N/2 distinct listings twice) | I3 | 0.417 | 0.176 |
| **tie-ordering on a subset of displayed fields** | I1 | 0.000 *(by luck)* | 0.000 |

An identifier carries no information about whether a description corroborates a
price; a judgment about whether a month is anomalous must not depend on the
units it is shown in. **Verdict: genuine agent faults**, fixed by the four
prompt-hygiene constraints of §4.5.

**The fourth is the most instructive.** I1 scored 0.000 across 108 runs, but a
prompt-invariance test showed the review ordering sorted on a *subset* of the
displayed fields, so listings tied on (psf, price, area) kept their input order
and reordering the rows *did* change the prompt. No tie happened to flip in
those 108 runs. **108 passing runs is not the same as the property holding.**

**I3's residual 0.176 is localised, and prompt perturbation is necessary but
not sufficient.** Comparing the selection prompts across all 36 base inputs
under all three seeds (108 cells, no inference required) gives:

| | not violated | violated |
|-------------------|-------------:|---------:|
| prompt identical  | 51 | **0** |
| prompt differs    | 38 | 19 |

The implication runs one way only. An identical prompt provably *cannot* break
the relation — identical prompt plus temperature-0 decoding implies an
identical judgment, per the 20/20 determinism probe of §4.4 — and indeed none
of those 51 cells violated. A differing prompt breaks it in 19 of 57 cases
(33%), so the perturbation is a necessary condition, not the whole mechanism.
11 of 36 base inputs violated at least once: four on all three seeds
(base22/23/30/31) and seven on one of three (base11/17/24/27/32/33/35). The
review batch comes out with fewer listings on the doubled frame, but *which*
perturbations bite is not isolated. Recorded as an open defect with a pinned
failing test rather than papered over.

### 8.6 The deterministic faults, and M1's data artifact

Before any model was involved, two relations were violated on **all 108 runs**:
`I4 count series differ` and `I3 count 9 -> 15, expected exactly 2x`.

**Mechanism.** Retrieval shards by `sha256(seed:listing_id)`, and the targeted
recomputation computed its MAD outlier threshold **per `(shard, month)` group**
rather than per month — making it a property of how a month was split across
workers.

**Evidence, one variable at a time** (12 inputs × 2 seeds):

| MR | group = `shard+month` | cycle 2 off | group = `month` |
|----|----------------------|-------------|-----------------|
| I3 | **1.000** | 0.000 | 0.000 |
| I4 | **1.000** | 0.000 | 0.000 |
| M2 | 0.042 | 0.000 | 0.000 |

**Independent corroboration:** varying only the agent count, `shard+month`
returns **185 listings at 8 agents** against **184** at 1, 2 and 4; per-month
grouping returns 184 at every count. Worker count is not a property of the
housing market. **Verdict: genuine agent fault**, fixed; regression test added.

**M1's deterministic residual, 0.139 — a data artifact.** On the five affected
inputs, **15/15 violations with cycle 2 enabled, 0/15 disabled**; and on the
synthetic snapshot M1 = 0.000. Adding a constant to *price* is not a constant
shift in *price per sqft* — Δ/area differs per listing (₹1,000 for 500 sqft,
₹100 for 5,000) — so the psf distribution changes shape and the outlier filter
reaches a different verdict. Whether it does depends on how close real listings
sit to the threshold, which is why clean synthetic data shows none.

### 8.7 The adaptive loop, and the trade-off we chose

**Found only by the synthetic control.** Three relations that hold on real data
are violated on synthetic data: `M3 locality subset gave MORE listings
(85 -> 331)`, `M2 widened band gave fewer (136 -> 67)`, `I3 85 -> 98`. With
cycle 1 disabled all three go to **0/24**; conditioning on the
relaxation-stable subdomain removes every violation (I3 0.167→0.000,
M2 0.056→0.000, M3 0.278→0.000). Coverage depends on listing counts, so a
transformation that changes counts changes how many relaxation rounds fire —
and the population for the whole window.

**Why the real snapshot hid it:** there, coverage is so far below target that
cycle 1 exhausts its levers in every run, so both executions relax identically.
A relation that *passes* on real data only because the real data is degenerate
is exactly the failure mode a control exists to catch.

**The trade-off.** Withholding counts from the critique closed I3's
count-doubling fault and made two others worse: **D1 0.222 → 0.667** and
**M1 0.222 → 0.333**, because the model then judges purely on the median series
and those are the relations that perturb medians. Stated generally:

> An LLM judge that reads the output statistics, and whose verdict changes which
> data is selected, creates a feedback path through those same statistics. What
> the model is shown determines *which* relations break — not *whether* they
> break.

We ship the configuration with **19 invariance violations rather than 116**,
accepting 136 directional ones, because invariance relations must hold
unconditionally — "renaming a listing must not change the trend" admits no
excuse — whereas D1 and D2 perturb data the judgment is legitimately about. We
stopped tuning there: removing the critique from the selection path would
likely score better, but that is fitting the system to pass its own tests.

### 8.8 A harness bug, in our own instrumentation

The first control-path comparison used the planner's human-readable relaxation
notes, which embed criteria values. Comparing those across two runs reports a
difference whenever the inputs differ, so **all 108 M3 runs were recorded as
path divergences** and M3's stable subdomain came out empty. Caught by noticing
that an empty subdomain was implausible; fixed by recording a canonical lever
sequence. It changed no violation rate — only the conditioning — but it is the
clearest reminder that a metamorphic suite needs the same scepticism as the
code it tests.

### 8.9 Summary of attributions

| Finding | Rate | Cause | Category |
|---------|------|-------|----------|
| **M1raw** | **0.806** | band applied after the shift changes the population | **ill-conceived MR** |
| **D1** | **0.667** | window shift changes the judge's own input | **ill-conceived MR for this architecture** |
| **D2** | **0.593** | price scaling changes the judge's own input | **ill-conceived MR for this architecture** |
| I4, I3, I2, I1 (LLM) | 0.630 → 0.000 etc. | prompts leaked identity, units, duplicates, order | **genuine agent faults** |
| I4, I3 (deterministic) | 1.000 | threshold per `(shard, month)` | **genuine agent fault** |
| M1 residual | 0.139 | real listings near the outlier boundary | **data artifact** |
| M2 (deterministic) | 0.019 | flagged set grows across rounds; MAD not idempotent | **genuine agent fault** |
| I3/M2/M3 (synthetic) | 0.167–0.278 | cycle-1 relaxation path diverges with input size | **design tension** |
| control-path reporting | — | signature compared message text | **harness bug** |

All four of the brief's categories are represented. Three of nine findings
concern the *relations* and one concerns our own *instrumentation* — only five
concern the system.

## 9. Threats to validity

**The headline figure is not robust, and this is the dominant limitation.**
The trend is measured from the first *sufficient* month, the early months hold
21–35 listings, and their medians are sampling noise — so the sufficiency
threshold effectively *selects* the answer:

| n ≥ | sufficient months | first sufficient | headline |
|-----|-------------------|------------------|----------|
| 10–25 | 12 | 2022-09 | **+87.18%** |
| 30 | 7 | 2022-10 | +18.35% |
| **40–60** | **6** | **2023-03** | **−6.41%** |
| 75–150 | 5 | 2023-04 | **+7.08%** |
| 200–300 | 4 | 2023-05 | +3.87% |

**Spread: 93.6 percentage points, and the sign flips.**

### 9.1 The external cross-check settles it: the headline is wrong

NHB RESIDEX, *Press Release July–September 2023*, reports **Hyderabad at
+6.8%** year-on-year. That series — HPI @ Market Price — is described in the
same release as "based on **Asking Price** of Unsold & under-construction
properties", so it measures the same kind of quantity we do and the comparison
is methodologically matched rather than approximate.

| Source | Hyderabad, annual change |
|--------|--------------------------|
| **NHB RESIDEX, HPI @ Market Price** | **+6.8%** |
| our snapshot, n ≥ 75 | **+7.08%** |
| our 3 km IT-corridor radius slice | +6.24% |
| **our snapshot, n ≥ 50 (shipped contract)** | **−6.41%** |

Three independent readings of our own data agree with the official index to
within 0.6 points, and at n ≥ 75 to within **0.3**. The shipped figure is the
outlier, and it has the **wrong sign**.

This is a sharper conclusion than "the headline is not robust": **the headline
is wrong, and the cause is the sufficiency threshold rather than the data.** At
a threshold that excludes the noisiest months, the pipeline reproduces the
published index almost exactly — simultaneously the strongest validation of the
method in this project and the clearest indictment of the n ≥ 50 choice.

We report −6.41% because it is what the §3 contract produces; changing the
threshold after seeing the external figure would be fitting the contract to the
answer. The honest statement is that **n ≥ 50 was chosen badly** and a revision
would use 75. Evidence and retained PDF: `results/residex/cross_check.md`. One
overlapping annual data point, not a series — two earlier quarterly releases
returned empty.

### 9.2 Other threats

**Single-point scrape, asking prices.** Older months hold only listings still
live on 26 August 2023, so the series is survivorship-biased in a direction we
cannot measure. `POSTING_DATE` is a posting timestamp and `MIN_PRICE` an asking
price — stickier and more optimistic than sale prices.

**A provenance trap.** The dataset's slug is
`gurgaon-real-estate-99acres-com`, but its title is "Indian Real Estate –
99acres.com" and it covers Gurgaon, Hyderabad, Mumbai and Kolkata. The dataset
the brief recommends for this route (`arnabk123/…`) covers Gurgaon only and
does *not* contain the Hyderabad file. Reasoning from the slug led us briefly
to the wrong conclusion; reading both pages corrected it. Origin and licence
verified.

**PIN codes are unavailable.** The brief suggests filtering by locality *and*
PIN code. The dataset has no PIN/ZIP/postal column, and the six-digit strings
in its free text are latitude fragments. Locality — the brief's own example —
is the convention used, with radius/geo as the alternative.

**The LLM path is weaker than its presence suggests.** Fallback rate
**0.0874** over 14,209 calls — roughly 1 in 11 produced nothing usable — and
the Aggregator's summary was rejected by the faithfulness guard on **35% of
runs**. So three agents use the model and the fourth is overridden about a
third of the time.

**Relations are stated over projections in three places** (M1's band-free
projection, I5's lakh projection, M2/M3's relaxation-stable subdomain). "M1
holds" means "M1 holds where no price band is in play"; excluded-case
frequencies are reported, not hidden.

**One open defect:** I3's residual 0.176, localised to 11 of 36 inputs, pinned
by a deliberately failing test.

**The synthetic snapshot is our own construction** — it validates the
statistics and the harness, not the realism of the market model.

**Single-machine numbers.** Versions pinned and the model digest recorded, but
untested across Python or pandas versions.

**The diagnosis rests on our own instrumentation**, which was wrong once
(§8.8); errors of the same kind would be equally invisible to us.

---

## 10. Reflection

The brief asks which aspects an LLM could have produced without running the
system.

**Producible from the text alone: the shape of nearly everything.** The brief
supplies eight example relations; extending them to eleven across three
families is routine. The architecture — planner, retriever, auditor, analyser,
critic, reporter, with a feedback edge and a conditional stop — is a design
pattern, and a competent model will produce it with a plausible justification
for why the loops are not decorative. The protocol is standard. Most of §§1–6
is of that character. A model could also write confident root-cause narratives
for a results table, which is precisely the danger.

**Requiring execution: every number, and every surprise.** No reading reveals
that `MIN_AREA_SQFT` holds square metres — that came from finding the ratio
pinned at 10.7639 across *both* tails, a result whose shape is what makes it
conclusive. Nor does reading reveal that our own two cycles were dead: the code
compiled, the tests passed, the output was plausible, and the loops were
unreachable because LangGraph discards updates to undeclared state keys. We
found it by reading a trace and seeing the auditor say `ITERATE` while nothing
iterated. Likewise the per-worker threshold, visible only as 185 listings at
eight workers against 184 at four; M1's band crossing, as a median falling
₹1,122,750 under a uniform increase; the prompt contamination, as three
invariance relations collapsing from 0.000 to 0.630.

**The sharpest version.** We were wrong three times running about why M1 failed,
and every wrong answer was articulate. We wrote an oracle that failed twice for
reasons internal to itself. We shipped a relation that passed 108 runs while
the property it claimed did not hold. We called a correct data citation suspect
and recommended replacing it with a wrong one. An LLM generates the hypothesis
space fluently; what it cannot do without execution is determine which element
is true — which, in a project about testing without an oracle, is the subject
matter.

---

## Appendix — reproducing this report

**One command rebuilds the headline table of §7.1** from the committed per-run
records, recomputing every rate and interval rather than copying them, and
`--check` additionally verifies that each rebuilt figure appears in this
report:

```bash
python scripts/headline_table.py --check
```

Re-running the sweeps from scratch is the stronger check:

```bash
pip install -r requirements.txt
python scripts/run_harness.py --tag check                 # deterministic, ~6 min
python scripts/run_harness.py --tag syn --synthetic        # synthetic control
python scripts/run_harness.py --tag llm --llm              # needs Ollama + the model
python -m pytest                                           # 101 tests, 1 xfail
python scripts/verify_claims.py                            # re-derive every number here
python scripts/prompt_sensitivity.py                       # the §8.1 evidence
```

Result sets: `results/phaseA_deterministic/`,
`results/llm_before_promptfix/`, `results/llm/`, `results/synthetic/`,
`results/diagnosis/`, `results/sensitivity/`.
Shipped artifacts: the frozen snapshot and its checksum, the recorded seeds
`[11, 23, 47]`, the model digest `d7f5d340f8953384`, and the response cache in
`data/llm_cache/`, which lets the LLM sweep replay without a GPU.
