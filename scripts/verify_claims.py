# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: re-derives every figure for the v2
# population and twelve relations. Lines by git blame: Vidhi Jain 87%, Paridhi
# Mittal 13%. Full attribution: CREDITS.md.
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

#: Quoted figures also appear in source files that the prose checks above do
#: not read. A stale copy in the UI contradicts the report just as loudly as a
#: stale copy in the report, so these are scanned too. (app.py carried "97%"
#: against the derived 96.5%, and relations.py said "Nine relations" against
#: the eleven it defines, both for several days.)
SOURCES = ["app.py", "src/mr/relations.py", "src/contract.py",
           "src/agents/nodes.py", "tests/test_llm.py", "README.md"]


def main() -> int:
    from src.contract import MIN_SUFFICIENT_N
    from src.loading import load_canonical, verify_snapshot
    from src.mr.base_inputs import generate_base_inputs
    from src.mr.relations import ALL_RELATIONS
    from src.mr.harness import SEEDS
    from src.mr.relations import ALL_RELATIONS

    frame, log = load_canonical()
    raw = pd.read_csv("data/raw/hyderabad.csv", low_memory=False)
    inputs = generate_base_inputs(frame)
    summary = pd.read_csv("results/llm/mr_summary.csv").set_index("mr_id")
    det = pd.read_csv("results/phaseA_deterministic/mr_summary.csv").set_index("mr_id")
    pre = pd.read_csv("results/llm_before_promptfix/mr_summary.csv").set_index("mr_id")
    meta = json.loads(Path("results/llm/run_meta.json").read_text(encoding="utf-8"))
    probe = json.loads(Path("results/llm/determinism_probe.json").read_text(encoding="utf-8"))
    sens = pd.read_csv("results/sensitivity/threshold_sensitivity.csv")

    checks: list[tuple[str, object, object]] = [
        ("snapshot sha256 prefix", verify_snapshot()[:16], "9e81698322606c86"),
        ("raw rows", len(raw), 9487),
        ("raw columns", len(raw.columns), 55),
        # Design note §2: listing_count includes listings without a valid
        # price, so the canonical frame keeps them (flagged); the price
        # statistics, and the figures below, use the price-valid ones.
        ("canonical listings", len(frame), 4975),
        ("price-valid listings", int(frame.price_valid.sum()), 4574),
        ("int32 sentinel value", 2**31 - 1, 2_147_483_647),
        ("PREFERENCE S/R/P", tuple(raw.PREFERENCE.value_counts()[["S","R","P"]]), (7927, 1467, 93)),
        ("missing BEDROOM_NUM", int(raw.BEDROOM_NUM.isna().sum()), 2814),
        ("of which Residential Land",
         int((raw[raw.BEDROOM_NUM.isna()].PROPERTY_TYPE == "Residential Land").sum()), 2806),
        ("relations", len(ALL_RELATIONS), 12),
        ("families 5/5/2",
         tuple(sum(1 for m in ALL_RELATIONS if m.family == f)
               for f in ("invariance","monotonic","directional")), (5, 5, 2)),
        ("locality base inputs", len(inputs), 36),
        ("seeds", list(SEEDS), [11, 23, 47]),
        ("sufficiency threshold", MIN_SUFFICIENT_N, 50),
        ("runs per LLM sweep (pre-v2)", meta["total_runs"], 1188),
        ("determinism probe trials", probe["trials"], 20),
        ("determinism distinct outputs", probe["distinct_outputs"], 1),
        ("LLM calls (post-fix)", meta["llm"]["llm_calls"], 14209),
        ("LLM fallback rate (post-fix)", meta["llm"]["llm_fallback_rate"], 0.0874),
        ("model name hash (committed LLM sweep)", meta["llm"]["model_tag_sha256"], "d7f5d340f8953384"),
    ]

    # Coordinate coverage, age-on-site and concentration, as quoted in
    # DESIGN/REPORT, are stated over price-valid listings.
    frame = frame[frame.price_valid]
    checks.append(("coordinate coverage %",
                   round(frame.latitude.notna().mean() * 100, 1), 94.7))
    checks.append(("median age on site (days)",
                   int(frame.age_on_site_days.median()), 36))

    # Share of the window's listings in its final six months.
    window = [f"2022-{m:02d}" for m in (9, 10, 11, 12)] + \
             [f"2023-{m:02d}" for m in range(1, 9)]
    inw = frame[frame.month.isin(window)]
    last6 = inw[inw.month.isin(window[-6:])]
    checks.append(("final six months share %",
                   round(len(last6) / len(inw) * 100, 1), 96.4))

    # Violation rates quoted in the documents.
    for mr, d, p, q in [("I4", 0.000, 0.630, 0.000), ("I3", 0.000, 0.417, 0.176),
                        ("I2", 0.000, 0.028, 0.000), ("D2", 0.000, 0.556, 0.593),
                        ("D1", 0.000, 0.222, 0.667), ("M1", 0.139, 0.222, 0.333),
                        ("M1raw", 0.861, 0.852, 0.806)]:
        checks.append((f"{mr} deterministic", round(det.loc[mr,"violation_rate"],3), d))
        checks.append((f"{mr} LLM pre-fix",  round(pre.loc[mr,"violation_rate"],3), p))
        checks.append((f"{mr} LLM post-fix", round(summary.loc[mr,"violation_rate"],3), q))

    # I3's residual: the 2x2 of prompt difference against actual violation,
    # quoted in DIAGNOSIS (formerly REPORT §8.5). An earlier draft claimed the
    # correlation was "exact"; this asserts the real, one-directional shape so
    # the claim cannot drift from the evidence again.
    i3 = Path("results/diagnosis/i3_prompt_vs_violation.csv")
    checks.append(("I3 prompt/violation evidence retained", i3.exists(), True))
    if i3.exists():
        c = pd.read_csv(i3)
        same = c[~c.prompt_differs]
        diff = c[c.prompt_differs]
        checks.append(("I3 cells compared", len(c), 108))
        checks.append(("I3 identical-prompt cells", len(same), 51))
        checks.append(("I3 violations when prompt identical",
                       int(same.violated.sum()), 0))
        checks.append(("I3 differing-prompt cells", len(diff), 57))
        checks.append(("I3 violations when prompt differs",
                       int(diff.violated.sum()), 19))
        per = c.groupby("base_input").violated.sum()
        checks.append(("I3 base inputs violating", int(per.gt(0).sum()), 11))
        checks.append(("I3 base inputs failing on all 3 seeds",
                       sorted(per[per == 3].index.tolist()),
                       ["base22", "base23", "base30", "base31"]))
        checks.append(("I3 base inputs failing on 1 of 3 seeds",
                       sorted(per[per == 1].index.tolist()),
                       ["base11", "base17", "base24", "base27",
                        "base32", "base33", "base35"]))

    # Threshold sensitivity, the headline caveat.
    at50 = sens[sens.min_sufficient_n == 50].headline_pct.iloc[0]
    checks.append(("headline at n>=50 %", round(at50, 2), -6.41))
    spread = sens.headline_pct.max() - sens.headline_pct.min()
    checks.append(("sensitivity spread (pp)", round(spread, 1), 93.6))
    checks.append(("sensitivity sign flips",
                   bool((sens.headline_pct > 0).any() and (sens.headline_pct < 0).any()), True))

    # The external cross-check, quoted in REPORT §9 and DESIGN §5.
    at75 = sens[sens.min_sufficient_n == 75].headline_pct.iloc[0]
    checks.append(("headline at n>=75 %", round(at75, 2), 7.08))
    residex = Path("results/residex/cross_check.md")
    checks.append(("RESIDEX evidence retained", residex.exists(), True))
    checks.append(("RESIDEX PDF retained",
                   Path("results/residex/Press_Release_July-September_2023.pdf").exists(), True))
    if residex.exists():
        checks.append(("RESIDEX Hyderabad figure quoted",
                       "+6.8%" in residex.read_text(encoding="utf-8"), True))

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

    # Figures quoted inside source files, which the prose scan does not read.
    print("\nFigures quoted in source files:")
    six = round(len(last6) / len(inw) * 100, 1)
    n_rel = len(ALL_RELATIONS)
    words = {9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}
    patterns = [
        (re.compile(r"(\d{2}(?:\.\d)?)% of the window"),
         f"{six}", "final six months share"),
        (re.compile(r"^\"\"\"The metamorphic relation catalogue\. (\w+) relations",
                    re.M), words.get(n_rel, "?"), "relation count in words"),
        # The v2 sweep: 36 locality + 36 radius base inputs.
        (re.compile(r"\*\*(\d+) relations \u00d7 72 base inputs"),
         str(n_rel), "relation count in the repro command"),
        (re.compile(r"72 base inputs \u00d7 3 seeds = ([\d,]+) runs"),
         f"{n_rel * 72 * 3:,}", "runs per sweep"),
    ]
    for src in SOURCES:
        text = Path(src).read_text(encoding="utf-8")
        for rx, want, label in patterns:
            for got in rx.findall(text):
                ok = got == want
                print(f"  {src:<22}{label:<28}{got!r} "
                      f"{'ok' if ok else 'STALE, want ' + want!r}")
                if not ok:
                    failures.append((f"{src} {label}", got, want))

    # Cross-document consistency: no stale agent names anywhere.
    stale = re.compile(r"ScanAgent|AnomalySentinel|CriteriaPlanner|TrendAggregator"
                       r"|CoverageAuditor|NarrativeAgent|cycle C[12]")
    print("\nStale agent/cycle names in documents:")
    bad = 0
    # The UI text is user-facing too: app.py carried "CoverageAuditor" and
    # "CriteriaPlanner" after the rename because only DOCS were scanned.
    for doc in DOCS + ["app.py"]:
        hits = len(stale.findall(Path(doc).read_text(encoding="utf-8")))
        bad += hits
        print(f"  {doc:<22}{hits}")
    failures.append(("stale names", bad, 0)) if bad else None

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
