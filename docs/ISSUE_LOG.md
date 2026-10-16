# Issue log — every problem found, how it was caught, how it was resolved

> **Credits:** Paridhi Mittal. Full attribution: CREDITS.md.

One row per issue, grouped by where the problem was. The detail lives in the
documents linked from each row; this file is the index.

| Document | What it records |
|---|---|
| `NOTEBOOK.md` | the lab notebook: what was done, in order (Stages 0–23) |
| `docs/DIAGNOSIS.md` | the root-cause experiments behind every violated relation (Findings 1–11, and the pre-v2 diagnoses moved from the report) |
| `AI_USE.md` | where the AI assistant was wrong and how it was caught (§§3, 5, 6) |
| `audit/test_logs/` | timestamped logs of every check run (`scripts/run_checks.py`); `legacy/audit/test_logs/` has the first implementation's |
| `audit/llm_logs/` | the LLM agents' per-agent fallback breakdowns and the final Kaggle notebook log |
| `results/<tag>/` | each sweep's per-run records, summary, metadata, trace and (LLM sweeps) harness and model-request logs |

**Columns.** *Caught by*: what exposed the problem. *Evidence*: where the
measurement is kept. *Resolution*: the fix, with its commit where the fix was
made in this repository's history (the pre-merge work arrived as two squashed
commits, `736d594` and `957224c`, so earlier fixes cite the notebook stage).

## 1. Data

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| D1 | `MIN_AREA_SQFT` holds square metres | ratio `AREA` / column = 10.7639 at both tails | NOTEBOOK Stage 1; `audit/` | area parsed from the display string |
| D2 | int32 sentinel (2,147,483,647) and zero prices | data audit | NOTEBOOK Stage 1 | not price-valid |
| D3 | sale, rent and PG listings mixed | `PREFERENCE` counts | NOTEBOOK Stage 1 | sale only |
| D4 | `BEDROOM_NUM` missing on 29.7% | 2,806 of 2,814 are land | NOTEBOOK Stage 1 | dwellings only |
| D5 | area-entry errors in the tail (27 sqft "villa") | audit; then cycle 2 had nothing to do | NOTEBOOK Stage 3 | **kept** for cycle 2 to catch; loader filters removed |
| D6 | "Price on Request" placeholder prices | first implementation's audit | `legacy/`; `contracts/Data.md` | not price-valid (`701154f`) |
| D7 | months derived in UTC move 18 listings | comparing both implementations | NOTEBOOK Stage 16 | months in `Asia/Kolkata` (`701154f`) |
| D8 | one `PROP_ID` appears twice | merge audit | `contracts/Data.md` | `listing_id = PROP_ID#row` (`745ec7b`) |
| D9 | the dataset slug says Gurgaon | reading the Kaggle page | `data/SOURCE.md`; AI_USE §3.11 | it is the multi-city archive; citation kept |

## 2. Agents (deterministic)

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| A1 | both agent cycles silently dead: LangGraph dropped undeclared state keys | a trace where Coverage said "iterate" and nothing iterated | NOTEBOOK Stage 4; AI_USE §3.1 | state keys declared; loop tests |
| A2 | one relaxation lever starved the others: BHK won every round and the binding locality filter never widened | coverage stuck at 0.1667 for three rounds | NOTEBOOK Stage 5 | a lever cursor that advances each round (coverage then reached the target) |
| A3 | outlier threshold computed per *(worker, month)* | **I3, I4 violated on 108/108 runs** | DIAGNOSIS Finding 1; `results/diagnosis/`, `results/v2_diagnosis/` | per-month threshold; result independent of 1, 2, 4, 8 agents |
| A4 | MAD outlier filter not idempotent: a second round rejects more | **M2** 0.019 | DIAGNOSIS Finding 3 | recomputation capped at one round (a second was measured to cause violations) |
| A5 | geography widening dropped the locality filter (whole metro) | M3 could not fail; widening fired in every run | NOTEBOOK Stage 17 | widening keeps a locality constraint (`36a2c19`) |
| A6 | widening around the selection's centre broke set inclusion | **M3 9/36** | DIAGNOSIS Finding 10; `results/v2_before_m3fix/` | per-locality widening that provably preserves inclusion (`fdc7b88`); M3 0/36 |
| A7 | retrieval merge returned both rows of the repeated `PROP_ID` | merge audit | `contracts/Retrieval.md` §3 | merge by unique `listing_id` (`745ec7b`) |
| A8 | the adaptive loop (cycle 1) breaks invariance when counts change | **synthetic control**: M3 85 → 331 listings | DIAGNOSIS Finding 6 | design tension; relations reported over the control-path-stable subdomain |

