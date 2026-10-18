# Runtime execution-graph integration

This patch replaces `scripts/build_runtime_state.py` so it calls the existing
`app.execution_graph.run_execution_graph` callbacks while keeping the existing
frozen-snapshot, month ordering, sale-price range rules, and null
`median_price_per_sqft_inr` semantics.

## Controlled behavior

- The planner returns the existing typed v1 `RunPlan`.
- The scanner verifies the frozen source SHA-256 before reading and selecting the
  Sep 2022–Aug 2023 source window.
- The aggregator computes the validated 12 monthly records and quality counts.
- The coverage validator accepts only when all 12 months have valid coherent
  price-bound metrics. The immutable snapshot is not repairable, so no
  `RepairProposal` is configured and no artificial coverage retries are created.
- The existing deterministic anomaly detector runs on the aggregated records.
- A deterministic diagnostic writer provides rule-linked evidence, and the
  critique gate checks that every anomaly has a matching diagnostic.
- The reporter serializes the graph-generated trace and loop accounting into
  the current typed runtime/public report.

The report keeps the established output fields and adds `anomalies`,
`diagnostics`, and `execution_graph` as supplementary top-level evidence.

## Apply safely on Windows

1. Back up the current script:

   ```powershell
   Copy-Item .\scripts\build_runtime_state.py .\scripts\build_runtime_state.py.pre_graph.bak
   ```

2. Extract this patch into the repository root (merge/overwrite only the listed
   files).
3. Run:

   ```powershell
   python -m pytest -q
   python .\scripts\build_runtime_state.py
   ```

4. Inspect `audit\runtime_state.json`, particularly `trace`, `loop_counters`,
   `anomalies`, `diagnostics`, and `execution_graph`.

If validation fails, restore the backup rather than editing the frozen CSV or
loosening schema validation.

The report exposes the contract-defined 12 records at the top level as `monthly_records` (one record per month).
