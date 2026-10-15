"""Golden regression tests: the deterministic numbers must not move.

Phase A renames agents, rebuilds cycle 2 and adds an LLM path. All of that is
structural; none of it may change what the deterministic pipeline computes,
because ``results/before_fix/`` and ``results/after_fix/`` -- the evidence
behind the entire root-cause analysis -- were produced by it.

The fixtures are pinned at the level of the reported *series*, not dataclass
field names, so they survive the contract rename and still prove the numbers
are identical. They change only through ``scripts/regenerate_golden.py`` for a
reviewed contract change, which records old and new values and the reason in
``_corrections`` (``contracts/Golden.md`` §4). Regenerating them to make a
failing test pass would defeat the purpose.
"""

import json
from pathlib import Path

import pytest

from src.agents import build_graph, run_pipeline
from src.loading import load_canonical
from src.mr.base_inputs import generate_base_inputs
from src.trend import Criteria, compute_trend

GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "deterministic_baseline.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def frame():
    return load_canonical()[0]


@pytest.fixture(scope="module")
def graph():
    return build_graph()


def _series_eq(actual, expected, label):
    assert len(actual) == len(expected), f"{label}: length changed"
    for i, (a, e) in enumerate(zip(actual, expected)):
        if a is None or e is None:
            assert a == e, f"{label}[{i}]: {a} != {e}"
        else:
            assert a == pytest.approx(e, rel=1e-12), f"{label}[{i}]: {a} != {e}"


TREND_CASES = {
    "all": Criteria(window_end="2023-08", label="all"),
    "bhk3": Criteria(window_end="2023-08", bhk=(3,), label="bhk3"),
    "banded": Criteria(window_end="2023-07", price_min_inr=5e6,
                       price_max_inr=2e7, label="banded"),
    "lakh": Criteria(window_end="2023-08", currency_unit="INR_LAKH",
                     area_unit="SQM", label="lakh"),
}


@pytest.mark.parametrize("label", sorted(TREND_CASES))
def test_trend_computation_unchanged(frame, label):
    want = GOLDEN[f"trend::{label}"]
    got = compute_trend(frame, TREND_CASES[label])
    _series_eq(got.psf_series(), want["psf"], f"{label}.psf")
    _series_eq(got.min_price_series(), want["min_price"], f"{label}.min_price")
    _series_eq(got.max_price_series(), want["max_price"], f"{label}.max_price")
    assert [m.is_partial_month for m in got.monthly] == want["partial"]
    _series_eq(got.pct_change_series(), want["pct"], f"{label}.pct")
    assert got.count_series() == want["counts"]
    assert got.ranking_order() == want["ranking"]
    assert got.n_listings_total == want["total"]
    assert got.yoy_span_months == want["span"]
    assert got.sufficient_months() == want["sufficient_months"]
    if want["yoy"] is None:
        assert got.yoy_median_psf_pct is None
    else:
        assert got.yoy_median_psf_pct == pytest.approx(want["yoy"], rel=1e-12)


def _pipeline_cases(frame):
    inputs = generate_base_inputs(frame)
    return {
        "narrow": (Criteria(window_end="2023-08", bhk=(3,),
                            localities=("Gachibowli",), label="narrow"), 7),
        "base00": (inputs[0], 11),
        "base05": (inputs[5], 23),
    }


@pytest.mark.parametrize("label", ["narrow", "base00", "base05"])
def test_agent_pipeline_unchanged(frame, graph, label):
    """The deterministic agent graph must produce identical output.

    This is the test that protects the committed result sets through the
    agent rename and the cycle-C2 rebuild.
    """
    criteria, seed = _pipeline_cases(frame)[label]
    want = GOLDEN[f"pipeline::{label}"]
    state = run_pipeline(frame, criteria, seed=seed, graph=graph)
    report = state["final_report"]

    _series_eq(report.psf_series(), want["psf"], f"{label}.psf")
    assert report.count_series() == want["counts"]
    assert report.ranking_order() == want["ranking"]
    assert report.n_listings_total == want["total"]
    assert report.yoy_span_months == want["span"]
    if want["yoy"] is None:
        assert report.yoy_median_psf_pct is None
    else:
        assert report.yoy_median_psf_pct == pytest.approx(want["yoy"], rel=1e-12)

    # Control flow must be unchanged too, not just the numbers. The state
    # keys were renamed to the design note's vocabulary in Phase A; the
    # fixture keys keep their original names and the VALUES must match, which
    # is the whole point of the comparison.
    assert state["retry_count"] == want["widen_rounds"]
    assert state["critique_rounds"] == want["critique_rounds"]
    assert state["n_rejected_outliers"] == want["n_rejected_outliers"]
    assert state["coverage_score"] == pytest.approx(want["coverage"], rel=1e-12)
    assert state["relaxations"] == want["relaxations"]
