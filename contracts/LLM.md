# MODEL/LLM SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.1.0-draft. This file restricts model use and defines reproducible fallback behaviour.

**Status:** Draft; implemented. The committed LLM sweeps predate contract v2 (§6).

## 1. Modes

| `agent_mode` | Behaviour |
|---|---|
| `DETERMINISTIC` (default) | No model call. Every judgment uses its deterministic rule. The test suite and all committed deterministic results use this mode. Runs offline with no keys. |
| `LLM` | Four agents add model judgment through `src/llm.py::LLMClient` (§2). Every statistic stays deterministic Python. |

The model is a local Ollama model, default `qwen2.5:3b-instruct-q4_K_M` at `http://localhost:11434`. No paid API or credentials are used.

## 2. Permitted uses

| Agent | The model may | The model may not |
|---|---|---|
| Criteria | choose `query_mode` from a free-text request | invent a centre, change any other field |
| Analysis | name grey-zone listings (`2.0 < \|z\| <= 3.5`) whose description contradicts their price/area | un-reject arithmetic rejections, touch unflagged months, compute numbers |
| Critique | add suspect months | remove deterministic flags |
| Aggregator | write the two-sentence summary | use any number not supplied |

The model never reads or mutates the snapshot, computes or revises a statistic, sets thresholds, or judges MR pass/fail.

## 3. Reproducibility

- Temperature 0, `top_k = 1`, `top_p = 1.0`, `repeat_penalty = 1.0`; the harness seed is passed on every call. Retry attempt *a* uses seed `seed + 1000·a`, so a retry re-rolls rather than replays.
- Responses are cached by SHA-256 of (model, temperature, seed, attempt, prompt) in `data/llm_cache/responses.json`. The cache is committed and doubles as a replay artefact.
- The model is the third reproducibility artefact with the snapshot and the seed list. Its identity is recorded as `model_digest`, the weights digest Ollama reports (`/api/tags`), or `"unavailable"` when Ollama is not reachable; `model_name_sha256` hashes only the name. The committed LLM sweeps recorded only the name hash (as `model_tag_sha256`), so they do not pin the weights and must not be described as doing so.
- A 20-repeat determinism probe (`results/llm/determinism_probe.json`) returned one distinct output; this is evidence, not a guarantee across hardware.

## 4. Prompt hygiene (each forced by a failing MR)

1. Listings are shown by position, never by identifier (I4 violated at 0.630 when IDs appeared).
2. Review batches are sorted on every displayed field, a total order (I1).
3. Batches are de-duplicated on displayed content; a verdict applies to every row with that content (I3 violated at 0.417).
4. The critique table uses canonical units with counts withheld (I2, I3).

These are tested directly: prompts are unchanged under ID relabelling, unit change, row reordering, currency projection and duplication (`test_*_leaves_every_prompt_unchanged`).

## 5. Validation, retries and fallback

- JSON replies are extracted (raw, fenced, or outermost braces) and validated per agent; anything else is a parse failure.
- At most `llm_max_attempts` (3) attempts per call; then a recorded deterministic fallback is used. No hidden retries.
- Every call, cache hit, parse retry, fallback and error is counted (`LLMStats`) and copied into `provenance`. The fallback rate is reported with LLM results, because a high rate means the "LLM" verdicts were mostly deterministic.
- Model output and listing descriptions are untrusted data; nothing they contain is executed or followed as an instruction.

## 6. Open decision

Resolved: `scripts/replay_llm_sweep.py` is the strict replay mode. Every request is answered from the cache, a miss stops the replay, and the run records are compared with `results/<tag>/mr_runs.csv`; it reproduces `results/v2_llm/` exactly. In a normal `--llm` run a cache miss still calls the model.

## 7. Tests

| Test | Status |
|---|---|
| JSON extraction, retry re-roll, fallback counting, cache round-trip (`tests/test_llm.py`) | exist |
| Both cycles fire in LLM mode; statistics identical in both modes | exist |
| Prompt invariance under the five transformations in §4 | exist |
| Model identity is the real digest or `"unavailable"` (`test_unreachable_ollama_reports_no_digest_rather_than_a_guess`) | exists |

## 8. Traceability

| This file | Parent |
|---|---|
| §1–2 | §8 |
| §3 | §8, §9 |
| §5 | §5.4, §9 |
