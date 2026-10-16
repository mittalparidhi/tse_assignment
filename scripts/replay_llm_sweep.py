"""Replay a committed LLM sweep offline from the reply cache, and compare.

Every model request is answered from ``data/llm_cache/responses.json``; a
request that is not in the cache is an error and stops the replay, so a
successful replay proves the committed results follow from the committed code
and the cached model replies alone -- no Ollama, no GPU.

    python scripts/replay_llm_sweep.py                    # results/v2_llm
    python scripts/replay_llm_sweep.py --tag v2_llm_before_reviewfix   # needs that commit's code

Exit code 0 when every run record (except wall-clock seconds) is identical.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import AgentMode, GraphConfig  # noqa: E402
from src.llm import DEFAULT_CACHE, DEFAULT_MODEL, Backend, LLMClient  # noqa: E402
from src.loading import load_canonical, verify_snapshot  # noqa: E402
from src.mr.base_inputs import generate_all_base_inputs  # noqa: E402
from src.mr.harness import run_all  # noqa: E402


class _CacheOnly(Backend):
    """Stands in for Ollama; any call means the cache lacks a reply."""

    name = "ollama"
    host = "offline"

    def generate(self, prompt, **kwargs):
        raise ConnectionRefusedError("offline replay: reply not in the cache")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", default="v2_llm")
    parser.add_argument("--llm-model", default=DEFAULT_MODEL)
    parser.add_argument("--llm-cache", default=str(DEFAULT_CACHE))
    args = parser.parse_args()

    verify_snapshot()
    frame = load_canonical()[0]
    llm = LLMClient(backend=_CacheOnly(), model=args.llm_model,
                    cache_path=Path(args.llm_cache), max_consecutive_errors=1)
    llm.flush_cache = lambda: None            # read-only
    config = GraphConfig(agent_mode=AgentMode.LLM, llm_model=args.llm_model)
    replayed = run_all(frame, generate_all_base_inputs(frame), config=config, llm=llm)

    committed = pd.read_csv(Path("results") / args.tag / "mr_runs.csv")
    a = replayed.drop(columns="seconds").reset_index(drop=True)
    b = committed.drop(columns="seconds")
    a = a.astype(str).where(a.notna(), "")
    b = b.astype(str).where(b.notna(), "")
    if a.shape != b.shape:
        print(f"shape differs: replayed {a.shape}, committed {b.shape}")
        return 1
    differing = int((a.values != b.values).any(axis=1).sum())
    print(f"replayed {len(a)} runs from the cache ({llm.stats.cache_hits} replies, "
          f"0 model calls); records differing from results/{args.tag}: {differing}")
    return 0 if differing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
