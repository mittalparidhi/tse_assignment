"""Chart builders for the dashboard.

Design rules applied deliberately:

* **No dual-axis chart.** Median price-per-sqft and active-listing count are
  different measures on different scales, so they get two stacked charts
  sharing an x-axis rather than two y-scales on one plot.
* **One series per chart means no legend** -- the title names the measure.
* **Sufficiency is never encoded by colour alone.** Thin months carry a hollow
  marker and a caption as well, so the distinction survives greyscale printing
  and colour-vision deficiency.
* Palette is the validated two-slot categorical set (blue #2a78d6, orange
  #eb6834). Both clear the lightness band, chroma floor, CVD separation
  (worst adjacent dE 24.7 protan), normal-vision floor (dE 33.6) and the 3:1
  contrast check against the light chart surface.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .contract import TrendReport

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8980"
GRID = "#e6e5e1"
SERIES_1 = "#2a78d6"     # blue
SERIES_2 = "#eb6834"     # orange
NEUTRAL = "#b6b5ad"

_FONT = dict(family="Inter, -apple-system, Segoe UI, sans-serif",
             color=TEXT_PRIMARY, size=13)


def _base_layout(title: str, height: int = 320) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=15, color=TEXT_PRIMARY)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=_FONT,
        height=height,
        margin=dict(l=56, r=24, t=52, b=52),
        hovermode="x unified",
        xaxis=dict(showgrid=False, linecolor=GRID,
                   tickfont=dict(color=TEXT_SECONDARY, size=11)),
        yaxis=dict(gridcolor=GRID, zeroline=False, linecolor=SURFACE,
                   tickfont=dict(color=TEXT_SECONDARY, size=11)),
        showlegend=False,
    )


def psf_line(report: TrendReport) -> go.Figure:
    """Median price per unit area across the window. One series, no legend."""
    months = list(report.window_months)
    values = report.psf_series()
    sufficient = [m.month_is_sufficient for m in report.monthly]
    cur = report.currency_unit.replace("INR_", "Rs ").replace("INR", "Rs")
    unit = f"{cur} / {report.area_unit.lower()}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=values, mode="lines",
        line=dict(color=SERIES_1, width=2),
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
        connectgaps=True, name="median",
    ))
    # Filled markers where the month has depth, hollow where it does not.
    fig.add_trace(go.Scatter(
        x=[m for m, s in zip(months, sufficient) if s],
        y=[v for v, s in zip(values, sufficient) if s],
        mode="markers",
        marker=dict(color=SERIES_1, size=9, line=dict(color=SURFACE, width=2)),
        hoverinfo="skip", name="adequate depth",
    ))
    fig.add_trace(go.Scatter(
        x=[m for m, s in zip(months, sufficient) if not s],
        y=[v for v, s in zip(values, sufficient) if not s],
        mode="markers",
        marker=dict(color=SURFACE, size=9, line=dict(color=NEUTRAL, width=2)),
        hoverinfo="skip", name="thin month",
    ))

    layout = _base_layout(f"Median asking price ({unit})")
    present = [(m, v) for m, v in zip(months, values) if v is not None]
    if present:
        last_month, final = present[-1]
        fig.add_annotation(
            x=last_month, y=final, text=f"<b>{final:,.0f}</b>",
            showarrow=False, xshift=36, font=dict(color=SERIES_1, size=12),
        )
    thin = sum(1 for s in sufficient if not s)
    if thin:
        layout["xaxis"]["title"] = dict(
            text=f"hollow markers: fewer than 50 listings "
                 f"({thin} of 12 months) - medians there are noise",
            font=dict(color=TEXT_MUTED, size=10))
    fig.update_layout(**layout)
    return fig


def count_bars(report: TrendReport) -> go.Figure:
    """Active-listing count per month. A separate chart, never a second axis."""
    months = list(report.window_months)
    counts = report.count_series()
    sufficient = [m.month_is_sufficient for m in report.monthly]

    fig = go.Figure(go.Bar(
        x=months, y=counts,
        marker=dict(color=[SERIES_1 if s else NEUTRAL for s in sufficient],
                    line=dict(color=SURFACE, width=2)),
        hovertemplate="%{x}<br>%{y:,} listings<extra></extra>",
    ))
    layout = _base_layout("Active listings per month", height=250)
    layout["bargap"] = 0.3
    fig.update_layout(**layout)
    fig.add_hline(y=50, line=dict(color=SERIES_2, width=1, dash="dot"),
                  annotation_text="sufficiency threshold (50)",
                  annotation_position="top left",
                  annotation_font=dict(color=SERIES_2, size=10))
    return fig


def locality_bars(report: TrendReport, top_n: int = 10) -> go.Figure:
    """Locality ranking by median price per unit area, highest at the top."""
    rows = list(report.locality_rankings)[:top_n]
    if not rows:
        return go.Figure(layout=_base_layout("No locality has enough depth"))
    rows = list(reversed(rows))        # plotly draws bottom-up
    fig = go.Figure(go.Bar(
        x=[r.median_psf for r in rows], y=[r.locality for r in rows],
        orientation="h",
        marker=dict(color=SERIES_1, line=dict(color=SURFACE, width=2)),
        text=[f"{r.median_psf:,.0f}" for r in rows], textposition="outside",
        textfont=dict(color=TEXT_SECONDARY, size=11),
        customdata=[r.n_active for r in rows],
        hovertemplate="%{y}<br>%{x:,.0f} per unit area<br>"
                      "n=%{customdata}<extra></extra>",
    ))
    layout = _base_layout("Most expensive localities (median)", height=380)
    layout["bargap"] = 0.35
    layout["yaxis"]["gridcolor"] = SURFACE
    layout["xaxis"].update(showgrid=True, gridcolor=GRID)
    layout["margin"] = dict(l=160, r=80, t=52, b=44)
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    return fig


def violation_ci_chart(summary: pd.DataFrame) -> go.Figure:
    """Violation rate per MR with its 95% Wilson interval.

    A dot-and-interval plot rather than bars: the quantity is an estimate with
    uncertainty, and a bar implies a count anchored at zero.
    """
    # Summaries written since contract v2 count base inputs; older committed
    # sweeps counted runs. Label the denominator with whichever unit it is.
    unit = "base_inputs" if "base_inputs" in summary and "run_rate" in summary else "runs"
    data = summary[summary[unit] > 0].iloc[::-1]
    unit_label = "base inputs" if unit == "base_inputs" else "runs"
    fig = go.Figure(go.Scatter(
        x=data["violation_rate"], y=data["mr_id"], mode="markers",
        error_x=dict(type="data", symmetric=False,
                     array=data["ci95_high"] - data["violation_rate"],
                     arrayminus=data["violation_rate"] - data["ci95_low"],
                     color=NEUTRAL, thickness=2, width=5),
        marker=dict(color=[SERIES_2 if r > 0 else SERIES_1
                           for r in data["violation_rate"]],
                    size=11, line=dict(color=SURFACE, width=2)),
        customdata=data[["relation", "violations", unit]].to_numpy(),
        hovertemplate="<b>%{y}</b> %{customdata[0]}<br>"
                      "rate %{x:.3f} (%{customdata[1]}/%{customdata[2]} "
                      f"{unit_label})"
                      "<extra></extra>",
    ))
    layout = _base_layout("Violation rate by relation, 95% Wilson interval",
                          height=360)
    layout["xaxis"].update(range=[-0.03, 1.03], showgrid=True, gridcolor=GRID,
                           title=dict(text="violation rate (orange = violated)",
                                      font=dict(color=TEXT_MUTED, size=10)))
    layout["yaxis"]["gridcolor"] = SURFACE
    layout["hovermode"] = "closest"
    fig.update_layout(**layout)
    return fig
