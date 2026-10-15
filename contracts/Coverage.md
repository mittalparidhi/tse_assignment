# COVERAGE AGENT SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft. **Related:** `Retrieval.md`, `Criteria.md`, `Testing.md`. The parent wins on conflicts.

**Status:** Draft; implemented.

## 1. Role and boundary

**Kind:** decision-maker; owns loop **C1** (brief requirement (b), conditional/iterative control). **LLM:** none. **Code:** `src/agents/nodes.py::coverage_agent`, `route_after_coverage`.

**Job:** score whether the retrieved listings can support a trend, and either proceed to Analysis or widen one criterion and send work back to Retrieval.

| Interface | Contract |
|---|---|
| Inputs | `raw_listings`, effective spec, `retry_count`, `relax_cursor`, `config.coverage_target`, `config.max_retry_rounds` |
| Outputs | `coverage_score`, `coverage_verdict` (`SUFFICIENT` \| `INSUFFICIENT`), `widened_filter_spec`, `retry_count`, `relax_cursor`, `relaxations`, `relax_levers`, `retry_requested`, one trace entry |
| May change | The effective criteria, by one lever per round, as below |
| Must preserve | The window, units, `query_mode`, the frame and every listing value |

## 2. Score and decision

- `coverage_score = (number of window months with >= MIN_SUFFICIENT_N retrieved listings) / 12`, computed on `raw_listings` before any outlier rejection.
- `SUFFICIENT` when `coverage_score >= coverage_target` (0.50).
- Retry (route `retry` → `RetrievalDispatch`) only if insufficient, `retry_count < max_retry_rounds` (3), and a lever can still widen. Otherwise route `analyse`.
- The number of distinct localities retrieved (`geographic_spread`) is logged for the trace; it does not affect the decision.
- Coverage measures depth in this snapshot only. It does not claim the slice represents the market.

## 3. Widening levers

Levers are tried in this order, each **at most once** per run (the cursor advances past a lever whether or not it applied, so an always-applicable lever cannot starve a later one):

| # | Lever (`relax_levers` name) | Rule | Not applicable when |
|---|---|---|---|
| 1 | `price_band` | `price_min_inr × 0.75`, `price_max_inr × 1.25` | no band set |
| 2 | `bhk` | each BHK value ±1 (minimum 1), merged | no BHK filter, or no change |
| 3 | `geography` | `RADIUS`: double `radius_km`. `EXACT_LOCALITY`: adds the nearest localities until depth at least doubles (below) | no geographic constraint |

**Geography rule.** For `EXACT_LOCALITY`, rank the unselected localities (excluding `"Unknown"`) by haversine distance from the median of the selected localities' median coordinates, ties broken by name, and add them in that order until the added localities hold at least as many snapshot listings as the selected ones; depth roughly doubles, like the radius lever. Depth is counted over the whole frame, so row order, duplication and window shifts cannot change the added set. The locality constraint is never removed. Reason: dropping it made every run collapse to the whole metro, so MR M3 (locality subset) passed vacuously (geography fired in 100% of logged runs). A first version added only as many localities as were selected; for "3 BHK in Gachibowli" that added one small locality and coverage stalled at 0.167.

**Consequence.** Narrow queries now usually end below `coverage_target` with their levers exhausted (measured: none of the 36 locality base inputs reaches 0.5), instead of answering a whole-metro question. The trace and the dashboard say which localities were added.

Every applied lever appends a human-readable note to `relaxations` (for example `"price band widened 25%"`) and its canonical name to `relax_levers`. The notes reach the report and the dashboard, which warns the user that the slice was relaxed.

## 4. Loop accounting

- The initial retrieval is not a retry. `retry_count` increments only when a retry is actually requested.
- Each retry produces a trace entry with `coverage_score`, `target`, `sufficient_months`, `decision`, and the relaxation applied.
- Termination is guaranteed: at most `max_retry_rounds` retries, and fewer if levers run out.
- The lever sequence (not the notes) is the control-path signature the harness compares between source and follow-up runs (`Testing.md` §5).

## 5. Must not

Change the window, units or `query_mode`; widen a lever twice; synthesise listings; or reject outliers.

## 6. Tests

| Test | Status |
|---|---|
| C1 fires (`test_cycle1_coverage_to_retrieval_fires`) | exists |
| Coverage improves until target met (`test_cycle1_improves_coverage_until_target_met`) | exists |
| Relaxations are recorded (`test_cycle1_relaxations_are_recorded_not_silent`) | exists |
| Levers advance instead of starving (`test_cycle1_advances_levers_instead_of_starving_them`) | exists |
| Graph terminates under an unsatisfiable target (`test_graph_terminates_under_an_unsatisfiable_target`) | exists |
| Geography widening keeps the locality and stays local (`test_geography_widening_adds_nearest_localities_not_the_whole_metro`, `test_cycle1_improves_coverage_until_target_met_or_levers_exhausted`) | exists |

## 7. Traceability

| This file | Parent |
|---|---|
| §2 Score | §3 `coverage_target`, §7 C1 |
| §3 Levers | §7 C1 |
| §4 Accounting | §7, §9 |
