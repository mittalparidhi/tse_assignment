"""Raw 99acres snapshot -> canonical listings frame.

Each filter below is tied to a defect verified in the frozen snapshot. The
counts in the comments were measured on ``data/raw/hyderabad.csv``
(SHA-256 in ``data/raw/CHECKSUMS.txt``, 9,487 rows) and are reproduced by
``RejectLog`` at run time, so they can be re-checked rather than trusted.

Defects found and handled
-------------------------
D1  ``MIN_AREA_SQFT`` / ``MAX_AREA_SQFT`` are **square metres despite the
    column name**. Verified: ratio of the ``AREA`` display string (always
    "<n> sq.ft.") to ``MIN_AREA_SQFT`` is 10.7639 at both the 5th and 95th
    percentile over 3,531 rows -- i.e. unanimously the sq.m->sq.ft constant.
    Using the named column would inflate every price-per-area figure 10.76x.
    We therefore parse area from the ``AREA`` display string.

D2  ``MIN_PRICE``/``MAX_PRICE`` carry the int32 sentinel 2,147,483,647
    (= 2**31 - 1) on 5 rows, and 0 on 75 rows. Both are dropped.

D3  ``PREFERENCE`` mixes sale (S, 7,927), rent (R, 1,467) and PG (P, 93).
    Mixing rent into an asking-price median is meaningless; sale only.

D4  ``BEDROOM_NUM`` is missing on 2,814 rows, of which 2,806 are
    ``Residential Land``. This is not missing data -- plots have no bedrooms.
    Restricting to dwellings removes the missingness *and* makes price per
    built-up area comparable. Of the rows where both exist, heading-derived
    BHK agrees with ``BEDROOM_NUM`` on 6,041 and conflicts on 0.

D5  Area-entry errors in the tail: a 27 sqft "villa" at Rs 2.15 cr
    (Rs 796,296/sqft) and a 285,599 sqft one, concentrated in
    ``Independent House/Villa``.

    **D5 is deliberately NOT filtered here.** These rows are left in the
    canonical frame on purpose. Detecting them is the job of the Analysis
    agent's targeted recomputation, which the Critique agent triggers when the
    aggregate looks wrong (DESIGN.md, cycle 2). If the loader removed them up
    front that path would be a no-op and the loop would be decorative --
    verified: on a plausibility-bounded frame the cross-field checks find
    0 disagreements in 4,504 rows, so the loop would never change an answer.
    Leaving the contamination in is what makes C2 a real control dependency
    and gives the metamorphic relations a genuine fault to find.

    The bounds themselves remain available via ``apply_plausibility=True``
    for the ablation reported in the final report.
"""

from __future__ import annotations

import ast
import json
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

RAW_PATH = Path("data/raw/hyderabad.csv")
EXPECTED_SHA256 = (
    "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"
)

#: Int32 sentinel observed in MIN_PRICE/MAX_PRICE (D2).
INT32_SENTINEL = 2_147_483_647

#: The scrape date, taken as the latest observed POSTING_DATE in the frozen
#: file. Used to derive age-on-site. Hard-coded rather than recomputed so the
#: derived column cannot drift if the frame is ever filtered before loading.
SCRAPE_DATE = pd.Timestamp("2023-08-26", tz="UTC")

#: Bounding box used to reject implausible coordinates (Hyderabad metro).
HYDERABAD_BBOX = (16.5, 18.5, 77.5, 79.5)   # lat_min, lat_max, lon_min, lon_max

#: PROPERTY_TYPE values that are dwellings with a built-up area (D4).
DWELLING_TYPES = frozenset({
    "Residential Apartment",
    "Independent House/Villa",
    "Independent/Builder Floor",
    "Studio Apartment",
    "Serviced Apartments",
})

#: Plausibility bounds (D5). Chosen just outside the 1st/99th percentile of
#: the sale-dwelling population so that genuine luxury stock survives.
#: OFF by default -- see D5 in the module docstring.
AREA_SQFT_BOUNDS = (100.0, 20_000.0)
PRICE_INR_BOUNDS = (500_000.0, 500_000_000.0)
PSF_INR_BOUNDS = (1_000.0, 100_000.0)

_AREA_RE = re.compile(r"^([\d.,]+)\s*sq\.ft\.$", re.IGNORECASE)
_SQM_RE = re.compile(r"^([\d.,]+)\s*sq\.m\.$", re.IGNORECASE)
_PRICE_RE = re.compile(r"^([\d.,]+)\s*(L|Cr|K)?$", re.IGNORECASE)

