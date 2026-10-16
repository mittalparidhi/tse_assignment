# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
"""How much the headline move depends on the sufficiency threshold.

    python scripts/threshold_sensitivity.py [--out results/v2_sensitivity]

The headline ``yoy_median_psf_pct`` compares the first and last *sufficient*
month, so the threshold that defines "sufficient" decides which months are
compared. This sweeps the threshold over the whole-metro default query
(window ending 2023-08, no agents: the statistics alone) and records, for
each value, the sufficient months, the endpoints, the span and the headline.

REPORT.md §9 relies on this table. It was first committed as
``results/sensitivity/threshold_sensitivity.csv`` without the script that
produced it; this script regenerates it, so the claim can be re-derived.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd                                    # noqa: E402

from src.contract import DEFAULT_WINDOW_END            # noqa: E402
from src.loading import load_canonical                 # noqa: E402
from src.trend import Criteria, compute_trend          # noqa: E402

THRESHOLDS = (10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 300)


def sweep(frame: pd.DataFrame, window_end: str = DEFAULT_WINDOW_END) -> pd.DataFrame:
    rows = []
    for n in THRESHOLDS:
        report = compute_trend(frame, Criteria(window_end=window_end),
                               min_sufficient_n=n)
        sufficient = report.sufficient_months()
        rows.append({
            "min_sufficient_n": n,
            "sufficient_months": len(sufficient),
            "first_sufficient": sufficient[0] if sufficient else None,
            "last_sufficient": sufficient[-1] if sufficient else None,
            "span_months": report.yoy_span_months,
            "headline_pct": report.yoy_median_psf_pct,
        })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="results/v2_sensitivity",
                        help="output folder (the pre-v2 table lives in "
                             "results/sensitivity and is left untouched)")
    args = parser.parse_args()
    frame, _ = load_canonical()
    table = sweep(frame)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "threshold_sensitivity.csv", index=False,
                 lineterminator="\n")
    print(table.to_string(index=False))
    moves = table.headline_pct.dropna()
    print(f"\nspread {moves.max() - moves.min():.1f} pp; "
          f"sign flips: {bool((moves > 0).any() and (moves < 0).any())}")
    print(f"written to {out}/threshold_sensitivity.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
