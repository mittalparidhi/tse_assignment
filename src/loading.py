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
    (= 2**31 - 1) on 5 rows, and 0 on 75 rows. Both are dropped. A row is
    kept only if both bounds are real prices and ``MIN_PRICE <= MAX_PRICE``
    (contract v2 decision 7: both medians are reported; MIN_PRICE is the
    asking price used for price per sqft).

D3  ``PREFERENCE`` mixes sale (S, 7,927), rent (R, 1,467) and PG (P, 93).
    Mixing rent into an asking-price median is meaningless; sale only.

D4  ``BEDROOM_NUM`` is missing on 2,814 rows, of which 2,806 are
    ``Residential Land``. This is not missing data -- plots have no bedrooms.
    Restricting to dwellings removes the missingness *and* makes price per
    built-up area comparable. Of the rows where both exist, heading-derived
    BHK agrees with ``BEDROOM_NUM`` on 6,041 and conflicts on 0.

D6  ``PRICE`` reads "Price on Request" on 87 raw rows: the seller published no
    price, so the numeric bounds are placeholders, not asking prices. Dropped.

Months are derived in Asia/Kolkata, never UTC (contract v2 decision 4).

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

#: Months are local calendar months. POSTING_DATE is an absolute instant (Unix
#: ms); deriving the month in UTC would put listings posted between 00:00 and
#: 05:30 IST into the previous month (18 canonical rows).
LOCAL_TIMEZONE = "Asia/Kolkata"

#: The latest POSTING_DATE in the frozen raw file, in local time. It marks
#: 2023-08 as a partial month and is the reference for age-on-site. Hard-coded
#: rather than recomputed so the derived column cannot drift if the frame is
#: ever filtered before loading.
LATEST_POSTING = pd.Timestamp("2023-08-26 10:29:05", tz=LOCAL_TIMEZONE)

#: Display text meaning the seller published no price (D6). These rows carry
#: placeholder numbers in MIN_PRICE/MAX_PRICE that are not asking prices.
PRICE_ON_REQUEST_RE = r"\bprice\s+on\s+request\b"

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

#: Display-suffix -> rupee multiplier, for the Analysis agent's cross-check.
_PRICE_SUFFIX = {"l": 1e5, "cr": 1e7, "k": 1e3, "": 1.0}

CANONICAL_COLUMNS = [
    "listing_id", "month", "price_inr", "max_price_inr", "area_sqft",
    "psf_inr", "bhk", "locality", "property_type", "city",
    # Independent restatements of price and area, kept for the Analysis
    # agent's targeted recomputation to cross-check against. Never used by
    # the deterministic statistics.
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
    ).dt.tz_convert(LOCAL_TIMEZONE)
    df = df.assign(_posted=posted).dropna(subset=["_posted"])
    log.record("parseable POSTING_DATE", len(df))

    on_request = df["PRICE"].astype("string").str.contains(   # D6
        PRICE_ON_REQUEST_RE, case=False, regex=True, na=False)
    df = df[~on_request]
    log.record("not Price on Request", len(df))

    # D2. A price range is usable only if both bounds are real prices and
    # coherent; MIN_PRICE is the asking price, MAX_PRICE its upper bound.
    price = pd.to_numeric(df["MIN_PRICE"], errors="coerce")
    max_price = pd.to_numeric(df["MAX_PRICE"], errors="coerce")
    df = df.assign(_price=price, _max_price=max_price)
    df = df[df["_price"].notna()
            & (df["_price"] > 0)
            & (df["_price"] < INT32_SENTINEL)]
    log.record("MIN_PRICE not zero/sentinel", len(df))
    df = df[df["_max_price"].notna()
            & (df["_max_price"] > 0)
            & (df["_max_price"] < INT32_SENTINEL)
            & (df["_price"] <= df["_max_price"])]
    log.record("MAX_PRICE valid and >= MIN_PRICE", len(df))

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

    # Age on site at the latest posting. Right-censored and length-biased; see
    # MonthStat.median_age_on_site_days for why it is not "days on market".
    age_days = (LATEST_POSTING - df["_posted"]).dt.days.astype(float)
    age_days = age_days.where(age_days.between(0, 1000))

    coords = df["MAP_DETAILS"].map(_parse_latlon)

    canonical = pd.DataFrame({
        "listing_id": df["PROP_ID"].astype(str).to_numpy(),
        "month": df["_posted"].dt.strftime("%Y-%m").to_numpy(),
        "price_inr": df["_price"].astype(float).to_numpy(),
        "max_price_inr": df["_max_price"].astype(float).to_numpy(),
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
    # Carried with the frame so reports can name the snapshot they describe.
    canonical.attrs["snapshot_sha256"] = EXPECTED_SHA256 if verify else None
    return canonical, log


def canonical_csv_bytes(frame: pd.DataFrame) -> bytes:
    """The exact bytes ``freeze_canonical`` writes, so a test can check that a
    rebuilt frame still matches the frozen copy without writing a file.
    The line terminator is fixed so the digest does not depend on the OS."""
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def freeze_canonical(
    out_path: Path = Path("data/snapshot/listings_canonical.csv"),
) -> pd.DataFrame:
    """Materialise the canonical frame next to its reject log and checksum."""
    frame, log = load_canonical()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canonical_csv_bytes(frame))

    # Explicit "\n" so the files, and the digest, are identical on Windows.
    log.as_frame().to_csv(
        out_path.with_name("canonical_reject_log.csv"), index=False,
        lineterminator="\n",
    )
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    out_path.with_name("CHECKSUMS.txt").write_text(
        f"{digest}  {out_path.name}\n", newline="\n"
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
