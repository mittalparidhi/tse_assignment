# Hyderabad Contract Suite

> **Credits:** Paridhi Mittal (first implementation, 11-12 Oct 2026). Full attribution: CREDITS.md.

## Authority and reading order

1. `CONTRACT.md` — authoritative shared rules and schemas.
2. The active agent subcontract, such as `Planner.md` or `Agents.md`.
3. Only the related support contract needed for the current task (`LLM.md` for model behavior; `Data.md` for source semantics; `Testing.md` for verification).

If a subordinate file conflicts with `CONTRACT.md`, the global contract wins. This suite is a draft tailored to the Hyderabad snapshot; freeze it only after resolving the decisions listed in the relevant contract files and checking against the assignment rubric.

## Context-budget policy

The 8,000-token limit applies **to each individual contract file**, not to the combined suite. Keep every contract under 8,000 tokens; a practical target is approximately 7,000–7,500 tokens to leave revision headroom. The current files are each substantially shorter than that target, so do not pad them just to use the budget. Keep the suite modular for clarity and maintainability, but the combined word/token count is not a contract-level limit. When preparing a model prompt, load the global contract and the relevant subcontract(s) required for the task; do not include raw CSV rows, long execution logs, or full code listings unless needed. Token totals depend on the tokenizer, so check the actual token count used by the target model before a contract approaches the ceiling.

## Verified source facts

- Raw file: `hyderabad.csv`, 9,487 rows × 55 columns.
- SHA-256: `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`.
- `POSTING_DATE` uses Unix milliseconds and must be converted to `Asia/Kolkata` before deriving month.
- The canonical window is September 2022 through August 2023; August 2023 is partial.
- `CITY` includes both Hyderabad and Secunderabad; the default source scope must not silently filter either label.

## Open decisions

- Confirm the supported request schema and intent grammar.
- Approve the coverage score/pass threshold and authorized repair table before enabling coverage repair.
- Define the parallel partition scheme before claiming parallel support.
- Verify `PRICE_SQFT` semantics and area units before reporting INR/sq ft.
- Do not infer `TRANSACT_TYPE` meanings or deduplicate repeated `PROP_ID` values without evidence.
