# LLM sweep, BEFORE the prompt-contamination fixes

Produced by the code as it stood at commit-time of the first Kaggle sweep
(1,188 runs, 2026-10-14, qwen2.5:3b-instruct-q4_K_M, seeds [11,23,47]).

**Retained deliberately.** This is the evidence that the metamorphic relations
detected three faults in the LLM integration. The shipped code no longer
behaves this way, so these numbers must not be presented as the system's
current behaviour — they are the "before" half of a before/after comparison.

Violation rates here, against deterministic mode:

| MR | deterministic | this run | cause found |
|----|---------------|----------|-------------|
| I1 | 0.000 | 0.000 | (held by luck — a tie-ordering fault was latent) |
| I2 | 0.000 | 0.028 | critique table rendered in display units |
| I3 | 0.000 | 0.417 | top-N of a doubled set returns N/2 distinct listings twice |
| I4 | 0.000 | 0.630 | listing ids present in the review prompt |
| D2 | 0.000 | 0.556 | prompt legitimately differs — NOT fixed, not fixable by prompt hygiene |

The determinism probe in this run returned 20/20 identical replies at
temperature 0, which is what establishes these as systematic faults rather
than model noise.
