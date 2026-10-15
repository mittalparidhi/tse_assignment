"""Emit the report's results tables straight from the result CSVs.

Transcribing 1,080-run figures by hand into a report is how numbers drift
apart from the artefacts they came from. This script is the single source for
every table in REPORT.md section 7.

    python scripts/make_results_section.py > /tmp/results_section.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load(tag: str):
    base = Path("results") / tag
    return (
        pd.read_csv(base / "mr_summary.csv"),
        pd.read_csv(base / "mr_runs.csv"),
        json.loads((base / "run_meta.json").read_text()),
    )


def fmt_rate(row, prefix="") -> str:
    rate = row[f"{prefix}rate"] if prefix else row["violation_rate"]
    lo = row[f"{prefix}ci95_low"] if prefix else row["ci95_low"]
    hi = row[f"{prefix}ci95_high"] if prefix else row["ci95_high"]
    if pd.isna(rate):
        return "n/a"
    return f"{rate:.3f} [{lo:.3f}, {hi:.3f}]"


def main() -> int:
    before_s, before_r, before_m = load("before_fix")
    after_s, after_r, after_m = load("after_fix")
    syn_s, syn_r, syn_m = load("synthetic")

    b = before_s.set_index("mr_id")
    a = after_s.set_index("mr_id")
    s = syn_s.set_index("mr_id")

    print("### 7.1 Headline results — real snapshot, after fixes\n")
    print(f"{after_m['total_runs']} runs: 10 relations x "
          f"{after_m['base_inputs']} base inputs x {len(after_m['seeds'])} "
          f"seeds {after_m['seeds']}. "
          f"Snapshot SHA-256 `{after_m['snapshot_sha256'][:16]}...`, "
          f"{after_m['canonical_rows']:,} canonical listings. "
          f"Completed in {after_m['elapsed_seconds']:.0f}s.\n")

    print("| MR | Family | Transformation | Runs | Viol. | Rate, 95% CI (Wilson) |")
    print("|----|--------|----------------|------|-------|------------------------|")
    for mr in a.index:
        row = a.loc[mr]
        mark = "**" if row["violations"] > 0 else ""
        print(f"| {mark}{mr}{mark} | {row['family']} | {row['relation']} "
              f"| {row['runs']} | {row['violations']} "
              f"| {mark}{fmt_rate(row)}{mark} |")

    print("\n### 7.2 Before and after the fixes\n")
    print("| MR | Before | After | Change |")
    print("|----|--------|-------|--------|")
    for mr in a.index:
        if mr not in b.index:
            print(f"| {mr} | — (added later) | {a.loc[mr,'violation_rate']:.3f} "
                  f"| new relation |")
            continue
        bv, av = b.loc[mr, "violation_rate"], a.loc[mr, "violation_rate"]
        if bv == av:
            change = "unchanged"
        elif av < bv:
            change = f"**reduced** ({bv:.3f} -> {av:.3f})"
        else:
            change = f"increased ({bv:.3f} -> {av:.3f})"
        print(f"| {mr} | {bv:.3f} | {av:.3f} | {change} |")

    print("\n### 7.3 Conditioning on the control path\n")
    diverged = int((~after_r[after_r.applicable].same_control_path).sum())
    total = int(after_r.applicable.sum())
    print(f"Of {total} applicable runs on the real snapshot, the C1 relaxation "
          f"path diverged between source and follow-up in **{diverged}** "
          f"({diverged/total*100:.1f}%).\n")
    print("| MR | All runs | Relaxation-stable subdomain | Path diverged |")
    print("|----|----------|------------------------------|----------------|")
    for mr in a.index:
        row = a.loc[mr]
        print(f"| {mr} | {fmt_rate(row)} | {fmt_rate(row, 'stable_')} "
              f"| {int(row['path_diverged'])} / {int(row['runs'])} |")

    print("\n### 7.4 Real versus synthetic snapshot\n")
    print(f"The synthetic snapshot carries a constructed trend "
          f"({syn_m['canonical_rows'] if 'canonical_rows' in syn_m else 4800:,} "
          f"rows, uniform monthly depth). A relation violated there cannot be "
          f"blamed on a data artifact, because the correct answer is known.\n")
    print("| MR | Real | Synthetic | Reading |")
    print("|----|------|-----------|---------|")
    for mr in a.index:
        rv, sv = a.loc[mr, "violation_rate"], s.loc[mr, "violation_rate"]
        if rv == 0 and sv == 0:
            note = "holds on both"
        elif rv > 0 and sv > 0:
            note = "fails on both — the relation or the harness, not the data"
        elif rv > 0 and sv == 0:
            note = "**fails on real only — data-dependent**"
        else:
            note = "**fails on synthetic only — masked by the real data**"
        print(f"| {mr} | {rv:.3f} | {sv:.3f} | {note} |")

    print("\n### 7.5 Loop activity\n")
    app = after_r[after_r.applicable]
    print(f"- C1 (widening) rounds per source run: "
          f"{dict(app.source_loops_c1.value_counts().sort_index())}")
    print(f"- C2 (strict) rounds per source run:   "
          f"{dict(app.source_loops_c2.value_counts().sort_index())}")
    print(f"- Mean wall-clock per run (two full pipeline executions): "
          f"{app.seconds.mean():.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
