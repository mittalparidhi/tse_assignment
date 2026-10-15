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