#: Display-suffix -> rupee multiplier, for the STRICT-mode cross-check.
_PRICE_SUFFIX = {"l": 1e5, "cr": 1e7, "k": 1e3, "": 1.0}

CANONICAL_COLUMNS = [
    "listing_id", "month", "price_inr", "area_sqft", "psf_inr",
    "bhk", "locality", "property_type", "city",
    # Independent restatements of price and area, kept for the retrieval
    # agents' STRICT mode to cross-check against. Never used by the
    # deterministic statistics.
    "area_sqm_raw", "price_display_inr",
    # Secondary statistic (see MonthStat.median_age_on_site_days).
    "age_on_site_days",
    # Coordinates, for the radius/geo retrieval path selected by query_mode.
    "latitude", "longitude",
    # Listing prose. Used only by the Analysis agent's LLM review of
    # grey-zone outliers; never read by the deterministic statistics.
    "description",
]


@dataclass
class RejectLog:
    """How many rows each rule removed, and why. Printed into the report."""

    stages: dict[str, int] = field(default_factory=dict)

    def record(self, stage: str, remaining: int) -> None:
        self.stages[stage] = remaining

    def as_frame(self) -> pd.DataFrame:
        rows, prev = [], None
        for stage, remaining in self.stages.items():
            rows.append({
                "stage": stage,
                "rows_remaining": remaining,
                "rows_dropped": None if prev is None else prev - remaining,
            })
            prev = remaining
        return pd.DataFrame(rows)

    def __str__(self) -> str:
        return self.as_frame().to_string(index=False)


def verify_snapshot(path: Path = RAW_PATH) -> str:
    """Fail loudly if the frozen snapshot is not the one we audited."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower() != EXPECTED_SHA256.lower():
        raise RuntimeError(
            f"snapshot checksum mismatch for {path}\n"
            f"  expected {EXPECTED_SHA256}\n  found    {digest}\n"
            "Results are not reproducible against a changed snapshot."
        )
    return digest


def _parse_area_sqft(value: object) -> float | None:
    """Area in sqft from the display string. See D1 -- never MIN_AREA_SQFT."""
    if not isinstance(value, str):
        return None
    match = _AREA_RE.match(value.strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_sqm(value: object) -> float | None:
    """Area restated in sq.m from ``SECONDARY_AREA``, for cross-checking."""
    if not isinstance(value, str):
        return None
    match = _SQM_RE.match(value.strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_price_display(value: object) -> float | None:
    """Rupees from the ``PRICE`` display string, e.g. '69.25 L' -> 6_925_000.

    An independent restatement of the price: it comes from a different column
    than ``MIN_PRICE`` and is formatted for humans, so a disagreement between
    the two is evidence of a data-entry fault.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = _PRICE_RE.match(text)
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = (match.group(2) or "").lower()
    return number * _PRICE_SUFFIX[suffix]


def _parse_latlon(value: object) -> tuple[float | None, float | None]:
    """Latitude/longitude from the embedded ``MAP_DETAILS`` dict-literal.

    Coordinates outside the Hyderabad bounding box are discarded rather than
    trusted: 548 of 9,487 rows carry missing or out-of-area values, and a
    stray coordinate would silently enlarge a radius query's catchment.
    """
    if not isinstance(value, str) or not value.strip():
        return None, None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(parsed, dict):
            continue
        try:
            lat = float(parsed.get("LATITUDE"))
            lon = float(parsed.get("LONGITUDE"))
        except (TypeError, ValueError):
            return None, None
        lat_min, lat_max, lon_min, lon_max = HYDERABAD_BBOX
        if lat_min < lat < lat_max and lon_min < lon < lon_max:
            return lat, lon
        return None, None
    return None, None


def _parse_locality(value: object) -> str:
    """LOCALITY_NAME out of the embedded ``location`` dict-literal column."""
    if not isinstance(value, str) or not value.strip():
        return "Unknown"
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict):
            name = parsed.get("LOCALITY_NAME")
            return str(name).strip() if name else "Unknown"
    return "Unknown"


