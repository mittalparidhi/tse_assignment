# NOTEBOOK.md — Lab notebook

Chronological record of what was tried, what broke, and what the numbers were
at each stage. Dead ends are kept: several of them are the evidence behind
decisions in `DESIGN.md` and `docs/DIAGNOSIS.md`.

All work on the Hyderabad slice of the 99acres snapshot
(SHA-256 `9e81698…c48898a`, 9,487 rows × 55 columns).

---

## Dataset decisions (Paridhi)

### Primary dataset
The headline run uses the supplied real Hyderabad property-listing snapshot. The raw source remains under `data/raw/`, and the deterministic cleaned dataset is `data/processed/hyderabad_clean.csv`.

### Missing-month policy
Do not synthesize, interpolate, or extrapolate missing monthly records. Report the source-period months using their observed data and actual coverage status. Distinguish months with no listings from months with unavailable or incomplete data. August 2023 is a partial month because the latest observed posting date is August 26, 2023.

### Synthetic data policy
If synthetic data is later used for a separate diagnostic experiment, explicitly label it as synthetic and report its results separately from the real-snapshot headline results. Never combine synthetic observations with the real dataset to fill missing months or present synthetic results as observed market evidence.

### Reporting limitations
Monthly listing counts describe listings observed in the supplied snapshot, not a census of the Hyderabad property market. Keep unverified metrics explicitly unverified and unsupported values null rather than fabricating values.

---

## Stage 0 — Data audit (pre-existing)

Snapshot frozen with a checksum and a provenance Readme; three audit scripts
produced monthly counts, column missingness and numeric anomalies.

**Finding that shaped everything after it.** The snapshot is a *single-point
scrape*: older months contain only listings still live on the scrape date.
Monthly counts after cleaning:

```
2022-09   24    2022-12   29    2023-03   58    2023-06   541
2022-10   34    2023-01   21    2023-04  158    2023-07  1689
2022-11   25    2023-02   23    2023-05  304    2023-08  1557
```

96.5% of the window falls in its last six months, and the thin months' medians
swing ₹4,104 → ₹8,567/sqft on 21–34 listings. Consequence: the output contract
carries a per-month `sufficient` flag (n ≥ 50), and month-comparing relations
are declared only over that subdomain.

## Stage 1 — Verifying the defects myself

Five defects, each confirmed rather than assumed.

**D1 — `MIN_AREA_SQFT` is square metres despite its name.** Compared the
`AREA` display string (always "`<n>` sq.ft.") against the numeric column:
ratio **10.7639 at both the 5th and 95th percentile** over 3,531 rows —
unanimously the sq.m→sq.ft constant. Using the named column would have
inflated every ₹/sqft figure 10.76×. Area is now parsed from the display
string.

**D2** — int32 sentinel 2,147,483,647 (= 2³¹−1) on 5 rows; zero on 75.

**D3** — `PREFERENCE` mixes sale (7,927), rent (1,467) and PG (93).

**D4 — the 29.7% missing bedroom counts are not missing.** Of 2,814 rows
without `BEDROOM_NUM`, **2,806 are `Residential Land`** — plots have no
bedrooms. Where both exist, heading-derived BHK agrees on 6,041 rows and
conflicts on **0**. So this is structural inapplicability, and restricting to
dwellings removes it entirely.

**D5** — area-entry errors in the tail: a **27 sqft "villa" at ₹2.15 cr**
(₹796,296/sqft) and a 285,599 sqft one, concentrated in
`Independent House/Villa`.

Filter cascade: 9,487 → 7,927 (sale) → 5,085 (dwellings) → 4,975 (dated) →
4,917 (price valid) → 4,578 (area parseable).

## Stage 2 — Output contract first

Written before any relation, because "the trend is unchanged" is
unfalsifiable until "the trend" is a named, finite set of numbers.

Three decisions made specifically to keep relations meaningful: **median not
mean** (the tail is contaminated, so a mean would make every invariance
relation fail for reasons unrelated to the agents); **counts reported
separately from prices** (duplication and band-widening move them in opposite
directions); and **`yoy_span_months` reported alongside the headline**.

**Dead end, fixed immediately.** The first version called the headline field
`yoy_median_psf_pct` while measuring it between the first and last
*sufficient* months — six months on this snapshot, not twelve. Shipping a
field named "yoy" that silently measures half a year would have let the
window-shift relation assert on an undefined quantity. The report now states
its own span: **−6.41% over 6 sufficient months (window spans 12)**.

