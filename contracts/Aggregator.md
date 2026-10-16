# AGGREGATOR AGENT SUBCONTRACT — Hyderabad Housing-Trends Application

> **Credits:** Paridhi Mittal. Full attribution: CREDITS.md.

**Parent:** `CONTRACT.md` v2.1.0-draft. **Related:** `Analysis.md`, `LLM.md`. The parent wins on conflicts.

**Status:** Draft; implemented. Phase 3 adds caveats for the new fields.

Note: in v1, "Aggregator" meant monthly aggregation. In v2 it is the final report agent; monthly statistics belong to `Analysis.md`.

## 1. Role and boundary

**Kind:** reporter. **LLM:** optional, narrative only. **Numeric mutation:** forbidden. **Code:** `src/agents/nodes.py::aggregator_agent`, `_deterministic_narrative`, `_narrative_is_faithful`.

**Job:** publish the approved `TrendReport` and a plain-language summary.

| Interface | Contract |
|---|---|
| Inputs | `trend_stats`, effective spec, `coverage_score`, `llm` |
| Outputs | `final_report` (the same `TrendReport` object as `trend_stats`), `narrative`, one or two trace entries |
| May change | `narrative`; the LLM accounting fields of `provenance` |
| Must preserve | Every statistic in the report |

## 2. Responsibilities

1. `final_report` is `trend_stats` unchanged. The only permitted update is refreshing LLM call/fallback counts in `provenance` after the last model call, so the reported fallback rate includes the critique and narrative calls.
2. The deterministic narrative states the window, `listing_count` and `price_valid_count` totals, how many months are `ADEQUATE` / `LIMITED` / `NO_DATA_IN_SNAPSHOT`, the ₹/sqft move with **the number of months it actually spans**, the most expensive locality with its count, any relaxations applied by C1 ("your query was too narrow and was relaxed: …"), and any listings rejected by C2.
3. If no move can be stated (fewer than two sufficient months), say so; never fill in a figure.
4. When the window includes the partial month, say that August 2023 is partial (data to 26 Aug).
5. Describe counts as observed listings in a snapshot, never as market inventory or sales.
6. Record the outcome as `provenance.review_status`: `APPROVED`, or `NEEDS_REVIEW` when the critique's cap was spent with a new problem outstanding (design note §4.3.7), and say so in the narrative. Record `provenance.coverage_verdict` (`ACCEPT` / `LIMITED`).

## 3. LLM narrative (LLM mode only)

- The model receives only: the ₹/sqft move, reliable months out of 12, the area covered (radius, locality list, or "the whole Hyderabad metro area"), and listings analysed.
- When the move is unavailable (fewer than two sufficient months) the model is **not asked**: the deterministic narrative is used and `provenance.narrative_source` is `template`, recorded as a skip, not a fallback. Asked, the 3B model copied the facts block on 49 of 51 such base inputs, and a dedicated no-trend prompt still failed on 5 of 6 locality inputs (`NOTEBOOK.md` Stage 21). `narrative_source` is `model` when the model's summary is used.
- **Faithfulness guard:** every number in the reply must be one of the supplied figures (including those in the area text, e.g. a radius and its centre), and no instruction text may leak into it. A reply failing the guard is replaced by the deterministic narrative and counted as a fallback.
- The model never sees or changes `TrendReport` fields.

## 4. Must not

Recompute or round statistics in the report; drop a month; hide relaxations or rejections; or publish a model narrative that failed the guard.

## 5. Tests

| Test | Status |
|---|---|
| Narrative comes from the model in LLM mode (`test_narrative_comes_from_the_model`) | exists |
| Unfaithful narrative rejected and counted (`test_unfaithful_narrative_is_rejected_and_counted`) | exists |
| Guard rejects leaked instructions and invented figures; accepts supplied ones | exists (`test_narrative_guard_*`) |
| A radius narrative may repeat its own centre and radius; no-trend runs do not ask the model (`test_radius_narrative_may_repeat_its_own_centre_and_radius`, `test_narrative_without_a_trend_does_not_ask_the_model`) | exists |
| LLM stats reach provenance (`test_llm_stats_reach_the_report_provenance`) | exists |
| Partial-month caveat only when 2023-08 is in the window (`test_narrative_flags_the_partial_month_only_when_in_window`) | exists |

## 6. Traceability

| This file | Parent |
|---|---|
| §2 Report | §5, §9 |
| §3 LLM | §8, `LLM.md` |
