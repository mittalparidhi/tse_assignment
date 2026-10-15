# CRITERIA AGENT SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft. **Related:** `Data.md`, `LLM.md`, `Retrieval.md`. The parent wins on conflicts.

**Status:** Draft. The agent and `query_mode` exist; request validation is ported from v1 (`legacy/app/criteria_agent.py`) in Phase 3.

## 1. Role and boundary

**Kind:** decision-maker. **Code:** `src/agents/nodes.py::criteria_agent`; **[P3]** validation in `src/validation.py`.

**Job:** turn a request into a validated `Criteria` (the `filter_spec`) and choose the retrieval algorithm via `query_mode`. It does not read listing rows (except locality names for the LLM prompt), compute statistics, or widen criteria.

| Interface | Contract |
|---|---|
| Inputs | `filter_spec` (a `Criteria`), optional `user_query`, `config.agent_mode`, `seed`, the canonical frame's catalogue of observed values |
| Outputs | `filter_spec` (possibly with `query_mode` changed), `query_mode`, one trace entry |
| May change | `query_mode` only, and only in LLM mode with a `user_query` |
| Must preserve | Every other `Criteria` field exactly as validated |

## 2. `Criteria` fields

| Field | Type | Meaning |
|---|---|---|
| `window_end` | `YYYY-MM` | last month of the 12-month window (inclusive); default `2023-08` |
| `bhk` | tuple of int or `None` | bedroom counts; `None` = all |
| `localities` | tuple of str or `None` | exact locality names; `None` = whole metro |
| `property_types` | tuple of str or `None` | dwelling types; `None` = all |
| `price_min_inr`, `price_max_inr` | float or `None` | price band in **rupees**, inclusive |
| `currency_unit` | `INR` \| `INR_LAKH` \| `INR_CRORE` | display only |
| `area_unit` | `SQFT` \| `SQM` | display only |
| `query_mode` | `EXACT_LOCALITY` \| `RADIUS` | retrieval algorithm (`Retrieval.md` §2) |
| `center_lat`, `center_lon`, `radius_km` | float or `None` | radius search parameters |
| `label` | str | base-input identifier; not a filter |

## 3. Validation rules **[P3]**

Validation runs at the request boundary: the Streamlit sidebar and any programmatic entry point. It is ported from the v1 Criteria agent.

1. Reject unknown request fields. Never silently ignore a filter.
2. `window_end` must match `YYYY-MM` and be a month present in the canonical frame (currently 2022-05 … 2023-08).
3. `bhk` values must be whole numbers in the source-observed domain 1–10; duplicates are removed and the list sorted.
4. Locality names are matched case- and whitespace-insensitively to source-observed names and replaced by the canonical spelling; duplicates removed, first-request order kept. An unmatched name is rejected, never approximated.
5. `property_types` must be dwelling types (`Data.md` §3).
6. Prices must be finite and `> 0`; `price_min_inr <= price_max_inr` when both are given.
7. Units must be from the allowed sets above.
8. `RADIUS` requires `center_lat`, `center_lon` inside the Hyderabad box (lat 16.5–18.5, lon 77.5–79.5) and `0 < radius_km <= 100`. `RADIUS` with `localities`, or `EXACT_LOCALITY` with a radius, is a mode conflict.
9. City is not a filter; both Hyderabad and Secunderabad are always in scope.

**MR transformations bypass this validation.** The harness builds follow-up `Criteria` directly, so a valid transformation (for example a window shifted into an edge month) is never rejected by request-boundary rules. Every harness base input must itself pass validation.

## 4. Error codes **[P3]**

Errors use `{"status": "error", "error_code": ..., "message": ...}`; the message names the field and the allowed values.

| Code | Trigger |
|---|---|
| `invalid_request` | request is not a mapping |
| `unknown_request_fields` | rule 1 |
| `invalid_date_format` / `unsupported_date_window` | rule 2 |
| `invalid_bhk` / `unsupported_bhk` | rule 3 |
| `unsupported_locality` | rule 4 |
| `unsupported_property_type` | rule 5 |
| `invalid_price` / `invalid_price_range` | rule 6 |
| `unsupported_unit` | rule 7 |
| `invalid_geo_radius` / `missing_geo_center` / `query_mode_mismatch` | rule 8 |

## 5. `query_mode` decision

- **Deterministic mode (default):** `query_mode` is taken from the validated request: `RADIUS` when a radius is supplied, else `EXACT_LOCALITY`. The agent records it in the trace.
- **LLM mode with a `user_query`:** the model chooses `EXACT_LOCALITY` or `RADIUS` (`LLM.md` §2). If it chooses `RADIUS` but no centre was supplied, the agent falls back to `EXACT_LOCALITY` and records why; it never invents a centre or geocodes a guess. Invalid model output uses the request's own mode as fallback.
- The choice is a genuine dependency (brief requirement (c)): it changes which algorithm Retrieval runs, not merely which rows it receives.

## 6. Must not

Change the window, units, price band, BHK or locality list; read files or the network; compute statistics; relax criteria (that is `Coverage.md`); or accept a model-proposed field other than `query_mode`.

## 7. Tests

| Test | Status |
|---|---|
| Default mode is deterministic | exists (`test_agents.py::test_default_mode_is_deterministic`) |
| LLM mode uses the model's `query_mode` | exists (`test_llm.py::test_criteria_agent_uses_the_models_query_mode`) |
| `RADIUS` requires a centre | exists (`test_agents.py::test_radius_requires_a_centre`) |
| LLM `RADIUS` without centre falls back to `EXACT_LOCALITY` | **[P3]** |
| Each rule in §3 rejects with its §4 code; valid requests pass unchanged | **[P3]** ported from `legacy/tests/test_criteria_agent.py` |
| Locality canonicalisation (case/whitespace) and de-duplication | **[P3]** |
| Every harness base input passes validation | **[P3]** |

## 8. Traceability

| This file | Parent |
|---|---|
| §2 Fields | §4.3, §5.3 |
| §3–4 Validation and errors | §5.4 |
| §5 `query_mode` | §6 requirement (c) |
| LLM use | `LLM.md` |
