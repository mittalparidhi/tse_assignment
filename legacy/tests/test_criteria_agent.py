# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.criteria_agent import (
    CriteriaAgent,
    CriteriaValidationError,
    FilterSpec,
    QueryMode,
    SourceCatalog,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "hyderabad.csv"
EXAMPLES = ROOT / "examples" / "criteria_requests.json"


@pytest.fixture(scope="module")
def agent() -> CriteriaAgent:
    return CriteriaAgent(catalog=SourceCatalog.from_csv(SOURCE))


def test_at_least_ten_example_requests_produce_typed_filter_specs_and_modes(agent):
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    assert len(examples) >= 10
    assert len({entry["id"] for entry in examples}) == len(examples)
    modes = set()
    for entry in examples:
        result = agent.run(entry["request"])
        assert isinstance(result.filter_spec, FilterSpec)
        assert isinstance(result.query_mode, QueryMode)
        assert result.filter_spec.source_period.start_month == "2022-09"
        assert result.filter_spec.source_period.end_month == "2023-08"
        assert len(result.filter_spec.source_period.months) == 12
        modes.add(result.query_mode)
    assert modes == {QueryMode.EXACT_LOCALITY, QueryMode.GEO_RADIUS}


def test_locality_mode_is_inferred_and_values_are_canonical(agent):
    result = agent.run({"city": "hYdErAbAd", "locality": " gachibowli ", "bhk": [3, 2, 3]})
    assert result.query_mode is QueryMode.EXACT_LOCALITY
    assert result.filter_spec.city == "Hyderabad"
    assert result.filter_spec.localities == ("Gachibowli",)
    assert result.filter_spec.bhk == (2, 3)


def test_geo_radius_requires_one_source_known_center(agent):
    result = agent.run({"city": "Hyderabad", "locality": "Kondapur", "geo_radius_km": 4})
    assert result.query_mode is QueryMode.GEO_RADIUS
    assert result.filter_spec.geo_radius_km == 4.0
    with pytest.raises(CriteriaValidationError, match="ambiguous_geo_radius_center"):
        agent.run({"city": "Hyderabad", "localities": ["Kondapur", "Miyapur"], "geo_radius_km": 4})


@pytest.mark.parametrize("request_case", [
    {"city": "Hyderabad", "locality": "Gachibowli", "min_price_inr": 9000000, "max_price_inr": 5000000},
    {"city": "Hyderabad", "locality": "Gachibowli", "min_price_inr": -1},
    {"city": "Hyderabad", "locality": "Gachibowli", "max_price_inr": 0},
    {"city": "Hyderabad", "locality": "Gachibowli", "min_price_inr": float("nan")},
])
def test_invalid_price_bands_are_rejected(agent, request_case):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run(request_case)
    assert error.value.code in {"invalid_price", "invalid_price_range"}


def test_unsupported_calendar_window_is_rejected_explicitly(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "start_month": "2023-01", "end_month": "2023-12"})
    assert error.value.code == "unsupported_date_window"


def test_incomplete_or_malformed_calendar_window_is_rejected(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "start_month": "2022-09"})
    assert error.value.code == "incomplete_date_window"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "start_month": "2022/09", "end_month": "2023-08"})
    assert error.value.code == "invalid_date_format"


def test_city_locality_and_property_type_are_source_validated(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Bengaluru", "locality": "Gachibowli"})
    assert error.value.code == "unsupported_city"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Secunderabad", "locality": "Gachibowli"})
    assert error.value.code == "unsupported_locality"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "property_type": "Castle"})
    assert error.value.code == "unsupported_property_type"


def test_bhk_is_integer_and_in_supported_source_domain(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "bhk": 2.5})
    assert error.value.code == "invalid_bhk"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "bhk": 77})
    assert error.value.code == "unsupported_bhk"


def test_query_mode_conflicts_are_rejected(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "query_mode": "GEO_RADIUS"})
    assert error.value.code == "query_mode_mismatch"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "geo_radius_km": 5, "query_mode": "EXACT_LOCALITY"})
    assert error.value.code == "query_mode_mismatch"


def test_geographic_scope_radius_and_unknown_fields_are_explicit(agent):
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad"})
    assert error.value.code == "missing_geographic_scope"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "geo_radius_km": 0})
    assert error.value.code == "invalid_geo_radius"
    with pytest.raises(CriteriaValidationError) as error:
        agent.run({"city": "Hyderabad", "locality": "Gachibowli", "radius": 5})
    assert error.value.code == "unknown_request_fields"


def test_report_serialization_has_typed_values_and_inr_names(agent):
    result = agent.run({
        "city": "Hyderabad", "locality": "Gachibowli", "bhk": 2,
        "property_type": "residential apartment", "min_price_inr": 5000000,
        "max_price_inr": 10000000,
    })
    payload = result.to_dict()
    assert payload["query_mode"] == "EXACT_LOCALITY"
    assert payload["filter_spec"]["city"] == "Hyderabad"
    assert payload["filter_spec"]["min_price_inr"] == 5000000
    assert payload["filter_spec"]["source_period"]["months"][0] == "2022-09"
    assert payload["filter_spec"]["source_period"]["months"][-1] == "2023-08"
