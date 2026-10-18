"""Exercise the LLM path against a real local model.

Phase A writes the LLM code but cannot prove a real model answers the prompts
usefully; only running one can. This script is that check, and it reports the
number that decides whether the LLM path is trustworthy: the **fallback rate**,
the share of calls where the model never produced parseable, valid output and
the agent had to use a recorded default.

    python scripts/validate_llm.py --model qwen2.5:0.5b-instruct

A small model is fine here -- the question is whether the plumbing and the
prompts work, not whether the answers are good.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import (                                      # noqa: E402
    AgentMode, GraphConfig, build_graph, run_pipeline,
)
from src.llm import (                                         # noqa: E402
    DEFAULT_HOST, LLMClient, OllamaBackend, model_fingerprint,
)
from src.loading import load_canonical                        # noqa: E402
from src.trend import Criteria                                # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:0.5b-instruct")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--cache", default="/tmp/llm_validate_cache.json")
    parser.add_argument("--max-fallback-rate", type=float, default=0.5,
                        help="fail if the model falls back more often than this")
    args = parser.parse_args()

    llm = LLMClient(backend=OllamaBackend(args.host), model=args.model,
                    cache_path=Path(args.cache))
    print("model fingerprint:", json.dumps(
        model_fingerprint(args.model, llm.backend)), flush=True)

    frame, _ = load_canonical()
    config = GraphConfig(agent_mode=AgentMode.LLM, llm_model=args.model,
                         llm_host=args.host)
    graph = build_graph(config.n_retrieval_agents)

    started = time.perf_counter()
    state = run_pipeline(
        frame,
        Criteria(window_end="2023-08", bhk=(3,), localities=("Gachibowli",),
                 label="llm-validate"),
        seed=args.seed, config=config, graph=graph,
        user_query="3 BHK flats in Gachibowli over the last twelve months",
        llm=llm,
    )
    elapsed = time.perf_counter() - started

    print("\n=== EXECUTION TRACE (LLM mode, real model) ===")
    for entry in state["trace"]:
        detail = "  ".join(f"{k}={v}" for k, v in entry.items()
                           if k not in {"step", "agent"})
        print(f"{entry['step']:>3}. {entry['agent']:<20} {detail[:125]}")

    report = state["final_report"]
    print(f"\ncycle 1 fired {state['retry_count']}x   "
          f"cycle 2 fired {state['critique_rounds']}x   "
          f"listings rejected {state['n_rejected_outliers']}")
    print(f"headline: {report.yoy_median_psf_pct:+.2f}% over "
          f"{report.yoy_span_months} sufficient months")

    print("\n=== NARRATIVE (written by the model) ===")
    print(state["narrative"][:600])

    stats = llm.stats.as_dict()
    print("\n=== LLM ACCOUNTING ===")
    for key, value in stats.items():
        print(f"  {key:<22} {value}")
    print(f"  wall clock             {elapsed:.1f}s")
    llm.flush_cache()

    rate = stats["llm_fallback_rate"]
    if rate > args.max_fallback_rate:
        print(f"\nFAIL: fallback rate {rate:.3f} exceeds "
              f"{args.max_fallback_rate:.2f}. The prompts need work before "
              "this path can be trusted.")
        return 1
    print(f"\nPASS: fallback rate {rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