## Stage 3 — A premature filter nearly made a cycle decorative

The loader originally applied plausibility bounds that removed the D5
contamination up front. This looked like hygiene and was actively harmful: it
removed the very thing `Retrieval agents`'s STRICT mode — and therefore cycle 2 —
exists to catch.

**Measured:** on the bounded frame the cross-field checks found **0
disagreements in 4,504 rows**. The loop could never have changed an answer.

Bounds are now off by default (`apply_plausibility=False`) and the
contamination is retained deliberately. Verified that C2 then matters:

| | months shifted | largest shift | ranking order |
|---|---|---|---|
| contaminated vs cleaned | **7 of 12** | **+5.50%** (2022-11) | **changes** — rank 10 flips Attapur ↔ Gachibowli |

## Stage 4 — Both agent cycles were silently dead

First LangGraph wiring set routing flags as `state["_widen"]` /
`state["_escalate"]`, keys **not declared** in the `TrendState` TypedDict.
LangGraph derives its channels from those annotations and silently discards
updates to undeclared keys, so both conditional edges were unreachable and the
graph ran as a linear pipeline.

**Caught by reading the trace, not the exit code.** The trace showed:

```
3. Coverage agent  coverage=0.0833  decision=ITERATE (cycle 1)
4. Analysis agent  listings=111
```

The auditor asked to loop; nothing looped. Flags promoted to declared
channels. `tests/test_agents.py::test_cycle_c1_actually_fires` now asserts it.

## Stage 5 — One relaxation lever starved the others

`Criteria agent` scanned its lever list from the start each round. BHK can
always widen by ±1, so it won every time and the **locality filter — the
actually-binding constraint — was never dropped.** Coverage stalled while the
trace looked healthy, because the loop *was* firing:

```
coverage 0.0833 -> 0.1667 -> 0.1667 -> 0.1667   (3 rounds, all BHK)
```

Fixed with a lever cursor that advances. After:

```
coverage 0.0833 -> 0.1667 -> 0.5000   (target met, stops)
```

## Stage 6 — First full harness run (`results/before_fix/`)

972 runs (9 relations × 36 base inputs × 3 seeds `[11,23,47]`) in 222s.

```
I1 0.000   I2 0.000   I3 1.000   I4 1.000   M1 0.787
M2 0.019   M3 0.000   D1 0.056   D2 0.000
```

Three most-violated: **I4, I3, M1**. The base-input generator needed fixing
first — M2 had only 24 applicable inputs, M3 27, D1 30, against the required
30 — and its option cycling degenerated because the periods shared factors.
Rebuilt as a strided sample of the full cross product: **36/36 applicable for
every relation.**

## Stage 7 — Diagnosis

Full write-up in `docs/DIAGNOSIS.md`. Summary of the controlled experiments:

**I3/I4 — genuine agent fault.** STRICT mode computed the MAD outlier
threshold per `(shard, month)` rather than per month, so the accepted set
depended on how listings were split across workers. Changing *only* the
grouping took both from 1.000 to 0.000. Independent corroboration: at
`n_shards=8` the buggy grouping returned **185 listings / 8 rejected** where
every other worker count returned **184 / 9**.

**M1 — ill-conceived relation.** Two wrong hypotheses before the right one:

1. *Band crossing* — first measurement showed only 2 listings crossing across
   12 inputs, which looked like a refutation.
2. *Control-flow divergence* — explained only 4 of 85 violations.

Resolved by computing medians directly with no agents involved:

```
base01  2023-03  n=15  median 18,000,000 -> 16,877,250  moved -1,122,750
```

The median **fell by ₹1.12M** after every price rose ₹500k. Hypothesis 1 was
right; the first measurement understated it because a *single* crossing
listing dominates a 15-listing month. **Lesson: the magnitude of a cause
cannot be inferred from the count of affected rows when the statistic is a
median over a thin sample.**

Control that confirms it: **D2 (scale prices by k) has rate 0.000**, because
D2 already scaled the band alongside the data.

**Refinement that backfired.** Shifting the band by ₹500k alongside the data
made it *worse*: **12/16 against 6/16**. It holds the target month's
population fixed but changes every untouched month's, because their prices did
not move. Adopted instead: declare M1 on the **band-free projection** via a
`prepare` hook applied to *both* runs — which required adding the hook to the
harness, since transforming only the follow-up cannot express it.

