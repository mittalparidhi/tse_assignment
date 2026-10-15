"""Generate a synthetic Hyderabad-shaped snapshot with a KNOWN ground truth.

Why this exists
---------------
The real snapshot cannot distinguish two of the brief's four root-cause
categories. If a relation is violated on 99acres data we cannot tell a
**harness bug** from a **data artifact**, because we do not know what the
correct answer was. Synthetic data fixes that: the trend is constructed, so
the correct answer is known by definition.

It gives two things the real snapshot cannot:

1. **A genuine oracle.** ``verify_ground_truth`` checks that ``compute_trend``
   recovers the growth rate that was put in. Metamorphic testing deliberately
   works without an oracle; where one is available it would be careless not
   to use it, and a harness that passes its relations while miscomputing the
   median would be caught here and nowhere else.
2. **Uniform monthly depth.** Every month holds the same number of listings,
   so the thin-month noise that dominates the real snapshot is absent. A
   relation that holds here but fails on real data is pointing at the data,
   not at the code.

Deliberate contamination
------------------------
A controlled fraction of listings carry an implausible price-per-sqft, so
cycle 2 has something real to catch. Their ids are prefixed ``OUT`` and the
count is recorded, which means the diagnosis can check whether STRICT mode
caught exactly the injected rows rather than merely "some" rows.

    python scripts/make_synthetic.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loading import CANONICAL_COLUMNS          # noqa: E402
from src.trend import Criteria, compute_trend, month_window  # noqa: E402

OUT_PATH = Path("data/snapshot/listings_synthetic.csv")
TRUTH_PATH = Path("data/snapshot/synthetic_ground_truth.json")

SEED = 20231013
WINDOW_END = "2023-08"
LISTINGS_PER_MONTH = 400          # uniform depth; large enough that the
                                  # median's sampling error is under 1%
OUTLIER_FRACTION = 0.02           # share carrying an implausible psf
MONTHLY_GROWTH = 0.010            # +1.0% per month in median psf -- the truth
PSF_LOG_SIGMA = 0.12              # multiplicative noise, symmetric in log
BASE_PSF = 7_000.0                # starting median price per sqft

#: Locality -> multiplier on the base psf. The rank order is therefore known
#: in advance, which is what MR-I2's ranking-invariance claim is checked against.
LOCALITY_FACTORS: dict[str, float] = {
    "Jubilee Hills":  1.80,
    "Gachibowli":     1.40,
    "Kondapur":       1.15,
    "Narsingi":       1.00,
    "Bachupally":     0.85,
    "Kollur":         0.70,
}

BHK_AREA = {1: 650.0, 2: 1150.0, 3: 1650.0, 4: 2400.0}
BHK_WEIGHTS = {1: 0.05, 2: 0.35, 3: 0.45, 4: 0.15}


def generate(seed: int = SEED) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    months = month_window(WINDOW_END)
    localities = list(LOCALITY_FACTORS)
    bhks = list(BHK_AREA)
    weights = np.array([BHK_WEIGHTS[b] for b in bhks])

    rows: list[dict] = []
    n_outliers = 0
    for month_index, month in enumerate(months):
        # The ground truth: median psf compounds at MONTHLY_GROWTH.
        month_psf = BASE_PSF * (1.0 + MONTHLY_GROWTH) ** month_index

        for i in range(LISTINGS_PER_MONTH):
            locality = localities[i % len(localities)]
            bhk = int(rng.choice(bhks, p=weights))
            area = BHK_AREA[bhk] * float(rng.normal(1.0, 0.04))
            area = float(np.clip(area, 300.0, 6000.0))

            # Multiplicative, symmetric-in-log noise so the MEDIAN of the
            # month stays at month_psf * factor rather than drifting upward
            # the way additive noise on a skewed variable would.
            noise = float(np.exp(rng.normal(0.0, PSF_LOG_SIGMA)))
            psf = month_psf * LOCALITY_FACTORS[locality] * noise

            is_outlier = rng.random() < OUTLIER_FRACTION
            listing_id = f"SYN{month_index:02d}{i:04d}"
            if is_outlier:
                psf *= float(rng.choice([0.02, 45.0]))   # far outside the band
                listing_id = f"OUT{month_index:02d}{i:04d}"
                n_outliers += 1

            price = psf * area
            rows.append({
                "listing_id": listing_id,
                "month": month,
                "price_inr": price,
                "area_sqft": area,
                "psf_inr": psf,
                "bhk": float(bhk),
                "locality": locality,
                "property_type": "Residential Apartment",
                "city": "Hyderabad",
                "area_sqm_raw": area / 10.7639104,
                "price_display_inr": price,
            })

    frame = pd.DataFrame(rows)[CANONICAL_COLUMNS]
    truth = {
        "seed": seed,
        "psf_log_sigma": PSF_LOG_SIGMA,
        "pooled_median_factor": pooled_median_factor(),
        "window_end": WINDOW_END,
        "months": list(months),
        "listings_per_month": LISTINGS_PER_MONTH,
        "monthly_growth": MONTHLY_GROWTH,
        "base_psf": BASE_PSF,
        "expected_total_pct_change": ((1 + MONTHLY_GROWTH) ** 11 - 1) * 100,
        "locality_factors": LOCALITY_FACTORS,
        "expected_locality_rank_order": sorted(
            LOCALITY_FACTORS, key=LOCALITY_FACTORS.get, reverse=True
        ),
        "n_outliers_injected": n_outliers,
        "outlier_id_prefix": "OUT",
        "n_rows": len(frame),
    }
    return frame, truth


def pooled_median_factor(
    factors: dict[str, float] = LOCALITY_FACTORS,
    sigma: float = PSF_LOG_SIGMA,
) -> float:
    """Median of ``factor x lognormal(0, sigma)`` pooled over equal-weight
    localities.

    This matters, and getting it wrong is instructive. A first version of this
    oracle expected the monthly median to equal ``base_psf * (1+g)**i``, which
    silently assumed every listing sat at the base price. Listings are spread
    across six localities with factors 0.70-1.80, so the pooled median is
    ``month_psf`` times the median of the mixture -- about 1.075 here, not 1.0.
    The oracle duly "failed" with a 4-12% positive bias that was entirely the
    oracle's own error. Recorded in NOTEBOOK.md.

    Solved numerically rather than sampled, so the expectation carries no
    Monte-Carlo error of its own.
    """
    from scipy.optimize import brentq
    from scipy.stats import norm

    values = list(factors.values())

    def excess_mass(m: float) -> float:
        # Fraction of the mixture below m, minus one half.
        below = sum(norm.cdf((np.log(m) - np.log(f)) / sigma) for f in values)
        return below / len(values) - 0.5

    lo, hi = min(values) * 0.1, max(values) * 10.0
    return float(brentq(excess_mass, lo, hi, xtol=1e-12))


def median_rel_stderr(n: int, sigma: float = PSF_LOG_SIGMA) -> float:
    """Relative standard error of a sample median.

    For a continuous distribution the median's asymptotic standard error is
    ``1/(2 f(m) sqrt(n))``; for a log-normal that reduces to
    ``1.2533 * sigma / sqrt(n)`` in relative terms. Used to set the oracle's
    tolerance from the design rather than from a guessed percentage.
    """
    return 1.2533 * sigma / np.sqrt(n)


def _bonferroni_z(n_tests: int, family_alpha: float = 0.01) -> float:
    """Two-sided z for ``n_tests`` simultaneous comparisons."""
    from scipy.stats import norm
    return float(norm.ppf(1.0 - family_alpha / (2.0 * n_tests)))


def verify_ground_truth(frame: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Does ``compute_trend`` recover the trend that was constructed?

    This is the oracle the real snapshot cannot provide. Outliers are excluded
    here because the question is whether the *statistics* are right, not
    whether the agents filter correctly -- that is what cycle 2 is for.
    """
    clean = frame[~frame["listing_id"].str.startswith("OUT")]
    report = compute_trend(clean, Criteria(window_end=truth["window_end"]))
    mix = truth["pooled_median_factor"]

    rows = []
    for index, stat in enumerate(report.monthly):
        expected = (truth["base_psf"]
                    * (1 + truth["monthly_growth"]) ** index
                    * mix)
        # Bonferroni-corrected per-month bound: twelve simultaneous tests at
        # a family-wise 1% level, not twelve independent 3-SE gates. With an
        # uncorrected 3-SE bound the chance that at least one of twelve months
        # trips is about 3%, so a passing system fails the oracle roughly one
        # run in thirty -- which is a property of the test, not the code.
        tol = (_bonferroni_z(12, 0.01) * median_rel_stderr(stat.n_active) * 100
               if stat.n_active else None)
        err = (None if not stat.median_psf
               else (stat.median_psf - expected) / expected * 100)
        rows.append({
            "month": stat.month,
            "n_active": stat.n_active,
            "expected_median_psf": expected,
            "observed_median_psf": stat.median_psf,
            "rel_error_pct": err,
            "tolerance_bonf_pct": tol,
            "within_tolerance": (None if err is None or tol is None
                                 else abs(err) <= tol),
        })
    return pd.DataFrame(rows)


