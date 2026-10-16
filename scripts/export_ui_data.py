"""Export real pipeline results for the web UI (docs/LOVABLE_PROMPT_*.md).

Runs the deterministic agent pipeline on a fixed set of queries and writes
``results/ui/scenarios.json``: for each query the monthly series, the
headline, coverage, rankings, how the query was widened, the narrative, a
readable execution trace, and the same statistics **before** the critique's
targeted recomputation (cycle 2), so the UI can show what the feedback loop
changed. Every query passes request validation first.

    python scripts/export_ui_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import build_graph, run_pipeline  # noqa: E402
from src.loading import load_canonical  # noqa: E402
from src.trend import Criteria, compute_trend  # noqa: E402
from src.validation import SourceCatalog, criteria_as_request, validate_request  # noqa: E402

SEED = 7
OUT = Path("results/ui/scenarios.json")


def _scenarios(frame) -> list[tuple[str, str, Criteria]]:
    located = frame.dropna(subset=["latitude", "longitude"])
    centre = located.groupby("locality")[["latitude", "longitude"]].median()
    kondapur = centre.loc["Kondapur"]
    return [
        ("gachibowli-3bhk", "3 BHK · Gachibowli",
         Criteria(window_end="2023-08", bhk=(3,), localities=("Gachibowli",))),
        ("kondapur-2bhk", "2 BHK · Kondapur",
         Criteria(window_end="2023-08", bhk=(2,), localities=("Kondapur",))),
        ("kokapet-narsingi-3bhk", "3 BHK · Kokapet + Narsingi · ₹80 L–3 Cr",
         Criteria(window_end="2023-08", bhk=(3,), localities=("Kokapet", "Narsingi"),
                  price_min_inr=8_000_000.0, price_max_inr=30_000_000.0)),
        ("kollur-tellapur-2-3bhk", "2–3 BHK · Kollur + Tellapur · ₹40 L–1.5 Cr",
         Criteria(window_end="2023-08", bhk=(2, 3), localities=("Kollur", "Tellapur"),
                  price_min_inr=4_000_000.0, price_max_inr=15_000_000.0)),
        ("radius-financial-district-5km", "3 BHK · within 5 km of Financial District",
         Criteria(window_end="2023-08", bhk=(3,), query_mode="RADIUS",
                  center_lat=17.4401, center_lon=78.3489, radius_km=5.0)),
        ("radius-kondapur-3km", "All BHK · within 3 km of Kondapur",
         Criteria(window_end="2023-08", query_mode="RADIUS",
                  center_lat=float(kondapur.latitude), center_lon=float(kondapur.longitude),
                  radius_km=3.0)),
        ("secunderabad-all", "All BHK · Secunderabad",
         Criteria(window_end="2023-08", cities=("Secunderabad",))),
        ("metro-all", "All BHK · whole Hyderabad metro",
         Criteria(window_end="2023-08")),
    ]


def _num(x, nd=1):
    return None if x is None else round(float(x), nd)


def _monthly(report) -> list[dict]:
    return [{
        "month": m.month,
        "listing_count": m.listing_count,
        "price_valid_count": m.price_valid_count,
        "median_price_per_sqft_inr": _num(m.median_price_per_sqft_inr),
        "median_listing_price_inr": _num(m.median_listing_price_inr, 0),
        "coverage_status": m.coverage_status,
        "month_is_sufficient": bool(m.month_is_sufficient),
        "is_partial_month": bool(m.is_partial_month),
    } for m in report.monthly]


def _trace(entries) -> list[dict]:
    """A readable trace: one line per step that matters, with the cycle that fired."""
    out = []
    for e in entries:
        agent, cycle, detail = e["agent"], None, None
        if agent == "RetrievalMerge":
            detail = f"{e.get('agents')} agents, round {e.get('round')}: {e.get('listings')} listings"
        elif agent == "CoverageAgent":
            detail = (f"coverage {e.get('coverage_score', 0):.2f} "
                      f"({e.get('covered_months')} of {e.get('attainable_months')} attainable months)"
                      f" → {e.get('verdict')}")
            if e.get("relaxation"):
                detail += f": {str(e['relaxation']).split(':')[0]}"
            if "cycle 1" in str(e.get("decision", "")):
                cycle = 1
        elif agent == "AnalysisAgent":
            detail = f"{e.get('mode')}: move {e.get('move_pct')}%"
            if e.get("rejected_this_pass"):
                detail += f", {e['rejected_this_pass']} outliers rejected"
        elif agent == "CritiqueAgent":
            n_flag = len(e.get("flagged") or [])
            detail = f"{n_flag} month{'' if n_flag == 1 else 's'} flagged → {e.get('verdict')}"
            if "cycle 2" in str(e.get("decision", "")):
                cycle = 2
        elif agent == "AggregatorAgent" and "chars" in e:
            detail = "report assembled"
        elif agent == "CriteriaAgent":
            detail = f"planned: query mode {e.get('query_mode')}"
        if detail:
            out.append({"step": e["step"], "agent": agent, "detail": detail, "cycle": cycle})
    return out


def main() -> int:
    frame = load_canonical()[0]
    catalog = SourceCatalog.from_frame(frame)
    graph = build_graph()
    scenarios = []
    for sid, label, criteria in _scenarios(frame):
        criteria = validate_request(criteria_as_request(criteria), catalog)
        state = run_pipeline(frame, criteria, seed=SEED, graph=graph)
        report = state["final_report"]
        spec = state.get("widened_filter_spec") or state["filter_spec"]
        before = compute_trend(state["raw_listings"], spec)
        scenarios.append({
            "id": sid,
            "label": label,
            "criteria": criteria_as_request(criteria),
            "window_months": list(report.window_months),
            "monthly": _monthly(report),
            "yoy_median_psf_pct": _num(report.yoy_median_psf_pct, 2),
            "yoy_span_months": report.yoy_span_months,
            "n_listings_total": report.n_listings_total,
            "n_price_valid_total": report.n_price_valid_total,
            "coverage_score": _num(state.get("coverage_score"), 3),
            "coverage_verdict": report.provenance.get("coverage_verdict"),
            "review_status": report.provenance.get("review_status"),
            "n_rejected_outliers": state.get("n_rejected_outliers", 0),
            "locality_rankings": [r.locality for r in report.locality_rankings[:5]],
            "relaxations": [str(r).split(":")[0] for r in state.get("relaxations", [])],
            "narrative": state["narrative"],
            "trace": _trace(state["trace"]),
            "before_critique": {
                "monthly_median_price_per_sqft_inr":
                    [_num(m.median_price_per_sqft_inr) for m in before.monthly],
                "monthly_price_valid_count": [m.price_valid_count for m in before.monthly],
                "yoy_median_psf_pct": _num(before.yoy_median_psf_pct, 2),
                "yoy_span_months": before.yoy_span_months,
            },
        })
        print(f"{label:<45} move {scenarios[-1]['yoy_median_psf_pct']}% "
              f"(before critique {scenarios[-1]['before_critique']['yoy_median_psf_pct']}%), "
              f"{report.n_listings_total} listings, rejected {scenarios[-1]['n_rejected_outliers']}, "
              f"coverage {scenarios[-1]['coverage_verdict']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seed": SEED, "agent_mode": "DETERMINISTIC",
               "snapshot_sha256": frame.attrs.get("snapshot_sha256"),
               "scenarios": scenarios}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"written to {OUT} ({OUT.stat().st_size // 1024} KB)")

    # A compact copy, short enough to paste into a UI-builder prompt: one
    # shared month list, parallel arrays, coverage as its first letter.
    compact = {"months": scenarios[0]["window_months"], "seed": SEED, "scenarios": [{
        "id": s["id"], "label": s["label"], "criteria": s["criteria"],
        "listings": [m["listing_count"] for m in s["monthly"]],
        "price_valid": [m["price_valid_count"] for m in s["monthly"]],
        "psf": [m["median_price_per_sqft_inr"] for m in s["monthly"]],
        "price_lakh": [None if m["median_listing_price_inr"] is None
                       else round(m["median_listing_price_inr"] / 1e5, 2) for m in s["monthly"]],
        "coverage": [m["coverage_status"][0] for m in s["monthly"]],
        "sufficient": [int(m["month_is_sufficient"]) for m in s["monthly"]],
        "yoy_pct": s["yoy_median_psf_pct"], "span": s["yoy_span_months"],
        "n_total": s["n_listings_total"], "n_valid": s["n_price_valid_total"],
        "coverage_score": s["coverage_score"], "verdict": s["coverage_verdict"],
        "review": s["review_status"], "rejected": s["n_rejected_outliers"],
        "top_localities": s["locality_rankings"], "widened": s["relaxations"],
        "narrative": s["narrative"],
        "trace": [[t["step"], t["agent"], t["detail"], t["cycle"]] for t in s["trace"]],
        "before_critique": {"psf": s["before_critique"]["monthly_median_price_per_sqft_inr"],
                            "yoy_pct": s["before_critique"]["yoy_median_psf_pct"],
                            "span": s["before_critique"]["yoy_span_months"]},
    } for s in scenarios]}
    small = OUT.with_name("scenarios.min.json")
    small.write_text(json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n",
                     encoding="utf-8", newline="\n")
    print(f"written to {small} ({small.stat().st_size:,} bytes, for pasting into a prompt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
