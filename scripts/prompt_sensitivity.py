"""Which prompts does each metamorphic transformation change?

This is the evidence behind the LLM-mode diagnoses in REPORT.md §8. It needs no
model: the determinism probe established that temperature-0 decoding with a
fixed seed returns identical replies (20/20), so an identical prompt implies an
identical judgment. Showing that a transformation *must* change a prompt
therefore proves the relation *must* break — a deductive argument rather than a
statistical one.

A scripted backend supplies fixed replies so the pipeline runs end to end with
no inference; only the prompts it issues are compared.

    python scripts/prompt_sensitivity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import AgentMode, GraphConfig, build_graph, run_pipeline  # noqa: E402
from src.llm import LLMClient, ScriptedBackend                           # noqa: E402
from src.loading import load_canonical                                   # noqa: E402
from src.mr.base_inputs import generate_base_inputs                      # noqa: E402
from src.mr.relations import ALL_RELATIONS                               # noqa: E402

ROUTES = {
    "You plan property searches": '{"query_mode":"EXACT_LOCALITY","reason":"x"}',
    "You review a twelve-month housing price trend":
        '{"suspect_months":[],"reason":"x"}',
    "You check property listings for data-entry errors":
        '{"suspect_numbers":[]}',
    "Summarise this housing data in two short sentences":
        "Prices eased across the reliable months. Metro-wide.",
}

#: Prompts whose answers decide WHICH listings are counted. The narrative is
#: excluded: it is written after every statistic is final.
SELECTION = ("You plan property searches", "data-entry errors",
             "twelve-month housing price trend")


def kind(prompt: str) -> str:
    if "plan property" in prompt:
        return "criteria"
    if "data-entry" in prompt:
        return "review"
    if "twelve-month" in prompt:
        return "critique"
    return "narrative"


def main(n_inputs: int = 6) -> int:
    frame, _ = load_canonical()
    config = GraphConfig(agent_mode=AgentMode.LLM)
    graph = build_graph(config.n_retrieval_agents)
    inputs = generate_base_inputs(frame)[:n_inputs]

    def prompts(fr, criteria):
        backend = ScriptedBackend(ROUTES)
        client = LLMClient(backend=backend, cache_path=None, model="scripted")
        run_pipeline(fr, criteria, seed=11, config=config, graph=graph,
                     user_query="listings", llm=client)
        return [p for p, _ in backend.calls]

    rows = []
    for mr in ALL_RELATIONS:
        counts = {"criteria": 0, "review": 0, "critique": 0, "narrative": 0}
        selection_differs = 0
        for criteria in inputs:
            prepared = mr.prepare(criteria)
            if not mr.applicable(frame, prepared):
                continue
            follow_frame, follow_criteria = mr.transform(
                frame, prepared, np.random.default_rng(11)
            )
            a, b = prompts(frame, prepared), prompts(follow_frame, follow_criteria)
            for x, y in zip(a, b):
                if x != y:
                    counts[kind(x)] += 1
            sa = [p for p in a if any(m in p for m in SELECTION)]
            sb = [p for p in b if any(m in p for m in SELECTION)]
            selection_differs += int(sa != sb)
        rows.append({"mr_id": mr.mr_id, "family": mr.family,
                     "inputs_tested": len(inputs),
                     "selection_prompts_differ": selection_differs, **counts})

    table = pd.DataFrame(rows)
    out = Path("results/diagnosis/prompt_sensitivity.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)

    print(f"Prompt changes under each transformation ({len(inputs)} base inputs)\n")
    print(table.to_string(index=False))
    print(f"\nwritten to {out}")
    print("\nReading: a relation whose SELECTION prompts never differ cannot be")
    print("broken by the model (identical prompt + deterministic decoding =>")
    print("identical judgment). One whose prompts do differ must be, and the")
    print("question becomes whether the differing information is something the")
    print("judgment is legitimately about.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
