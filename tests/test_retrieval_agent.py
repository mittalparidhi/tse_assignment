from __future__ import annotations

import builtins
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.criteria_agent import CriteriaAgent, FilterSpec, QueryMode
from app.retrieval_agent import RetrievalAgent, RetrievalError, _coordinate_pair, _safe_dict
from app.schemas import FROZEN_SOURCE_SHA256

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "hyderabad.csv"


def test_hand_counted_frozen_snapshot_locality_date_and_filter_example():
    """Manual audit example: Gachibowli + 2BHK apartment + inclusive INR band."""
    criteria = CriteriaAgent(source_path=SOURCE).run({
        "city": "Hyderabad",
        "locality": "Gachibowli",
        "bhk": 2,
        "property_type": "Residential Apartment",
        "min_price_inr": 5_000_000,
        "max_price_inr": 10_000_000,
        "start_month": "2022-09",
        "end_month": "2023-08",
    })

    result = RetrievalAgent(SOURCE).retrieve(criteria)

    # Hand-checked row IDs/property IDs from the pinned canonical CSV. The full
    # ID list prevents a coincidental count-only test from passing.
    expected_property_ids = [
        "Q69255364", "J70257340", "V70657016", "Z60331450", "T65066010",
        "L69228804", "E69995518", "M70698488", "X70270432", "S70312078",
        "S70310604", "L70308592", "Q70297544", "C70802468", "F70780388",
        "S70772186", "I70910350", "P70832368", "E70803372", "I70371884",
        "F70100324", "U70323056", "O70865844", "D70085386",
    ]
    assert len(result.rows) == 24
    assert result.rows["PROP_ID"].astype(str).tolist() == expected_property_ids
    assert result.query_mode is QueryMode.EXACT_LOCALITY
    assert result.source_sha256 == FROZEN_SOURCE_SHA256
    assert result.rows["REGISTER_DATE__U"].map(lambda x: str(x)[:7]).between("2022-09", "2023-08").all()
    assert result.rows["PROPERTY_TYPE"].eq("Residential Apartment").all()
    assert pd.to_numeric(result.rows["BEDROOM_NUM"]).eq(2).all()


def test_geo_radius_frozen_snapshot_example_returns_expected_count():
    criteria = CriteriaAgent(source_path=SOURCE).run({
        "city": "Hyderabad",
        "locality": "Kondapur",
        "geo_radius_km": 2,
        "property_type": "Residential Apartment",
        "bhk": 2,
    })
    result = RetrievalAgent(SOURCE).retrieve(criteria)
    assert len(result.rows) == 112
    assert result.center_latitude == pytest.approx(17.4609913)
    assert result.center_longitude == pytest.approx(78.3532083)
    assert result.rows["PROPERTY_TYPE"].eq("Residential Apartment").all()
    assert pd.to_numeric(result.rows["BEDROOM_NUM"]).eq(2).all()


def test_criteria_agent_accepts_locality_id_and_retrieval_matches_parsed_id():
    agent = CriteriaAgent(source_path=SOURCE)
    criteria = agent.run({"city": "Hyderabad", "locality": "5561"})
    assert criteria.filter_spec.localities == ("5561",)

    result = RetrievalAgent(SOURCE).retrieve(criteria)
    assert len(result.rows) == 38
    parsed = result.rows["location"].map(_safe_dict)
    assert parsed.map(lambda x: str(x.get("LOCALITY_ID", "")).strip()).eq("5561").all()


def test_geo_radius_uses_valid_map_details_coordinates():
    """Synthetic fixture has three rows within 2 km, one outside, invalid coords."""
    path = _write_fixture()
    agent = RetrievalAgent(path, expected_sha256=_digest(path))
    result = agent.retrieve(_fixture_spec(localities=("Alpha",), radius=2.0), QueryMode.GEO_RADIUS)
    assert result.rows["source_row_id"].tolist() == [0, 1, 8]
    assert result.center_latitude == pytest.approx(17.0)
    assert result.center_longitude == pytest.approx(78.0)
    assert result.invalid_coordinate_rows >= 2


