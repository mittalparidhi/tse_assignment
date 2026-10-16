# Contributions — who did what

**Team:** Paridhi Mittal and her teammate (two-person team, as the brief allows)
**Sources for every row:** the git history (`git log --format="%h %an %ad %s"`),
the teammate's own notes in her commit (`docs/FOR_PARIDHI.md` at `957224c`),
the first implementation kept in `legacy/`, and the diff between the two
implementations. Each person's AI assistance is disclosed in `AI_USE.md`.

---

## 1. At a glance

| Area | Paridhi | Teammate |
|---|---|---|
| Frozen data snapshot, checksum, provenance | **built it** (11 Oct) | built on it |
| Dataset audit | **missingness, monthly counts, numeric anomalies, field inspection** (11 Oct) | verified and characterised five defects with measurements |
| Design note | **wrote it**: six agents with Reads/Writes, both cycles, `query_mode`, MR table, LangGraph | reviewed it against measurements; proposed corrections |
| Agent contracts | **13-file suite** (v1); rewrote it as the final 12-file suite (v2.1) | — |
| Data, audit and cleaning scripts | **31 scripts** (v1) | — |
| First implementation | **criteria, retrieval, anomaly agents, execution graph, typed schemas, tests** (v1) | — |
| Second implementation (LangGraph graph, statistics, dashboard) | — | **built it**, following the design note |
| Metamorphic relations and harness | added M4 and 36 radius inputs; base-input statistics; rejected-count recording | **11 relations, harness, base inputs** |
| Synthetic control snapshot | repaired the generator | **built it**, with its oracle |
| Local-model mode | safeguards, I3 review fix, narrative fixes, offline replay | **built it**: Ollama client, prompt-hygiene rules, determinism probe |
| Pre-v2 sweeps and diagnosis | — | **ran them** (deterministic and two LLM sweeps on Kaggle); Findings 1–9 |
| Merge of the two implementations | **did it**, in reviewed phases | — |
| Data rules and validation in the final system | **ported from v1**: IST months, Price-on-Request, price validity, unique IDs, request validation | — |
| Alignment with the refined design note (v2.1) | **did it**; documented ten deviations | — |
| v2 sweeps (deterministic, synthetic, LLM) | **ran them**; LLM sweep on Kaggle; verified by offline replay | — |
| Faults found by the relations in v2 | **M3** (widening), **I3** (LLM review), narrative guard — each fixed and re-measured | — |
| RESIDEX cross-check, threshold sensitivity | made the sensitivity table reproducible (script) | **did the cross-check**; first table |
| Report | rewrote for v2; cut to 10 pages; PDF | wrote the first report (pre-v2) |
| NOTEBOOK, AI_USE, DIAGNOSIS | Stages 16–24; AI_USE §§5–6; Findings 10–11; issue index | Stages 0–15; AI_USE §§1–4; Findings 1–9 |
| Tests | 84 functions (v1); final suite 132 functions | 84 functions (v2 starting point) |
| Commits | all the others: 3 for the foundation, 1 for the first implementation (`459aeca`), the rest for the integration | 2 (each a large snapshot of her work) |

Commit counts are not a measure of effort: the teammate committed her work in
two large snapshots, and Paridhi's first implementation was committed in one.

---

## 2. Timeline

| Date | Who | What | Commits |
|---|---|---|---|
| 11 Oct | Paridhi | froze the raw snapshot with checksum and Readme | `0caeb2e` |
| 11 Oct | Paridhi | dataset audit; field and anomaly inspection | `3793127`, `273045e` |
| ≤ 12 Oct | Paridhi | design note; first implementation, contracts, scripts, tests (six logged test runs on 12 Oct) | in `459aeca`; `legacy/` |
| 14–15 Oct | Teammate | second implementation, built from `273045e` and aligned to the design note; pre-v2 sweeps; diagnosis; first report | `736d594`, `957224c` |
| 15 Oct | Paridhi | merge; contract suite v2; data rules and validation ported; harness and agent fixes; M3 fault found and fixed; v2 sweeps | `bed240b` … `65db1ec` |
| 15 Oct | Paridhi | alignment with the refined design note (v2.1); re-run | `f4752f8` … `5b9271e` |
| 16 Oct | Paridhi | v2 LLM sweep on Kaggle; I3 fault found and fixed; offline replay; report cut; logs and issue index | `c8e6e85` … `a2988b5` |

