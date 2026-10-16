# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: the base input as the statistical unit;
# rejected counts per run. Lines by git blame: Vidhi Jain 72%, Paridhi Mittal
# 28%. Full attribution: CREDITS.md.
"""The metamorphic harness: transform -> re-run -> compare with tolerance.

Protocol (from the brief, section 2 "Statistical checking"):

* at least 30 distinct base inputs per MR,
* each base input repeated under k >= 3 fixed, recorded seeds, for both the
  source and the follow-up run,
* report the seed list, base-input count, violation rate and a 95% confidence
  interval.

The interval is a **Wilson** score interval rather than the normal
approximation. Violation rates here are expected to sit at or very near 0 and
1; the normal interval produces bounds outside [0, 1] and zero width at
p-hat = 0 in exactly those cases, which would misstate the evidence where it
matters most.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from ..agents import AgentMode, GraphConfig, build_graph, run_pipeline
from ..contract import TrendReport
from ..trend import Criteria
from .relations import ALL_RELATIONS, MR

#: Fixed, recorded seeds. Changing these changes the published numbers, so
#: they are part of the artefact, not a tuning knob.
SEEDS: tuple[int, ...] = (11, 23, 47)

#: 95% two-sided.
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class MRResult:
    mr_id: str
    family: str
    base_input: str
    seed: int
    applicable: bool
    violated: bool
    detail: str
    source_loops_c1: int
    source_loops_c2: int
    follow_loops_c1: int
    follow_loops_c2: int
    #: Did both runs take the same relaxation path through cycle 1?
    #:
    #: This matters more than it looks. Coverage depends on listing counts, so
    #: any transformation that changes counts -- duplication, widening a band,
    #: restricting to a sub-region -- can change how many relaxation rounds
    #: fire, and therefore the final criteria for the WHOLE window. When the
    #: paths differ, the two runs are answering different questions and the
    #: relation is not a statement about the aggregation at all.
    #:
    #: The relations are therefore reported twice: unconditionally, and over
    #: the relaxation-stable subdomain. The share of runs where the path
    #: diverges is itself a finding about the system, so it is never silently
    #: dropped.
    same_control_path: bool
    source_relaxations: str
    follow_relaxations: str
    #: Listings rejected by cycle 2's targeted recomputation in each run.
    #: A transformation that changes this changed the analysed population,
    #: which is the mechanism behind M1's residual violations (Analysis.md §3).
    source_rejected: int
    follow_rejected: int
    seconds: float


def wilson_ci(successes: int, trials: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials == 0:
        return (float("nan"), float("nan"))
    p = successes / trials
    denom = 1.0 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = (z / denom) * math.sqrt(
        p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def _run_one(
    frame: pd.DataFrame, criteria: Criteria, seed: int, graph, config,
    llm=None,
) -> tuple[TrendReport, dict]:
    state = run_pipeline(frame, criteria, seed=seed, config=config,
                         graph=graph, llm=llm)
    report = state["final_report"]
    assert report is not None, "pipeline produced no report"
    return report, {
        "c1": state.get("retry_count", 0),
        "c2": state.get("critique_rounds", 0),
        "relaxations": list(state.get("relaxations", [])),
        "levers": list(state.get("relax_levers", [])),
        "rejected": int(state.get("n_rejected_outliers", 0)),
    }


def run_relation(
    mr: MR,
    frame: pd.DataFrame,
    criteria: Criteria,
    seed: int,
    *,
    graph=None,
    config: GraphConfig | None = None,
    llm=None,
) -> MRResult:
    """Execute one (MR, base input, seed) triple."""
    started = time.perf_counter()
    config = config or GraphConfig()
    graph = graph if graph is not None else build_graph(config.n_retrieval_agents)

    # The relation may be declared on a projection of the input space; apply
    # it before BOTH runs so source and follow-up share the same population.
    criteria = mr.prepare(criteria)

    if not mr.applicable(frame, criteria):
        return MRResult(mr.mr_id, mr.family, criteria.label, seed,
                        False, False, "outside subdomain", 0, 0, 0, 0,
                        True, "", "", 0, 0, time.perf_counter() - started)

    rng = np.random.default_rng(seed)
    source_report, src_loops = _run_one(frame, criteria, seed, graph, config, llm)

    follow_frame, follow_criteria = mr.transform(frame, criteria, rng)
    follow_report, dst_loops = _run_one(
        follow_frame, follow_criteria, seed, graph, config, llm
    )

    ok, detail = mr.check(source_report, follow_report)
    # Compare the LEVER SEQUENCE, not the rendered notes: the notes embed the
    # criteria values, so two runs on different inputs always differ textually
    # even when the control flow was identical.
    src_relax = ">".join(src_loops["levers"])
    dst_relax = ">".join(dst_loops["levers"])
    return MRResult(
        mr_id=mr.mr_id, family=mr.family, base_input=criteria.label, seed=seed,
        applicable=True, violated=not ok, detail=detail,
        source_loops_c1=src_loops["c1"], source_loops_c2=src_loops["c2"],
        follow_loops_c1=dst_loops["c1"], follow_loops_c2=dst_loops["c2"],
        same_control_path=(src_relax == dst_relax
                           and src_loops["c2"] == dst_loops["c2"]),
        source_relaxations=src_relax, follow_relaxations=dst_relax,
        source_rejected=src_loops["rejected"],
        follow_rejected=dst_loops["rejected"],
        seconds=time.perf_counter() - started,
    )


def run_all(
    frame: pd.DataFrame,
    base_inputs: list[Criteria],
    *,
    relations: tuple[MR, ...] = ALL_RELATIONS,
    seeds: tuple[int, ...] = SEEDS,
    config: GraphConfig | None = None,
    progress: bool = True,
    llm=None,
) -> pd.DataFrame:
    """Run the full matrix: relations x base inputs x seeds."""
    config = config or GraphConfig()
    graph = build_graph(config.n_retrieval_agents)
    rows: list[dict] = []
    total = len(relations) * len(base_inputs) * len(seeds)
    done = 0
    for mr in relations:
        for criteria in base_inputs:
            for seed in seeds:
                rows.append(asdict(run_relation(
                    mr, frame, criteria, seed, graph=graph, config=config,
                    llm=llm,
                )))
                done += 1
                if progress and done % 50 == 0:
                    extra = ""
                    if llm is not None:
                        extra = (f"  [llm calls={llm.stats.calls} "
                                 f"cache={llm.stats.cache_hits} "
                                 f"fallback={llm.stats.fallback_rate:.3f}]")
                    print(f"  {done}/{total} runs{extra}", flush=True)
                if llm is not None and done % 200 == 0:
                    llm.flush_cache()
    return pd.DataFrame(rows)


def per_base_input(runs: pd.DataFrame) -> pd.DataFrame:
    """Collapse the seeds of each (relation, base input) into one outcome.

    The statistical unit is the base input, not the run (contracts/Testing.md
    §6). The seeds of one base input are repeated measurements of the same
    input, not independent samples: in the deterministic sweep they agree
    every time, and treating 3 x 36 runs as 108 independent trials makes a
    zero-violation interval look three times tighter than the evidence
    supports (0/108 -> upper 0.034; 0/36 -> upper 0.096).

    A base input is *violated* if any of its seeds violated, and *stable* if
    every seed took the same control path in source and follow-up.
    """
    applicable = runs[runs.applicable]
    if applicable.empty:
        return pd.DataFrame(columns=["mr_id", "base_input", "violated",
                                     "stable", "seeds", "seeds_violated"])
    grouped = applicable.groupby(["mr_id", "base_input"], sort=False)
    return grouped.agg(
        violated=("violated", "any"),
        stable=("same_control_path", "all"),
        seeds=("seed", "nunique"),
        seeds_violated=("violated", "sum"),
    ).reset_index()


def summarise(results: pd.DataFrame) -> pd.DataFrame:
    """Per-MR violation rate with a 95% Wilson interval over base inputs.

    Reported over all applicable base inputs and over the relaxation-stable
    subdomain (every seed took the same path through cycle 1 in both runs).
    Per-run counts are kept alongside for comparison with earlier sweeps, and
    ``seed_disagreements`` counts base inputs whose seeds did not all agree.
    """
    bases = per_base_input(results)
    rows = []
    for mr in ALL_RELATIONS:
        runs = results[(results.mr_id == mr.mr_id) & results.applicable]
        b = bases[bases.mr_id == mr.mr_id]
        n, k = len(b), int(b.violated.sum())
        lo, hi = wilson_ci(k, n)
        stable = b[b.stable]
        sn, sk = len(stable), int(stable.violated.sum())
        s_lo, s_hi = wilson_ci(sk, sn)
        run_k = int(runs.violated.sum())
        run_lo, run_hi = wilson_ci(run_k, len(runs))
        disagree = int(((b.seeds_violated > 0)
                        & (b.seeds_violated < b.seeds)).sum())
        rows.append({
            "mr_id": mr.mr_id,
            "family": mr.family,
            "relation": mr.name,
            "base_inputs": n,
            "violations": k,
            "violation_rate": (k / n) if n else float("nan"),
            "ci95_low": lo,
            "ci95_high": hi,
            "path_diverged": n - sn,
            "stable_base_inputs": sn,
            "stable_violations": sk,
            "stable_rate": (sk / sn) if sn else float("nan"),
            "stable_ci95_low": s_lo,
            "stable_ci95_high": s_hi,
            "seed_disagreements": disagree,
            "runs": len(runs),
            "run_violations": run_k,
            "run_rate": (run_k / len(runs)) if len(runs) else float("nan"),
            "run_ci95_low": run_lo,
            "run_ci95_high": run_hi,
        })
    return pd.DataFrame(rows)


def headline_table(results: pd.DataFrame) -> str:
    """The report's headline results table. Unit: base input."""
    summary = summarise(results)
    lines = [
        "Unit = base input (violated if any seed violates)  | Relaxation-stable subdomain",
        f"{'MR':<6}{'family':<12}{'bases':>6}{'viol':>5}{'rate':>7}"
        f"{'95% CI':>18}{'disagr':>7}  | {'bases':>6}{'viol':>5}{'rate':>7}{'95% CI':>18}",
        "-" * 106,
    ]
    for row in summary.itertuples(index=False):
        if row.base_inputs == 0:
            continue
        ci = f"[{row.ci95_low:.3f},{row.ci95_high:.3f}]"
        sci = ("[  n/a  ]" if row.stable_base_inputs == 0
               else f"[{row.stable_ci95_low:.3f},{row.stable_ci95_high:.3f}]")
        srate = ("  n/a" if row.stable_base_inputs == 0
                 else f"{row.stable_rate:>7.3f}")
        lines.append(
            f"{row.mr_id:<6}{row.family:<12}{row.base_inputs:>6}"
            f"{row.violations:>5}{row.violation_rate:>7.3f}{ci:>18}"
            f"{row.seed_disagreements:>7}  | {row.stable_base_inputs:>6}"
            f"{row.stable_violations:>5}{srate}{sci:>18}"
        )
    lines.append("-" * 106)
    diverged = int((~results[results.applicable].same_control_path).sum())
    lines.append(
        f"seeds: {list(SEEDS)}   total runs: {len(results)}   "
        f"runs where the C1 relaxation path diverged: {diverged}   "
        f"disagr = base inputs whose seeds disagreed"
    )
    return "\n".join(lines)
