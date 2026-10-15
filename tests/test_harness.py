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