def test_exact_locality_supports_name_or_id_and_composes_filters():
    path = _write_fixture()
    agent = RetrievalAgent(path, expected_sha256=_digest(path))
    criteria = _fixture_spec(
        localities=("101",),
        bhk=(2,),
        property_types=("Residential Apartment",),
        min_price_inr=5_500_000,
        max_price_inr=6_500_000,
    )
    result = agent.retrieve(criteria, QueryMode.EXACT_LOCALITY)
    assert result.rows["source_row_id"].tolist() == [0]
    assert result.rows.iloc[0]["PROP_ID"] == "P0"


def test_registration_month_bounds_are_inclusive_and_use_register_date_not_posting_date():
    path = _write_fixture()
    agent = RetrievalAgent(path, expected_sha256=_digest(path))
    period = SimpleNamespace(start_month="2023-07", end_month="2023-08")
    spec = FilterSpec(city="Hyderabad", localities=("101", "102"), source_period=period)
    result = agent.retrieve(spec, QueryMode.EXACT_LOCALITY)
    # Row 0 has a 2020 posting timestamp but register date at the first day of
    # the lower bound; row 1 is on the last day of the upper bound. Rows 4 and
    # 7 sit immediately outside the month bounds; row 5 has an invalid date.
    assert result.rows["source_row_id"].tolist() == [0, 1, 3, 6, 8]
    assert result.source_period_start == "2023-07"
    assert result.source_period_end == "2023-08"


def test_invalid_register_date_is_excluded_and_reported():
    path = _write_fixture()
    agent = RetrievalAgent(path, expected_sha256=_digest(path))
    result = agent.retrieve(_fixture_spec(localities=("101",)), QueryMode.EXACT_LOCALITY)
    assert result.invalid_registration_date_rows == 1
    assert 5 not in result.rows["source_row_id"].tolist()


def test_safe_parsers_do_not_call_builtin_eval(monkeypatch):
    def fail_eval(*args, **kwargs):
        pytest.fail("built-in eval must never be called")

    monkeypatch.setattr(builtins, "eval", fail_eval)
    assert _safe_dict("{'LOCALITY_NAME': 'Alpha', 'LOCALITY_ID': '101'}")["LOCALITY_ID"] == "101"
    assert _safe_dict('{"CITY_NAME": "Hyderabad"}')["CITY_NAME"] == "Hyderabad"
    assert _safe_dict("__import__('os').system('echo unsafe')") == {}
    assert _coordinate_pair("{'LATITUDE': '17.0', 'LONGITUDE': '78.0'}") == (17.0, 78.0)


def test_invalid_or_out_of_range_coordinates_are_rejected():
    assert _coordinate_pair("{'LATITUDE': 'nan', 'LONGITUDE': '78'}") is None
    assert _coordinate_pair("{'LATITUDE': '91', 'LONGITUDE': '78'}") is None
    assert _coordinate_pair("{'LATITUDE': '17', 'LONGITUDE': '181'}") is None
    assert _coordinate_pair("malformed") is None


def test_geo_radius_fails_explicitly_when_centre_has_no_valid_coordinates():
    path = _write_fixture(center_invalid=True)
    agent = RetrievalAgent(path, expected_sha256=_digest(path))
    with pytest.raises(RetrievalError) as error:
        agent.retrieve(_fixture_spec(localities=("Alpha",), radius=2.0), QueryMode.GEO_RADIUS)
    assert error.value.code == "center_coordinates_unavailable"


def test_snapshot_digest_mismatch_fails_closed():
    with pytest.raises(RetrievalError) as error:
        RetrievalAgent(SOURCE, expected_sha256="0" * 64).retrieve(
            CriteriaAgent(source_path=SOURCE).run({"city": "Hyderabad", "locality": "Kondapur"})
        )
    assert error.value.code == "snapshot_integrity_error"


