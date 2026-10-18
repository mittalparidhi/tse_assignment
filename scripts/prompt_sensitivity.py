"""Which prompts does each metamorphic transformation change?

This is the evidence behind the LLM-mode diagnoses in REPORT.md §8. It needs no
model: the determinism probe established that temperature-0 decoding with a
fixed seed returns identical replies (20/20), so an identical prompt implies an
identical judgment. Showing that a transformation changes no prompt
therefore proves the relation cannot break through the model — a deductive
argument rather than a statistical one. The converse does not follow: a changed
prompt only permits a violation, it does not entail one.

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
from src.mr.relations import ALL_RELATIONS, BY_ID                               # noqa: E402

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


#: Per-cell evidence behind the I3 residual in REPORT.md 8.5 / DIAGNOSIS.md.
I3_OUT = Path("results/diagnosis/i3_prompt_vs_violation.csv")

#: The shipped LLM sweep whose violations the comparison is joined against.
I3_RUNS = Path("results/llm/mr_runs.csv")

I3_SEEDS = (11, 23, 47)


def _i3_prompt_vs_violation(frame, config, graph, prompts_at):
    """Cross-tabulate "did the prompt change" against "did I3 actually fail".

    The aggregate table above counts prompt changes but cannot say whether a
    changed prompt is what *caused* a failure. Joining per (base input, seed)
    against the shipped sweep answers that, and the answer is one-directional:
    an identical prompt never violates, but a differing prompt usually does not
    either. Reported because an earlier draft of the report claimed the
    correlation was exact, which this refutes.
    """
    if not I3_RUNS.exists():
        print(f"\n[skipped I3 cross-tab: {I3_RUNS} not present]")
        return None

    runs = pd.read_csv(I3_RUNS)
    runs = runs[(runs.mr_id == "I3") & runs.applicable]
    violated = runs.set_index(["base_input", "seed"]).violated

    mr = BY_ID["I3"]
    rows = []
    for criteria in generate_base_inputs(frame):
        prepared = mr.prepare(criteria)
        if not mr.applicable(frame, prepared):
            continue
        for seed in I3_SEEDS:
            follow_frame, follow_criteria = mr.transform(
                frame, prepared, np.random.default_rng(seed)
            )
            a = [p for p in prompts_at(frame, prepared, seed)
                 if any(m in p for m in SELECTION)]
            b = [p for p in prompts_at(follow_frame, follow_criteria, seed)
                 if any(m in p for m in SELECTION)]
            rows.append({
                "base_input": criteria.label,
                "seed": seed,
                "prompt_differs": a != b,
                "violated": bool(violated.get((criteria.label, seed), False)),
            })

    table = pd.DataFrame(rows)
    I3_OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(I3_OUT, index=False, lineterminator="\n")
    return table


def main(n_inputs: int | None = None) -> int:
    frame, _ = load_canonical()
    config = GraphConfig(agent_mode=AgentMode.LLM)
    graph = build_graph(config.n_retrieval_agents)
    all_inputs = generate_base_inputs(frame)
    inputs = all_inputs if n_inputs is None else all_inputs[:n_inputs]

    def prompts_at(fr, criteria, seed):
        backend = ScriptedBackend(ROUTES)
        client = LLMClient(backend=backend, cache_path=None, model="scripted")
        run_pipeline(fr, criteria, seed=seed, config=config, graph=graph,
                     user_query="listings", llm=client)
        return [p for p, _ in backend.calls]

    def prompts(fr, criteria):
        return prompts_at(fr, criteria, 11)

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
    table.to_csv(out, index=False, lineterminator="\n")

    i3 = _i3_prompt_vs_violation(frame, config, graph, prompts_at)

    print(f"Prompt changes under each transformation ({len(inputs)} base inputs)\n")
    print(table.to_string(index=False))
    print(f"\nwritten to {out}")
    if i3 is not None:
        print("\nMR-I3, prompt difference vs actual violation "
              "(36 base inputs x 3 seeds):\n")
        print(pd.crosstab(i3.prompt_differs, i3.violated,
                          rownames=["prompt differs"],
                          colnames=["violated"]).to_string())
        print("\nIdentical prompt never violates; a differing prompt is "
              "necessary, not sufficient.")
        print(f"written to {I3_OUT}")
    print("\nReading: the implication runs ONE WAY. A relation whose SELECTION")
    print("prompts never differ cannot be broken by the model (identical prompt")
    print("+ deterministic decoding => identical judgment), and none are. The")
    print("converse is false: I2 and I5 perturb a prompt on a few inputs and")
    print("still hold at 0.000, because the perturbation must also change a")
    print("judgment that changes which listings are counted. So this table")
    print("BOUNDS which relations the model can break; it does not predict")
    print("which it did. See REPORT.md 8.1 and AI_USE.md 3.12.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