## 3. LLM agents (Qwen2.5-3B via Ollama)

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| L1 | listing IDs printed in the review prompt | **I4 0.630** | DIAGNOSIS Finding 8 | listings shown by position |
| L2 | critique table in display units | **I2 0.028** | DIAGNOSIS Finding 8 | canonical units |
| L3 | top-N taken from a duplicated set | **I3 0.417** | DIAGNOSIS Finding 8 | content-addressed batch (partial: I3 0.176 remained, see L9) |
| L4 | review sorted on a subset of displayed fields | prompt-invariance test (I1 passed by luck) | DIAGNOSIS Finding 8; AI_USE §3.8 | total order over displayed fields |
| L5 | listing counts in the critique prompt | I3 (duplication doubled counts) | DIAGNOSIS Finding 9 | counts withheld; **trade-off**: D1 and M1 got worse |
| L6 | narrative guard's leak markers broadened to phrases the model could legitimately write (~100% rejection in a 22-call smoke test) | comparing accounting between runs | AI_USE §3.10 | markers narrowed; full-run rejection 35% (pre-v2) |
| L7 | narrative: model copied the facts block when there was no price change (49/72) | fallback rate ≈ 0.2 → per-agent breakdown | `audit/llm_logs/fallback_breakdown_405a3dc_before_narrative_fix.txt`; NOTEBOOK Stage 21 | no model summary without a change (`07979f5`; a no-trend prompt, `3b3006d`, failed first) |
| L8 | narrative guard rejected the radius figures it supplied (9/72) | same breakdown | same file | scope figures count as supplied (`3b3006d`) |
| L9 | review batch cut to 12 rows **before** removing duplicates | **I3 8/72** in the v2 LLM sweep | `results/v2_llm_before_reviewfix/`; DIAGNOSIS Finding 11 | de-duplicate, then cut (`98c741e`); re-run on Kaggle: I3 0/72; closes L3's residual |
| L10 | "model digest" was a hash of the model name | reproducing the record | AI_USE §5.6 | weights digest from Ollama recorded (`4d25530`): `357c53fb…` |
| L11 | a dead model server made every call fall back silently | a Kaggle run with no model calls for an hour | AI_USE §6.2 | one real call before starting; stop after 10 errors in a row; replies saved every 50 (`405a3dc`) |

## 4. Metamorphic relations

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| R1 | M1 with a price band in place changes the selected population | median **fell** ₹1,122,750 after a +₹500,000 shift | DIAGNOSIS Finding 2; REPORT §8.1 | ill-conceived: kept as `M1raw`; M1 declared on the band-free projection |
| R2 | M1's residual comes from the relative outlier filter | 15/15 violations with cycle 2 on, 0/15 off; 0 on synthetic | DIAGNOSIS Finding 5; REPORT §8.2 | data artifact; reported |
| R3 | D1, D2 (and part of M1) change what the LLM judge is shown | hold deterministically, fail with the model | DIAGNOSIS (pre-v2 §§8.3–8.4); REPORT §8.3 | ill-conceived for an LLM-judged pipeline; invariance favoured by design |
| R4 | M3 could not fail before the merge | counting how often widening fired | NOTEBOOK Stage 17 | became testable (A5), then found A6 |
| R5 | a precondition ("no listing crosses a plausibility bound") was vacuous | reading the loader | AI_USE §5.5 | replaced by recording cycle 2's rejected counts per run |

