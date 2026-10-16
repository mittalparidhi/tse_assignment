# AI_USE.md — Disclosure of AI assistance

> **Credits:** §§1-4 by Vidhi Jain (commits 736d594, 957224c); §§5-7 by Paridhi Mittal. Lines by git blame: Vidhi Jain 56%, Paridhi Mittal 44%. Full attribution: CREDITS.md.

Per the brief's ground rules: all substantive AI use is disclosed here,
**including the cases where the tool was wrong and how that was caught.**

## 1. Where AI is used

| Context | Use |
|---------|-----|
| **Building the project** | Claude (Anthropic), via the Claude Code CLI, wrote most of the application code, the MR catalogue, the harness and the dashboard, and drafted `DESIGN.md`, `REPORT.md` and `docs/DIAGNOSIS.md`. It ran the data audits, the controlled experiments and the diagnostic analyses. |
| **Merging the two implementations (contract v2)** | Claude Opus 5.5, via the Claude Code desktop app, used by Paridhi: compared the two codebases, wrote the v2 contract suite, ported the first implementation's data and validation rules, fixed the harness and the agents, and updated the documents (§5). The deterministic v2 sweeps were run by Paridhi. |
| **Aligning with the design note, the v2 LLM sweep, the report cut (§6)** | The same assistant adopted the team's design note as contract v2.1, diagnosed and fixed the LLM-mode faults, wrote the Kaggle notebook cells and later pushed the final notebook through the Kaggle API, verified every result by offline replay, and cut REPORT.md to the brief's length. A second Claude session, run by Paridhi in parallel, made one commit (`07979f5`, §6.4). Paridhi ran the first Kaggle sessions, created the Kaggle credentials and approved every upload. |
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
`qwen2.5:3b-instruct-q4_K_M` with `d7f5d340f8953384`, which was described as
the model digest but is a hash of the model *name* (§5.6); the code now records
the weights digest Ollama reports, and the v2 LLM sweep records `357c53fb…`.
A determinism probe
(20 repeats, same prompt, same seed) returned **20/20 identical replies on a
Kaggle T4**, so the recorded seeds genuinely pin behaviour. Replies are cached
under a hash of model, temperature, seed, attempt and the full prompt, and the
cache is shipped: `scripts/replay_llm_sweep.py` replays the v2 LLM sweep with
no model at all, treating any missing reply as an error, and reproduces every
run record.

**Honesty about failure.** Calls that never yield parseable, valid output fall
back to a recorded default, and **every fallback is counted and reported**.
Pre-v2, over 14,209 calls: **fallback rate 0.0874**, and the Aggregator's
summary was rejected by a faithfulness guard (a figure not in the supplied
facts) on **35% of runs** (826 of 2,376). In the v2 LLM sweep the fallback rate
is **0.0383** over 17,164 requests. The summary is now requested only when
there is a price change (§6.4): replaying all 72 base inputs at seed 11, 21
summaries come from the model and none is rejected, the other 51 use the
template, and the remaining fallbacks are 8 listing-review replies that were
not valid JSON. In the harness the Criteria agent is not asked (the requests
are structured, not free text), so three agents use the model there.

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

### 3.12 A sample size written up as a finding

REPORT.md §8.5 (now in `docs/DIAGNOSIS.md`) stated that under duplication "the prompts still differ on
exactly **6 of 36** base inputs, and the correlation with the failures is
**exact**", naming base11/17/22/23/30/31. Both halves were false, and the two
errors had different origins.

The **6** was the *sample size*: `scripts/prompt_sensitivity.py` defaulted to
`generate_base_inputs(frame)[:6]`, so only base00–base05 were ever compared —
and for I3 that sample recorded *zero* prompt differences. The figure 6 was
lifted from the `inputs_tested` column and presented as though it were the
result. The named list came from the violation table of an earlier sweep, not
from any prompt comparison at all; the two were spliced into one sentence that
asserted a relationship neither had measured.

The word **"exact"** was the more serious error, because it claimed a
biconditional. Re-running the comparison over all 36 base inputs under all
three seeds — 108 cells — gives:

| | not violated | violated |
|-------------------|-------------:|---------:|
| prompt identical  | 51 | **0** |
| prompt differs    | 38 | 19 |

