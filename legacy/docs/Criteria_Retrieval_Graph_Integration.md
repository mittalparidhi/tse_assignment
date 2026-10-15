# Criteria → Retrieval → Aggregator graph integration

## Purpose

`app/filtered_execution.py` connects the typed Criteria Agent and Retrieval Agent to the existing `app.execution_graph.run_execution_graph` orchestration. The Planner callback invokes `run_criteria_agent`; the Scanner callback passes the resulting `CriteriaResult` to `RetrievalAgent.retrieve`; the Aggregator consumes the returned `RetrievalResult.rows`.

The existing no-filter full-snapshot builder remains the default, preserving its canonical monthly reporting baseline. Filtered requests use a separate report (`audit/filtered_runtime_state.json`) and do not overwrite `audit/runtime_state.json`.

## Date semantics

Retrieval inclusively filters on `REGISTER_DATE__U` month bounds (source-anchored to September 2022 through August 2023). The filtered result's monthly reporting grid is still assigned from localized `POSTING_DATE`, matching the existing reporting contract. Thus retrieval eligibility and reporting month semantics remain distinct and explicitly documented.

## Safe parsing and integrity

The underlying Retrieval Agent parses `location` and `MAP_DETAILS` with `json.loads` and `ast.literal_eval`, validates coordinates, and verifies the frozen source SHA-256. No source records are modified. Returned rows carry a stable zero-based `source_row_id`.

## Run it

From the project root:

```powershell
python -m scripts.run_filtered_analysis --request-file examples/filtered_request.json
```

Default output: `audit/filtered_runtime_state.json`.

Run integration tests:

```powershell
python -m pytest -q tests/test_agent_graph_integration.py
```

## Traceability

The output preserves the orchestration trace and adds `agent_interaction_trace`, explicitly recording that Criteria runs within the Planner callback, Retrieval within the Scanner callback, and Aggregator consumes selected rows. Coverage repairs are not fabricated: no permitted filter-relaxation provider is configured.
