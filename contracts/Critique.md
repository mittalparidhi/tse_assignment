# CRITIQUE AGENT SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft. **Related:** `Analysis.md`, `LLM.md`. The parent wins on conflicts.

**Status:** Draft; implemented. What the critique inspects changes in Phase 4.

## 1. Role and boundary

**Kind:** validator; owns loop **C2** (brief requirement (a), a downstream agent sending work back upstream). **LLM:** optional, adds flags only. **Code:** `src/agents/nodes.py::critique_agent`, `route_after_critique`.

**Job:** decide whether the computed trend is plausible. If not, send Analysis a specific complaint naming the months at fault.

| Interface | Contract |
|---|---|
| Inputs | `trend_stats`, `raw_listings`, `flagged_months`, `critique_rounds`, `config`, `seed`, `llm` |
| Outputs | `critique_verdict` (`APPROVED` \| `REJECTED`), `critique_complaint` (`flagged_months`, up to 6 `reasons`), `flagged_months`, `critique_rounds`, `recompute_requested`, one trace entry |
| May change | Control flow and the flagged-month set |
| Must preserve | Every statistic and listing |

## 2. Deterministic flagging rules (always run)

A month is flagged when any holds:

| Rule | Condition |
|---|---|
| Structural | the month has listings but no computable median ₹/sqft |
| Jump | month-on-month change in `median_psf` exceeds `jump_threshold_pct` (25%) in absolute value, and the month has listings |
| Contextual outlier | some listing in the month has robust \|z\| of log ₹/sqft `> robust_z_threshold` (3.5) |

**[P4]** The contextual-outlier rule is evaluated on the listings that remain after any rejection (currently it re-reads `raw_listings`, so it can never confirm a recomputation fixed anything).

## 3. LLM judgment (LLM mode only)

- The model sees the 12 monthly medians in **canonical units (₹ per sq ft) with listing counts withheld**, and may name additional suspect months. Display units would let a unit change alter the judgment (MR I2); counts would let duplication alter it (MR I3).
- Model flags are added to the deterministic set; the model can never remove a deterministic flag or switch the rules off. Months outside the window are ignored.
- Invalid output falls back to "no extra months" and is counted (`LLM.md` §5).

## 4. Decision and loop accounting

- `new_flags = flagged − flagged_months already handled`.
- Recompute (route `recompute` → `AnalysisAgent`) only if `new_flags` is non-empty and `critique_rounds < max_critique_rounds` (1). Otherwise route `report`.
- On recompute: `flagged_months` becomes the full flagged set, `critique_rounds` increments, and the complaint carries the months and reasons.
- Termination is guaranteed: at most one round. A second round is unsound because the flagged set grows between rounds and the relative threshold is not idempotent (measured 2/16 MR violations at two rounds, 0/16 at one).
- Each decision is traced with `flagged`, `new_flags`, `verdict`, `decision` and the first reason.

## 5. Must not

Change any number; reject listings itself (that is Analysis); remove deterministic flags on a model's advice; or flag months outside the window.

## 6. Tests

| Test | Status |
|---|---|
| C2 fires (`test_cycle2_critique_to_analysis_fires`) | exists |
| Complaint names the months at fault (`test_cycle2_complaint_names_the_months_at_fault`) | exists |
| Model adds flagged months (`test_critique_agent_adds_the_models_flagged_months`) | exists |
| Model cannot switch off the deterministic floor (`test_llm_mode_cannot_switch_off_the_deterministic_floor`) | exists |
| Critique prompt withholds counts (`test_critique_prompt_withholds_listing_counts`) | exists |
| Outlier rule evaluated on post-rejection listings | **[P4]** |

## 7. Traceability

| This file | Parent |
|---|---|
| §2 Rules | §3 thresholds, §7 C2 |
| §3 LLM | §8, `LLM.md` |
| §4 Loop | §7 C2, §9 |