---

## 3. Paridhi's work

### 3.1 Foundation (before the teammate's work)

- **Frozen snapshot** (`0caeb2e`): the 99acres Hyderabad slice, 9,487 rows ×
  55 columns, with its SHA-256 checksum and a provenance Readme. The dataset
  citation and licence were later verified as correct, against a suggestion
  that they were a transcription error (`docs/FOR_PARIDHI.md`, item 10).
- **Dataset audit** (`3793127`, `273045e`): missingness per column, monthly
  listing counts, numeric anomalies, field inspection
  (`audit/hyderabad_*.csv`, `scripts/audit_hyderabad.py`,
  `scripts/inspect_hyderabad_*.py`).
- **Design note** (`Assignment1_Design_Note_Final.docx`): the six agents with
  explicit Reads/Writes; cycle 2 as Critique → Analysis with a specific
  complaint and flagged months; `query_mode` as the genuine dependency; the
  control-flow table with "why necessary"; the five-column MR table; LangGraph.
  The teammate's notes record adopting all of these, and that cycle 2 and
  `query_mode` replaced her earlier design.
- **Contract suite** (`legacy/contracts/`, 13 files, about 33,000 words):
  global contract, data, agents, planner, validator, anomaly, reporter,
  aggregator, diagnostic, LLM, testing, golden, and a consistency audit.
- **Data, audit and cleaning scripts** (`legacy/scripts/`, 31 scripts): the
  cleaning pipeline and processed snapshot, the Price-on-Request exclusion,
  reporting-month identity, locality / price / month audits, runtime-state
  builders.
- **First implementation** (`legacy/app/`, about 3,250 lines): criteria agent,
  retrieval agent, anomaly detector, execution graph, typed schemas, snapshot
  repository.
- **Tests** (`legacy/tests/`): 84 test functions in 15 files, with six logged
  runs (`legacy/audit/test_logs/`; last: 77 passed, 12 subtests).

### 3.2 Integration and the final system (after the teammate's work)

Detailed change by change, with reasons, in `docs/INTEGRATION_REPORT.md`. In
summary:

- **Merged** the second implementation in reviewed phases; made the snapshot
  checksum survive Windows; moved the first implementation to `legacy/`.
- **Contracts:** rewrote the suite for the integrated system (12 files,
  v2.1.0-draft), with ten argued deviations from the refined design note.
- **Data rules** ported from the first implementation: months in IST,
  Price-on-Request and price-validity flags (rows kept, not dropped), unique
  listing IDs, locality IDs, the midpoint listing price. Population 4,975
  listings, 4,574 with a usable price.
- **Request validation** ported (`src/validation.py`) and wired into the
  dashboard.
- **Agents:** coverage with ACCEPT / RETRY / LIMITED and the note's lever
  order; geography widening that keeps the locality filter and provably
  preserves set inclusion; critique coherence checks and NEEDS_REVIEW;
  correct rejection accounting; provenance of every report.
- **Harness:** 36 radius base inputs and relation M4 (72 inputs, 12
  relations); the base input as the statistical unit; rejected counts recorded
  per run; transforms that keep price fields consistent.
- **Local model:** weights digest recorded; a check that the model answers
  before a sweep; stop on a dead server; replies saved as they arrive; the
  offline replay that reproduces the LLM sweep without a GPU.
- **Sweeps:** the v2 deterministic and synthetic sweeps, and the v2 LLM sweep
  on a Kaggle T4 — run, re-run after the fix, and verified by replay.
- **Faults found by the relations and fixed:**
  - **M3**: the second implementation's widening dropped the locality filter,
    so M3 could not fail; Paridhi's first fix then broke set inclusion, M3
    caught it (9/36), and the final rule fixed it (0/36);
  - **I3 under the model**: the review cut its batch before removing
    duplicates — a line from the second implementation, also behind its open
    I3 residual (8/72 → 0/72);
  - the **narrative guard** rejected figures it had itself supplied, and the
    model copied the facts when there was no price change.
- **Reproducibility:** headline-table checks for both sweeps,
  `verify_claims.py` for the v2 population, the threshold-sensitivity script,
  golden regeneration with recorded reasons, logged check runs, a
  clean-checkout check.
- **Documents:** the report rewritten for v2 and cut to 10 pages (with PDF);
  NOTEBOOK Stages 16–24; AI_USE §§5–6; DIAGNOSIS Findings 10–11; the issue
  index; the integration report.
