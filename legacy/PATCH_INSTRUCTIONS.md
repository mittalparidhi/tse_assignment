# Criteria → Retrieval → Aggregator Graph Integration Patch

## Files added
- `app/filtered_execution.py`: connects typed Criteria Agent output to Retrieval Agent and sends selected rows into Aggregator through the existing execution graph.
- `scripts/run_filtered_analysis.py`: runnable filtered request entry point. Writes a separate report and does not overwrite the full-snapshot `audit/runtime_state.json`.
- `examples/filtered_request.json`: deterministic Gachibowli apartment example.
- `tests/test_agent_graph_integration.py`: end-to-end checks for exact locality, locality ID, geo-radius mode, and fail-closed unsupported localities.
- `docs/Criteria_Retrieval_Graph_Integration.md`: architecture and date semantics.

## Important behavior
- The Planner callback invokes Criteria Agent.
- The Scanner callback invokes Retrieval Agent using the typed `CriteriaResult`.
- The Aggregator consumes `RetrievalResult.rows` from the Scanner; it does not rescan the full snapshot.
- Retrieval filters on inclusive `REGISTER_DATE__U` month bounds. Reporting still derives each monthly bucket from localized `POSTING_DATE` according to the current contract.
- The existing default full-snapshot report builder is not replaced. Filtered reports go to `audit/filtered_runtime_state.json`.
- No automatic repair relaxes user filters; a filtered report with incomplete monthly price coverage is marked `partial` rather than inventing data.

## Apply on Windows
From `C:\Users\parid\Desktop\assignment_tse`, download this ZIP, then run:

```powershell
$zip = Get-ChildItem "$HOME\Downloads" -Filter "Retrieval_Graph_Integration_Patch.zip" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw "Download Retrieval_Graph_Integration_Patch.zip first." }
Expand-Archive -Path $zip.FullName -DestinationPath . -Force
```

Then run the focused integration tests and smoke request:

```powershell
python -m pytest -q tests\test_agent_graph_integration.py
python -m scripts.run_filtered_analysis --request-file examples/filtered_request.json
```

Check that `audit/filtered_runtime_state.json` has 12 `monthly_records`, a `trace`, `agent_interaction_trace`, and the expected retrieval count of 24 for the bundled hand-checked example.

Finally run the project's logged full test/build workflow:

```powershell
.\scripts\run_tests_logged.ps1
```

The full-snapshot builder and raw CSV are not modified by this patch.
