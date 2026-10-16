# Credits — who did what

**Authors:** Paridhi Mittal and Vidhi Jain.

## Summary

| | Paridhi Mittal | Vidhi Jain |
|---|---|---|
| Foundation (11-12 Oct) | Froze and audited the Hyderabad snapshot; wrote the design note (`Assignment1_Design_Note_Final.docx`) whose architecture the system follows; wrote the first contract suite, 31 data/audit/cleaning scripts and a first implementation with tests (`legacy/`) | |
| Second implementation (14-15 Oct) | | Built on that snapshot and design: the LangGraph agent graph with both cycles, the four retrieval agents, the loader, output contract and statistics, the relations and harness (11 relations, 36 inputs), the synthetic control, the local-model mode and its Kaggle sweeps, the dashboard, the first diagnosis, RESIDEX cross-check and first REPORT, DESIGN, NOTEBOOK and AI_USE (commits `736d594`, `957224c`) |
| Integration (15-16 Oct) | Merged the two implementations; rewrote the contracts as v2.1 (`contracts/`); ported the data rules and request validation; found and fixed seven faults (geography widening, the I3 review batch, duplicate IDs, the model digest, the dead-server fallback, critique accounting, the per-run statistical unit) and one in her own first fix (M3); added radius inputs and M4; re-ran every sweep including the v2 LLM sweep on Kaggle with offline replay; added live agent views to the dashboard; rewrote the report to 10 pages; issue log, check logs and repository cleanup | |

## Files

292 files at the commit this was written: 179 by Paridhi Mittal alone, 60 by Vidhi Jain alone, 53 written by one and changed by the other.
Who wrote and changed each file comes from `git log --follow`; the line shares from `git blame -M -C`,
measured before the credit lines were added. Her commits carry the placeholder identity
`local <local@localhost>`; `.mailmap` maps it to her name.

Files that can hold a comment (code, Markdown, configuration) also carry a credit line at the top.
Data, result, log and binary files cannot, so they are credited here only.

### Application, tests, scripts, documents and data