- **Tests:** from 84 to 132 test functions (154 cases), including request
  validation and a dashboard test.

---

## 4. The teammate's work

All in commits `736d594` and `957224c` (14–15 October), built from Paridhi's
commit `273045e` and aligned to her design note:

- **The second implementation:** the LangGraph graph with two cycles and four
  parallel retrieval agents with stable hashing (`src/agents/`, 1,254
  lines of agent code among 3,592 lines in `src/`); the loader, output
  contract and statistics; the dashboard (`app.py`, `src/viz.py`).
- **Defect verification:** measured the five data defects — the square-metre
  area column (ratio 10.7639 at both tails), the int32 sentinel, mixed sale /
  rent / PG listings, structurally missing bedrooms on land, area-entry
  errors — and kept the last for cycle 2.
- **Metamorphic relations and harness:** 11 relations across the three
  families, 36 base inputs, three seeds, Wilson intervals, control-path
  stability, the retained counter-example `M1raw`.
- **Synthetic control snapshot** with a known trend and its oracle.
- **Local-model mode:** the Ollama client with seeding, caching and counted
  fallbacks; the four prompt-hygiene rules; the determinism probe (20/20
  identical replies); two LLM sweeps on Kaggle.
- **Diagnosis:** Findings 1–9 — the per-worker outlier threshold behind I3 and
  I4, M1's band crossing, the non-idempotent filter behind M2, the
  synthetic-only loop tension, a harness bug, the prompt faults and the
  architectural trade-off.
- **External cross-check:** NHB RESIDEX against the snapshot, and the
  threshold-sensitivity table showing the headline's sign depends on the
  threshold.
- **Scripts:** `run_harness.py`, `diagnose.py`, `headline_table.py`,
  `verify_claims.py`, `prompt_sensitivity.py`, `make_synthetic.py`,
  `make_results_section.py`, `validate_llm.py`.
- **Tests:** 84 test functions (101 cases) in 7 files.
- **Documents:** the first REPORT, DESIGN (structured to mirror the design
  note), NOTEBOOK Stages 0–15, AI_USE §§1–4, DIAGNOSIS.
- **Review of the design note** (`docs/FOR_PARIDHI.md`): 25 items, including
  five measured corrections — the sufficiency flag, renaming days on market,
  M1's band-free subdomain, D2's tolerance, and the conditionality of M2 / M3.

---

## 5. Where each part of the final system came from

| Component | Origin | Final state |
|---|---|---|
| Snapshot and checksum | Paridhi | unchanged; pinned on every load |
| Architecture: six agents, Reads/Writes, both cycles, `query_mode` | Paridhi's design note | implemented by the teammate; aligned to the refined note by Paridhi |
| LangGraph graph, parallel retrieval | teammate | kept |
| Data rules: IST months, Price on Request | Paridhi (v1) | ported by Paridhi |
| Data rules: price-validity flags, unique listing IDs, midpoint price | Paridhi (integration) | new |
| Defect handling (square metres, sentinels, sale only, dwellings) | teammate's measurements | kept |
| Output contract | teammate (v1 fields); refined note | rewritten by Paridhi (v2.1) |
| Contracts | Paridhi (v1 format) | rewritten by Paridhi |
| Request validation | Paridhi (v1) | ported by Paridhi |
| Relations I1–I5, M1–M3, M1raw, D1, D2 | teammate | updated by Paridhi for the new contract |
| M4 and radius inputs | Paridhi | new |
| Harness statistics (base-input unit) | teammate (per run) | changed by Paridhi |
| Synthetic control | teammate | repaired by Paridhi |
| LLM mode and prompt hygiene | teammate | safeguards and two fixes by Paridhi |
| Pre-v2 diagnosis | teammate | kept in `docs/DIAGNOSIS.md` |
| v2 sweeps and diagnosis | Paridhi | the report's results |
| Report | teammate (pre-v2) | rewritten by Paridhi |

---

## 6. AI assistance

Both implementations were built with AI assistance, as the brief encourages:
the teammate's with Claude through the Claude Code CLI (`AI_USE.md` §1), and
Paridhi's integration with Claude Opus 5.5 through the Claude Code desktop app
(`AI_USE.md` §§1, 5–6), including one commit (`2edd7bf`) from a second
session she ran in parallel. In both cases the decisions, the runs and the
responsibility for the results were the authors'.
