# Metamorphic Testing of a Multi-Agent Housing-Trends Application

A six-agent system that reads a frozen snapshot of Hyderabad residential
listings and reports how asking prices moved over twelve months — tested with
**ten metamorphic relations** rather than against known-correct answers.

TSE assignment. Target market: Hyderabad / Secunderabad (the brief's optional
Indian-metro route).

---

## Reproducing the headline results

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# the contract-v2 results table, rebuilt from the committed records (instant);
# --check also verifies every rate and interval bound appears in REPORT.md
python scripts/headline_table.py --v2 --check

# the earlier published three-configuration table, and a check that every
# rate in it appears in REPORT.md
python scripts/headline_table.py --check

# or re-run the contract-v2 sweep from scratch (stronger, ~50 min)
python scripts/run_harness.py --tag v2_deterministic
```

That verifies the snapshot checksum, rebuilds the canonical frame, runs
**12 relations × 72 base inputs × 3 seeds = 2,592 runs** (36 locality and
36 radius inputs; each relation runs on the inputs in its subdomain), and
writes the results table to `results/v2_deterministic/headline.txt`.

Contract-v2 deterministic sweep (statistical unit = base input; a base input
is violated if any seed violates):

```
MR     family       bases  viol   rate    95% CI           stable-path rate
I1-I5  invariance     72     0   0.000   [0.000, 0.051]    0.000
M1     monotonic      72    14   0.194   [0.120, 0.300]    0.194
M2     monotonic      72     0   0.000   [0.000, 0.051]    0.000
M3     monotonic      36     0   0.000   [0.000, 0.096]    0.000
M4     monotonic      36     0   0.000   [0.000, 0.096]    0.000
M1raw  monotonic      71    51   0.718   [0.605, 0.810]    0.718
D1     directional    72     0   0.000   [0.000, 0.051]    0.000
D2     directional    72     0   0.000   [0.000, 0.051]    0.000

seeds [11, 23, 47] · seeds disagreed on 0 base inputs · C1 path diverged in 42/2,592 runs
```

**`M1raw` is meant to fail** — the documented unsound relation. **M1**
violates only when the follow-up run's cycle-2 rejected set differs (14/14):
the relative outlier filter is not shift-invariant. **M3 found a genuine
design fault** — geography widening around the selection's shared centre
broke locality-set inclusion (9/36 bases, M2 2/72; kept in
`results/v2_before_m3fix/`). Widening is now per locality and preserves
inclusion; M3 and M2 are 0 (`NOTEBOOK.md` Stages 17–18). These are the
numbers after aligning with the team's design note (contract v2.1); the sweep
before it is kept in `results/v2_before_note_alignment/` (M1 0.167, M1raw
0.542, all else 0) and every deviation from the note is listed in
`contracts/CONTRACT.md` §13 (`NOTEBOOK.md` Stage 20).

The earlier sweeps (`results/phaseA_deterministic`, `llm_before_promptfix`,
`llm`; 11 relations × 36 inputs, per-run intervals, the pre-v2 population)
are kept as the record behind `docs/DIAGNOSIS.md`, which also holds their tables. The
pre-v2 LLM sweeps are superseded by the v2 LLM sweep below.

Contract-v2 LLM sweep (`results/v2_llm/`, Kaggle T4, `qwen2.5:3b-instruct-q4_K_M`;
same 72 base inputs, unit = base input):

```
MR     bases  viol   rate    95% CI           deterministic
I1-I5    72     0   0.000   [0.000, 0.051]    0.000
M1       72    27   0.375   [0.272, 0.490]    0.194
M2-M4  72/36    0   0.000                     0.000
M1raw    71    53   0.746   [0.634, 0.833]    0.718
D1       72     5   0.069   [0.030, 0.152]    0.000
D2       72    19   0.264   [0.176, 0.376]    0.000

