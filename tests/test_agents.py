"""The agent graph: cycles must be real, must fire, and must terminate.

Mapped to the brief's three control-flow requirements:
  (a) feedback loop            -> cycle 2, Critique -> Analysis
  (b) conditional/iterative    -> cycle 1, Coverage -> Retrieval
  (c) genuine dependency       -> Criteria sets query_mode, Retrieval switches
                                  algorithm
"""

import numpy as np
import pytest

from src.agents import AgentMode, GraphConfig, build_graph, run_pipeline
from src.agents.nodes import _robust_z, _outlier_mask, shard_of
from src.loading import load_canonical
from src.trend import Criteria, apply_criteria, haversine_km


@pytest.fixture(scope="module")
def frame():
    return load_canonical()[0]


@pytest.fixture(scope="module")
def graph():
    return build_graph()


#: A deliberately narrow query: Gachibowli 3BHK is too thin to answer, so the
#: Coverage agent must widen and re-retrieve.
NARROW = Criteria(window_end="2023-08", bhk=(3,),
                  localities=("Gachibowli",), label="test-narrow")


# ---------------------------------------------------------------- cycle 1

def test_cycle1_coverage_to_retrieval_fires(frame, graph):
    """(b) conditional/iterative control step."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert state["retry_count"] > 0, "the coverage retry loop never fired"
    assert any("cycle 1" in str(e.get("decision", "")) for e in state["trace"])


def test_cycle1_improves_coverage_until_target_met_or_levers_exhausted(frame, graph):
    """Coverage never goes backwards, and the loop stops only when the target
    is met or no lever can widen further (contracts/Coverage.md §2). Since
    geography widening keeps a locality constraint, a narrow query can end
    below target: the answer stays about the place the user asked for."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    scores = [e["coverage_score"] for e in state["trace"]
              if e["agent"] == "CoverageAgent"]
    assert scores == sorted(scores), f"coverage went backwards: {scores}"
    assert scores[-1] > scores[0], "widening did not add depth"
    met = scores[-1] >= GraphConfig().coverage_target
    exhausted = state["relax_levers"] == ["bhk", "geography"]
    assert met or exhausted
    assert "Gachibowli" in state["final_report"].criteria["localities"]


def test_geography_widening_adds_nearest_localities_not_the_whole_metro(frame, graph):
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    widened = state["final_report"].criteria["localities"]
    assert widened[0] == "Gachibowli" and len(widened) > 1
    assert state["final_report"].n_listings_total < len(frame) / 2


def test_cycle1_relaxations_are_recorded_not_silent(frame, graph):
    """A user reading a widened trend must be told the question changed."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert state["relaxations"]
    assert state["final_report"].provenance["relaxations"] == state["relaxations"]


def test_cycle1_advances_levers_instead_of_starving_them(frame, graph):
    """Regression: BHK can always widen by +-1, and once starved the geography
    filter -- the binding constraint -- was never relaxed, stalling coverage."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert "geography" in state["relax_levers"]


# ---------------------------------------------------------------- cycle 2

def test_cycle2_critique_to_analysis_fires(frame, graph):
    """(a) feedback loop: a downstream agent sends work back upstream."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert state["critique_rounds"] > 0, "the critique loop never fired"
    assert any("cycle 2" in str(e.get("decision", "")) for e in state["trace"])


def test_cycle2_complaint_names_the_months_at_fault(frame, graph):
    """The loop's payload must be specific, or Analysis cannot target it."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    recompute = [e for e in state["trace"]
                 if e["agent"] == "AnalysisAgent"
                 and e.get("mode") == "targeted recomputation"]
    assert recompute, "Analysis never performed a targeted recomputation"
    assert recompute[0]["recomputed_months"], "recomputation had no target"


def test_cycle2_changes_the_answer_so_it_is_not_decorative(frame, graph):
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert state["n_rejected_outliers"] > 0


# ------------------------------------------------- (c) genuine dependency

def test_query_mode_selects_a_different_algorithm(frame):
    """EXACT_LOCALITY and RADIUS must not be interchangeable."""
    exact = Criteria(window_end="2023-08", localities=("Gachibowli",))
    radius = Criteria(window_end="2023-08", query_mode="RADIUS",
                      center_lat=17.4401, center_lon=78.3489, radius_km=3.0)
    a = set(apply_criteria(frame, exact)["listing_id"])
    b = set(apply_criteria(frame, radius)["listing_id"])
    assert a and b
    assert a != b, "the two retrieval algorithms returned identical sets"


def test_radius_retrieval_is_monotone_in_radius(frame):
    sizes = []
    for km in (1.0, 2.0, 5.0, 10.0, 25.0):
        c = Criteria(window_end="2023-08", query_mode="RADIUS",
                     center_lat=17.4401, center_lon=78.3489, radius_km=km)
        sizes.append(len(apply_criteria(frame, c)))
    assert sizes == sorted(sizes), f"not monotone: {sizes}"