def _fixture_spec(
    *,
    localities=("Alpha",),
    radius=None,
    bhk=(),
    property_types=(),
    min_price_inr=None,
    max_price_inr=None,
):
    # A lightweight period intentionally tests inclusive date-bound handling
    # at the retrieval layer; the public Criteria Agent currently constrains
    # requests to the frozen 12-month contract period.
    period = SimpleNamespace(start_month="2023-07", end_month="2023-08")
    return FilterSpec(
        city="Hyderabad",
        localities=tuple(localities),
        bhk=tuple(bhk),
        property_types=tuple(property_types),
        min_price_inr=min_price_inr,
        max_price_inr=max_price_inr,
        geo_radius_km=radius,
        source_period=period,
    )


def _write_fixture(*, center_invalid=False) -> Path:
    # Use a unique temp directory so parallel test workers do not collide.
    from tempfile import mkdtemp

    directory = Path(mkdtemp(prefix="retrieval-agent-test-"))
    path = directory / "fixture.csv"
    center_map = "malformed" if center_invalid else "{'LATITUDE': '17.0', 'LONGITUDE': '78.0'}"
    beta_map = "not-a-dict" if center_invalid else "{'LATITUDE': '17.01', 'LONGITUDE': '78.0'}"
    gamma_map = "{'LATITUDE': '17.05', 'LONGITUDE': '78.0'}"
    edge_map = "not-a-dict" if center_invalid else "{'LATITUDE': '17.0001', 'LONGITUDE': '78.0'}"
    invalid_date_map = "not-a-dict" if center_invalid else "{'LATITUDE': '17.0', 'LONGITUDE': '78.0'}"
    june_map = "not-a-dict" if center_invalid else "{'LATITUDE': '17.0', 'LONGITUDE': '78.0'}"
    final_map = "not-a-dict" if center_invalid else "{'LATITUDE': '17.0', 'LONGITUDE': '78.0'}"
    rows = [
        _row(0, "101", "Alpha", center_map, "2023-07-01 00:00:00", "2020-01-01 00:00:00", "Residential Apartment", 2, 5_000_000, 6_000_000),
        _row(1, "102", "Beta", beta_map, "2023-08-31 23:59:59", "2023-08-31 12:00:00", "Residential Apartment", 2, 6_000_000, 7_000_000),
        _row(2, "103", "Gamma", gamma_map, "2023-08-10 12:00:00", "2023-08-10 12:00:00", "Residential Apartment", 2, 4_000_000, 5_000_000),
        _row(3, "101", "Alpha", "{'LATITUDE': '95', 'LONGITUDE': '78.0'}", "2023-07-15 12:00:00", "2023-07-15 12:00:00", "Residential Land", 3, 5_000_000, 5_000_000),
        _row(4, "101", "Alpha", edge_map, "2023-09-01 00:00:00", "2023-09-01 00:00:00", "Residential Apartment", 2, 5_000_000, 6_000_000),
        _row(5, "101", "Alpha", invalid_date_map, "not-a-date", "2023-08-01 00:00:00", "Residential Apartment", 2, 5_000_000, 6_000_000),
        _row(6, "102", "Beta", "not-a-dict", "2023-08-01 00:00:00", "2023-08-01 00:00:00", "Residential Apartment", 2, 5_000_000, 6_000_000),
        _row(7, "101", "Alpha", june_map, "2023-06-30 23:59:59", "2023-06-30 23:59:59", "Residential Apartment", 2, 5_000_000, 6_000_000),
        _row(8, "101", "Alpha", final_map, "2023-08-20 12:00:00", "2023-08-20 12:00:00", "Residential Apartment", 2, 7_000_000, 8_000_000),
    ]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _row(
    i, locality_id, locality_name, map_details, register_date, posting_date,
    property_type, bedroom, min_price, max_price,
):
    return {
        "PROP_ID": f"P{i}",
        "CITY": "Hyderabad",
        "PROPERTY_TYPE": property_type,
        "BEDROOM_NUM": bedroom,
        "MIN_PRICE": min_price,
        "MAX_PRICE": max_price,
        "PREFERENCE": "S",
        "REGISTER_DATE__U": register_date,
        "POSTING_DATE": posting_date,
        "MAP_DETAILS": map_details,
        "location": repr({
            "CITY_NAME": "Hyderabad",
            "LOCALITY_NAME": locality_name,
            "LOCALITY_ID": locality_id,
        }),
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
