# Credits: Paridhi Mittal. Full attribution: CREDITS.md.
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


def _narrow():
    """3 BHK in Gachibowli: both loops fire, so every new panel has content."""
    at = AppTest.from_file(APP, default_timeout=300).run()
    by_label = {m.label: m for m in at.sidebar.multiselect}
    by_label["BHK"].select(3)
    by_label["Localities"].select("Gachibowli")
    return at.run()


def _metric(at, label):
    return next(m for m in at.metric if m.label == label)


def test_before_critique_toggle_shows_the_first_analysis():
    at = _narrow()
    assert not at.exception, [e.value for e in at.exception]
    at.toggle[0].set_value(True).run()
    move = _metric(at, "Median Rs/sqft move")
    assert move.value == "-0.70%" and move.delta == "before critique: -4.45%"


def test_threshold_slider_recomputes_the_headline():
    at = _narrow()
    slider = next(s for s in at.select_slider
                  if s.label == "Minimum listings for a month to count")
    slider.set_value(75).run()
    assert not at.exception
    assert _metric(at, "First month").value == "2023-07"


def test_replay_slider_steps_through_the_run():
    at = _narrow()
    step = next(s for s in at.slider if s.label == "Step")
    step.set_value(0).run()
    assert not at.exception
    assert _metric(at, "Answer at this step").value == "—"
    step = next(s for s in at.slider if s.label == "Step")
    step.set_value(int(step.max)).run()
    assert _metric(at, "Answer at this step").value == "-0.70%"