fallback rate 0.0383 over 17,164 model requests · I3 was 0.111 before the review fix
```

It found one genuine fault — the listing review cut its batch before removing
duplicates, so duplicating the data changed what the model saw (I3 0.111 →
0.000 after the fix; `results/v2_llm_before_reviewfix/`). D1, D2 and M1's
excess fail because shifting the window or the prices changes what the model
judges. `python scripts/replay_llm_sweep.py` reproduces it from the committed
reply cache without a GPU (`REPORT.md` §7.2, §8).

### Other entry points

```bash
streamlit run app.py                                  # the dashboard
python -m pytest                                      # 154 tests
python scripts/run_checks.py                          # all checks, logged to audit/test_logs/
python scripts/replay_llm_sweep.py                    # the LLM sweep replayed offline, no GPU
python scripts/build_report_pdf.py                    # REPORT.md -> REPORT.pdf (needs `pip install markdown` and Chrome/Edge)
python scripts/export_ui_data.py                      # real results for 8 queries -> results/ui/ (for the web UI prompts in docs/)
python scripts/make_synthetic.py                      # synthetic snapshot + oracle check
python scripts/run_harness.py --tag syn --synthetic   # relations vs known ground truth
python scripts/diagnose.py                            # the root-cause experiments
python -m src.agents.graph                            # print an execution trace
python scripts/run_harness.py --tag quick --quick     # 3 base inputs, fast
```

---

## What the system does

Six agents over a shared state, in a graph with **two cycles**:

```
Criteria agent ──> Retrieval agents (x4, parallel) ──> Coverage agent
                          ^                                  │
                          └──── (C1) widen one criterion ────┤ coverage < target
                                                             ↓ ok
                   Analysis agent <──── (C2) recompute ──── Critique agent
                          │            flagged months             ^
                          └───────────────────────────────────────┘
                                                             ↓ approved
                                                      Aggregator agent
