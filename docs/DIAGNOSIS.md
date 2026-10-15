# Root-Cause Analysis — detailed experiment log

**Relationship to the report.** §8 of `REPORT.md` is the summary a reader needs;
this file is the full log, with every controlled experiment's table and the
order in which hypotheses were raised and discarded. Where the two differ in
detail, the numbers here are the primary record.

**Naming.** This log was written while cycle 2's outlier rejection was called
"STRICT mode" (a retrieval-side scan mode). It now lives in the Analysis
agent's targeted recomputation, triggered by the Critique agent
(`contracts/Analysis.md` §3); "STRICT round" below means one round of that
recomputation. The experiments are unchanged.

# Findings

The brief requires each top violation to be attributed, with evidence, to one
of four causes: a **genuine agent/aggregation fault**, a **data artifact**, an
**ill-conceived MR**, or a **harness bug**. Asserting a cause is not evidence,
so every attribution below rests on a controlled experiment in which exactly
one thing changes.

All figures come from `results/before_fix/` (972 runs, 9 relations × 36 base
inputs × 3 seeds `[11, 23, 47]`) and `results/diagnosis/`.

## Pre-fix violation rates

| MR | Family | Transformation | Rate | 95% CI (Wilson) |
|----|--------|----------------|------|-----------------|
| I1 | invariance | reorder listings | 0.000 | [0.000, 0.034] |
| I2 | invariance | change display units | 0.000 | [0.000, 0.034] |
| **I3** | invariance | **duplicate every listing** | **1.000** | **[0.966, 1.000]** |
| **I4** | invariance | **relabel listing ids** | **1.000** | **[0.966, 1.000]** |
| **M1** | monotonic | **add ₹500k to one month** | **0.787** | **[0.701, 0.854]** |
| M2 | monotonic | widen the price band | 0.019 | [0.005, 0.065] |
| M3 | monotonic | restrict to a locality subset | 0.000 | [0.000, 0.034] |
| D1 | directional | shift the window one month | 0.056 | [0.026, 0.116] |
| D2 | directional | scale all prices by k=1.5 | 0.000 | [0.000, 0.034] |

The three most-violated relations are **I4, I3 and M1**. They have two
different causes, and only one of them is a bug in the system.

---

## Finding 1 — I3 and I4: a genuine agent fault

**Verdict: genuine agent fault.** Both relations were violated on every one of
108 runs. The system's answer depended on how listings were named and on how
many workers happened to process them.

### Symptom

```
I4  count series differ: [0, 9, 6, 17, 5, 21, 18, 18, 23, 15, 15, 37]
                     vs  [0, 8, 6, 17, 5, 21, 19, 18, 21, 13, 13, 37]
I3  2022-05: count 9 -> 15, expected exactly 2x
```

Renaming listing IDs — which changes no price, area or date — moved monthly
counts by one or two listings. Duplicating the dataset gave 15 where 18 was
required.

### Mechanism

`Retrieval/Analysis agents` shards listings across workers by `sha256(seed:listing_id)`. In
targeted recomputation it computed the MAD-based robust outlier threshold **per
`(shard, month)` group** rather than per month. The threshold is therefore a
property of how a month happened to be split across workers. Relabelling IDs
reshuffles shards; duplicating adds `#dup`-suffixed IDs that hash elsewhere.
Either way the accepted set moves.

### Evidence — Experiments A and B

12 base inputs × 2 seeds, one variable changed per condition:

| MR | Baseline (C2 on, group=`shard+month`) | A: C2 disabled | B: C2 on, group=`month` |
|----|---------------------------------------|----------------|-------------------------|
| I3 | **1.000** | 0.000 | 0.000 |
| I4 | **1.000** | 0.000 | 0.000 |
| M2 | 0.042 | 0.000 | 0.000 |
| all others | 0.000 | 0.000 | 0.000 |

Condition A removes cycle 2 entirely and the violations vanish, locating the
fault inside C2. Condition B keeps C2 running and changes **only the grouping**
— violations also vanish. The grouping is the mechanism, not merely C2's
existence.

### Evidence — Experiment C, independent corroboration

