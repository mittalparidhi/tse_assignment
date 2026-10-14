"""Base-input generation.

The brief requires at least 30 *distinct base inputs per MR* -- criteria sets
or slices, not repeated runs. Two constraints make this non-trivial:

1. Some relations are only applicable on part of the space. MR-M2 needs a
   price band to widen, MR-M3 needs two or more localities to subset, and
   MR-D1 needs a window that can still be shifted forward inside the data
   range. A naive sweep left those at 24, 27 and 30 applicable inputs, so the
   quotas are now guaranteed by construction and asserted.

2. Cycling several option lists by one index degenerates: with periods
   5, 5, 3 and 4 the combination repeats after lcm = 60 and in practice much
   sooner, collapsing the catalogue onto one varying dimension. We therefore
   enumerate the full cross product and take a strided sample, which spreads
   every dimension evenly.
"""

from __future__ import annotations

import itertools

import pandas as pd

from ..trend import Criteria

#: Every base input must satisfy these, so MR-M2/M3/D1 are always applicable.
MIN_BASE_INPUTS = 36


def top_localities(frame: pd.DataFrame, n: int = 12) -> list[str]:
    """Deepest localities in the snapshot, by listing count (data-driven)."""
    return frame["locality"].value_counts().head(n).index.tolist()


def generate_base_inputs(
    frame: pd.DataFrame, target: int = MIN_BASE_INPUTS
) -> list[Criteria]:
    """Build the base-input catalogue. Deterministic given the frame."""
    months = sorted(frame["month"].dropna().unique().tolist())
    # Drop the final month so the forward-shifted window of MR-D1 always
    # stays inside the observed range.
    ends = [m for m in months[:-1]][-5:]
    locs = top_localities(frame)

    bhk_options: list[tuple[int, ...] | None] = [None, (2,), (3,), (2, 3), (3, 4)]
    # Every option carries a band, so MR-M2 is applicable on all inputs.
    band_options: list[tuple[float, float]] = [
        (4_000_000.0, 15_000_000.0),
        (5_000_000.0, 20_000_000.0),
        (8_000_000.0, 40_000_000.0),
        (10_000_000.0, 60_000_000.0),
    ]
    # Every option names >= 2 localities, so MR-M3 is applicable on all inputs.
    locality_options: list[tuple[str, ...]] = [
        tuple(locs[:2]),
        tuple(locs[:4]),
        tuple(locs[2:6]),
        tuple(locs[:8]),
    ]

    grid = list(itertools.product(ends, bhk_options, band_options, locality_options))
    # Stride through the product so no dimension is held constant.
    stride = max(1, len(grid) // target)
    picked = [grid[(i * stride) % len(grid)] for i in range(target * 2)]

    out: list[Criteria] = []
    seen: set[tuple] = set()
    for end, bhk, band, localities in picked:
        key = (end, bhk, band, localities)
        if key in seen:
            continue
        seen.add(key)
        out.append(Criteria(
            window_end=end,
            bhk=bhk,
            localities=localities,
            price_min_inr=band[0],
            price_max_inr=band[1],
            label=f"base{len(out):02d}",
        ))
        if len(out) == target:
            break

    if len(out) < 30:
        raise RuntimeError(
            f"only {len(out)} distinct base inputs generated; the brief "
            "requires at least 30 per MR"
        )
    return out


def summarise(inputs: list[Criteria]) -> pd.DataFrame:
    return pd.DataFrame([{
        "label": c.label,
        "window_end": c.window_end,
        "bhk": "all" if not c.bhk else "/".join(map(str, c.bhk)),
        "n_localities": 0 if not c.localities else len(c.localities),
        "band_lakh": (f"{(c.price_min_inr or 0)/1e5:.0f}-"
                      f"{(c.price_max_inr or 0)/1e5:.0f}"),
    } for c in inputs])
