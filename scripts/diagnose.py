"""Root-cause analysis of the three most-violated relations.

The brief requires each top violation to be attributed, with evidence, to one
of: a genuine agent/aggregation fault, a data artifact, an ill-conceived MR, or
a harness bug. Asserting a cause is not evidence, so each hypothesis here is
tested by a controlled experiment in which exactly one thing changes.

    python scripts/diagnose.py [--out results/v2_diagnosis]

Writes <out>/*.csv (default results/v2_diagnosis) and a summary to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import GraphConfig, build_graph                   # noqa: E402
from src.loading import load_canonical                            # noqa: E402
from src.mr.base_inputs import generate_base_inputs               # noqa: E402
from src.mr.relations import ALL_RELATIONS, BY_ID                 # noqa: E402
from src.mr.harness import run_relation                           # noqa: E402
from src.mr.transforms import add_to_month_price                  # noqa: E402
from src.mr.relations import M1_DELTA_INR, _pick_shift_month      # noqa: E402
from src.trend import apply_criteria, month_window                # noqa: E402

#: Where results go. The pre-v2 experiments behind docs/DIAGNOSIS.md are in
#: results/diagnosis and are not overwritten by default.
OUT = Path("results/v2_diagnosis")
SEEDS = (11, 23)
N_INPUTS = 12


def sweep(frame, inputs, graph, label: str, config: GraphConfig) -> pd.DataFrame:
    rows = []
    for mr in ALL_RELATIONS:
        violations = applicable = 0
        for criteria in inputs:
            for seed in SEEDS:
                r = run_relation(mr, frame, criteria, seed,
                                 graph=graph, config=config)
                if r.applicable:
                    applicable += 1
                    violations += int(r.violated)
        rows.append({"condition": label, "mr_id": mr.mr_id,
                     "family": mr.family, "violations": violations,
                     "runs": applicable,
                     "rate": violations / applicable if applicable else None})
        print(f"  [{label}] {mr.mr_id}: {violations}/{applicable}", flush=True)
    return pd.DataFrame(rows)


def experiment_a_and_b(frame, inputs, graph) -> pd.DataFrame:
    """A: is cycle 2 responsible at all?  B: is the grouping the mechanism?"""
    conditions = {
        # Baseline reproduces the original implementation exactly.
        "baseline (C2 on, group=shard+month)":
            GraphConfig(max_critique_rounds=1, group_outliers_by_month=False),
        # A: remove cycle 2 entirely. If violations vanish, cycle 2 is the locus.
        "A: C2 disabled":
            GraphConfig(max_critique_rounds=0, group_outliers_by_month=False),
        # B: keep C2, change only the grouping. If violations vanish, the
        #    grouping is the mechanism.
        "B: C2 on, group=month":
            GraphConfig(max_critique_rounds=1, group_outliers_by_month=True),
    }
    return pd.concat([sweep(frame, inputs, graph, name, cfg)
                      for name, cfg in conditions.items()], ignore_index=True)


def experiment_c(frame, inputs, graph) -> pd.DataFrame:
    """C: shard-count sensitivity.

    If the accepted set depends on how listings are split across workers, then
    changing the worker count must change the answer -- for a correct system it
    cannot, since the number of workers is not a property of the market.
    """
    rows = []
    deepest = max(inputs, key=lambda c: len(apply_criteria(frame, c)))
    for n_shards in (1, 2, 4, 8):
        for group_by_month in (False, True):
            cfg = GraphConfig(n_retrieval_agents=n_shards,
                              max_critique_rounds=1,
                              group_outliers_by_month=group_by_month)
            # Retrieval fan-out is fixed when the graph is compiled, so each
            # agent count needs its own graph (src/agents/graph.py).
            graph = build_graph(n_shards)
            totals = []
            for criteria in inputs[:6]:
                r = run_relation(BY_ID["I1"], frame, criteria, 11,
                                 graph=graph, config=cfg)
                totals.append(r.violated)
            # Also record the actual listing total, which must be shard-invariant,
            # on the deepest input: a thin one (contract v2 keeps narrow
            # queries narrow) rejects nothing, and then cannot show the effect.
            from src.agents import run_pipeline
            state = run_pipeline(frame, deepest, seed=11, config=cfg,
                                 graph=graph)
            rows.append({
                "n_shards": n_shards,
                "grouping": "month" if group_by_month else "shard+month",
                "I1_violations": int(sum(totals)),
                "I1_runs": len(totals),
                "listings_total": state["final_report"].n_listings_total,
                "rejected": state["n_rejected_outliers"],
                "listings_input": deepest.label,
            })
            print(f"  [C] shards={n_shards} grouping="
                  f"{'month' if group_by_month else 'shard+month'} "
                  f"listings={state['final_report'].n_listings_total} "
                  f"rejected={state['n_rejected_outliers']}", flush=True)
    return pd.DataFrame(rows)


def experiment_d(frame, inputs) -> pd.DataFrame:
    """D: does MR-M1's price shift push listings across the band criterion?

    This is a pure data measurement -- no agents involved -- so it can
    distinguish an ill-conceived MR from an agent fault. If listings cross the
    band, the transformation changes the selected population and the relation
    cannot hold however correct the system is.
    """
    rows = []
    for criteria in inputs:
        month = _pick_shift_month(frame, criteria)
        if month is None:
            continue
        before = apply_criteria(frame, criteria)
        before = before[before["month"] == month]
        shifted_frame = add_to_month_price(frame, month, M1_DELTA_INR)
        after = apply_criteria(shifted_frame, criteria)
        after = after[after["month"] == month]
        crossed_out = len(set(before["listing_id"]) - set(after["listing_id"]))
        crossed_in = len(set(after["listing_id"]) - set(before["listing_id"]))
        rows.append({
            "base_input": criteria.label,
            "shift_month": month,
            "band_min_lakh": (criteria.price_min_inr or 0) / 1e5,
            "band_max_lakh": (criteria.price_max_inr or 0) / 1e5,
            "n_before": len(before),
            "n_after": len(after),
            "left_the_band": crossed_out,
            "entered_the_band": crossed_in,
            "population_changed": bool(crossed_out or crossed_in),
        })
    return pd.DataFrame(rows)


def main() -> int:
    global OUT
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    OUT = Path(parser.parse_args().out)
    OUT.mkdir(parents=True, exist_ok=True)
    frame, _ = load_canonical()
    inputs = generate_base_inputs(frame)[:N_INPUTS]
    graph = build_graph()
    print(f"diagnosis: {len(inputs)} base inputs x seeds {list(SEEDS)}\n")

    print("== Experiments A and B: is cycle 2's grouping the cause? ==")
    ab = experiment_a_and_b(frame, inputs, graph)
    ab.to_csv(OUT / "exp_ab_conditions.csv", index=False, lineterminator="\n")

    print("\n== Experiment C: shard-count sensitivity ==")
    c = experiment_c(frame, inputs, graph)
    c.to_csv(OUT / "exp_c_shard_sensitivity.csv", index=False, lineterminator="\n")

    print("\n== Experiment D: does M1's shift move listings across the band? ==")
    d = experiment_d(frame, inputs)
    d.to_csv(OUT / "exp_d_m1_band_crossing.csv", index=False, lineterminator="\n")
    print(d.to_string(index=False))

    print("\n\n================ SUMMARY ================")
    pivot = ab.pivot(index="mr_id", columns="condition", values="rate")
    print(pivot.to_string())
    print("\nM1 band crossing: "
          f"{int(d.population_changed.sum())}/{len(d)} base inputs change "
          f"population under the +Rs {M1_DELTA_INR:,.0f} shift")
    print(f"  listings leaving the band:  total {int(d.left_the_band.sum())}")
    print(f"  listings entering the band: total {int(d.entered_the_band.sum())}")
    print(f"\nwritten to {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
