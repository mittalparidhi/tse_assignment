"""Request validation (contracts/Criteria.md §3-4).

Ported from the first implementation's ``tests/test_criteria_agent.py``:
every rule rejects with its stable code, and valid requests come back as a
canonical ``Criteria``. City is no longer a field (both cities are always in
scope) and the window is movable, so those v1 cases became window-membership
and unknown-field cases.
"""

import pytest

from src.loading import load_canonical
from src.mr.base_inputs import generate_all_base_inputs
from src.validation import (
    CriteriaValidationError,
    SourceCatalog,
    criteria_as_request,
    validate_request,
)


@pytest.fixture(scope="module")
def frame():
    return load_canonical()[0]


@pytest.fixture(scope="module")
def catalog(frame):
    return SourceCatalog.from_frame(frame)


def _code(catalog, request):
    with pytest.raises(CriteriaValidationError) as error:
        validate_request(request, catalog)
    assert error.value.to_dict()["status"] == "error"
    return error.value.code


def test_empty_request_is_the_whole_metro_default_window(catalog):
    criteria = validate_request({}, catalog)
    assert criteria.window_end == "2023-08"
    assert criteria.localities is None and criteria.bhk is None
    assert criteria.query_mode == "EXACT_LOCALITY"


def test_locality_names_are_canonicalised_and_deduplicated(catalog, frame):
    name = frame["locality"].value_counts().index[0]
    messy = "  " + name.upper().replace(" ", "   ") + " "
    criteria = validate_request({"localities": [messy, name]}, catalog)
    assert criteria.localities == (name,)


def test_unknown_names_are_rejected_not_approximated(catalog):
    assert _code(catalog, {"localities": ["Gachibowlee"]}) == "unsupported_locality"
    assert _code(catalog, {"localities": ["Unknown"]}) == "unsupported_locality"
    assert _code(catalog, {"property_types": ["Residential Land"]}) == \
        "unsupported_property_type"


def test_unknown_fields_are_rejected_not_ignored(catalog):
    assert _code(catalog, {"city": "Hyderabad"}) == "unknown_request_fields"
    assert _code(catalog, ["window_end"]) == "invalid_request"


def test_window_must_be_a_snapshot_month(catalog):
    assert _code(catalog, {"window_end": "2023/08"}) == "invalid_date_format"
    assert _code(catalog, {"window_end": "2023-13"}) == "invalid_date_format"
    assert _code(catalog, {"window_end": "2024-01"}) == "unsupported_date_window"
    assert validate_request({"window_end": "2023-03"}, catalog).window_end == "2023-03"


def test_bhk_is_whole_and_in_the_source_domain(catalog):
    assert validate_request({"bhk": [3, 2, 3.0]}, catalog).bhk == (2, 3)
    assert _code(catalog, {"bhk": 2.5}) == "invalid_bhk"
    assert _code(catalog, {"bhk": True}) == "invalid_bhk"
    assert _code(catalog, {"bhk": [11]}) == "unsupported_bhk"


@pytest.mark.parametrize("request_case, code", [
    ({"price_min_inr": 0}, "invalid_price"),
    ({"price_max_inr": -5}, "invalid_price"),
    ({"price_min_inr": float("nan")}, "invalid_price"),
    ({"price_min_inr": "5000000"}, "invalid_price"),
    ({"price_min_inr": 9e6, "price_max_inr": 5e6}, "invalid_price_range"),
])
def test_invalid_price_bands_are_rejected(catalog, request_case, code):
    assert _code(catalog, request_case) == code


def test_units_come_from_the_allowed_sets(catalog):
    assert _code(catalog, {"currency_unit": "USD"}) == "unsupported_unit"
    assert _code(catalog, {"area_unit": "ACRE"}) == "unsupported_unit"


def test_radius_queries_need_a_valid_centre_and_radius(catalog):
    ok = validate_request(
        {"radius_km": 5, "center_lat": 17.44, "center_lon": 78.35}, catalog)
    assert ok.query_mode == "RADIUS" and ok.radius_km == 5.0
    assert _code(catalog, {"radius_km": 5}) == "missing_geo_center"
    assert _code(catalog, {"radius_km": 0, "center_lat": 17.44,
                           "center_lon": 78.35}) == "invalid_geo_radius"
    assert _code(catalog, {"radius_km": 101, "center_lat": 17.44,
                           "center_lon": 78.35}) == "invalid_geo_radius"
    assert _code(catalog, {"radius_km": 5, "center_lat": 28.6,
                           "center_lon": 77.2}) == "invalid_geo_center"


def test_query_mode_conflicts_are_rejected(catalog, frame):
    name = frame["locality"].value_counts().index[0]
    assert _code(catalog, {"query_mode": "RADIUS"}) == "query_mode_mismatch"
    assert _code(catalog, {"query_mode": "EXACT_LOCALITY", "radius_km": 5,
                           "center_lat": 17.44, "center_lon": 78.35}) == \
        "query_mode_mismatch"
    assert _code(catalog, {"localities": [name], "radius_km": 5,
                           "center_lat": 17.44, "center_lon": 78.35}) == \
        "query_mode_mismatch"
    assert _code(catalog, {"center_lat": 17.44, "center_lon": 78.35}) == \
        "query_mode_mismatch"


def test_every_harness_base_input_passes_validation(catalog, frame):
    """Testing.md §3: base inputs must be requests a user could make."""
    for base in generate_all_base_inputs(frame):
        assert validate_request(criteria_as_request(base), catalog) == base


def test_city_scope_is_a_validated_filter(catalog):
    """Design note §3: city is user-selectable; both cities by default."""
    assert validate_request({}, catalog).cities is None
    assert validate_request({"cities": ["secunderabad"]}, catalog).cities == ("Secunderabad",)
    assert _code(catalog, {"cities": ["Mumbai"]}) == "unsupported_city"


def test_locality_ids_and_the_geo_radius_name_are_accepted(catalog, frame):
    some_id = frame["locality_id"].dropna().iloc[0]
    assert validate_request({"localities": [some_id]}, catalog).localities == (some_id,)
    geo = validate_request({"query_mode": "GEO_RADIUS", "radius_km": 5,
                            "center_lat": 17.44, "center_lon": 78.35}, catalog)
    assert geo.query_mode == "RADIUS"
