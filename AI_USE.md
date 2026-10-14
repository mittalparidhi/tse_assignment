# AI_USE.md — Disclosure of AI assistance

Per the brief's ground rules: all substantive AI use is disclosed here,
**including the cases where the tool was wrong and how that was caught.**

## 1. Where AI is used

| Context | Use |
|---------|-----|
| **Building the project** | Claude (Anthropic), via the Claude Code CLI, wrote most of the application code, the MR catalogue, the harness and the dashboard, and drafted `DESIGN.md`, `REPORT.md` and `docs/DIAGNOSIS.md`. It ran the data audits, the controlled experiments and the diagnostic analyses. |
| **Inside the application, at run time** | **Qwen2.5-3B-Instruct (Q4_K_M) served locally by Ollama**, used by four of the six agents. |

## 2. The local model inside the application

`agent_mode=LLM` routes four agents' *judgment* through the local model:

| Agent | What the model decides |
|-------|------------------------|
| Criteria | whether the request wants exact-locality or radius retrieval (`query_mode`) |
| Analysis | which **grey-zone** listings (robust \|z\| between 2.0 and 3.5) have descriptions that contradict their stated price or area |
| Critique | which months of the trend look implausible |
| Aggregator | the user-facing summary |

**Every statistic stays deterministic Python in both modes.** An LLM computing
a median would make every metamorphic relation meaningless; the model supplies
judgment and language, never arithmetic. A parity test asserts that with the
critique held fixed, both modes produce byte-identical series.

**Reproducibility.** Temperature is 0 and the harness's recorded seed is passed
to the model on every call, so the model is a **third pinned artifact**
alongside the frozen snapshot and the seed list — recorded as
`qwen2.5:3b-instruct-q4_K_M`, digest `d7f5d340f8953384`. A determinism probe
(20 repeats, same prompt, same seed) returned **20/20 identical replies on a
Kaggle T4**, so the recorded seeds genuinely pin behaviour. Responses are
cached by `(prompt, seed, model)` hash and the cache is shipped, so the sweep
replays without a GPU.

**Honesty about failure.** Calls that never yield parseable, valid output fall
back to a recorded default, and **every fallback is counted and reported**.
Measured over 14,209 calls: **fallback rate 0.0874**. Separately, the
Aggregator's summary is rejected by a faithfulness guard whenever it contains a
figure not present in the supplied facts — that happened on **35% of runs**
(826 of 2,376), and those runs show the deterministic template instead. So the
honest statement is that three agents use the model and the fourth is
overridden about a third of the time.

### Why a small model, and why not a bigger one

The brief permits a local model and notes a small one is fine. Qwen2.5-3B was
chosen as the smallest size that returns parseable JSON reliably; at 1.5B the
retry logic dominated. A sweep is 1,188 checks × ~6 calls, so a larger model
would not have fitted the Kaggle session.

## 3. Where the AI was wrong, and how it was caught

These are real errors made during this project, in the order they happened.

### 3.1 Both agent cycles were silently dead

The first LangGraph wiring set routing flags as `state["_widen"]` and
`state["_escalate"]` — keys **not declared** in the state TypedDict. LangGraph
derives its channels from those annotations and silently discards updates to
undeclared keys, so both conditional edges were unreachable and the graph ran
as a linear pipeline.

**Caught by** reading the execution trace rather than trusting the exit code:
it showed `CoverageAgent decision=ITERATE` immediately followed by
`AnalysisAgent`. The auditor asked to loop and nothing looped. Tests now assert
each cycle fires.

### 3.2 One relaxation lever starved the others

The planner re-scanned its lever list from the start each round. BHK can always
widen by ±1, so it won every time and the geography filter — the actually
binding constraint — was never relaxed. Coverage stalled at 0.167 for three
rounds while the trace *looked* healthy, because the loop was firing.

**Caught by** noticing coverage did not improve between rounds. Fixed with a
lever cursor; coverage now goes 0.083 → 0.167 → 0.500.

### 3.3 Filtering the data made a cycle decorative

The loader originally applied plausibility bounds that removed the area-entry
errors up front. That looked like hygiene and was actively harmful: it removed
the very contamination the escalation cycle exists to catch. Verified — on the
bounded frame the cross-field checks found **0 disagreements in 4,504 rows**,
so the loop could never change an answer.

**Caught by** measuring whether the loop changed the output instead of assuming
it did.

### 3.4 A confidently-stated root cause that was wrong twice

The diagnosis of MR-M1's 0.787 violation rate was first asserted as price-band
boundary crossing; a first measurement appeared to contradict it (only 2
crossing listings across 12 inputs), prompting a second hypothesis about
control-flow divergence — which explained only 4 of 85 violations.

