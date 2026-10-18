"""Which LLM agent falls back, and why, on the harness's base inputs.

Replays each base input once (seed 11, the source run every relation starts
from) through the LLM pipeline and tallies, per agent and per input kind
(locality / radius), how often the model's reply was used or replaced by the
deterministic fallback; narrative rejections are broken down by reason.

Replies come from the cache, so after a sweep has passed the first relation
this makes few or no model calls. The cache file is never written.

    python scripts/llm_fallback_breakdown.py            # needs Ollama only for misses
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import AgentMode, GraphConfig, build_graph, nodes, run_pipeline  # noqa: E402
from src.llm import (DEFAULT_CACHE, DEFAULT_HOST, DEFAULT_MODEL,  # noqa: E402
                     LLMClient, OllamaBackend)
from src.loading import load_canonical  # noqa: E402
from src.mr.base_inputs import generate_all_base_inputs  # noqa: E402

_AGENT_BY_PROMPT = {
    "You check property listings": "review",
    "You review a twelve-month": "critique",
    "You plan property searches": "criteria",
    "Summarise this housing data": "narrative",
}


def _agent(prompt: str) -> str:
    return next((name for head, name in _AGENT_BY_PROMPT.items()
                 if prompt.startswith(head)), "other")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--llm-model", default=DEFAULT_MODEL)
    parser.add_argument("--llm-host", default=DEFAULT_HOST)
    parser.add_argument("--llm-cache", default=str(DEFAULT_CACHE))
    args = parser.parse_args()

    frame = load_canonical()[0]
    llm = LLMClient(backend=OllamaBackend(args.llm_host), model=args.llm_model,
                    cache_path=Path(args.llm_cache))
    llm.flush_cache = lambda: None            # read-only: never write the cache
    config = GraphConfig(agent_mode=AgentMode.LLM, llm_model=args.llm_model,
                         llm_host=args.llm_host)
    graph = build_graph(config.n_retrieval_agents)

    used = collections.Counter()              # (kind, agent, "model"|"fallback")
    why = collections.Counter()               # (kind, reason)
    kind = ["?"]

    ask_json, ask_text = llm.ask_json, llm.ask_text

    def counted_json(prompt, **kw):
        value, fell_back = ask_json(prompt, **kw)
        used[(kind[0], _agent(prompt), "fallback" if fell_back else "model")] += 1
        if fell_back:
            why[(kind[0], f"{_agent(prompt)}: no valid JSON")] += 1
        return value, fell_back

    def counted_text(prompt, **kw):
        before = llm.stats.fallbacks
        text = ask_text(prompt, **kw)
        if llm.stats.fallbacks > before:
            why[(kind[0], f"{_agent(prompt)}: empty reply or error")] += 1
        return text

    faithful = nodes._narrative_is_faithful

    def counted_faithful(text, allowed):
        ok, reason = faithful(text, allowed)
        used[(kind[0], "narrative", "model" if ok else "fallback")] += 1
        if not ok:
            # Keep the offending token for invented figures, so the cause is
            # visible ("invented figure '17.440'" vs "invented figure '16'").
            why[(kind[0], "narrative: " + reason)] += 1
        return ok, reason

    llm.ask_json, llm.ask_text = counted_json, counted_text
    misses = [0]
    generate = llm.backend.generate

    def counted_generate(*a, **kw):
        misses[0] += 1
        return generate(*a, **kw)

    llm.backend.generate = counted_generate
    nodes._narrative_is_faithful = counted_faithful

    bases = generate_all_base_inputs(frame)
    for criteria in bases:
        kind[0] = "radius" if criteria.query_mode == "RADIUS" else "locality"
        run_pipeline(frame, criteria, seed=args.seed, config=config,
                     graph=graph, llm=llm)

    print(f"{len(bases)} base inputs, seed {args.seed}; "
          f"replies from the cache {llm.stats.cache_hits}, "
          f"new model calls {misses[0]}")
    print(f"\n{'kind':9} {'agent':10} {'model':>6} {'fallback':>9}")
    for k in ("locality", "radius"):
        for agent in ("review", "critique", "criteria", "narrative"):
            m, f = used[(k, agent, "model")], used[(k, agent, "fallback")]
            if m or f:
                print(f"{k:9} {agent:10} {m:6d} {f:9d}")
    print("\nfallback reasons (count):")
    for (k, reason), n in why.most_common(25):
        print(f"  {n:4d}  {k:9} {reason}")


if __name__ == "__main__":
    main()