```

- **C1** — `Coverage agent`, downstream of retrieval, scores how many of the
  12 months have enough listings and, if too few, widens one criterion (price
  band, then BHK, then geography) and sends work back to the Retrieval
  agents, recording what it gave up. Forced by the data: "3 BHK in Gachibowli
  over 12 months" yields months with n < 50, so most of the trend is
  otherwise undefined.
- **C2** — `Critique agent` checks the computed trend and, when a month looks
  wrong, sends a complaint naming those months back to the `Analysis agent`,
  which recomputes only them with contextual outliers removed.
- **Dependency** — the `Criteria agent` sets `query_mode`, and the Retrieval
  agents then run a different algorithm (locality set membership or haversine
  radius search).

The contracts for every agent are in `contracts/` (v2.0.0-draft).

Both are real conditional edges in the compiled graph, both are capped so
termination is guaranteed, and both are asserted to fire by tests
(`tests/test_agents.py`). A trace from the contract-v2 sweep, showing both loops firing, is in
`results/v2_deterministic/trace_example.txt`.

## Repository layout

| Path | Contents |
|------|----------|
| `REPORT.md`, `REPORT.pdf` | the final report (10 pages, A4) |
| `DESIGN.md` | design note: architecture, data source, the MR catalogue |
| `contracts/` | the output contract and one contract per agent (v2.1.0-draft) |
| `docs/DIAGNOSIS.md` | root-cause experiments for every violated relation, and the pre-v2 results |
| `docs/ISSUE_LOG.md` | **index of every issue found**: how it was caught, the evidence, the fix |
| `docs/INTEGRATION_REPORT.md` | every change made to the second implementation during the merge, and why |
| `docs/CONTRIBUTIONS.md` | who did what: each team member's work, with the commits and files behind it |
| `AI_USE.md` | AI-assistance disclosure, including where it was wrong |
| `NOTEBOOK.md` | lab notebook: what was tried, what broke, what the numbers were |
| `audit/` | data audits; `test_logs/` (check runs), `llm_logs/` (LLM agent fallback logs, Kaggle log) |
| `src/contract.py` | **the output contract** — what every MR asserts on |
| `src/loading.py` | raw snapshot → canonical frame; defects handled as documented in `contracts/Data.md` |
| `src/trend.py` | the deterministic statistics |
| `src/agents/` | the six agents and the cyclic graph |
| `src/mr/` | transformations, the 12 relations, base inputs, the harness |
| `src/llm.py` | Ollama client: seeded, cached, counted fallbacks |
| `src/viz.py`, `app.py` | the dashboard |
| `notebooks/` | `kaggle_v2_llm_sweep/`: the Kaggle job behind `results/v2_llm/`; `kaggle_llm_sweep.ipynb`: the pre-v2 notebook |
| `data/raw/` | the frozen 99acres snapshot, never modified, SHA-256 pinned |
| `data/snapshot/` | derived canonical + synthetic snapshots |
| `results/` | v2: `v2_deterministic/`, `v2_llm/`, `v2_llm_before_reviewfix/`, `v2_synthetic/`, `v2_before_m3fix/`, `v2_before_note_alignment/`, `v2_diagnosis/`, `v2_sensitivity/`; pre-v2 sets described in `docs/DIAGNOSIS.md` |

## Data

99acres.com Hyderabad slice via Kaggle, 9,487 rows × 55 columns, scraped
≈ 26 Aug 2023. CDLA-Sharing-1.0. The raw file is never modified and its
SHA-256 is re-verified on every load — a changed snapshot aborts the run
rather than silently producing different numbers.

Five defects are documented and handled, among them:

- **`MIN_AREA_SQFT` is square metres despite its name.** The ratio of the
  `AREA` display string to that column is **10.7639 at both the 5th and 95th
  percentile** over 3,531 rows. Using it would inflate every ₹/sqft figure
  10.76×.
- **An int32 sentinel** (2,147,483,647 = 2³¹−1) in the price fields.
- **2,806 of 2,814 missing bedroom counts are `Residential Land`** — plots have
  no bedrooms, so this is structural inapplicability rather than missing data.

**The main threat:** it is a single-point scrape, so older months hold only
listings still live on the scrape date. 96.4% of the window's listings fall in
its last six months, and thin months' medians swing on 22–35 listings. The
report therefore carries a per-month `sufficient` flag and month-comparing
relations are declared only over that subdomain.

## Why a synthetic snapshot as well

`scripts/make_synthetic.py` builds a snapshot with a **constructed** trend, so
the correct answer is known. It supplies the one thing the real data cannot:
an **oracle**. The check confirms `compute_trend` recovers the growth rate
that was put in — mean error **−0.057% ± 0.220% SE (z = −0.26)**, with the
locality rank order recovered exactly.

This is also what separates two of the brief's root-cause categories: a
relation violated on data whose ground truth is known cannot be blamed on a
data artifact.

## Running with the local model

Four agents' *judgment* can be routed through a local Qwen2.5-3B via Ollama
(`--llm`). All arithmetic stays deterministic Python in both modes. The model
is a third pinned artifact alongside the snapshot and the seeds:
`qwen2.5:3b-instruct-q4_K_M`, digest `d7f5d340f8953384`, temperature 0, seed
passed on every call. A determinism probe returned **20/20 identical** replies.
Responses are cached in `data/llm_cache/`, so the sweep **replays without a
GPU**.

```bash
ollama serve &
ollama pull qwen2.5:3b-instruct-q4_K_M
python scripts/run_harness.py --tag llm --llm
```

## Caveats

- **The headline figure is not robust.** Varying the sufficiency threshold
  moves it from −6.41% to +87.18% — **93.6 points, and the sign flips** —
  because the early months hold 21–35 listings. We report −6.41% as what the
  contract produces, *not* as a finding about Hyderabad's market
  (`REPORT.md` §9).
- `POSTING_DATE` is a posting timestamp, so this is an **asking-price** trend.
- The n ≥ 50 sufficiency threshold is a judgement call, not a derived value.
- **The LLM path is weaker than its presence suggests**: pre-v2 the fallback
  rate was 0.0874 and the summary was rejected by a faithfulness guard on 35%
  of runs; in v2 it is 0.0383, and the summary comes from the model only when
  there is a price change.
- The dataset's slug (`gurgaon-real-estate-99acres-com`) is misleading: it is a
  multi-city archive titled "Indian Real Estate – 99acres.com" covering
  Gurgaon, Hyderabad, Mumbai and Kolkata. Origin and CDLA-Sharing-1.0 licence
  verified on the dataset page.