## 5. Harness and our own instrumentation

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| H1 | control-path signature compared message text | M3's stable subdomain came out empty | DIAGNOSIS Finding 7 | canonical lever sequence |
| H2 | the synthetic oracle failed twice for its own reasons: a wrong expected median, then multiple comparisons | oracle mismatches on known data | NOTEBOOK Stage 9 | mixture median solved numerically; Bonferroni bound plus a bias z-test |
| H3 | confidence intervals over runs overstated precision | 0/108 runs vs 0/36 inputs | REPORT §6 | base input is the unit (`4d25530`) |
| H4 | too few applicable base inputs (M2 24, M3 27, D1 30) | first sweep's counts | NOTEBOOK Stage 6 | strided sample of the full cross product; then 72 inputs (`6ac6098`) |
| H5 | `base_inputs.csv` does not record locality names | 9 inputs changed unseen (M1raw 72 → 71 inputs) | AI_USE §6.1; NOTEBOOK Stage 20 | detected by regenerating both input sets; **open**: the file still records only the count |
| H6 | figures quoted without a generating script | trying to regenerate every number | AI_USE §5.6 | `threshold_sensitivity.py` added; "+6.24%" withdrawn |
| H7 | quoted tables could drift from the result files | — | — | `headline_table.py --check` and `verify_claims.py` rebuild and compare every figure |

## 6. Platform and operations

| # | Issue | Caught by | Evidence | Resolution |
|---|---|---|---|---|
| P1 | git on Windows rewrote line endings in checksum-pinned files | snapshot checksum failed | AI_USE §5.7 | `.gitattributes` `-text` for data, results, golden, audit (`914ea82`) |
| P2 | scripts crashed reading "₹" as cp1252; a "≠" header crashed redirected output | running on Windows | AI_USE §5.7 | UTF-8 I/O, ASCII headers (`a0c3e16`) |
| P3 | no Ollama on the Windows laptop | — | — | LLM sweeps run on Kaggle T4; the reply cache makes them replayable without a GPU (`scripts/replay_llm_sweep.py`) |
| P4 | cancelling one Kaggle cell stopped the first run; the restart made no model calls | progress checks | AI_USE §6.2 | safeguards L11; server started in its own session |
| P5 | code files in the Kaggle zip had Windows line endings | a patch cell's assertion | AI_USE §6.3 | `git -c core.autocrlf=false archive` |
| P6 | the sweep was started twice and two runs wrote the same files | `ps` showed two harnesses | NOTEBOOK Stage 21 | both stopped, one restarted |
| P7 | the Kaggle notebook log downloaded empty on Windows | 0-byte file | — | download with `PYTHONUTF8=1`; saved in `audit/llm_logs/` |
| P8 | which code had produced the Kaggle results was not what was sent | offline replay matched another commit | AI_USE §6.5 | every LLM result set is verified by replay before it is reported |

## 7. The AI assistant

The assistant's own mistakes — wrong root causes, unchecked claims, edits that
broke code — are listed with how each was caught in `AI_USE.md`: §3 (building
the first implementation, 12 entries), §5 (the merge, 7), §6 (the design-note
alignment and the LLM sweep, 7).

## 8. Test and check logs

- **Current code:** `python scripts/run_checks.py` runs the tests, `verify_claims.py`
  and the three table checks, and writes `audit/test_logs/check_run_<time>.txt`
  plus a row in `audit/test_logs/check_log_index.csv`; `--replay` adds the
  offline LLM replay.
- **First implementation:** `legacy/audit/test_logs/` (6 runs, 12 October).
- **Sweeps:** each `results/<tag>/headline.txt` is that sweep's printed table;
  `results/v2_llm*/harness.log` are the Kaggle harness logs and
  `ollama_requests.log` every model request the server logged.
- **LLM agents:** `audit/llm_logs/fallback_breakdown_*.txt` (per agent, before
  and after the narrative fix) and the final Kaggle notebook's full log.