The number of workers is not a property of the Hyderabad housing market, so it
must not change the answer. Holding the input fixed and varying only
`n_shards`:

| n_shards | grouping | listings returned | rejected |
|----------|----------|-------------------|----------|
| 1 | shard+month | 184 | 9 |
| 2 | shard+month | 184 | 9 |
| 4 | shard+month | 184 | 9 |
| **8** | **shard+month** | **185** | **8** |
| 1, 2, 4, 8 | month | 184 | 9 |

At eight workers the buggy grouping returns a different answer. With per-month
grouping every worker count agrees. This is a second, independent
demonstration of the same fault, and it is a property no MR was needed to
state — which is why it corroborates rather than merely repeats.

### Fix

`GraphConfig.strict_group_by_month`, now `True` by default: the rejection
decision is taken once over the whole month, across every shard, before
sharding is applied. The faulty behaviour is retained behind the flag so this
diagnosis stays reproducible.

### Why the relations caught it and a conventional test would not

No individual answer here is wrong-looking. A median of ₹7,500/sqft is
plausible whether or not one listing was wrongly rejected, so there is no
oracle to compare against. The fault was only visible as a *relationship*
between two runs — which is precisely the case metamorphic testing exists for.

---

## Finding 2 — M1: an ill-conceived relation, not a fault

**Verdict: ill-conceived MR.** The property does not hold as originally
stated, and the system is not at fault. The brief's instruction applies
directly: an MR is a hypothesis, not an axiom.

### The original relation

> Add ₹500,000 to every list price in one month; that month's median list
> price rises by ≈₹500,000 and no month decreases.

### Evidence — pure arithmetic, no agents involved

Computing the median directly on the frame, with the agent graph entirely out
of the picture:

| base input | band (₹ lakh) | month | n | median before | median after | moved |
|------------|---------------|-------|---|---------------|--------------|-------|
| base00 | 40–150 | 2023-03 | 2 | 14,377,250 | 14,500,000 | **+122,750** |
| base01 | 80–400 | 2023-03 | 15 | 18,000,000 | 16,877,250 | **−1,122,750** |
| base09 | 40–150 | 2023-04 | 15 | 8,253,000 | 8,051,500 | **−201,500** |
| base02–08 | — | — | 1–11 | — | — | exactly +500,000 |

On `base01` the median **fell by ₹1.12M** after every price rose by ₹500k.
Since no agent participates in this computation, the cause cannot be an agent
fault or a harness bug.

### Mechanism

The price-band criterion is applied **after** the shift, so the follow-up run
selects a different population:

| base input | band (₹ lakh) | n before | n after | left the band | entered |
|------------|---------------|----------|---------|---------------|---------|
| base00 | 40–150 | 2 | 1 | 1 | 0 |
| base01 | 80–400 | 15 | **16** | 0 | **1** |
| base09 | 40–150 | 15 | 14 | 1 | 0 |

Only one listing crosses in each case. It dominates the median because these
sliced months hold 1–15 listings — the thin-month problem recorded in
`DESIGN.md` §1.3 reappearing as an MR-design trap.

### The control that confirms it

**MR-D2 scales all prices by k=1.5 and has a violation rate of 0.000.** It is
the same class of transformation, and it holds for exactly one reason: D2
already scaled the band alongside the data (`scale_price_criteria`). The same
transformation class passes when the population is held fixed and fails when
it is not. That is the diagnosis, stated as a controlled comparison.

### Refinement, including the attempt that failed

**First attempt — shift the band by ₹500k alongside the data. This made it
worse: 12/16 violations, against 6/16 for leaving the band alone.** Shifting
the band globally holds the *target* month's population fixed but changes
every *untouched* month's, because their prices did not move. The failure
message shifted accordingly, from "median price moved" to "untouched month
moved". Recorded here because a refinement that backfires is evidence about
the relation's structure, not a detour.

**Second attempt, adopted.** M1 is declared on the **band-free projection** of
each base input. A `prepare` hook on the relation removes the price band
before *both* the source and the follow-up run, so the population is fixed in
all twelve months. Transforming only the follow-up cannot express this, since
the source would still carry the band — which is why the hook had to be added
to the harness rather than to the transformation.