def main() -> int:
    frame, truth = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT_PATH, index=False)

    digest = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    truth["sha256"] = digest

    import json
    TRUTH_PATH.write_text(json.dumps(truth, indent=2))

    print(f"wrote {OUT_PATH}  rows={len(frame):,}  sha256={digest[:16]}...")
    print(f"injected outliers: {truth['n_outliers_injected']} "
          f"({truth['n_outliers_injected']/len(frame)*100:.2f}%)")
    print(f"constructed growth: +{truth['monthly_growth']*100:.1f}%/month "
          f"= +{truth['expected_total_pct_change']:.2f}% over 11 steps\n")

    check = verify_ground_truth(frame, truth)
    print("=== ORACLE CHECK: does compute_trend recover the known trend? ===")
    print(check.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))

    import numpy as _np
    errors = check["rel_error_pct"].dropna().to_numpy()
    per_month_ok = bool(check["within_tolerance"].all())
    tol = check["tolerance_bonf_pct"].iloc[0]

    # The decisive test. A genuine defect -- a wrong quantile, a unit error, an
    # off-by-one in bucketing -- biases EVERY month in the same direction. That
    # shows up in the mean error, whose standard error is 1/sqrt(12) of a
    # single month's, giving far more power than any per-month bound.
    n_months = len(errors)
    mean_err = float(errors.mean())
    mean_se = float(median_rel_stderr(int(check["n_active"].mean())) * 100
                    / _np.sqrt(n_months))
    bias_z = mean_err / mean_se
    bias_ok = abs(bias_z) <= 3.0

    print(f"\npooled median factor (locality mix): "
          f"{truth['pooled_median_factor']:.4f}")
    print(f"per-month errors within Bonferroni bound (+-{tol:.2f}%): "
          f"{per_month_ok}  (worst {_np.abs(errors).max():.2f}%)")
    print(f"systematic bias test: mean error {mean_err:+.3f}% "
          f"+- {mean_se:.3f}% SE  -> z = {bias_z:+.2f}  (|z| <= 3 required)")
    verdict = "PASS" if per_month_ok and bias_ok else "FAIL"
    print(f"oracle verdict: {verdict}")

    observed = compute_trend(
        frame[~frame["listing_id"].str.startswith("OUT")],
        Criteria(window_end=truth["window_end"]),
    )
    # Endpoint-to-endpoint move, with the sampling error it inherits from two
    # medians, so "close enough" is a stated interval rather than a feeling.
    import numpy as _np2
    se_end = median_rel_stderr(LISTINGS_PER_MONTH) * _np2.sqrt(2) * 100
    obs_move = observed.yoy_median_psf_pct
    exp_move = truth["expected_total_pct_change"]
    print(f"\nrecovered total move: {obs_move:+.2f}% "
          f"over {observed.yoy_span_months} months "
          f"(constructed {exp_move:+.2f}%, endpoint SE ~{se_end:.2f}%, "
          f"z = {(obs_move - exp_move) / se_end:+.2f})")
    print(f"recovered rank order: {observed.ranking_order()}")
    print(f"constructed  order  : {truth['expected_locality_rank_order']}")
    print(f"rank order matches  : "
          f"{observed.ranking_order() == truth['expected_locality_rank_order']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
