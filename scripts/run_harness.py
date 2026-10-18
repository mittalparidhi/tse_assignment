"""One-command reproduction of the headline results table.

    python scripts/run_harness.py [--tag TAG]

Writes:
    results/<tag>/mr_runs.csv       one row per (MR, base input, seed)
    results/<tag>/mr_summary.csv    per-MR violation rate + 95% Wilson CI
    results/<tag>/headline.txt      the table reproduced in the report
    results/<tag>/trace_example.txt an execution trace showing both loops fire
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import (                                      # noqa: E402
    AgentMode, GraphConfig, build_graph, run_pipeline,
)
from src.llm import (                                         # noqa: E402
    DEFAULT_CACHE, DEFAULT_HOST, DEFAULT_MODEL,
    LLMClient, OllamaBackend, model_fingerprint,
)
from src.loading import load_canonical, verify_snapshot       # noqa: E402
from src.mr.base_inputs import (generate_base_inputs,             # noqa: E402
                                generate_radius_inputs, summarise)
from src.mr.harness import SEEDS, headline_table, run_all, summarise as mr_summarise  # noqa: E402
from src.trend import Criteria                                # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="current",
                       help="subdirectory under results/")
    parser.add_argument("--quick", action="store_true",
                       help="3 base inputs only, for a fast check")
    parser.add_argument("--synthetic", action="store_true",
                       help="run against the synthetic snapshot with known "
                            "ground truth, to separate a harness bug from a "
                            "data artifact")
    parser.add_argument("--llm", action="store_true",
                       help="route the judgment steps through a local model")
    parser.add_argument("--llm-model", default=DEFAULT_MODEL)
    parser.add_argument("--llm-host", default=DEFAULT_HOST)
    parser.add_argument("--llm-cache", default=str(DEFAULT_CACHE))
    args = parser.parse_args()

    out = Path("results") / args.tag
    out.mkdir(parents=True, exist_ok=True)

    if args.synthetic:
        import hashlib
        syn = Path("data/snapshot/listings_synthetic.csv")
        if not syn.exists():
            raise SystemExit("run scripts/make_synthetic.py first")
        digest = hashlib.sha256(syn.read_bytes()).hexdigest()
        frame = pd.read_csv(syn)
        print(f"SYNTHETIC snapshot: sha256={digest[:16]}...  "
              f"rows={len(frame):,}")
        print("Known ground truth: a relation violated here cannot be a data "
              "artifact, so it is a harness bug or a real fault.")
    else:
        digest = verify_snapshot()
        print(f"snapshot verified: sha256={digest[:16]}...")
        frame, reject_log = load_canonical()
        print(f"canonical listings: {len(frame):,}")
        reject_log.as_frame().to_csv(out / "filter_cascade.csv", index=False, lineterminator="\n")

    if args.synthetic:
        # The synthetic snapshot has no coordinates, so it cannot carry the
        # radius inputs; its role is the oracle check on the statistics.
        base_inputs = generate_base_inputs(frame)
        if args.quick:
            base_inputs = base_inputs[:3]
    else:
        locality, radius = generate_base_inputs(frame), generate_radius_inputs(frame)
        if args.quick:
            locality, radius = locality[:3], radius[:3]
        base_inputs = locality + radius
    summarise(base_inputs).to_csv(out / "base_inputs.csv", index=False, lineterminator="\n")
    print(f"base inputs: {len(base_inputs)}   seeds: {list(SEEDS)}")

    llm = None
    config = GraphConfig()
    if args.llm:
        llm = LLMClient(
            backend=OllamaBackend(args.llm_host),
            model=args.llm_model,
            cache_path=Path(args.llm_cache),
            flush_every=50,
            max_consecutive_errors=10,
        )
        # Preflight: one real call. Without it a dead server makes every call
        # fall back and the sweep finishes as a deterministic one.
        try:
            llm.backend.generate("Reply with OK.", seed=0, model=args.llm_model,
                                 temperature=0.0, num_predict=4)
        except Exception as error:                                # noqa: BLE001
            sys.exit(f"Ollama at {args.llm_host} did not answer ({error!r}); "
                     "start it with `ollama serve` and pull the model first.")
        config = GraphConfig(agent_mode=AgentMode.LLM,
                             llm_model=args.llm_model,
                             llm_host=args.llm_host)
        print(f"LLM mode: {args.llm_model} via {args.llm_host}")
        print(f"  fingerprint: {model_fingerprint(args.llm_model, llm.backend)}")

    started = time.perf_counter()
    results = run_all(frame, base_inputs, config=config, llm=llm)
    elapsed = time.perf_counter() - started
    print(f"completed {len(results)} runs in {elapsed:.1f}s")

    if llm is not None:
        llm.flush_cache()
        print(f"LLM accounting: {llm.stats.as_dict()}")

    results.to_csv(out / "mr_runs.csv", index=False, lineterminator="\n")
    mr_summarise(results).to_csv(out / "mr_summary.csv", index=False, lineterminator="\n")

    table = headline_table(results)
    (out / "headline.txt").write_text(table + "\n", encoding="utf-8",
                                      newline="\n")
    print("\n" + table)

    # An execution trace proving both cycles fire at run time.
    graph = build_graph()
    narrow = Criteria(window_end="2023-08", bhk=(3,),
                      localities=("Gachibowli",), label="trace-demo")
    state = run_pipeline(frame, narrow, seed=7, graph=graph,
                         config=config, llm=llm,
                         user_query="3 BHK in Gachibowli over the last year")
    lines = [f"{e['step']:>3}. {e['agent']:<17} " +
             "  ".join(f"{k}={v}" for k, v in e.items()
                       if k not in {"step", "agent"})
             for e in state["trace"]]
    (out / "trace_example.txt").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8", newline="\n")

    (out / "run_meta.json").write_text(json.dumps({
        "snapshot_sha256": digest,
        "synthetic": bool(args.synthetic),
        "canonical_rows": int(len(frame)),
        "base_inputs": int(len(base_inputs)),
        "seeds": list(SEEDS),
        "total_runs": int(len(results)),
        "elapsed_seconds": round(elapsed, 2),
        "agent_mode": config.agent_mode.value,
        "llm": (None if llm is None else {
            **model_fingerprint(args.llm_model, llm.backend),
            **llm.stats.as_dict(),
        }),
    }, indent=2), encoding="utf-8", newline="\n")

    print(f"\nwritten to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