**M2 — second agent fault.** Violations required a *second* STRICT round
(2/16 at two rounds, 0/16 at one). The flagged-month set grows between rounds,
and the MAD threshold is relative, so the filter is not idempotent — adding
one listing to a month changes the z-score of every listing already in it.
`max_strict_rounds` capped at 1. The cycle still fires.

## Stage 8 — After-fix run (`results/after_fix/`)

1,080 runs in 122s.

```
I3  1.000 -> 0.000      M2  0.019 -> 0.000
I4  1.000 -> 0.000      D1  0.056 -> 0.000
M1  0.787 -> 0.139      M1raw        0.861  (counter-example, correctly fails)
```

M1's residual 0.139 traced to cycle 2: **15/15 with C2 on, 0/15 with C2
off.** Mechanism — adding a constant to *price* is not a constant shift in
*psf*, since Δ/area differs per listing (₹1,000 for a 500 sqft flat, ₹100 for
a 5,000 sqft one). The psf distribution changes **shape**, so the psf-based
outlier filter legitimately rejects a different set. Scoped and reported
rather than forced to pass.

## Stage 9 — Synthetic control, and the oracle that caught itself twice

`scripts/make_synthetic.py` constructs a snapshot with a known trend
(+1.0%/month, uniform 400 listings/month, six localities with known rank
order, 2% injected outliers).

**Oracle failure 1 — my expectation was wrong, not the code.** Expected median
was set to `base_psf × (1+g)^i`, which assumes every listing sits at the base
price. Listings spread across six localities with factors 0.70–1.80, so the
pooled median is `month_psf ×` the mixture median — **1.0746**, not 1.0. The
oracle "failed" with a 4–12% positive bias that was entirely its own error.
Fixed by solving the mixture median numerically (`brentq` + normal CDF) rather
than sampling.

**Oracle failure 2 — multiple comparisons.** With twelve independent per-month
3-SE gates, the chance at least one trips is ~3%, and one did (2023-05 at
−2.28% against a 2.29% bound). Replaced with a Bonferroni-corrected per-month
bound plus a **systematic-bias z-test on the mean error**, which is what
actually has power against a real defect: a wrong quantile or a unit error
biases every month the same way.

**Oracle result: PASS.** Mean error **−0.057% ± 0.220% SE, z = −0.26**; worst
month 2.28% within the 2.55% bound; locality rank order recovered exactly;
endpoint move +9.50% against a constructed +11.57% (z = −1.94). This is the
one check metamorphic testing cannot provide — a real oracle — and it confirms
the statistics independently of every relation.

### The synthetic snapshot then exposed a fault the real data had masked

Running the relations against synthetic data:

```
            real    synthetic
I3         0.000    0.167
M2         0.000    0.056
M3         0.000    0.278
```

Magnitudes made the cause obvious before any experiment: a locality *subset*
returning **85 → 331** listings, and a *widened* band returning **136 → 67**.
Direct test — with cycle 1 disabled, all three go to **0/24**.

**Mechanism.** Coverage depends on listing counts, so any transformation that
changes counts changes how many relaxation rounds fire, which changes the final
criteria — and therefore the population — for the entire window. The adaptive
loop that makes the system *useful* breaks the invariance and monotonicity
properties.

**Why the real data hid it, now quantified.** On the real snapshot **all 1,080
runs used exactly 3 relaxation rounds** — C1 always hits its cap, because
coverage is so far below target that three relaxations never suffice. Both runs
therefore relax identically, and real-data path divergence is **0 of 1,080**.
The synthetic snapshot's uniform depth puts coverage at the decision boundary,
where paths diverged in **99** runs.

**Resolution.** Relations are now reported twice — unconditionally and over the
**relaxation-stable subdomain** — with the divergence count stated. Conditioned
on that subdomain, every synthetic violation disappears:

| MR | Synthetic, all runs | Stable subdomain | Diverged |
|----|---------------------|------------------|----------|
| I3 | 0.167 [0.108, 0.248] | **0.000** [0.000, 0.041] | 18 / 108 |
| M2 | 0.056 [0.026, 0.116] | **0.000** [0.000, 0.044] | 24 / 108 |
| M3 | 0.278 [0.202, 0.369] | **0.000** [0.000, 0.070] | 57 / 108 |