def test_radius_excludes_rows_without_coordinates(frame):
    """A radius query is a claim about geography; a row with no location
    cannot satisfy it, and keeping such rows would make a tight radius return
    the whole city."""
    c = Criteria(window_end="2023-08", query_mode="RADIUS",
                 center_lat=17.4401, center_lon=78.3489, radius_km=2.0)
    got = apply_criteria(frame, c)
    assert got["latitude"].notna().all()


def test_radius_requires_a_centre(frame):
    c = Criteria(window_end="2023-08", query_mode="RADIUS", radius_km=5.0)
    with pytest.raises(ValueError, match="center_lat"):
        apply_criteria(frame, c)


def test_haversine_against_known_distance():
    """Hyderabad (17.3850, 78.4867) to Bengaluru (12.9716, 77.5946) is ~500 km."""
    d = haversine_km(17.3850, 78.4867,
                     np.array([12.9716]), np.array([77.5946]))[0]
    assert 490 < d < 520, d


# ------------------------------------------------------------ robustness

def test_graph_terminates_under_an_unsatisfiable_target(frame, graph):
    state = run_pipeline(frame, NARROW, seed=7, graph=graph,
                         config=GraphConfig(coverage_target=1.0))
    assert state["final_report"] is not None
    assert state["retry_count"] <= GraphConfig().max_retry_rounds


def test_answer_is_independent_of_retrieval_agent_count(frame):
    """The fault the id-relabelling relation exposed: the number of
    cooperating agents is not a property of the housing market and must not
    change the answer."""
    totals = set()
    for n in (1, 2, 4, 8):
        cfg = GraphConfig(n_retrieval_agents=n)
        state = run_pipeline(frame, NARROW, seed=7,
                             graph=build_graph(n), config=cfg)
        totals.add(state["final_report"].n_listings_total)
    assert len(totals) == 1, f"answer varied with agent count: {totals}"


def test_pipeline_is_deterministic_for_a_fixed_seed(frame, graph):
    a = run_pipeline(frame, NARROW, seed=7, graph=graph)
    b = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert a["final_report"].psf_series() == b["final_report"].psf_series()
    assert a["final_report"].count_series() == b["final_report"].count_series()


def test_shard_assignment_is_stable_across_processes():
    """Uses sha256, not Python's randomised hash -- otherwise the relabelling
    relation would report violations caused by PYTHONHASHSEED."""
    assert shard_of("Z70135726", 11, 4) == shard_of("Z70135726", 11, 4)
    assert 0 <= shard_of("Z70135726", 11, 4) < 4


def test_robust_z_is_unmoved_by_an_extreme_outlier():
    """MAD, not standard deviation: the contaminating point must not set the
    threshold that is meant to catch it."""
    clean = np.array([5000., 5500., 6000., 6500., 7000.])
    z = _robust_z(np.append(clean, 800_000.))
    assert abs(z[-1]) > 3.5
    assert all(abs(v) < 3.5 for v in z[:-1])


def test_default_mode_is_deterministic():
    """The committed result sets and the test suite both depend on this."""
    assert GraphConfig().agent_mode == AgentMode.DETERMINISTIC


def test_narrative_flags_the_partial_month_only_when_in_window(frame, graph):
    """contracts/Aggregator.md §2.4: August 2023 is never presented as a full
    month."""
    with_aug = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                            graph=graph)
    without = run_pipeline(frame, Criteria(window_end="2023-07"), seed=11,
                           graph=graph)
    assert "2023-08 is a partial month" in with_aug["narrative"]
    assert "partial month" not in without["narrative"]
    assert with_aug["final_report"].provenance["contract_version"] == "2.0.0-draft"
    assert with_aug["final_report"].provenance["snapshot_sha256"].startswith("9e8169")


def test_rejected_count_is_not_summed_across_critique_rounds(frame):
    """contracts/Analysis.md §5: each recomputation starts from raw_listings,
    so the reported count is that pass's count, and it must equal the
    listings actually missing from the report."""
    config = GraphConfig(max_critique_rounds=2)
    state = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                         config=config, graph=build_graph())
    report = state["final_report"]
    assert state["critique_rounds"] >= 1
    assert state["n_rejected_outliers"] == (
        len(state["raw_listings"]) - report.n_listings_total)


def test_critique_inspects_the_listings_the_report_was_built_from(frame, graph):
    state = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                         graph=graph)
    analysed = state["analysed_listings"]
    assert len(analysed) == state["final_report"].n_listings_total
    assert len(analysed) == len(state["raw_listings"]) - state["n_rejected_outliers"]


def test_no_coordinate_count_respects_the_criteria(frame, graph):
    """contracts/Retrieval.md §4: only rows a radius query had to exclude."""
    radius = Criteria(window_end="2023-08", bhk=(3,), query_mode="RADIUS",
                      center_lat=17.44, center_lon=78.35, radius_km=5.0)
    state = run_pipeline(frame, radius, seed=11, graph=graph)
    # Cycle 1 may have widened BHK; the count follows the effective criteria.
    spec = state["widened_filter_spec"] or radius
    window = frame[frame["month"].isin(
        state["final_report"].window_months)]
    expected = int(window[window["bhk"].isin(spec.bhk)]["latitude"].isna().sum())
    assert state["n_no_coordinate"] == expected
    assert expected < int(window["latitude"].isna().sum())
