# LLM sweep, AFTER the prompt-contamination fixes

1,188 runs, qwen2.5:3b-instruct-q4_K_M via Ollama on a Kaggle T4, seeds
[11, 23, 47]. The code that produced these numbers is byte-identical to the
shipped code (verified by SHA-256 on every modified module).

The "before" half is in ../llm_before_promptfix/.
