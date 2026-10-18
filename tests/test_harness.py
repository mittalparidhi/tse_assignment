"""The harness itself must be trustworthy before its numbers mean anything."""

import math

import pytest

from src.mr.harness import wilson_ci
from src.mr.relations import ALL_RELATIONS


def test_three_families_are_all_represented():
    families = {mr.family for mr in ALL_RELATIONS}
    assert families == {"invariance", "monotonic", "directional"}


def test_at_least_eight_relations():
    assert len(ALL_RELATIONS) >= 8


def test_relation_ids_are_unique():
    ids = [mr.mr_id for mr in ALL_RELATIONS]
    assert len(ids) == len(set(ids))


def test_every_relation_documents_subdomain_tolerance_and_fault():
    """A relation without these is not falsifiable in the way the brief asks."""
    for mr in ALL_RELATIONS:
        assert mr.subdomain.strip(), f"{mr.mr_id} has no subdomain"
        assert mr.tolerance.strip(), f"{mr.mr_id} has no tolerance"
        assert mr.fault.strip(), f"{mr.mr_id} names no fault"


@pytest.mark.parametrize("k,n", [(0, 108), (1, 108), (54, 108), (108, 108)])
def test_wilson_interval_stays_inside_zero_one(k, n):
    """The reason Wilson was chosen over the normal approximation: rates at
    the boundaries are expected here, and the normal interval leaves [0,1]."""
    lo, hi = wilson_ci(k, n)
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_interval_has_width_even_at_zero_violations():
    lo, hi = wilson_ci(0, 108)
    assert lo == 0.0
    assert hi > 0.0, "a zero-width interval would overstate the evidence"


def test_wilson_interval_contains_the_point_estimate():
    for k, n in [(3, 50), (25, 100), (97, 100)]:
        lo, hi = wilson_ci(k, n)
        assert lo <= k / n <= hi


def test_wilson_interval_narrows_as_trials_grow():
    widths = [wilson_ci(n // 2, n)[1] - wilson_ci(n // 2, n)[0]
              for n in (20, 100, 1000)]
    assert widths[0] > widths[1] > widths[2]


def test_empty_trials_is_nan_not_a_crash():
    lo, hi = wilson_ci(0, 0)
    assert math.isnan(lo) and math.isnan(hi)


def test_radius_inputs_exercise_m4_on_at_least_thirty_bases():
    """contracts/Testing.md §3: the RADIUS algorithm is exercised by the
    relations, and M4 has >= 30 distinct applicable base inputs."""
    from src.loading import load_canonical
    from src.mr.base_inputs import generate_radius_inputs
    from src.mr.relations import BY_ID
    frame, _ = load_canonical()
    radius = generate_radius_inputs(frame)
    assert all(c.query_mode == "RADIUS" for c in radius)
    assert len({c.label for c in radius}) == len(radius) >= 30
    assert sum(BY_ID["M4"].applicable(frame, c) for c in radius) >= 30
    assert not any(BY_ID["M3"].applicable(frame, c) for c in radius)


# -- statistical unit and fault detection (contracts/Testing.md §6, §8) ------

def _runs(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["mr_id", "base_input", "seed",
                                       "applicable", "violated",
                                       "same_control_path"])


def test_seeds_collapse_into_one_outcome_per_base_input():
    from src.mr.harness import per_base_input, summarise
    runs = _runs([
        ("I1", "b0", 11, True, False, True), ("I1", "b0", 23, True, False, True),
        ("I1", "b1", 11, True, True, True), ("I1", "b1", 23, True, False, True),
        ("I1", "b2", 11, False, False, True),          # outside the subdomain
    ])
    bases = per_base_input(runs)
    assert len(bases) == 2                             # b2 is not applicable
    row = summarise(runs).set_index("mr_id").loc["I1"]
    assert (row.base_inputs, row.violations, row.seed_disagreements) == (2, 1, 1)
    assert row.violation_rate == 0.5
    assert (row.runs, row.run_violations) == (4, 1)


def test_zero_violations_over_36_bases_is_not_reported_as_108_trials():
    from src.mr.harness import summarise
    runs = _runs([("I1", f"b{i}", s, True, False, True)
                  for i in range(36) for s in (11, 23, 47)])
    row = summarise(runs).set_index("mr_id").loc["I1"]
    assert row.ci95_high == pytest.approx(wilson_ci(0, 36)[1])
    assert row.ci95_high > 0.09 > row.run_ci95_high


@pytest.fixture(scope="module")
def real_frame():
    from src.loading import load_canonical
    return load_canonical()[0]


def _detects(monkeypatch, frame, mr_id, broken_median):
    """Plant a fault in the statistics and run one relation over the first
    base inputs; a useful relation must report at least one violation."""
    from src.agents import build_graph
    from src.mr.base_inputs import generate_base_inputs
    from src.mr.harness import run_relation
    from src.mr.relations import BY_ID
    import src.trend as trend
    monkeypatch.setattr(trend, "_median", broken_median)
    graph = build_graph()
    return any(run_relation(BY_ID[mr_id], frame, c, 11, graph=graph).violated
               for c in generate_base_inputs(frame)[:6])


def test_reorder_relation_catches_order_dependent_aggregation(monkeypatch, real_frame):
    """A 'median' that just takes the first value depends on row order."""
    first = lambda values: float(values[0]) if values.size else None
    assert _detects(monkeypatch, real_frame, "I1", first)


def test_scaling_relation_catches_non_linear_aggregation(monkeypatch, real_frame):
    """A 'median' computed on log prices does not scale by k."""
    import numpy as np
    logged = lambda values: float(np.median(np.log(values))) if values.size else None
    assert _detects(monkeypatch, real_frame, "D2", logged)