The unrefined relation is retained as **`M1raw`**, still measured and still
failing, as the documented counter-example.

---

## Finding 3 — M2: a second, subtler agent fault

Not in the top three by rate (0.019), but it shares the C2 machinery and the
diagnosis completes the picture.

### Symptom

```
2022-10: widened band gave fewer listings (17 -> 15)
```

A strictly wider band returned fewer listings in one month — while returning
*more* overall (212 against 204), with both runs applying identical
relaxations.

### Evidence

8 base inputs × 2 seeds, varying only the control-flow caps:

| condition | M2 violations |
|-----------|---------------|
| C1 ≤ 3, **C2 ≤ 2**, group=month | **2/16** |
| C1 ≤ 3, **C2 ≤ 1**, group=month | 0/16 |
| C2 disabled | 0/16 |
| C1 disabled | 0/16 |
| both loops disabled | 0/16 |

The violation requires a **second** STRICT round.

### Mechanism — the filter is not idempotent

Two compounding causes:

1. The `Critique agent`'s flagged-month set **grows** between rounds, and
   which months look anomalous depends on the whole slice. So a wider band can
   cause a month to be strict-filtered in one run and not in the other.
2. The MAD-based threshold is **relative to the month's own distribution**, so
   adding listings changes the z-scores of listings already present:

   ```
   psf set            [5000, 5500, 6000, 6500, 7000, 7500, 8000, 60000]
   rejected (|z|>3.5) [  F     F     F     F     F     F     F     T  ]

   after adding one listing at 59000:
   rejected (|z|>3.5) [  F     F     F     F     F     F     F     T    T ]
   ```

   Removing outliers shrinks the MAD, so a further round rejects more. The
   filter does not converge to a fixed point.

### Fix

`max_strict_rounds` defaults to **1**. The cycle still fires — this caps
iterations, it does not remove the back-edge, and C2 remains a genuine control
dependency. A principled alternative (computing the threshold once from the
pre-rejection distribution and reusing it across rounds) is noted as future
work.

---

## Finding 4 — D1: the same root cause

D1 (window shift) violated 6/108 runs, always as
`count N != N across the shifted window`. Loop counts diverged between source
and follow-up in 3 of those runs. Conditions A and B both drive it to 0.000,
so it is the Finding 1 fault surfacing through a different transformation
rather than an independent defect.

---

## Finding 5 — M1's residual 0.139 after the refinement

After both fixes, M1 fell from 0.787 to **0.139 [0.086, 0.217]** — improved,
but not zero. The residual is 15 violations on 5 of 36 base inputs
(`base08`, `base15`, `base16`, `base17`, `base24`), identical across all three
seeds, with no loop divergence. All of one kind:

```
2023-04: median price moved 403,000.00, expected 500,000.00
2023-05: median price moved 470,000.00, expected 500,000.00
```

### Evidence

M1 on exactly those 5 inputs, varying only cycle 2:

| condition | M1 violations |
|-----------|---------------|
| C2 enabled (default) | **15/15** |
| C2 disabled | **0/15** |

