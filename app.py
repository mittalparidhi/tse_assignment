"""Interactive dashboard for the Hyderabad housing-trends agent system.

    streamlit run app.py

Three views:
  * Trend      -- the 12-month report for a user-chosen slice, plus the
                  execution trace showing which agent loops fired.
  * Relations  -- the MR catalogue and the harness results with 95% CIs.
  * Data       -- the snapshot, its filter cascade and the known defects.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src import viz
from src.agents import AgentMode, GraphConfig, build_graph, run_pipeline
from src.loading import load_canonical, verify_snapshot
from src.mr.relations import ALL_RELATIONS
from src.trend import Criteria, available_months

st.set_page_config(page_title="Hyderabad Housing Trends",
                   page_icon="H", layout="wide")


@st.cache_data(show_spinner="Loading frozen snapshot...")
def _load():
    digest = verify_snapshot()
    frame, log = load_canonical()
    return frame, log.as_frame(), digest


@st.cache_resource
def _graph(n_retrieval_agents: int):
    return build_graph(n_retrieval_agents)


frame, cascade, digest = _load()
months = available_months(frame)
locality_counts = frame["locality"].value_counts()

# ---------------------------------------------------------------- sidebar

st.sidebar.title("Search criteria")
st.sidebar.caption(
    "The agents scan the frozen snapshot against these. If a slice is too "
    "thin to support a trend, the CoverageAuditor sends work back upstream "
    "and the CriteriaPlanner relaxes it - you will see that in the trace."
)

window_end = st.sidebar.selectbox(
    "Window ends", months, index=len(months) - 1,
    help="The 12-month window ends at and includes this month.",
)
bhk_choice = st.sidebar.multiselect("BHK", [1, 2, 3, 4, 5], default=[])
locality_choice = st.sidebar.multiselect(
    "Localities", locality_counts.index.tolist()[:40], default=[],
    help="Ranked by listing depth. Leave empty for the whole metro.",
)
band_on = st.sidebar.checkbox("Apply a price band", value=False)
if band_on:
    lo_lakh, hi_lakh = st.sidebar.slider(
        "Asking price (Rs lakh)", 5, 2000, (40, 300), step=5,
    )
else:
    lo_lakh = hi_lakh = None

st.sidebar.divider()
st.sidebar.subheader("Agent control")
coverage_target = st.sidebar.slider(
    "Coverage target", 0.0, 1.0, 0.50, 0.05,
    help="Share of the 12 months that must have adequate depth before the "
         "CoverageAuditor stops iterating.")
max_retry = st.sidebar.slider(
    "Max retrieval retries (cycle 1)", 0, 5, 3,
    help="Coverage agent -> Retrieval agents.")
max_critique = st.sidebar.slider(
    "Max critique rounds (cycle 2)", 0, 3, 1,
    help="Critique agent -> Analysis agent.")
n_agents = st.sidebar.slider(
    "Cooperating retrieval agents", 1, 8, 4,
    help="Several agents each scan a shard. The answer must not depend on "
         "how many there are.")
seed = st.sidebar.number_input("Seed", value=11, step=1)

st.sidebar.divider()
geo = st.sidebar.radio(
    "Retrieval algorithm (query_mode)", ["EXACT_LOCALITY", "RADIUS"],
    help="The Criteria agent sets this and the Retrieval agents run a "
         "different algorithm as a result.")
center_lat = center_lon = radius_km = None
if geo == "RADIUS":
    radius_km = st.sidebar.slider("Radius (km)", 1.0, 40.0, 5.0, 0.5)
    center_lat = st.sidebar.number_input("Centre latitude", value=17.4401,
                                         format="%.4f")
    center_lon = st.sidebar.number_input("Centre longitude", value=78.3489,
                                         format="%.4f")

criteria = Criteria(
    window_end=window_end,
    bhk=tuple(sorted(bhk_choice)) or None,
    localities=tuple(locality_choice) or None,
    price_min_inr=None if lo_lakh is None else lo_lakh * 1e5,
    price_max_inr=None if hi_lakh is None else hi_lakh * 1e5,
    query_mode=geo,
    center_lat=center_lat,
    center_lon=center_lon,
    radius_km=radius_km,
    label="ui",
)
config = GraphConfig(coverage_target=coverage_target,
                     max_retry_rounds=max_retry,
                     max_critique_rounds=max_critique,
                     n_retrieval_agents=n_agents)

trend_tab, mr_tab, data_tab = st.tabs(["Trend", "Relations", "Data"])

# ------------------------------------------------------------------ trend

with trend_tab:
    state = run_pipeline(frame, criteria, seed=int(seed),
                         config=config, graph=_graph(n_agents))
    report = state["final_report"]

    st.markdown(f"#### {report.window_months[0]} to {report.window_months[-1]}")
    st.caption(state["narrative"])

    c1, c2, c3, c4 = st.columns(4)
    move = report.yoy_median_psf_pct
    c1.metric(
        "Median Rs/sqft move",
        "n/a" if move is None else f"{move:+.1f}%",
        help=f"Measured across the {report.yoy_span_months} months with "
             f"adequate depth; the window spans 12.",
    )
    c2.metric("Listings in window", f"{report.n_listings_total:,}")
    c3.metric("Months with depth",
              f"{len(report.sufficient_months())} / 12")
    c4.metric("Suspect listings rejected",
              f"{report.provenance.get('n_rejected_outliers', 0):,}",
              help="Removed by the Analysis agent's targeted recomputation "
                   "after the Critique agent rejected the trend.")

    if report.provenance.get("relaxations"):
        st.warning(
            "**Your query was too narrow to answer, so the agents relaxed "
            "it.** " + "; ".join(report.provenance["relaxations"])
            + ". The numbers below describe the relaxed slice."
        )

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(viz.psf_line(report), width='stretch')
        st.plotly_chart(viz.count_bars(report), width='stretch')
    with right:
        st.plotly_chart(viz.locality_bars(report), width='stretch')

    if st.checkbox("Show the numbers as a table", value=False,
                   help="Every chart here has a table equivalent."):
        st.dataframe(pd.DataFrame([{
            "month": m.month, "active_listings": m.n_active,
            "median_psf": m.median_psf, "median_price": m.median_price,
            "p25_psf": m.p25_psf, "p75_psf": m.p75_psf,
            "adequate_depth": m.month_is_sufficient,
        } for m in report.monthly]), width='stretch', hide_index=True)

    with st.expander(
        f"Execution trace - {len(state['trace'])} steps, "
        f"cycle 1 fired {state['retry_count']}x, "
        f"cycle 2 fired {state['critique_rounds']}x",
        expanded=False,
    ):
        st.caption(
            "The graph is cyclic. Rows marked ITERATE or ESCALATE are the "
            "back-edges firing: a downstream agent sending work upstream."
        )
        trace_rows = []
        for entry in state["trace"]:
            detail = {k: v for k, v in entry.items()
                      if k not in {"step", "agent"}}
            trace_rows.append({
                "step": entry["step"], "agent": entry["agent"],
                "detail": "  ".join(f"{k}={v}" for k, v in detail.items()),
            })
        st.dataframe(pd.DataFrame(trace_rows),
                     width='stretch', hide_index=True)

# -------------------------------------------------------------- relations

with mr_tab:
    st.markdown("#### Metamorphic relation catalogue")
    st.caption(
        "Each relation transforms an input, re-runs the system and checks the "
        "two outputs relate as the property demands. No oracle for any "
        "individual answer is needed."
    )
    st.dataframe(pd.DataFrame([{
        "MR": mr.mr_id, "family": mr.family, "transformation": mr.name,
        "subdomain": mr.subdomain, "tolerance": mr.tolerance,
        "fault exposed if violated": mr.fault,
    } for mr in ALL_RELATIONS]), width='stretch', hide_index=True)

    runs = sorted(p.name for p in Path("results").glob("*")
                  if (p / "mr_summary.csv").exists())
    if not runs:
        st.info("No harness results yet. Run `python scripts/run_harness.py`.")
    else:
        tag = st.selectbox("Harness run", runs, index=len(runs) - 1)
        summary = pd.read_csv(Path("results") / tag / "mr_summary.csv")
        st.plotly_chart(viz.violation_ci_chart(summary),
                        width='stretch')
        st.dataframe(summary, width='stretch', hide_index=True)

        detail_path = Path("results") / tag / "mr_runs.csv"
        if detail_path.exists():
            detail = pd.read_csv(detail_path)
            violated = detail[detail.violated]
            st.markdown(
                f"**{len(violated)} violating runs** of "
                f"{len(detail[detail.applicable])} applicable."
            )
            if not violated.empty:
                st.dataframe(
                    violated[["mr_id", "base_input", "seed", "detail"]],
                    width='stretch', hide_index=True,
                )

# ------------------------------------------------------------------- data

with data_tab:
    st.markdown("#### Frozen snapshot")
    a, b, c = st.columns(3)
    a.metric("Canonical listings", f"{len(frame):,}")
    b.metric("Distinct localities", f"{frame['locality'].nunique():,}")
    c.metric("Months observed", f"{frame['month'].nunique()}")
    st.caption(f"99acres Hyderabad slice. SHA-256 `{digest}` "
               f"re-verified on load; the raw file is never modified.")

    st.markdown("**Filter cascade** - every dropped row is accounted for.")
    st.dataframe(cascade, width='stretch', hide_index=True)

    st.markdown("**Known defects in the source data**")
    st.dataframe(pd.DataFrame([
        {"id": "D1", "defect": "MIN_AREA_SQFT is square metres despite the name",
         "evidence": "AREA/MIN_AREA_SQFT = 10.7639 at p5 and p95 over 3,531 rows",
         "handling": "area parsed from the AREA display string instead"},
        {"id": "D2", "defect": "int32 sentinel 2,147,483,647 in price fields",
         "evidence": "5 rows at exactly 2**31-1; 75 rows at zero",
         "handling": "dropped"},
        {"id": "D3", "defect": "sale, rent and PG listings mixed",
         "evidence": "PREFERENCE: S=7,927 R=1,467 P=93",
         "handling": "sale only"},
        {"id": "D4", "defect": "BEDROOM_NUM missing on 29.7% of rows",
         "evidence": "2,806 of 2,814 are Residential Land - plots have no bedrooms",
         "handling": "restricted to dwellings"},
        {"id": "D5", "defect": "area-entry errors in the tail",
         "evidence": "a 27 sqft villa at Rs 2.15 cr = Rs 796,296/sqft",
         "handling": "left in deliberately; the Analysis agent's targeted "
                     "recomputation is what must catch these (cycle 2)"},
    ]), width='stretch', hide_index=True)

    st.markdown(
        "**The threat this snapshot carries.** It is a single-point scrape, "
        "so older months hold only listings still live on the scrape date. "
        "96.5% of the window's listings fall in its last six months, and the "
        "thin months' medians swing on 21-34 listings. That is why the report "
        "carries a per-month `adequate_depth` flag and why month-comparing "
        "relations are declared only over the sufficient subdomain."
    )
