"""Check the numeric claims in the documents against code and result files.

Written because two factual errors slipped through earlier: the data README
named one Kaggle dataset while linking another, and an assistant claim about
what DESIGN.md said turned out to be false. Both were avoidable by checking
rather than remembering.

Every claim below is re-derived from the frozen snapshot, the committed result
files or the test suite. Claims that cannot be derived are listed explicitly as
unverifiable rather than silently trusted.

    python scripts/verify_claims.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

DOCS = ["DESIGN.md", "REPORT.md", "README.md", "NOTEBOOK.md", "AI_USE.md",
        "docs/DIAGNOSIS.md"]


def main() -> int:
    from src.contract import MIN_SUFFICIENT_N
    from src.loading import load_canonical, verify_snapshot
    from src.mr.base_inputs import generate_base_inputs
    from src.mr.harness import SEEDS
    from src.mr.relations import ALL_RELATIONS

    frame, log = load_canonical()
    raw = pd.read_csv("data/raw/hyderabad.csv", low_memory=False)
    inputs = generate_base_inputs(frame)
    summary = pd.read_csv("results/llm/mr_summary.csv").set_index("mr_id")
    det = pd.read_csv("results/phaseA_deterministic/mr_summary.csv").set_index("mr_id")
    pre = pd.read_csv("results/llm_before_promptfix/mr_summary.csv").set_index("mr_id")
    meta = json.loads(Path("results/llm/run_meta.json").read_text())
    probe = json.loads(Path("results/llm/determinism_probe.json").read_text())
    sens = pd.read_csv("results/sensitivity/threshold_sensitivity.csv")

    checks: list[tuple[str, object, object]] = [
        ("snapshot sha256 prefix", verify_snapshot()[:16], "9e81698322606c86"),
        ("raw rows", len(raw), 9487),
        ("raw columns", len(raw.columns), 55),
        ("canonical rows", len(frame), 4578),
        ("int32 sentinel value", 2**31 - 1, 2_147_483_647),
        ("PREFERENCE S/R/P", tuple(raw.PREFERENCE.value_counts()[["S","R","P"]]), (7927, 1467, 93)),
        ("missing BEDROOM_NUM", int(raw.BEDROOM_NUM.isna().sum()), 2814),
        ("of which Residential Land",
         int((raw[raw.BEDROOM_NUM.isna()].PROPERTY_TYPE == "Residential Land").sum()), 2806),
        ("relations", len(ALL_RELATIONS), 11),
        ("families 5/4/2",
         tuple(sum(1 for m in ALL_RELATIONS if m.family == f)
               for f in ("invariance","monotonic","directional")), (5, 4, 2)),
        ("base inputs", len(inputs), 36),
        ("seeds", list(SEEDS), [11, 23, 47]),
        ("sufficiency threshold", MIN_SUFFICIENT_N, 50),
        ("runs per sweep", meta["total_runs"], 1188),
        ("determinism probe trials", probe["trials"], 20),
        ("determinism distinct outputs", probe["distinct_outputs"], 1),
        ("LLM calls (post-fix)", meta["llm"]["llm_calls"], 14209),
        ("LLM fallback rate (post-fix)", meta["llm"]["llm_fallback_rate"], 0.0874),
        ("model digest", meta["llm"]["model_tag_sha256"], "d7f5d340f8953384"),
    ]

    # Coordinate coverage and age-on-site, as quoted in DESIGN/REPORT.
    checks.append(("coordinate coverage %",
                   round(frame.latitude.notna().mean() * 100, 1), 94.7))
    checks.append(("median age on site (days)",
                   int(frame.age_on_site_days.median()), 37))

    # Share of the window's listings in its final six months.
    window = [f"2022-{m:02d}" for m in (9, 10, 11, 12)] + \
             [f"2023-{m:02d}" for m in range(1, 9)]
    inw = frame[frame.month.isin(window)]
    last6 = inw[inw.month.isin(window[-6:])]
    checks.append(("final six months share %",
                   round(len(last6) / len(inw) * 100, 1), 96.5))

    # Violation rates quoted in the documents.
    for mr, d, p, q in [("I4", 0.000, 0.630, 0.000), ("I3", 0.000, 0.417, 0.176),
                        ("I2", 0.000, 0.028, 0.000), ("D2", 0.000, 0.556, 0.593),
                        ("D1", 0.000, 0.222, 0.667), ("M1", 0.139, 0.222, 0.333),
                        ("M1raw", 0.861, 0.852, 0.806)]:
        checks.append((f"{mr} deterministic", round(det.loc[mr,"violation_rate"],3), d))
        checks.append((f"{mr} LLM pre-fix",  round(pre.loc[mr,"violation_rate"],3), p))
        checks.append((f"{mr} LLM post-fix", round(summary.loc[mr,"violation_rate"],3), q))

    # Threshold sensitivity, the headline caveat.
    at50 = sens[sens.min_sufficient_n == 50].headline_pct.iloc[0]
    checks.append(("headline at n>=50 %", round(at50, 2), -6.41))
    spread = sens.headline_pct.max() - sens.headline_pct.min()
    checks.append(("sensitivity spread (pp)", round(spread, 1), 93.6))
    checks.append(("sensitivity sign flips",
                   bool((sens.headline_pct > 0).any() and (sens.headline_pct < 0).any()), True))

    # The external cross-check, quoted in REPORT §9.1 and DESIGN §5.
    at75 = sens[sens.min_sufficient_n == 75].headline_pct.iloc[0]
    checks.append(("headline at n>=75 %", round(at75, 2), 7.08))
    residex = Path("results/residex/cross_check.md")
    checks.append(("RESIDEX evidence retained", residex.exists(), True))
    checks.append(("RESIDEX PDF retained",
                   Path("results/residex/Press_Release_July-September_2023.pdf").exists(), True))
    if residex.exists():
        checks.append(("RESIDEX Hyderabad figure quoted",
                       "+6.8%" in residex.read_text(), True))

    failures = []
    print(f"{'claim':<34}{'derived':>22}{'documented':>22}")
    print("-" * 78)
    for name, got, want in checks:
        ok = (abs(got - want) < 1e-9 if isinstance(got, float) and isinstance(want, float)
              else got == want)
        if not ok:
            failures.append((name, got, want))
        print(f"{name:<34}{str(got):>22}{str(want):>22}  {'' if ok else '<-- MISMATCH'}")

    print("\n" + "-" * 78)
    if failures:
        print(f"{len(failures)} MISMATCH(ES):")
        for name, got, want in failures:
            print(f"  {name}: derived {got!r}, documents say {want!r}")
    else:
        print("all derivable claims match the documents")

    print("\nProvenance: origin and licence were VERIFIED against the Kaggle")
    print("dataset page (arvanshul/gurgaon-real-estate-99acres-com, titled")
    print("'Indian Real Estate - 99acres.com', covering Gurgaon/Hyderabad/")
    print("Mumbai/Kolkata, CDLA-Sharing-1.0). The slug is misleading; the")
    print("dataset the brief recommends covers Gurgaon only. Not re-checked")
    print("here because it needs network access -- see data/raw/Readme.md.")

    # Cross-document consistency: no stale agent names anywhere.
    stale = re.compile(r"ScanAgent|AnomalySentinel|CriteriaPlanner|TrendAggregator"
                       r"|CoverageAuditor|NarrativeAgent|cycle C[12]")
    print("\nStale agent/cycle names in documents:")
    bad = 0
    for doc in DOCS:
        hits = len(stale.findall(Path(doc).read_text()))
        bad += hits
        print(f"  {doc:<22}{hits}")
    failures.append(("stale names", bad, 0)) if bad else None

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