**It also reclassified M1's residual.** M1 = 0.000 on synthetic against 0.139
on real, so the residual is a **data artifact** — real listings sitting near
the outlier threshold — not an inherent limit of the relation, which is what we
had recorded.

## Stage 10 — A harness bug in our own conditioning

The first control-path signature compared the planner's human-readable
relaxation notes, which embed criteria values
(`locality filter dropped (was ['Kondapur', ...])`). Two runs on different
inputs always differ textually, so **all 108 M3 runs were logged as
divergences** and M3's stable subdomain came out empty.

**Caught by** noticing an empty subdomain was implausible. **Fixed by**
recording a canonical lever sequence (`price_band > bhk > localities`) that
describes control flow only. After the fix: real-data divergence 0, M3's stable
subdomain the full 108 runs. It changed no violation rate — only the
conditioning — but it is the clearest reminder here that the harness needs the
same scepticism as the system.

## Stage 11 — Reconciling with the project design note

A design note written separately described a six-agent system with different
agent names, a different cycle-2 semantics (Critique → Analysis, recomputing
flagged months) and a different genuine dependency (`query_mode` selecting
exact-ZIP vs radius retrieval). Two of those were **better** than what had been
built, so the implementation was moved to them rather than the reverse:

- agents renamed to Criteria / Retrieval / Coverage / Analysis / Critique /
  Aggregator
- cycle 2 rebuilt as a complaint carrying **flagged months**, with Analysis
  recomputing only those
- **`query_mode`** added: exact-locality matching or haversine radius search.
  94.7% of the frame carries usable coordinates — and the US dataset the note
  originally specified has none, so the Hyderabad retarget *enabled* its own
  design
- retrieval fanned out into **four parallel graph nodes**, matching the brief's
  "several cooperating agents each scan listings"
- `median_age_on_site_days` added, honestly named (right-censored and
  length-biased, §3 of the report)

Three places where measurement had already shown the note's spec to be wrong
were kept as-is and recorded as deviations: the missing sufficiency flag, MR8's
1% tolerance on an exact-arithmetic relation, and MR4's subdomain.

**Guarded by golden fixtures** captured *before* any edit: the full
deterministic sweep reproduced all ten pre-existing relations byte-identically
(1,188 runs). One fixture field was corrected — the old coverage auditor
incremented its round counter before checking whether a lever could be applied,
so it counted one no-op iteration. Every reported statistic was unchanged;
the correction is recorded in the fixture file.

## Stage 12 — Adding the local model

Ollama installed user-space (no sudo), Qwen2.5-3B-Instruct-Q4_K_M. Four agents'
judgment routed through it; all arithmetic left deterministic.

Validated locally against a 0.5B model first, which caught three defects before
any GPU time was spent:

1. the model reported a metro-wide decline as being "in the Gandipet locality"
   and called a 12-month window "6 months of reliable listings" → explicit
   scope in the prompt, plus an output guard rejecting any numeric token absent
   from the supplied facts
2. both 0.5B and 3B echoed instruction lines into user-facing prose →
   de-labelled prompt plus leak detection
3. **worst:** the LLM branch *replaced* the deterministic anomaly checks instead
   of augmenting them. With 3B the critique returned no suspect months, cycle 2
   never fired, **zero contamination was rejected**, and the headline came out
   −10.9% instead of −13.6%. LLM mode was strictly worse than deterministic.
   Fixed so the deterministic checks are an unconditional floor.

A fourth constraint came from arithmetic, not a model: the grey-zone review
issued 16 calls per run with all twelve months flagged, which would have been
~38,000 calls and overrun the Kaggle session. Bounded to the three months with
most candidates → 7 calls per run.

## Stage 13 — Two LLM sweeps, and what the relations caught

**First sweep** (`results/llm_before_promptfix/`, 1,188 runs, 4,137s): three
invariance relations that hold deterministically failed — relabelling ids
**0.630**, duplication **0.417**, display units **0.028**.

The determinism probe returned **20/20 identical replies**, which reframed
everything: these were not model noise but *systematic* consequences of the
prompt text changing. Four causes, all in what the model was shown — listing
ids, display units, listing counts, and taking the top-N of a duplicated set.

