# Credits: written by Vidhi Jain (second implementation, commits 736d594 and
# 957224c); changed by Paridhi Mittal: city selection, GEO_RADIUS switch,
# request validation, coverage status, the three live agent views, typography.
# Lines by git blame: Vidhi Jain 49%, Paridhi Mittal 51%. Full attribution:
# CREDITS.md.
"""Interactive dashboard for the Hyderabad housing-trends agent system.

    streamlit run app.py

Three views:
  * Trend      -- the 12-month report for a user-chosen slice, plus the
                  execution trace showing which agent loops fired.
  * Relations  -- the MR catalogue and the harness results with 95% CIs.
  * Data       -- the snapshot, its filter cascade and the known defects.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src import viz
from src.agents import AgentMode, GraphConfig, build_graph, run_pipeline
from src.agents.readable import readable_trace
from src.loading import load_canonical, verify_snapshot
from src.mr.relations import ALL_RELATIONS
from src.trend import available_months, compute_trend
from src.validation import (
    CriteriaValidationError,
    SourceCatalog,
    validate_request,
)

st.set_page_config(page_title="Hyderabad Housing Trends",
                   page_icon="H", layout="wide")

# Newsreader for headings, IBM Plex Sans for text, IBM Plex Mono for numbers.
# Selectors are targeted rather than "*": Streamlit draws its icons with an
# icon font, and a blanket override would turn them into their ligature names.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');
html, body, .stApp, [data-testid="stSidebar"], .stMarkdown, [data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"], [data-testid="stMetricLabel"], [data-testid="stExpander"] summary,
.stTabs [data-baseweb="tab"], button, input, textarea {
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}
h1, h2, h3, h4, h5, [data-testid="stHeading"] h1, [data-testid="stHeading"] h2,
[data-testid="stHeading"] h3, [data-testid="stHeading"] h4 {
  font-family: 'Newsreader', Georgia, serif !important;
  font-weight: 500 !important;
  letter-spacing: -0.01em;
}
[data-testid="stMetricValue"], code, pre, .mono {
  font-family: 'IBM Plex Mono', Consolas, monospace !important;
  font-variant-numeric: tabular-nums;
}
.trace-step { padding: 6px 10px; border-left: 3px solid transparent; margin: 2px 0;
  border-radius: 4px; font-size: 0.92rem; }
.trace-step.current { border-left-color: #2E8B82; background: rgba(46,139,130,0.16); }
.trace-step.future { opacity: 0.35; }
.cycle-tag { font-size: 0.75rem; padding: 1px 7px; border-radius: 10px; margin-left: 6px;
  background: #1F5F5B; color: #FFFFFF; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)

#: Thresholds for the "how sure is the headline?" panel (REPORT §9).
SENSITIVITY_STEPS = [10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 300]
#: NHB RESIDEX, Hyderabad, July-September 2023 (results/residex/cross_check.md).
RESIDEX_HYDERABAD_PCT = 6.8
#: Agent names in the trace -> boxes in the architecture diagram.
DIAGRAM_NODE = {"CriteriaAgent": "Criteria", "RetrievalDispatch": "Retrieval",
                "RetrievalMerge": "Retrieval", "CoverageAgent": "Coverage",
                "AnalysisAgent": "Analysis", "CritiqueAgent": "Critique",
                "AggregatorAgent": "Aggregator"}


def _diagram(active: str | None, cycle: int | None) -> str:
    """Graphviz source for the six agents and both cycles; the active agent
    and, when it fires, its cycle are drawn in the accent colour."""
    accent, idle, border = "#1F5F5B", "#FFFFFF", "#B6B5AD"
    labels = {"Criteria": "Criteria", "Retrieval": "Retrieval ×4",
              "Coverage": "Coverage", "Analysis": "Analysis",
              "Critique": "Critique", "Aggregator": "Aggregator"}
    lines = ['digraph G {', 'rankdir=TB; bgcolor="transparent"; nodesep=0.6; ranksep=0.32; forcelabels=true;',
             'node [shape=box, style="rounded,filled", fontname="IBM Plex Sans", '
             'fontsize=11, width=1.6, height=0.36, penwidth=1.2];',
             'edge [color="#8A8980", arrowsize=0.6, fontname="IBM Plex Sans", fontsize=9];']
    for key, label in labels.items():
        on = key == active
        lines.append(f'{key} [label="{label}", fillcolor="{accent if on else idle}", '
                     f'fontcolor="{"#FFFFFF" if on else "#1A1A1A"}", '
                     f'color="{accent if on else border}"];')
    lines += ["Criteria -> Retrieval; Retrieval -> Coverage; Coverage -> Analysis;",
              "Analysis -> Critique; Critique -> Aggregator;"]
    c1 = 'color="#1F5F5B", penwidth=2.4, fontcolor="#1F5F5B"' if cycle == 1 else 'style=dashed'
    c2 = 'color="#1F5F5B", penwidth=2.4, fontcolor="#1F5F5B"' if cycle == 2 else 'style=dashed'
    lines.append(f'Coverage -> Retrieval [xlabel="cycle 1  ", constraint=false, {c1}];')
    lines.append(f'Critique -> Analysis [xlabel="cycle 2  ", constraint=false, {c2}];')
    lines.append("}")
    return "\n".join(lines)


@st.cache_data(show_spinner="Loading frozen snapshot...")
def _load():
    digest = verify_snapshot()
    frame, log = load_canonical()
    return frame, log.as_frame(), digest


@st.cache_resource
def _graph(n_retrieval_agents: int):
    return build_graph(n_retrieval_agents)


frame, cascade, digest = _load()


@st.cache_resource
def _catalog() -> SourceCatalog:
    return SourceCatalog.from_frame(frame)
months = available_months(frame)
locality_counts = frame["locality"].value_counts()

# ---------------------------------------------------------------- sidebar

st.sidebar.title("Search criteria")
st.sidebar.caption(
    "The agents scan the frozen snapshot against these. If a slice is too "
    "thin to support a trend, the Coverage agent widens one criterion and "
    "sends work back to the Retrieval agents - you will see that in the trace."
)

window_end = st.sidebar.selectbox(
    "Window ends", months, index=len(months) - 1,
    help="The 12-month window ends at and includes this month.",
)
city_choice = st.sidebar.multiselect(
    "City", sorted(frame["city"].dropna().unique()), default=[],
    help="Leave empty for both Hyderabad and Secunderabad.")
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
         "Coverage agent stops widening.")
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
    "Retrieval algorithm (query_mode)", ["EXACT_LOCALITY", "GEO_RADIUS"],
    help="The Criteria agent sets this and the Retrieval agents run a "
         "different algorithm as a result.")
center_lat = center_lon = radius_km = None
if geo == "GEO_RADIUS":
    radius_km = st.sidebar.slider("Radius (km)", 1.0, 40.0, 5.0, 0.5)
    center_lat = st.sidebar.number_input("Centre latitude", value=17.4401,
                                         format="%.4f")
    center_lon = st.sidebar.number_input("Centre longitude", value=78.3489,
                                         format="%.4f")
    if locality_choice:
        # A radius search is defined by its centre; it cannot also take a
        # locality list (contracts/Criteria.md rule 8). Say so, don't block.
        st.sidebar.caption("The locality selection is ignored for a radius "
                           "search.")
        locality_choice = []

request = {
    "window_end": window_end,
    "bhk": sorted(bhk_choice) or None,
    "localities": list(locality_choice) or None,
    "cities": list(city_choice) or None,
    "price_min_inr": None if lo_lakh is None else lo_lakh * 1e5,
    "price_max_inr": None if hi_lakh is None else hi_lakh * 1e5,
    "query_mode": geo,
    "center_lat": center_lat,
    "center_lon": center_lon,
    "radius_km": radius_km,
    "label": "ui",
}
try:
    # contracts/Criteria.md §3: every request is checked against values the
    # snapshot actually contains before any agent runs.
    criteria = validate_request(
        {k: v for k, v in request.items() if v is not None}, _catalog())
except CriteriaValidationError as error:
    st.error(f"**{error.code}**: {error.message}")
    st.stop()
config = GraphConfig(coverage_target=coverage_target,
                     max_retry_rounds=max_retry,
                     max_critique_rounds=max_critique,
                     n_retrieval_agents=n_agents)

st.title("Hyderabad Housing Trends")
st.caption(f"Frozen snapshot · SHA-256 `{digest[:12]}…` · every number below is "
           "computed live by the agent pipeline for the criteria in the sidebar.")

trend_tab, mr_tab, data_tab = st.tabs(["Trend", "Relations", "Data"])

# ------------------------------------------------------------------ trend

with trend_tab:
    state = run_pipeline(frame, criteria, seed=int(seed),
                         config=config, graph=_graph(n_agents))
    report = state["final_report"]
    spec = state.get("widened_filter_spec") or state["filter_spec"]
    # The same statistics before the critique's targeted recomputation
    # (cycle 2): the first analysis pass, on the retrieved listings as they were.
    before = compute_trend(state["raw_listings"], spec, adequate_n=config.adequate_n)
    rejected = report.provenance.get("n_rejected_outliers", 0)

    st.markdown(f"#### {report.window_months[0]} to {report.window_months[-1]}")
    st.caption(state["narrative"])
    show_before = st.toggle(
        "Show before critique", value=False, disabled=not rejected,
        help="Overlay the trend as it was before the Critique agent sent the "
             "flagged months back to the Analysis agent (cycle 2)." if rejected
        else "The critique approved the first analysis; nothing was recomputed.")

    c1, c2, c3, c4 = st.columns(4)
    move = report.yoy_median_psf_pct
    before_move = before.yoy_median_psf_pct
    c1.metric(
        "Median Rs/sqft move",
        "n/a" if move is None else f"{move:+.2f}%",
        delta=(None if not (show_before and rejected) else
               "before critique: " + ("n/a" if before_move is None
                                      else f"{before_move:+.2f}%")),
        delta_color="off",
        help=f"Measured across the {report.yoy_span_months} months with "
             f"adequate depth; the window spans 12.",
    )
    c2.metric("Listings in window", f"{report.n_listings_total:,}")
    c3.metric("Months ADEQUATE",
              f"{report.coverage_series().count('ADEQUATE')} / 12",
              help="At least 30 usable price-and-area listings (design "
                   "note). Review status: "
                   f"{report.provenance.get('review_status')}.")
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
        st.plotly_chart(viz.psf_line(report, before if show_before and rejected else None),
                        width='stretch')
        st.plotly_chart(viz.count_bars(report), width='stretch')
    with right:
        st.plotly_chart(viz.locality_bars(report), width='stretch')

    if st.checkbox("Show the numbers as a table", value=False,
                   help="Every chart here has a table equivalent."):
        st.dataframe(pd.DataFrame([{
            "month": m.month, "listing_count": m.listing_count,
            "price_valid_count": m.price_valid_count,
            "median_listing_price_inr": m.median_listing_price_inr,
            "median_price_per_sqft_inr": m.median_price_per_sqft_inr,
            "coverage_status": m.coverage_status,
            "median_min_price_inr": m.median_min_price_inr,
            "median_max_price_inr": m.median_max_price_inr,
            "partial_month": m.is_partial_month,
            "p25_psf": m.p25_psf, "p75_psf": m.p75_psf,
            "headline_month (n>=50)": m.month_is_sufficient,
        } for m in report.monthly]), width='stretch', hide_index=True)

    # -- how sure is the headline? ------------------------------------------
    st.markdown("#### How sure is the headline?")
    st.caption(
        "The yearly move runs from the first to the last month with enough "
        "listings. Change how many a month needs, and watch the headline move. "
        "Computed live on this run's analysed listings; the contract uses 50.")
    analysed = state.get("analysed_listings")
    if analysed is None:
        analysed = state["raw_listings"]
    sens_rows = []
    for n in SENSITIVITY_STEPS:
        alt = compute_trend(analysed, spec, min_sufficient_n=n,
                            adequate_n=config.adequate_n)
        months_ok = alt.sufficient_months()
        sens_rows.append({"min_n": n, "headline_pct": alt.yoy_median_psf_pct,
                          "span": alt.yoy_span_months,
                          "first": months_ok[0] if months_ok else None})
    s_left, s_right = st.columns([2, 3])
    with s_left:
        chosen = st.select_slider("Minimum listings for a month to count",
                                  options=SENSITIVITY_STEPS, value=50)
        row = next(r for r in sens_rows if r["min_n"] == chosen)
        m1, m2, m3 = st.columns(3)
        m1.metric("Headline", "n/a" if row["headline_pct"] is None
                  else f"{row['headline_pct']:+.2f}%")
        m2.metric("Spans", f"{row['span']} mo" if row["span"] else "—")
        m3.metric("First month", row["first"] or "—")
        st.caption(
            f"Official index for comparison: NHB RESIDEX puts Hyderabad (whole "
            f"metro) at {RESIDEX_HYDERABAD_PCT:+.1f}%. For the whole-metro query "
            "the contract's n ≥ 50 gives the opposite sign, n ≥ 75 agrees "
            "(REPORT §9).")
    with s_right:
        st.plotly_chart(viz.sensitivity_bars(
            sens_rows, chosen, RESIDEX_HYDERABAD_PCT,
            f"NHB RESIDEX Hyderabad {RESIDEX_HYDERABAD_PCT:+.1f}%"), width='stretch')

    # -- the loops, step by step ---------------------------------------------
    st.markdown("#### Agent trace — watch the loops fire")
    steps = readable_trace(state["trace"])
    st.caption(
        f"This run: cycle 1 fired {state['retry_count']}×, cycle 2 fired "
        f"{state['critique_rounds']}×. Move the slider, or press Replay, to step "
        "through the run; the active agent and any loop that fires are highlighted.")

    def _render(i: int, list_box, diagram_box, answer_box) -> None:
        current = steps[i]
        moves = [s["move_pct"] for s in steps[: i + 1] if s["move_pct"] is not None]
        answer_box.metric("Answer at this step",
                          "—" if not moves else f"{moves[-1]:+.2f}%",
                          help="The headline after the latest Analysis pass so far.")
        diagram_box.graphviz_chart(_diagram(DIAGRAM_NODE.get(current["agent"]),
                                            current["cycle"]))
        html = []
        for j, s in enumerate(steps):
            cls = "current" if j == i else ("future" if j > i else "")
            tag = (f'<span class="cycle-tag">Cycle {s["cycle"]} · '
                   f'{"coverage → retrieval" if s["cycle"] == 1 else "critique → analysis"}'
                   f'</span>') if s["cycle"] else ""
            html.append(f'<div class="trace-step {cls}"><span class="mono">#{s["step"]} '
                        f'{s["agent"]}</span>{tag}<br>{s["detail"]}</div>')
        list_box.markdown("".join(html), unsafe_allow_html=True)

    if steps:
        t_left, t_right = st.columns([3, 2])
        with t_right:
            replay = st.button("▶ Replay run", help="Step through the run automatically.")
            answer_box = st.empty()
            diagram_box = st.empty()
        with t_left:
            index = st.slider("Step", 0, len(steps) - 1, len(steps) - 1,
                              format="%d", help="0 = the first step of the run.")
            list_box = st.empty()
        if replay:
            for i in range(len(steps)):
                _render(i, list_box, diagram_box, answer_box)
                time.sleep(0.7)
        else:
            _render(index, list_box, diagram_box, answer_box)

    with st.expander(
        f"Execution trace - {len(state['trace'])} steps, "
        f"cycle 1 fired {state['retry_count']}x, "
        f"cycle 2 fired {state['critique_rounds']}x",
        expanded=False,
    ):
        st.caption(
            "Every field each agent logged. The graph is cyclic. Rows whose decision reads 'WIDEN and "
            "re-retrieve (cycle 1)' or 'REJECT -> recompute flagged months "
            "(cycle 2)' are the back-edges firing: a downstream agent sending "
            "work upstream."
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
            applicable = detail[detail.applicable]
            # The statistical unit is the base input (contracts/Testing.md
            # §6); runs are shown alongside because each seed is listed below.
            bases = applicable.groupby(["mr_id", "base_input"]).violated.any()
            st.markdown(
                f"**{int(bases.sum())} violating base inputs** of "
                f"{len(bases)} applicable (relation, base input) pairs; "
                f"{len(violated)} violating runs of {len(applicable)} "
                f"across the seeds."
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
         "handling": "kept and flagged: counted in listing_count, not price-valid"},
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
        {"id": "D6", "defect": "'Price on Request' listings",
         "evidence": "87 rows; numeric bounds are placeholders, not prices",
         "handling": "kept and flagged: counted in listing_count, not price-valid"},
    ]), width='stretch', hide_index=True)

    st.markdown(
        "**The threat this snapshot carries.** It is a single-point scrape, "
        "so older months hold only listings still live on the scrape date. "
        "96.4% of the window's listings fall in its last six months, and the "
        "thin months' medians swing on 22-35 listings. That is why the report "
        "carries a per-month `month_is_sufficient` flag and why month-comparing "
        "relations are declared only over the sufficient subdomain."
    )
