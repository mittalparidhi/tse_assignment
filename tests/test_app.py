"""Smoke tests for the Streamlit dashboard (the brief's visual interface).

The dashboard is run headlessly with Streamlit's AppTest: it must render
without an exception in both retrieval modes and show its three tabs.
"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _run(**radio):
    at = AppTest.from_file(APP, default_timeout=300).run()
    for label, value in radio.items():
        next(r for r in at.sidebar.radio if r.label == label).set_value(value)
        at.run()
    return at


def test_dashboard_renders_without_errors():
    at = _run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert len(at.tabs) == 3
    assert len(at.metric) > 0


def test_dashboard_runs_a_radius_query():
    at = _run(**{"Retrieval algorithm (query_mode)": "GEO_RADIUS"})
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 3
