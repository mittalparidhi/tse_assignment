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

# the headline results table, rebuilt from the committed records (instant,
# no model needed) -- and --check verifies every rate appears in REPORT.md
python scripts/headline_table.py --check

# or re-run a sweep from scratch (stronger, slower)
python scripts/run_harness.py --tag check      # deterministic, ~6 min
```

That verifies the snapshot checksum, rebuilds the canonical frame, runs
**11 relations × 36 base inputs × 3 seeds = 1,188 runs**, and writes the
results table to `results/check/headline.txt`.

Three configurations were swept, 1,188 checks each:

```
MR     family       determ.  LLM pre-fix  LLM post-fix   95% CI (post-fix)
I1     invariance    0.000      0.000        0.000        [0.000, 0.034]
I2     invariance    0.000      0.028        0.000        [0.000, 0.034]
I3     invariance    0.000      0.417        0.176        [0.116, 0.258]
I4     invariance    0.000      0.630        0.000        [0.000, 0.034]
I5     invariance    0.000      0.000        0.000        [0.000, 0.034]
M1     monotonic     0.139      0.222        0.333        [0.252, 0.427]
M2     monotonic     0.000      0.111        0.111        [0.065, 0.184]
M3     monotonic     0.000      0.000        0.000        [0.000, 0.034]
M1raw  monotonic     0.861      0.852        0.806        [0.721, 0.869]
D1     directional   0.000      0.222        0.667        [0.573, 0.748]
D2     directional   0.000      0.556        0.593        [0.498, 0.681]

seeds [11, 23, 47] · C1 path divergence 0/1188 in all three
```

**`M1raw` is meant to fail** — it is the documented unsound relation, retained
as a counter-example. **I4 and I2 going 0.630/0.028 → 0.000** is the LLM
prompt-contamination fix (`docs/DIAGNOSIS.md` Finding 8). **D1 and M1 getting
worse** is a measured trade-off, argued in `REPORT.md` §8.6.

### Other entry points

```bash
streamlit run app.py                                  # the dashboard
python -m pytest                                      # 101 tests, 1 xfail
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
(`tests/test_agents.py`). A trace is in `results/after_fix/trace_example.txt`.

## Repository layout

| Path | Contents |
|------|----------|
| `DESIGN.md` | design note: architecture, data source, the MR catalogue |
| `docs/DIAGNOSIS.md` | root-cause analysis of the most-violated relations |
| `AI_USE.md` | AI-assistance disclosure, including where it was wrong |
| `NOTEBOOK.md` | lab notebook: what was tried, what broke, what the numbers were |
| `src/contract.py` | **the output contract** — what every MR asserts on |
| `src/loading.py` | raw snapshot → canonical frame, with five documented defects |
| `src/trend.py` | the deterministic statistics |
| `src/agents/` | the six agents and the cyclic graph |
| `src/mr/` | transformations, the 10 relations, base inputs, the harness |
| `src/llm.py` | Ollama client: seeded, cached, counted fallbacks |
| `src/viz.py`, `app.py` | the dashboard |
| `notebooks/` | the Kaggle notebook for the LLM sweep |
| `data/raw/` | the frozen 99acres snapshot, never modified, SHA-256 pinned |
| `data/snapshot/` | derived canonical + synthetic snapshots |
| `results/` | `before_fix/`, `after_fix/`, `synthetic/`, `diagnosis/` |

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
- **The LLM path is weaker than its presence suggests**: fallback rate 0.0874,
  and the summary agent's output is rejected by a faithfulness guard on 35% of
  runs.
- The dataset's slug (`gurgaon-real-estate-99acres-com`) is misleading: it is a
  multi-city archive titled "Indian Real Estate – 99acres.com" covering
  Gurgaon, Hyderabad, Mumbai and Kolkata. Origin and CDLA-Sharing-1.0 licence
  verified on the dataset page.