def load_canonical(
    path: Path = RAW_PATH,
    *,
    verify: bool = True,
    apply_plausibility: bool = False,
) -> tuple[pd.DataFrame, RejectLog]:
    """Load the raw snapshot into the canonical listing frame.

    Returns the frame plus the reject log. The frame is the *only* input the
    agents ever see, and the unit of every metamorphic transformation.
    """
    if verify:
        verify_snapshot(path)

    raw = pd.read_csv(path, low_memory=False)
    log = RejectLog()
    log.record("raw rows", len(raw))

    df = raw[raw["PREFERENCE"] == "S"].copy()              # D3
    log.record("sale only (PREFERENCE=S)", len(df))

    df = df[df["PROPERTY_TYPE"].isin(DWELLING_TYPES)]      # D4
    log.record("dwellings only", len(df))

    posted = pd.to_datetime(
        pd.to_numeric(df["POSTING_DATE"], errors="coerce"),
        unit="ms", errors="coerce", utc=True,
    )
    df = df.assign(_posted=posted).dropna(subset=["_posted"])
    log.record("parseable POSTING_DATE", len(df))

    price = pd.to_numeric(df["MIN_PRICE"], errors="coerce")  # D2
    df = df.assign(_price=price)
    df = df[df["_price"].notna()
            & (df["_price"] > 0)
            & (df["_price"] < INT32_SENTINEL)]
    log.record("price not zero/sentinel", len(df))

    area = df["AREA"].map(_parse_area_sqft)                  # D1
    df = df.assign(_area=area).dropna(subset=["_area"])
    df = df[df["_area"] > 0]
    log.record("parseable AREA (sqft)", len(df))

    df = df.assign(_psf=df["_price"] / df["_area"])

    if apply_plausibility:                                   # D5, off by default
        lo, hi = AREA_SQFT_BOUNDS
        df = df[df["_area"].between(lo, hi)]
        log.record(f"area in [{lo:,.0f}, {hi:,.0f}] sqft", len(df))

        lo, hi = PRICE_INR_BOUNDS
        df = df[df["_price"].between(lo, hi)]
        log.record("price within plausibility bounds", len(df))

        lo, hi = PSF_INR_BOUNDS
        df = df[df["_psf"].between(lo, hi)]
        log.record(f"psf in [{lo:,.0f}, {hi:,.0f}] INR/sqft", len(df))
    else:
        log.record("plausibility bounds DEFERRED to Analysis recomputation", len(df))

    bhk = pd.to_numeric(df["BEDROOM_NUM"], errors="coerce")

    # Age on site at the scrape date. Right-censored and length-biased; see
    # MonthStat.median_age_on_site_days for why it is not "days on market".
    age_days = (SCRAPE_DATE - df["_posted"]).dt.days.astype(float)
    age_days = age_days.where(age_days.between(0, 1000))

    coords = df["MAP_DETAILS"].map(_parse_latlon)

    canonical = pd.DataFrame({
        "listing_id": df["PROP_ID"].astype(str).to_numpy(),
        "month": df["_posted"].dt.strftime("%Y-%m").to_numpy(),
        "price_inr": df["_price"].astype(float).to_numpy(),
        "area_sqft": df["_area"].astype(float).to_numpy(),
        "psf_inr": df["_psf"].astype(float).to_numpy(),
        "bhk": bhk.to_numpy(),
        "locality": df["location"].map(_parse_locality).to_numpy(),
        "property_type": df["PROPERTY_TYPE"].astype(str).to_numpy(),
        "city": df["CITY"].astype(str).to_numpy(),
        "area_sqm_raw": df["SECONDARY_AREA"].map(_parse_sqm).to_numpy(),
        "price_display_inr": df["PRICE"].map(_parse_price_display).to_numpy(),
        "age_on_site_days": age_days.to_numpy(),
        "latitude": [c[0] for c in coords],
        "longitude": [c[1] for c in coords],
        "description": df["DESCRIPTION"].astype(str).str.slice(0, 400).to_numpy(),
    })[CANONICAL_COLUMNS].reset_index(drop=True)

    log.record("canonical listings", len(canonical))
    return canonical, log


def freeze_canonical(
    out_path: Path = Path("data/snapshot/listings_canonical.csv"),
) -> pd.DataFrame:
    """Materialise the canonical frame next to its reject log and checksum."""
    frame, log = load_canonical()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_path, index=False)

    log.as_frame().to_csv(
        out_path.with_name("canonical_reject_log.csv"), index=False
    )
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    out_path.with_name("CHECKSUMS.txt").write_text(
        f"{digest}  {out_path.name}\n"
    )
    return frame


if __name__ == "__main__":
    frame, log = load_canonical()
    print("=== filter cascade ===")
    print(log)
    print("\n=== canonical frame ===")
    print(frame.head(8).to_string(index=False))
    print("\nrows:", len(frame), " months:", frame["month"].nunique(),
          " localities:", frame["locality"].nunique())