**Verification without a model.** Since identical prompt + deterministic
decoding implies identical judgment, proving *prompt invariance* proves the
relation. Eight prompt-invariance tests were written, needing no inference —
and one of them caught a latent fault the 108-run sweep had missed by luck: the
review ordering sorted on a subset of displayed fields, so tied listings kept
their input order.

**Second sweep** (`results/llm/`, 1,188 runs, 2,340s): I4 **0.630 → 0.000**,
I2 **0.028 → 0.000**, I3 **0.417 → 0.176**, D2 **0.556 → 0.593** (predicted
unchanged). But D1 **0.222 → 0.667** and M1 **0.222 → 0.333** — withholding
counts from the critique traded count-sensitivity for median-sensitivity.

Invariance violations fell 116 → 19. We ship that configuration and argue the
choice explicitly in the report rather than tuning further, which would fit the
system to its own tests.

## Stage 14 — Measuring our own fragility

Chasing an overclaim in the design note ("the sensitivity of the headline is
reported" — it was not) produced the single most important caveat in the
project:

```
n >= 10-25 -> +87.18%     n >= 40-60 -> -6.41%  (ours)
n >= 30    -> +18.35%     n >= 75+   -> +7.08%
```

**93.6 percentage points of spread, and the sign flips.** The headline is
measured from the first sufficient month, the early months hold 21–35 listings,
and their medians are noise — so the threshold *selects* the answer. Two
independent checks agree: a 3 km radius slice gives **+6.24%** against the
metro-wide −10.9%, and the snapshot is survivorship-biased by construction.

## Stage 15 — The external cross-check, which settled the question

NHB RESIDEX's *Press Release July–September 2023* reports **Hyderabad +6.8%**
year-on-year on its HPI @ Market Price — a series the release describes as
based on *asking prices*, the same kind of measure as ours.

| source | annual change |
|---|---|
| NHB RESIDEX | **+6.8%** |
| ours, n ≥ 75 | **+7.08%** |
| ours, 3 km radius slice | +6.24% |
| ours, n ≥ 50 (shipped) | **−6.41%** |

Agreement to within 0.3 points at n ≥ 75. So the conclusion is sharper than
"not robust": **the headline is wrong and the threshold is why.** At a
threshold excluding the noisiest months the pipeline reproduces the published
index almost exactly — the best validation of the method in the project and the
clearest indictment of the n ≥ 50 choice. We did not move the threshold after
seeing the external figure, because that would be fitting the contract to the
answer; the report says n ≥ 50 was chosen badly and that a revision would use
75.

## Final state

| | |
|---|---|
| Relations | **11** across 3 families (10 + 1 retained counter-example) |
| Base inputs | 36 per relation, all applicable |
| Seeds | `[11, 23, 47]` |
| Runs per sweep | **1,188** (two pipeline executions each) |
| Sweep time | ~355s deterministic · 4,137s LLM pre-fix · 2,340s LLM post-fix |
| Local model | `qwen2.5:3b-instruct-q4_K_M`, digest `d7f5d340f8953384` |
| Determinism probe | **20/20 identical** at temperature 0 |
| LLM fallback rate | **0.0874** over 14,209 calls |
| Tests | **101 passing, 1 xfail** (the pinned I3 residual) |
| Result sets | `phaseA_deterministic/`, `llm_before_promptfix/`, `llm/`, `synthetic/`, `diagnosis/`, `sensitivity/` |

Deterministic: all relations 0.000 except M1 at 0.139 (data artifact) and
`M1raw` at 0.861 by design. LLM post-fix: invariance 19 violations (from 116),
directional 136 — the trade-off argued in §8.6 of the report.

## Threats to validity (carried into the report)

1. **Single-point scrape.** The series is survivorship-biased: older months
   hold only listings still live on 26 Aug 2023.
2. **Asking prices, not transactions.** `POSTING_DATE` is a posting timestamp.
3. **n ≥ 50 sufficiency threshold** is a judgement call, not a derived value.
4. **No LLM at run time.** The relations exercise the orchestration, not an
   LLM's judgement. Reasoning in `AI_USE.md`.
5. **Relations are stated over a projection in two places** — M1's band-free
   projection and the relaxation-stable subdomain. Both are reported with the
   frequency of the excluded cases rather than hidden.
6. **The synthetic snapshot is our own construction**, so it validates the
   statistics and the harness, not the realism of the market model.
