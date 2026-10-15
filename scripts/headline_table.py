"""Rebuild the report's headline results table from the committed result files.

The brief asks for "a one-command reproduction of your headline results table."
`run_harness.py` re-runs a sweep, but the headline table in REPORT.md §7.1 spans
three configurations and two of them need Ollama and a 1.9 GB model, so a fresh
machine cannot rebuild it in one command. This script closes that gap: it
assembles the published table from the committed per-run CSVs, recomputing every
rate and confidence interval from the raw results rather than copying them.

    python scripts/headline_table.py            # the table as published
    python scripts/headline_table.py --check     # also verify it matches REPORT.md

Re-running a sweep from scratch is still available and is the stronger check:
    python scripts/run_harness.py --tag check               # deterministic
    python scripts/run_harness.py --tag llm --llm           # needs Ollama
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from src.mr.harness import wilson_ci          # noqa: E402
from src.mr.relations import ALL_RELATIONS    # noqa: E402

CONFIGS = [
    ("deterministic", "phaseA_deterministic"),
    ("LLM pre-fix", "llm_before_promptfix"),
    ("LLM post-fix", "llm"),
]


def rates(tag: str) -> pd.DataFrame:
    """Recompute rate and Wilson interval from the per-run records."""
    runs = pd.read_csv(Path("results") / tag / "mr_runs.csv")
    rows = []
    for mr in ALL_RELATIONS:
        subset = runs[(runs.mr_id == mr.mr_id) & runs.applicable]
        if subset.empty:
            continue
        violations, trials = int(subset.violated.sum()), len(subset)
        lo, hi = wilson_ci(violations, trials)
        rows.append({"mr_id": mr.mr_id, "family": mr.family, "runs": trials,
                     "violations": violations, "rate": violations / trials,
                     "lo": lo, "hi": hi})
    return pd.DataFrame(rows).set_index("mr_id")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify the rebuilt rates appear in REPORT.md")
    args = parser.parse_args()

    tables = {}
    for label, tag in CONFIGS:
        path = Path("results") / tag / "mr_runs.csv"
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 2
        tables[label] = rates(tag)

    meta = json.loads(Path("results/llm/run_meta.json").read_text())
    shipped = tables["LLM post-fix"]

    print("Headline results — rebuilt from the committed per-run records\n")
    print(f"{'MR':<7}{'family':<13}{'determ.':>9}{'pre-fix':>9}"
          f"{'post-fix':>10}{'95% CI (post-fix)':>21}")
    print("-" * 69)
    for mr in shipped.index:
        cells = []
        for label, _ in CONFIGS:
            t = tables[label]
            cells.append(f"{t.loc[mr,'rate']:.3f}" if mr in t.index else "—")
        row = shipped.loc[mr]
        ci = f"[{row.lo:.3f}, {row.hi:.3f}]"
        print(f"{mr:<7}{row.family:<13}{cells[0]:>9}{cells[1]:>9}"
              f"{cells[2]:>10}{ci:>21}")
    print("-" * 69)
    print(f"{len(shipped)} relations x {meta['base_inputs']} base inputs "
          f"x {len(meta['seeds'])} seeds {meta['seeds']} = "
          f"{meta['total_runs']} checks per sweep")
    print(f"snapshot {meta['snapshot_sha256'][:16]}...  "
          f"model {meta['llm']['model']} ({meta['llm']['model_tag_sha256']})")
    print(f"LLM fallback rate {meta['llm']['llm_fallback_rate']}  "
          f"determinism probe "
          f"{json.loads(Path('results/llm/determinism_probe.json').read_text())['identical_rate']:.0%} identical")

    if args.check:
        report = Path("REPORT.md").read_text()
        missing = []
        for mr in shipped.index:
            for label, _ in CONFIGS:
                t = tables[label]
                if mr not in t.index:
                    continue
                token = f"{t.loc[mr, 'rate']:.3f}"
                if token not in report:
                    missing.append(f"{mr} {label} {token}")
        print()
        if missing:
            print(f"{len(missing)} rebuilt rate(s) not found in REPORT.md:")
            for m in missing:
                print(f"  {m}")
            return 1
        print("every rebuilt rate appears in REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
