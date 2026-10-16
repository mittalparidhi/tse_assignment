# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
"""Regenerate the golden vectors for a reviewed contract change.

    python scripts/regenerate_golden.py --reason "<why the numbers moved>"

Golden vectors are regression oracles (contracts/Golden.md). They may change
only for an intentional contract change, and every change is recorded: this
script recomputes each vector with the current code, writes it, and appends a
``_corrections`` entry per vector with the old and new totals and the reason.
Run the full test suite first and read the diff before committing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents import build_graph, run_pipeline           # noqa: E402
from src.loading import load_canonical                      # noqa: E402
from tests.test_golden import TREND_CASES, _pipeline_cases  # noqa: E402
from src.trend import compute_trend                         # noqa: E402

GOLDEN_PATH = ROOT / "tests" / "golden" / "deterministic_baseline.json"


def trend_vector(report) -> dict:
    return {
        "counts": report.count_series(),
        "valid_counts": report.valid_count_series(),
        "coverage": report.coverage_series(),
        "psf": report.psf_series(),
        "listing_price": report.listing_price_series(),
        "min_price": report.min_price_series(),
        "max_price": report.max_price_series(),
        "partial": [m.is_partial_month for m in report.monthly],
        "pct": report.pct_change_series(),
        "ranking": report.ranking_order(),
        "sufficient_months": report.sufficient_months(),
        "total": report.n_listings_total,
        "span": report.yoy_span_months,
        "yoy": report.yoy_median_psf_pct,
    }


def pipeline_vector(state) -> dict:
    report = state["final_report"]
    return {
        "counts": report.count_series(),
        "valid_counts": report.valid_count_series(),
        "psf": report.psf_series(),
        "ranking": report.ranking_order(),
        "total": report.n_listings_total,
        "review_status": report.provenance.get("review_status"),
        "coverage_verdict": state["coverage_verdict"],
        "span": report.yoy_span_months,
        "yoy": report.yoy_median_psf_pct,
        "coverage": state["coverage_score"],
        "relaxations": list(state["relaxations"]),
        "widen_rounds": state["retry_count"],
        "critique_rounds": state["critique_rounds"],
        "n_rejected_outliers": state["n_rejected_outliers"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reason", required=True,
                        help="the reviewed contract change that moved the numbers")
    args = parser.parse_args()

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    frame, _ = load_canonical()
    graph = build_graph()

    fresh: dict[str, dict] = {}
    for label, criteria in TREND_CASES.items():
        fresh[f"trend::{label}"] = trend_vector(compute_trend(frame, criteria))
    for label, (criteria, seed) in _pipeline_cases(frame).items():
        fresh[f"pipeline::{label}"] = pipeline_vector(
            run_pipeline(frame, criteria, seed=seed, graph=graph))

    corrections = golden.setdefault("_corrections", {})
    for key, new in fresh.items():
        old = golden.get(key, {})
        if old == new:
            continue
        # Never overwrite an earlier record: number repeated corrections.
        entry, n = f"{key}.total", 2
        while entry in corrections:
            entry, n = f"{key}.total#{n}", n + 1
        corrections[entry] = {
            "was": old.get("total"),
            "now": new["total"],
            "reason": args.reason,
        }
        golden[key] = new
        print(f"{key}: total {old.get('total')} -> {new['total']}")

    GOLDEN_PATH.write_text(
        json.dumps(golden, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