| File | Author | Lines V / P | What Paridhi changed |
|---|---|---|---|
| `.gitattributes` | Paridhi Mittal |  |  |
| `.gitignore` | written by Vidhi Jain; changed by Paridhi Mittal | 0% / 100% | ignores for scratch results and local folders |
| `.mailmap` | Paridhi Mittal |  |  |
| `.streamlit/config.toml` | Paridhi Mittal |  |  |
| `AI_USE.md` | written by Vidhi Jain; changed by Paridhi Mittal | 56% / 44% | §§1-4 by Vidhi Jain; §§5-7 by Paridhi Mittal |
| `DESIGN.md` | written by Vidhi Jain; changed by Paridhi Mittal | 79% / 21% | updated for contract v2.1 (the design follows Paridhi Mittal's original design note) |
| `NOTEBOOK.md` | written by Vidhi Jain; changed by Paridhi Mittal | 56% / 44% | Stages 0-15 by Vidhi Jain; dataset decisions and Stages 16-25 by Paridhi Mittal |
| `README.md` | written by Vidhi Jain; changed by Paridhi Mittal | 53% / 47% | updated for the integrated system; authors section |
| `REPORT.md` | written by Vidhi Jain; changed by Paridhi Mittal | 18% / 82% | rewritten for the v2 results and cut to 10 pages (Paridhi Mittal); §§1-4 and 6-10 began from Vidhi Jain's first report |
| `REPORT.pdf` | Paridhi Mittal |  |  |
| `app.py` | written by Vidhi Jain; changed by Paridhi Mittal | 49% / 51% | city selection, GEO_RADIUS switch, request validation, coverage status, the three live agent views, typography |
| `contracts/Aggregator.md` | Paridhi Mittal |  |  |
| `contracts/Analysis.md` | Paridhi Mittal |  |  |
| `contracts/CONTRACT.md` | Paridhi Mittal |  |  |
| `contracts/Coverage.md` | Paridhi Mittal |  |  |
| `contracts/Criteria.md` | Paridhi Mittal |  |  |
| `contracts/Critique.md` | Paridhi Mittal |  |  |
| `contracts/Data.md` | Paridhi Mittal |  |  |
| `contracts/Golden.md` | Paridhi Mittal |  |  |
| `contracts/LLM.md` | Paridhi Mittal |  |  |
| `contracts/README.md` | Paridhi Mittal |  |  |
| `contracts/Retrieval.md` | Paridhi Mittal |  |  |
| `contracts/Testing.md` | Paridhi Mittal |  |  |
| `data/SOURCE.md` | Paridhi Mittal |  |  |
| `data/llm_cache/responses.json` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `data/raw/CHECKSUMS.txt` | Paridhi Mittal |  |  |
| `data/raw/Readme.md` | written by Paridhi Mittal; edited by Vidhi Jain | 62% / 38% |  |
| `data/raw/hyderabad.csv` | Paridhi Mittal |  |  |
| `data/snapshot/CHECKSUMS.txt` | written by Vidhi Jain; changed by Paridhi Mittal | 0% / 100% |  |
| `data/snapshot/canonical_price_validity.csv` | Paridhi Mittal |  |  |
| `data/snapshot/canonical_reject_log.csv` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `data/snapshot/listings_canonical.csv` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `data/snapshot/listings_synthetic.csv` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `data/snapshot/synthetic_ground_truth.json` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `docs/DIAGNOSIS.md` | written by Vidhi Jain; changed by Paridhi Mittal | 86% / 14% | Findings 1-9 by Vidhi Jain; Findings 10-11 and the moved pre-v2 sections by Paridhi Mittal |
| `docs/ISSUE_LOG.md` | Paridhi Mittal |  |  |
| `docs/design_note_hyderabad_refined.pdf` | Paridhi Mittal |  |  |
| `notebooks/kaggle_llm_sweep.ipynb` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `notebooks/kaggle_v2_llm_sweep/README.md` | Paridhi Mittal |  |  |
| `notebooks/kaggle_v2_llm_sweep/dataset-metadata.json` | Paridhi Mittal |  |  |
| `notebooks/kaggle_v2_llm_sweep/kernel-metadata.json` | Paridhi Mittal |  |  |
| `notebooks/kaggle_v2_llm_sweep/run_sweep.py` | Paridhi Mittal |  |  |
| `pytest.ini` | written by Vidhi Jain; changed by Paridhi Mittal | 100% / 0% |  |
| `requirements.txt` | Vidhi Jain |  |  |
| `scripts/audit_hyderabad.py` | Paridhi Mittal |  |  |
| `scripts/build_report_pdf.py` | Paridhi Mittal |  |  |
| `scripts/diagnose.py` | written by Vidhi Jain; changed by Paridhi Mittal | 83% / 17% | repaired; writes all canonical columns |
| `scripts/export_ui_data.py` | Paridhi Mittal |  |  |
| `scripts/headline_table.py` | written by Vidhi Jain; changed by Paridhi Mittal | 68% / 32% | --v2, --tag and --check against the report |
| `scripts/inspect_hyderabad_anomalies.py` | Paridhi Mittal |  |  |
| `scripts/inspect_hyderabad_fields.py` | Paridhi Mittal |  |  |
| `scripts/llm_fallback_breakdown.py` | Paridhi Mittal |  |  |
| `scripts/make_results_section.py` | written by Vidhi Jain; changed by Paridhi Mittal | 99% / 1% | UTF-8 reads |
| `scripts/make_synthetic.py` | written by Vidhi Jain; changed by Paridhi Mittal | 93% / 7% | repaired; writes all canonical columns |
| `scripts/prompt_sensitivity.py` | written by Vidhi Jain; changed by Paridhi Mittal | 99% / 1% | fixed line endings |
| `scripts/regenerate_golden.py` | Paridhi Mittal |  |  |
| `scripts/replay_llm_sweep.py` | Paridhi Mittal |  |  |
| `scripts/run_checks.py` | Paridhi Mittal |  |  |
| `scripts/run_harness.py` | written by Vidhi Jain; changed by Paridhi Mittal | 81% / 19% | radius inputs; UTF-8 and fixed line endings |
| `scripts/threshold_sensitivity.py` | Paridhi Mittal |  |  |
| `scripts/validate_llm.py` | Vidhi Jain |  |  |
| `scripts/verify_claims.py` | written by Vidhi Jain; changed by Paridhi Mittal | 87% / 13% | re-derives every figure for the v2 population and twelve relations |
| `src/__init__.py` | Vidhi Jain |  |  |
| `src/agents/__init__.py` | Vidhi Jain |  |  |
| `src/agents/graph.py` | Vidhi Jain |  |  |
| `src/agents/nodes.py` | written by Vidhi Jain; changed by Paridhi Mittal | 78% / 22% | geography widening that keeps the locality and preserves set inclusion (M3); ACCEPT/RETRY/LIMITED coverage; critique coherence checks and NEEDS_REVIEW; the I3 review-batch fix; per-pass rejection counts |
| `src/agents/readable.py` | Paridhi Mittal |  |  |
| `src/agents/state.py` | written by Vidhi Jain; changed by Paridhi Mittal | 92% / 8% | ACCEPT/RETRY/LIMITED and NEEDS_REVIEW verdicts, adequate_n, analysed_listings |
| `src/contract.py` | written by Vidhi Jain; changed by Paridhi Mittal | 64% / 36% | contract v2.1: the five monthly fields, coverage_status, min/max-price medians, partial month |
| `src/llm.py` | written by Vidhi Jain; changed by Paridhi Mittal | 82% / 18% | weights digest from Ollama, BackendUnavailable on a dead server, periodic atomic cache writes |
| `src/loading.py` | written by Vidhi Jain; changed by Paridhi Mittal | 73% / 27% | months in IST, price-validity flags, Price on Request, midpoint price, locality_id, unique listing_id, fixed line endings |
| `src/mr/__init__.py` | Vidhi Jain |  |  |
| `src/mr/base_inputs.py` | written by Vidhi Jain; changed by Paridhi Mittal | 68% / 32% | the 36 radius base inputs |
| `src/mr/harness.py` | written by Vidhi Jain; changed by Paridhi Mittal | 72% / 28% | the base input as the statistical unit; rejected counts per run |
| `src/mr/relations.py` | written by Vidhi Jain; changed by Paridhi Mittal | 80% / 20% | relation M4; checks on the v2.1 fields; explicit M3 check |
| `src/mr/transforms.py` | written by Vidhi Jain; changed by Paridhi Mittal | 91% / 9% | MIN, MAX and midpoint shifted together; shrink_radius for M4 |
| `src/trend.py` | written by Vidhi Jain; changed by Paridhi Mittal | 82% / 18% | city filter, locality IDs, price-band overlap, price-valid medians, adequate_n |
| `src/validation.py` | Paridhi Mittal |  |  |
| `src/viz.py` | written by Vidhi Jain; changed by Paridhi Mittal | 72% / 28% | before-critique overlay, threshold-sensitivity bars, typography |
| `tests/conftest.py` | Vidhi Jain |  |  |
| `tests/golden/deterministic_baseline.json` | written by Vidhi Jain; changed by Paridhi Mittal |  |  |
| `tests/test_agents.py` | written by Vidhi Jain; changed by Paridhi Mittal | 57% / 43% | tests for widening and set inclusion, NEEDS_REVIEW, rejection accounting, stable counts |
| `tests/test_app.py` | Paridhi Mittal |  |  |
| `tests/test_contract.py` | written by Vidhi Jain; changed by Paridhi Mittal | 85% / 15% | tests for the v2.1 fields |
| `tests/test_golden.py` | written by Vidhi Jain; changed by Paridhi Mittal | 87% / 13% | golden vectors regenerated only with a recorded reason |
| `tests/test_harness.py` | written by Vidhi Jain; changed by Paridhi Mittal | 44% / 56% | planted-fault tests and base-input intervals |
| `tests/test_llm.py` | written by Vidhi Jain; changed by Paridhi Mittal | 82% / 18% | tests for the safeguards and the I3 and narrative fixes |
| `tests/test_loading.py` | written by Vidhi Jain; changed by Paridhi Mittal | 40% / 60% | tests for the data rules and price validity |
| `tests/test_trend.py` | written by Vidhi Jain; changed by Paridhi Mittal | 50% / 50% | tests for the new fields and filters |
| `tests/test_validation.py` | Paridhi Mittal |  |  |

### Result, audit and legacy folders

| Folder or file | Files | Author |
|---|---|---|
| `audit/hyderabad_missingness.csv` | 1 | Paridhi Mittal |
| `audit/hyderabad_monthly_counts.csv` | 1 | Paridhi Mittal |
| `audit/hyderabad_numeric_anomalies.csv` | 1 | Paridhi Mittal |
| `audit/llm_logs/` | 3 | Paridhi Mittal |
| `audit/test_logs/` | 3 | Paridhi Mittal |
| `legacy/README.md` | 1 | Paridhi Mittal |
| `legacy/app/` | 9 | Paridhi Mittal |
| `legacy/audit/` | 18 | Paridhi Mittal |
| `legacy/contracts/` | 14 | Paridhi Mittal |
| `legacy/criteria_examples_output.json` | 1 | Paridhi Mittal |
| `legacy/data/` | 2 | Paridhi Mittal |
| `legacy/docs/` | 5 | Paridhi Mittal |
| `legacy/example_response.json` | 1 | Paridhi Mittal |
| `legacy/examples/` | 2 | Paridhi Mittal |
| `legacy/scripts/` | 20 | Paridhi Mittal |
| `legacy/tests/` | 15 | Paridhi Mittal |
| `results/after_fix/` | 7 | Vidhi Jain |
| `results/before_fix/` | 7 | Vidhi Jain |
| `results/diagnosis/` | 5 | Vidhi Jain |
| `results/llm/` | 9 | Vidhi Jain |
| `results/llm_before_promptfix/` | 9 | Vidhi Jain |
| `results/phaseA_deterministic/` | 7 | Vidhi Jain |
| `results/residex/` | 2 | Vidhi Jain |
| `results/sensitivity/` | 1 | Vidhi Jain |
| `results/synthetic/` | 6 | Vidhi Jain |
| `results/ui/` | 3 | Paridhi Mittal |
| `results/v2_before_m3fix/base_inputs.csv` | 1 | Paridhi Mittal |
| `results/v2_before_m3fix/filter_cascade.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_before_m3fix/headline.txt` | 1 | Paridhi Mittal |
| `results/v2_before_m3fix/mr_runs.csv` | 1 | Paridhi Mittal |
| `results/v2_before_m3fix/mr_summary.csv` | 1 | Paridhi Mittal |
| `results/v2_before_m3fix/run_meta.json` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_before_m3fix/trace_example.txt` | 1 | Paridhi Mittal |
| `results/v2_before_note_alignment/base_inputs.csv` | 1 | Paridhi Mittal |
| `results/v2_before_note_alignment/filter_cascade.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_before_note_alignment/headline.txt` | 1 | Paridhi Mittal |
| `results/v2_before_note_alignment/mr_runs.csv` | 1 | Paridhi Mittal |
| `results/v2_before_note_alignment/mr_summary.csv` | 1 | Paridhi Mittal |
| `results/v2_before_note_alignment/run_meta.json` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_before_note_alignment/trace_example.txt` | 1 | Paridhi Mittal |
| `results/v2_deterministic/base_inputs.csv` | 1 | Paridhi Mittal |
| `results/v2_deterministic/filter_cascade.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_deterministic/headline.txt` | 1 | Paridhi Mittal |
| `results/v2_deterministic/mr_runs.csv` | 1 | Paridhi Mittal |
| `results/v2_deterministic/mr_summary.csv` | 1 | Paridhi Mittal |
| `results/v2_deterministic/run_meta.json` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_deterministic/trace_example.txt` | 1 | Paridhi Mittal |
| `results/v2_diagnosis/exp_ab_conditions.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_diagnosis/exp_c_shard_sensitivity.csv` | 1 | Paridhi Mittal |
| `results/v2_diagnosis/exp_d_m1_band_crossing.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_llm/base_inputs.csv` | 1 | Paridhi Mittal |
| `results/v2_llm/filter_cascade.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_llm/harness.log` | 1 | Paridhi Mittal |
| `results/v2_llm/headline.txt` | 1 | Paridhi Mittal |
| `results/v2_llm/mr_runs.csv` | 1 | Paridhi Mittal |
| `results/v2_llm/mr_summary.csv` | 1 | Paridhi Mittal |
| `results/v2_llm/ollama_requests.log` | 1 | Paridhi Mittal |
| `results/v2_llm/run_meta.json` | 1 | Paridhi Mittal |
| `results/v2_llm/trace_example.txt` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/base_inputs.csv` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/filter_cascade.csv` | 1 | written by Vidhi Jain; changed by both |
| `results/v2_llm_before_reviewfix/harness.log` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/headline.txt` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/mr_runs.csv` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/mr_summary.csv` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/ollama_requests.log` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/run_meta.json` | 1 | Paridhi Mittal |
| `results/v2_llm_before_reviewfix/trace_example.txt` | 1 | Paridhi Mittal |
| `results/v2_sensitivity/` | 1 | Paridhi Mittal |
| `results/v2_synthetic/` | 6 | Paridhi Mittal |