And on the synthetic snapshot, where the data is clean by construction,
**M1 = 0.000** (Finding 6's run).

### Mechanism

Adding a **constant to price is not a constant shift in price-per-sqft**. Each
listing's psf moves by `Δ / area`, which differs per listing:

| area (sqft) | psf before | psf after +₹500k | psf change |
|-------------|-----------|------------------|------------|
| 500 | 10,000 | 11,000 | **+1,000** |
| 2,000 | 10,000 | 10,250 | **+250** |
| 5,000 | 10,000 | 10,100 | **+100** |

The psf distribution changes **shape**, not merely location, so the MAD-based
outlier filter in targeted recomputation legitimately rejects a different set — which
changes the population and hence the median price.

### Verdict: data artifact

Our first reading of this was "an inherent tension, correctly scoped" — i.e.
that the relation simply could not hold while a psf-based filter was active.
The synthetic run corrected that. With clean data the relation holds exactly
(0.000), so the violations are not inherent to the relation: they depend on how
close *real* listings sit to the rejection boundary. The synthetic snapshot's
injected outliers sit at 0.02× and 45× the base, far outside the threshold, and
produce no violations at all.

The filter is behaving correctly and the relation is sound. We report the 0.139
with its mechanism rather than suppressing it by disabling C2 for this
relation, which would mean measuring a system we do not ship. The interval
[0.086, 0.217] is tight enough to establish the effect as real and confined.

### M1's three states

| Form | Rate | Status |
|------|------|--------|
| `M1raw` — band left in place | 0.861 [0.783, 0.914] | retained counter-example; the relation is unsound |
| band shifted alongside the data | 12/16 (pilot) | abandoned: fixes the target month, breaks the untouched ones |
| `M1` — band-free projection | 0.139 [0.086, 0.217] | adopted; residual is a data artifact |

---

## Finding 6 — the adaptive loop breaks invariance (found only by the synthetic control)

The synthetic snapshot exists to separate a harness bug from a data artifact.
It did more than that: it exposed a fault the real snapshot structurally could
not reveal.

### Symptom

Three relations that hold on real data are violated on synthetic data, and the
magnitudes are not subtle:

```
M3  2022-09: locality subset gave MORE listings (85 -> 331)
M2  2022-09: widened band gave fewer listings (136 -> 67)
I3  2022-09: count 85 -> 98, expected exactly 2x
```

### Evidence

With cycle 1 disabled, all three go to **0/24**. Conditioning on the
relaxation-stable subdomain — runs where both executions took the same path
through C1 — removes every violation:

| MR | Synthetic, all runs | Stable subdomain | Runs diverged |
|----|---------------------|------------------|---------------|
| I3 | 0.167 [0.108, 0.248] | **0.000** [0.000, 0.041] | 18 / 108 |
| M2 | 0.056 [0.026, 0.116] | **0.000** [0.000, 0.044] | 24 / 108 |
| M3 | 0.278 [0.202, 0.369] | **0.000** [0.000, 0.070] | 57 / 108 |

### Mechanism

Coverage depends on listing counts. Any transformation that changes counts —
duplication, widening a band, restricting to a sub-region — changes how many
relaxation rounds fire, hence the final criteria, hence the population for the
**entire window**. The loop that makes the system useful breaks the invariance
and monotonicity properties the relations assert.

### Why the real snapshot hid it

**All 1,080 real-data runs used exactly 3 relaxation rounds** — C1 always hit
its cap, because coverage on this survivorship-biased snapshot is so far below
target that three relaxations never suffice. Both executions therefore relax
identically and the path cannot diverge: real-data divergence is **0 of 1,080**.
The synthetic snapshot's uniform monthly depth puts coverage at the decision
boundary, where a small change in input size flips the decision.

### Verdict: genuine design tension, exposed by the control

Adaptive systems whose control flow responds to aggregate properties of the
input cannot satisfy input-size invariance unconditionally. Every relation is
now reported twice — unconditionally and over the relaxation-stable subdomain —
with the divergence count stated, because that count is itself a property of
the system worth knowing.

---

## Finding 7 — a harness bug, in our own instrumentation

The first version of the control-path comparison used the planner's
human-readable relaxation notes, which embed criteria values
(`locality filter dropped (was ['Kondapur', ...])`). Comparing those across two
runs reports a difference whenever the inputs differ, so **all 108 M3 runs were
recorded as path divergences** and M3's stable subdomain came out empty.

**Caught by** noticing that an empty subdomain was implausible — M3 restricts
localities, which should not always change the control flow. **Fixed by**
recording a canonical lever sequence (`price_band > bhk > localities`) that
describes control flow only. After the fix, real-data divergence is 0 and M3's
stable subdomain is the full 108 runs.

**Verdict: harness bug**, in the reporting layer rather than in the relations.
It changed no violation rate, only the conditioning — but it is the clearest
reminder here that a metamorphic suite needs the same scepticism as the code it
tests.

---

## Summary of attributions

| MR | Pre-fix | Post-fix | Cause | Category |
|----|---------|----------|-------|----------|
| I4 | 1.000 | 0.000 | robust threshold computed per `(shard, month)` | **genuine agent fault** |
| I3 | 1.000 | 0.000 | same | **genuine agent fault** |
| M1 | 0.787 | 0.139 | band applied after the shift changes the population | **ill-conceived MR** |
| M1 residual | — | 0.139 | real listings near the outlier threshold; psf shifts non-uniformly | **data artifact** |
| M2 | 0.019 | 0.000 | flagged set grows across rounds; MAD threshold not idempotent | **genuine agent fault** |
| D1 | 0.056 | 0.000 | same as I3/I4 | **genuine agent fault** |
| I3, M2, M3 (synthetic) | — | 0.000 conditioned | C1 relaxation path diverges with input size | **genuine design tension** |
| control-path reporting | — | fixed | signature compared message text, not control flow | **harness bug** |

**All four of the brief's categories are represented, each with a controlled
experiment behind it.** Two of them — the data artifact in M1's residual and
the harness bug in the control-path signature — were only identifiable once the
synthetic snapshot provided a known ground truth. On the real snapshot alone
the M1 residual would have been indistinguishable from an inherent limitation
of the relation, which is what we initially recorded it as.

**A note on how two of these conclusions changed.** Findings 1–5 were written
before the synthetic control was run, and at that point we had concluded that
no violation was attributable to a data artifact or to a harness bug. Both
conclusions turned out to be wrong, and the sequence is itself the evidence:

* **M1's residual** was recorded as an inherent limitation of the relation.
  The synthetic run showed the relation holding exactly on clean data, which
  reclassified it as a **data artifact** (Finding 5).
* **A harness bug** surfaced only when we built the control-path conditioning
  that Finding 6 required (Finding 7).

Each conclusion was correct given what had been measured at the time, and
changed when more was measured. That is the argument for the synthetic control
in miniature.


---

## Finding 8 — four faults in the LLM prompts

Introduced when four agents' judgment was routed through Qwen2.5-3B (Ollama).
Three relations that hold deterministically failed badly on the first LLM
sweep.

### Symptom

| MR | deterministic | LLM pre-fix |
|----|---------------|-------------|
| I4 relabel listing ids | 0.000 | **0.630** |
| I3 duplicate every listing | 0.000 | **0.417** |
| I2 change display units | 0.000 | **0.028** |
| D2 scale all prices | 0.000 | **0.556** |

### What ruled out model noise

The determinism probe — 20 repeats of one prompt at temperature 0 with a fixed
seed, on the Kaggle T4 — returned **20/20 identical replies**
(`results/llm/determinism_probe.json`). A deterministic model given an
identical prompt must answer identically, so these violations are *systematic*:
the model was being shown different text.

Cycle-2 round counts were identical in source and follow-up on 100% of runs, so
the cause was not *whether* the model was consulted but *what it was shown*.

### Four causes

| # | Cause | Breaks | Why it is a fault |
|---|-------|--------|-------------------|
| 1 | **listing ids printed in the review prompt** | I4, I3 | an identifier carries no information about whether a description corroborates a price |
| 2 | **critique table rendered in display units** | I2 | a judgment about whether a month is anomalous must not depend on the units shown |
| 3 | **listing counts shown to the critique** | I3 | duplication doubles every count, so a count-aware judge flags different months |
| 4 | **top-N taken from a duplicated set** | I3 | returns N/2 distinct listings twice instead of N distinct ones |

### Fix, and the result

Listings are presented **by position**; the review batch is sorted on **every
displayed field** (a total order) and **deduplicated on content**, with a
verdict applying to every row carrying that content; the critique table is
rendered in **canonical units** with **counts withheld**.

| MR | pre-fix | post-fix |
|----|---------|----------|
| I4 | 0.630 | **0.000** |
| I2 | 0.028 | **0.000** |
| I3 | 0.417 | 0.176 |
| D2 | 0.556 | 0.593 — *predicted unchanged* |

D2 holding steady while I4 collapsed was predicted **before** the second sweep:
scaling prices genuinely changes the figures the model is shown, so a different
judgment is legitimate and no prompt hygiene can fix it.

### A relation that passed by luck

The reorder relation scored 0.000 across 108 runs. A prompt-invariance test
later showed the review ordering sorted on a *subset* of the displayed fields,
so listings tied on (psf, price, area) kept their input order and reordering the
rows *did* change the prompt. No tie happened to flip in those 108 runs.
**108 passing runs is not the same as the property holding.**

### I3's residual — localised, not isolated

Comparing the selection prompts under duplication across **all 36 base inputs
under all three seeds** — 108 cells, run through `ScriptedBackend` so no
inference is involved — settles the mechanism one way and refutes it the other:

| | not violated | violated |
|-------------------|-------------:|---------:|
| prompt identical  | 51 | **0** |
| prompt differs    | 38 | 19 |

**A differing prompt is necessary but not sufficient.** The necessary direction
is deductive and clean: an identical prompt with temperature-0 decoding yields
an identical judgment (the 20/20 determinism probe), so the relation cannot
break — and none of those 51 cells did. The sufficient direction fails: 38 of
the 57 differing cells passed regardless, so the prompt perturbation only
*enables* the violation, it does not determine it.

Prompts differ on 19 of 36 base inputs; 11 of 36 violated at least once. The
seed pattern splits those 11 in two, which the earlier "exact correlation"
reading could not account for:

* **four fail on all three seeds** — base22/23/30/31
* **seven fail on exactly one of three** — base11/17/24/27/32/33/35

The review batch comes out with fewer listings on the doubled frame, but which
perturbations bite is not isolated. Pinned by a deliberately failing test
(`test_duplication_invariance_residual_on_specific_inputs`) rather than papered
over.

Per-cell evidence: `results/diagnosis/i3_prompt_vs_violation.csv` (108 rows),
regenerated by `python scripts/prompt_sensitivity.py`.

*A note on how this was mis-stated.* An earlier draft of this section reported
"6 of 36 base inputs" with an "exact" correlation. That 6 was the **sample
size** — `prompt_sensitivity.py` defaulted to the first six base inputs — and
it was written up as though it were the finding. The named list came from the
violation table of an earlier sweep, not from any prompt comparison. The script
now defaults to the full catalogue and `verify_claims.py` asserts the 2x2 above,
so the number cannot drift from the evidence again. See AI_USE.md §3.12.

---

## Finding 9 — the architectural tension, with a measured trade-off

Fixing cause 3 (withholding counts) closed one fault and opened two:

| MR | LLM pre-fix | LLM post-fix |
|----|-------------|--------------|
| D1 shift the window | 0.222 | **0.667** |
| M1 add ₹X to one month | 0.222 | **0.333** |

The model now judges purely on the median series, and those are precisely the
two relations that perturb medians.

**The general statement:**

> An LLM judge that reads the output statistics, and whose verdict changes which
> data is selected, creates a feedback path through those same statistics. No
> relation about them can survive it. What the model is shown determines *which*
> relations break — not *whether* they break.

The deterministic configuration survives because its rules are stable step
functions; small perturbations rarely flip them.

**The configuration choice, stated as a judgement.** Invariance relations must
hold unconditionally — "renaming a listing must not change the trend" admits no
excuse — whereas D1 and D2 perturb data the model legitimately sees. We
therefore ship the configuration with **19 invariance violations rather than
116**, accepting 136 directional ones. Tuning further (removing the critique
from the selection path) would fit the system to pass its own tests, which is
overfitting an oracle we do not have.

---

## Categories, final

| Category | Instances |
|----------|-----------|
| **Genuine agent fault** | per-`(shard, month)` threshold (I3, I4, M2, D1); four prompt-contamination faults (I4, I3, I2, I1) |
| **Ill-conceived MR** | M1 with the band in place (retained as `M1raw`) |
| **Data artifact** | M1's deterministic residual 0.139 — real listings near the outlier boundary |
| **Harness bug** | the control-path signature comparing message text |
| *(beyond the brief's four)* | the cycle-1 relaxation tension; the LLM-judge feedback path |

All four of the brief's categories occurred. Two of nine findings concern the
*relations*, one concerns our own *instrumentation*, and the rest concern the
system.
