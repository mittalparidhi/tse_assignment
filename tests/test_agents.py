# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: tests for widening and set inclusion,
# NEEDS_REVIEW, rejection accounting, stable counts. Lines by git blame: Vidhi
# Jain 57%, Paridhi Mittal 43%. Full attribution: CREDITS.md.
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
    # Design note §4.3.4: at most two retries; below target the run proceeds
    # with LIMITED coverage instead of looping or inventing data.
    cfg = GraphConfig()
    assert state["retry_count"] <= cfg.max_retry_rounds == 2
    met = scores[-1] >= cfg.coverage_target
    assert state["coverage_verdict"] == ("ACCEPT" if met else "LIMITED")
    assert state["relax_levers"][0] == "geography"      # note's lever order
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
    assert with_aug["final_report"].provenance["contract_version"] == "2.1.0-draft"
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
    # Rejected listings lose their price but stay listings (note §2).
    raw_valid = int(state["raw_listings"]["price_valid"].sum())
    assert state["n_rejected_outliers"] == raw_valid - report.n_price_valid_total
    assert report.n_listings_total == len(state["raw_listings"])


def test_critique_inspects_the_listings_the_report_was_built_from(frame, graph):
    state = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                         graph=graph)
    analysed = state["analysed_listings"]
    assert len(analysed) == state["final_report"].n_listings_total
    assert int(analysed["price_valid"].sum()) == (
        int(state["raw_listings"]["price_valid"].sum()) - state["n_rejected_outliers"])


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


def test_merge_returns_exactly_the_current_rounds_matches(frame, graph):
    """contracts/Retrieval.md §3: after cycle 1 widens the query, the merged
    listings are exactly what the widened criteria select -- no leftovers
    from an earlier, narrower round and no twins of a repeated PROP_ID."""
    state = run_pipeline(frame, NARROW, seed=7, graph=graph)
    assert state["retry_count"] > 0
    spec = state["widened_filter_spec"]
    expected = apply_criteria(frame, spec)
    expected = expected[expected["month"].isin(
        state["final_report"].window_months)]
    merged = state["raw_listings"]
    assert merged["listing_id"].is_unique
    assert set(merged["listing_id"]) == set(expected["listing_id"])


def test_geography_widening_preserves_set_inclusion(frame):
    """contracts/Coverage.md §3: if A is a subset of B, widen(A) must be a
    subset of widen(B). The shared-centre rule broke this and MR M3 caught it
    (9/36 base inputs); each locality now brings its own neighbourhood."""
    from src.agents.nodes import _relax_geography
    from src.mr.base_inputs import generate_base_inputs
    checked = 0
    for base in generate_base_inputs(frame):
        full = base.localities
        half = full[: max(1, len(full) // 2)]
        big = _relax_geography(base, frame)
        small = _relax_geography(base.with_(localities=half), frame)
        assert big is not None and small is not None
        assert set(small[0].localities) <= set(big[0].localities), base.label
        checked += 1
    assert checked >= 30

    # Beyond the M3 halves: arbitrary subsets of a deep-locality set.
    import random
    rng = random.Random(11)
    pool = frame["locality"].value_counts().index[:12].tolist()
    for _ in range(40):
        big_set = tuple(rng.sample(pool, rng.randint(2, 8)))
        small_set = tuple(rng.sample(big_set, rng.randint(1, len(big_set))))
        spec = Criteria(window_end="2023-08", localities=big_set)
        big = _relax_geography(spec, frame)
        small = _relax_geography(spec.with_(localities=small_set), frame)
        assert set(small[0].localities) <= set(big[0].localities)


def test_spent_critique_cap_is_reported_as_needs_review(frame, graph):
    """Design note §4.3.7: an unresolved complaint is labelled NEEDS_REVIEW,
    never silently accepted."""
    state = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                         config=GraphConfig(max_critique_rounds=0),
                         graph=build_graph())
    assert state["critique_verdict"] == "NEEDS_REVIEW"
    assert state["final_report"].provenance["review_status"] == "NEEDS_REVIEW"
    assert "NEEDS_REVIEW" in state["narrative"]
    normal = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11, graph=graph)
    assert normal["final_report"].provenance["review_status"] == "APPROVED"


def test_listing_count_is_stable_under_outlier_rejection(frame, graph):
    """Rejected listings lose their price, not their place in listing_count."""
    on = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11, graph=graph)
    off = run_pipeline(frame, Criteria(window_end="2023-08"), seed=11,
                       config=GraphConfig(max_critique_rounds=0), graph=build_graph())
    assert on["n_rejected_outliers"] > 0
    assert on["final_report"].count_series() == off["final_report"].count_series()
    assert (sum(off["final_report"].valid_count_series())
            - sum(on["final_report"].valid_count_series())) == on["n_rejected_outliers"]
