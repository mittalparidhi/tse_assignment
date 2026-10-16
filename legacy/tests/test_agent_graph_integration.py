# Credits: Paridhi Mittal (first implementation, 11-12 Oct 2026). Full
# attribution: CREDITS.md.
from app.criteria_agent import CriteriaValidationError
from app.filtered_execution import run_filtered_execution_graph


def test_criteria_retrieval_aggregator_are_connected_through_graph():
    request = {
        "city": "Hyderabad",
        "locality": "Gachibowli",
        "bhk": 2,
        "property_type": "Residential Apartment",
        "min_price_inr": 5_000_000,
        "max_price_inr": 10_000_000,
        "start_month": "2022-09",
        "end_month": "2023-08",
    }
    result = run_filtered_execution_graph(request)
    report = result.report

    assert report["retrieval"]["selected_row_count"] == 24
    assert len(report["monthly_records"]) == 12
    assert report["criteria_result"]["query_mode"] == "EXACT_LOCALITY"
    assert report["agent_interaction_trace"][0]["agent"] == "criteria_agent"
    assert report["agent_interaction_trace"][1]["agent"] == "retrieval_agent"
    assert report["agent_interaction_trace"][2]["agent"] == "aggregator"
    assert report["trace"]
    assert report["loop_counters"] == {"coverage_repair": 0, "critique_revision": 0}
    assert report["source_sha256"] == "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"


def test_locality_id_request_uses_criteria_and_retrieval():
    result = run_filtered_execution_graph({"city": "Hyderabad", "locality": "5561"})
    assert result.report["retrieval"]["selected_row_count"] == 38
    assert result.report["criteria_result"]["filter_spec"]["localities"] == ["5561"]


def test_geo_radius_request_uses_retrieval_coordinates():
    request = {
        "city": "Hyderabad",
        "locality": "Kondapur",
        "geo_radius_km": 2,
        "property_type": "Residential Apartment",
        "bhk": 2,
    }
    result = run_filtered_execution_graph(request)
    assert result.report["criteria_result"]["query_mode"] == "GEO_RADIUS"
    assert result.report["retrieval"]["selected_row_count"] == 112
    assert result.report["retrieval"]["center_coordinates"] is not None


def test_unsupported_locality_fails_before_retrieval():
    try:
        run_filtered_execution_graph({"city": "Hyderabad", "locality": "Not A Real Locality"})
    except CriteriaValidationError as exc:
        assert exc.code == "unsupported_locality"
    else:
        raise AssertionError("unsupported locality unexpectedly passed Criteria Agent")