**Caught by** computing the medians directly with no agents involved, which
showed a median *falling* by ₹1,122,750 under a uniform ₹500,000 increase. The
original mechanism was right; the first measurement had understated it, because
a single crossing listing dominates a 15-listing month. **Lesson recorded: the
magnitude of a cause cannot be inferred from the count of affected rows when
the statistic is a median over a thin sample.**

### 3.5 A refinement that made the relation worse

The first fix for M1 shifted the price band alongside the data. Violations went
**up**, 6/16 to 12/16: it holds the target month's population fixed but changes
every untouched month's, because their prices did not move.

**Caught by** re-running the relation instead of trusting the reasoning.

### 3.6 Four faults in the LLM prompts — found by the relations themselves

The first LLM sweep showed three relations that hold deterministically failing
badly: relabelling listing ids **0.630**, duplication **0.417**, a display-unit
change **0.028**. The determinism probe (20/20 identical) ruled out model noise,
so these were systematic. Causes:

1. **Listing ids appeared in the review prompt.** A bijective relabelling
   changed the text the model saw. An identifier carries no information about
   whether a description corroborates a price.
2. **The critique table was rendered in display units.** Re-expressing the
   report in ₹lakh per square metre changed which months were called anomalous.
3. **Listing counts were shown to the critique.** Duplication doubles every
   count, so a count-aware judge flagged different months.
4. **The review batch took the top N of a duplicated set**, returning N/2
   distinct listings twice instead of N distinct ones.

**Caught by** the metamorphic relations — none of this is visible by reading the
code. Fixed by presenting listings positionally, sorting on every displayed
field, deduplicating on content, and rendering the critique in canonical units
with counts withheld. Re-measured: **I4 0.630 → 0.000, I2 0.028 → 0.000,
I3 0.417 → 0.176.**

### 3.7 A fix that traded one fault for two others

Withholding counts from the critique (cause 3 above) left the model judging
purely on the median series — and that made two *other* relations worse:
**window-shift 0.222 → 0.667** and **add-₹X 0.222 → 0.333**, because those are
exactly the relations that perturb medians.

**Caught by** the second sweep. Reported as a measured trade-off rather than
quietly left in the table; §8 of the report argues why invariance was the right
side to favour.

### 3.8 A test that passed by luck

The reorder relation scored 0.000 across 108 runs — but a prompt-invariance test
later showed the review ordering sorted on a *subset* of the displayed fields,
so listings tied on (psf, price, area) kept their input order and reordering the
rows *did* change the prompt. No tie happened to flip in those 108 runs.

**Caught by** a test that checked the property directly rather than sampling it.
**Lesson: 108 passing runs is not the same as the property holding.**

### 3.9 A false statement about the project's own documents

While advising which file to share with a teammate, the assistant stated that
`DESIGN.md` cited a specific Kaggle dataset owner. It did not — the claim came
from a recommendation written elsewhere. **Caught by** the user asking where it
appeared, which prompted a grep. The document-verification pass in §4 exists
because of this.

### 3.10 An over-strict output guard

After rewriting the narrative prompt, the guard's leak markers were broadened to
phrases the model could legitimately produce, pushing narrative rejection from
82% to ~100% in a smoke test. **Caught by** comparing accounting between runs.
The full-run figure is 35%; the 100% was a 22-call artifact, and the assistant
had over-read it.

## 4. Document verification

Because of §3.9, every factual claim in `DESIGN.md`, `REPORT.md`, `README.md`,
`NOTEBOOK.md` and `docs/DIAGNOSIS.md` was re-checked against code, result files
or a measurement before submission (`scripts/verify_claims.py` re-derives them
and exits non-zero on any mismatch). That pass found two wrong numbers — a
"97%" that was 96.5%, and twenty stale agent names surviving a first rename.

### 3.11 A citation the assistant called suspect, which was correct

The data README cited `arvanshul/gurgaon-real-estate-99acres-com`. Reasoning
from the slug, the assistant judged this a transcription error — a Gurgaon
dataset could not hold a Hyderabad file — and recommended citing the dataset
the brief names instead. **Both conclusions were wrong.** Reading the two
dataset pages showed the cited one is titled "Indian Real Estate – 99acres.com"
and covers "Gurgaon, Hyderabad, Mumbai, Kolkata", with the CDLA-Sharing-1.0
licence exactly as claimed; the brief's recommended dataset covers Gurgaon only
and does not contain the file. Acting on the recommendation would have
introduced a false citation.

**Caught by** checking the sources instead of reasoning from a name — the same
failure mode as §3.9, one step further out.

## 5. Human responsibility

The authors reviewed all code and all numerical claims. Errors that remain are
the authors'.