The necessary direction holds perfectly and deductively. The sufficient
direction fails in 38 of 57 cases. The true claim is weaker than the one
published, but it is also a better finding: it accounts for the seed pattern
(four base inputs failing on 3/3 seeds, seven on 1/3) that an exact correlation
could not explain.

**Caught by** a reader asking whether the Relations tab reports per-criteria or
whole-system results. Checking that led to the per-base-input breakdown, where
11 violating base inputs contradicted the published 6. The headline rate
(0.176) was never wrong, and `verify_claims.py` had been checking it — which is
why the error survived: the verifier asserted the *rate* but nothing about the
*localisation*, so a false mechanism sat behind a true number. It now asserts
the full 2x2 and both seed groups, and the script defaults to the whole
catalogue.

**Lesson recorded.** A number copied out of a results table inherits the
scope of the run that produced it, not the scope of the sentence it is dropped
into. This is the second instance of the same failure mode as §3.9 and §3.11:
asserting something about an artefact without reading the artefact.

## 5. The merge into contract v2, and where the assistant was wrong again

Two team members built independent implementations. Claude (Opus 5.5, Claude
Code desktop app) compared them, and the team chose this implementation as the
base and the first one's contracts, data rules and validation as the rules to
port. The assistant then did the work in reviewed phases (`NOTEBOOK.md`
Stages 16–18): merge, contract suite (`contracts/`), data-rule port, harness
and agent fixes. Decisions were made by Paridhi — for example, keeping both
price bounds (decision 7 in `contracts/CONTRACT.md` §11) and fixing M3's
fault rather than only reporting it. Errors the assistant made, in order:

### 5.1 Test names asserted, not checked

The first draft of the agent contracts listed tests as "exists" from memory;
four did not exist under those names. **Caught by** listing every test function
before committing and correcting each row.

### 5.2 An automated edit that produced invalid Python

A regex rewrite added `lineterminator="\n"` as the *first* argument of
`to_csv(...)`, before positional arguments, and nested double quotes inside an
f-string. **Caught by** compiling every file before committing; reverted and
redone with bracket matching.

### 5.3 Three geography-widening rules before one was right

(1) Adding as many localities as were selected stalled "3 BHK in Gachibowli"
at coverage 0.167 — caught by measuring coverage. (2) Widening around the
selection's centre until depth doubled broke set inclusion — caught by MR M3
(9/36). (3) The first inclusion-preserving rule ignored the selection and
halved the depth a clustered query gained (105 → 46 listings) — caught by
printing listing counts; the final rule skips selected localities and gives 60
while keeping inclusion (proved in `src/agents/nodes.py`, tested on 76 pairs).

### 5.4 An explanation written before it was measured

The report draft said the RESIDEX gap at n ≥ 75 "depended partly on" the
Price-on-Request exclusion and IST months. **Caught by** measuring before
committing: either change alone moves the figure by at most 0.2 points, the
two together by 1.24. The sentence now states the measurement.

### 5.5 A precondition described as checked when it was vacuous

The v2 testing contract first said the harness would check that M1/D2 move no
listing across a plausibility bound. The loader applies no such bounds, so the
check would always pass. **Caught by** reading the loader while implementing
it; replaced by recording cycle 2's rejected counts, the real mechanism.

### 5.6 Inherited claims that did not survive checking

Three claims in the earlier documents were not true as stated, and the
assistant had initially repeated them: the "model digest" was a hash of the
model name; the threshold-sensitivity table had no generating script (one now
exists and reproduces it); and the "+6.24% radius slice" could not be
reproduced at all (withdrawn). **Caught by** trying to regenerate every number
the report quotes rather than copying it.

### 5.7 Platform faults no one had seen

On Windows, git rewrote line endings in checksum-pinned files (the snapshot
checksum failed), two checking scripts crashed reading "₹" as cp1252, and a
"≠" column header crashed any redirected output. **Caught by** running the
reproduction commands on the Windows machine itself rather than assuming they
worked because they had worked elsewhere.

## 6. Aligning with the design note and the v2 LLM sweep (15–16 October 2026)

