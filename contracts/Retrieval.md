# RETRIEVAL AGENTS SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.1.0-draft. **Related:** `Criteria.md`, `Coverage.md`, `Data.md`. The parent wins on conflicts.

**Status:** Draft; implemented.

## 1. Role and boundary

**Kind:** workers (several, cooperating). **LLM:** none. **Code:** `src/agents/nodes.py::make_retrieval_agent`, `retrieval_dispatch`, `retrieval_merge`.

**Job:** select the canonical listings that match the effective criteria and fall inside the 12-month window, split across `n_retrieval_agents` parallel graph nodes, and merge their shards into one deterministic result.

| Interface | Contract |
|---|---|
| Inputs | Effective spec (`widened_filter_spec` if set, else `filter_spec`), `frame`, `seed`, `retry_count`, `config.n_retrieval_agents` |
| Outputs | `retrieval_report` (one entry per agent per round: agent, round, `query_mode`, `n_matched`, `listing_ids`); after merge, `raw_listings` and `n_no_coordinate` |
| May change | The selected row set |
| Must preserve | Every column value of every selected row; the frame itself |

## 2. Two algorithms, selected by `query_mode`

| `query_mode` | Algorithm |
|---|---|
| `EXACT_LOCALITY` | set membership: `locality` or `locality_id` in `localities` (no filter when `localities` is `None`) |
| `RADIUS` | haversine great-circle distance from (`center_lat`, `center_lon`) `<= radius_km`; rows without coordinates are **excluded**, because an unlocated row cannot satisfy a geographic claim |

Both apply the same BHK, city, property-type and price-band filters (`src/trend.py::apply_criteria`; bands inclusive, in rupees, by the listing-range overlap rule — `MAX_PRICE >= band minimum` and `MIN_PRICE <= band maximum`; listings without a valid price cannot be placed in a band and are excluded when one is set) and keep only months in the window. Without a band, listings without a valid price are retrieved: they count in `listing_count`.

## 3. Sharding and merge

1. **Dispatch** marks the start of a round and fans out to all agents.
2. **Each agent** selects matching rows and keeps those with `shard_of(listing_id, seed, n) == agent_index`, where `shard_of` takes the first byte of `sha256(f"{seed}:{listing_id}")` mod `n`. A stable hash, never Python's randomised `hash`.
3. **Merge** collects the `listing_ids` from the current round's entries only (selected by `round == retry_count`), and returns those rows from `frame` in canonical index order.
4. The result must not depend on row order, worker completion order, the number of agents, or the seed.

Merge selects rows by `listing_id`, which is unique (`Data.md` §5); before that fix, the one repeated `PROP_ID` returned both rows whenever either matched.

## 4. Responsibilities

- A zero-row selection is valid, not an error; it is passed on and the trace records it.
- Every round is logged per agent (`retrieved`, `retry_round`) and at merge (`listings`, `agents`, `excluded_no_coordinate`).
- `n_no_coordinate` counts only rows that match the non-geographic criteria and window but lack coordinates.

## 5. Must not

Compute statistics, reject outliers, widen criteria, deduplicate rows, alter values, or read the network or files.

## 6. Known limitation

Each agent currently filters the whole frame and then keeps its shard, so parallelism is structural rather than a speed-up. This is acceptable for the snapshot size and is stated in the report; the invariance guarantees in §3 are what the MRs test.

## 7. Tests

| Test | Status |
|---|---|
| Answer independent of agent count (1, 2, 4, 8) | exists (`test_agents.py::test_answer_is_independent_of_retrieval_agent_count`) |
| `query_mode` selects a different algorithm | exists (`test_agents.py::test_query_mode_selects_a_different_algorithm`) |
| Radius excludes unlocated rows; monotone in radius; haversine correct | exists (`test_agents.py`: `test_radius_excludes_rows_without_coordinates`, `test_radius_retrieval_is_monotone_in_radius`, `test_haversine_against_known_distance`) |
| Shard assignment stable across processes | exists (`test_agents.py::test_shard_assignment_is_stable_across_processes`) |
| Merge returns exactly the current round's matches, IDs unique (`test_merge_returns_exactly_the_current_rounds_matches`) | exists |
| `n_no_coordinate` respects the criteria (`test_no_coordinate_count_respects_the_criteria`) | exists |

MRs that exercise this contract: I1 (row order), I4 (ID relabel), M2, M3 (`Testing.md`).

## 8. Traceability

| This file | Parent |
|---|---|
| §2 Algorithms | §6 requirement (c) |
| §3 Sharding/merge | §6, §8 |
| §4 Identity dependency | §4.4 |