Paridhi asked the assistant to adopt the team's design note (*Agent
Architecture – Hyderabad Refined*), keep the choices it argued for, and
document each deviation; then to run the LLM sweep under the new contract,
which had not been possible on the Windows laptop. The first Kaggle sessions
were run by Paridhi from cells the assistant wrote; the final one was pushed by
the assistant through the Kaggle API after Paridhi created the credentials
and approved the upload of a private dataset and a private notebook.
The assistant never read the credentials file. Errors, in order:

### 6.1 A changed set of base inputs, noticed late

After the alignment the sweep reported M1raw over 71 base inputs instead of
72. Locality depth now counted all 4,975 listings, so 9 of the 36 locality
inputs had silently changed their fourth locality, and 9 more their order.
`base_inputs.csv` records only how many localities an input has, not which,
so comparing the two files showed no difference. **Caught by** regenerating
both input sets from their own commits and comparing them; the report states
the change and measures M1raw on the 63 inputs common to both sweeps.

### 6.2 A wrong diagnosis of a stalled run

When a Kaggle run made no model calls, the assistant concluded that the Ollama
server had died. The evidence was weaker than presented: the process listing it
relied on was cut to its first lines and showed only 8 of 12 processes, and a
later run reached a server on the same port. The safeguards added in response
are sound regardless (the harness now makes one real call before starting,
stops after ten backend errors in a row instead of falling back for hours, and
saves replies every 50), but the cause of that stall was not established.

### 6.3 Two statements about the upload that were not checked

The assistant said that `git archive` would give the zip Linux line endings.
That held for the data files, which the repository stores as-is, but with
`core.autocrlf=true` the code files came out with Windows line endings.
**Caught by** a patch cell's own assertion failing on Kaggle; the cell was
corrected and later archives were built with `core.autocrlf=false`.
Separately, it estimated that the final re-run would need 358 new model calls;
it needed 86. The estimate came from an offline replay in which every missing
reply fell back, which changed the later prompts.

### 6.4 A first explanation that covered part of the fallbacks, and a fix that failed

The first v2 LLM run had a fallback rate near 0.2. The assistant found a real
fault (the narrative guard rejected the radius figures it had itself supplied)
and guessed that the rest came from the model writing a count of the widened
localities. Measuring per agent (`scripts/llm_fallback_breakdown.py`) showed
otherwise: 49 of the 58 rejected summaries were the model copying the facts
block when there was no price change. The assistant's fix, a dedicated no-trend
prompt (`3b3006d`), was then tested on Kaggle by a second Claude session run by
Paridhi, which measured a fallback rate of 0.277 after 50 runs and replaced it
by not asking the model when there is no change (`07979f5`). That commit is
that session's, not this assistant's; the assistant learned of it only when it
found it in the history while verifying the results.

### 6.5 Results verified by replay, which exposed which code had run

The assistant did not take the Kaggle numbers on trust. The run record showed
almost no model time, so it replayed all 2,592 runs on the laptop from the
saved replies with any missing reply treated as an error. The replay matched
exactly with the code of `07979f5`, not the patch the assistant had sent,
which is how the second session's change was discovered (§6.4). The final
sweep was verified the same way, and the replay became
`scripts/replay_llm_sweep.py`.

### 6.6 A fault in the original code, found by the LLM sweep

The LLM sweep violated I3 on 8 of 72 inputs. Capturing the review prompts
showed the model 10 distinct listings in the source run and 8 after
duplication: the review cut its batch before removing duplicates. The line had
been in the code since the first implementation, and the pre-v2 report had
recorded its effect as an open defect, "localised, not isolated". Fixed and
re-measured on Kaggle (I3 0/72); the test that had been pinned as an expected
failure now passes. This was the relations working as intended rather than an
assistant error, but the assistant had read that code during the merge
without seeing the fault.

### 6.7 The report cut

REPORT.md was cut from 11,558 to about 5,300 words to meet the brief's 10–12
pages, after Paridhi approved an outline, including the choice of the LLM
sweep's three most-violated relations for the root-cause analysis. The pre-v2
results and diagnoses moved unchanged into `docs/DIAGNOSIS.md`, and the
scripts that check the published tables were pointed at their new locations.

## 7. Human responsibility

Decisions were Paridhi's throughout: which implementation to build on, which
of the design note's choices to keep, fixing faults rather than only reporting
them, re-running the LLM sweep after the I3 fix, and every action on the Kaggle
account. The authors reviewed all code and all numerical claims. Errors that
remain are the authors'.
