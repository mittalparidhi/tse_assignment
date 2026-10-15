# Hyderabad Snapshot: Anomaly Investigation

## Scope and integrity

The audit used `data/raw/hyderabad.csv`, covering September 2022 through August 2023.
The frozen raw SHA-256 was verified as:

`9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`

The raw dataset was not modified. No records were removed or balanced.

## Finding 1 — Listing-volume changes (AN-03)

- February 2023: 45 observed rows.
- March 2023: 217 observed rows, approximately 4.82 times February.
- June 2023: 947 observed rows.
- July 2023: 3,447 observed rows, approximately 3.64 times June.
- July has postings across all 31 calendar dates; August has postings across 26 observed dates.
- Distinct locality names rise from 232 in June to 468 in July and 436 in August.
- Only one repeated property ID was observed in July, accounting for two rows.

**Diagnosis:** The count increases are substantial and distributed across dates and localities. The inspected duplicate ID does not explain the increases. Changes in source coverage, ingestion behavior, or listing composition remain possible; the available snapshot does not identify the cause.

**Limitation:** No explicit crawl timestamp or collection-batch field was identified in the column-name audit.

## Finding 2 — Aggregate price changes (AN-01)

The overall median minimum sale price changed as follows:

- December 2022 to January 2023: INR 6,351,485 to INR 13,500,000 (+112.55%).
- February to March 2023: INR 9,150,000 to INR 6,500,000 (-28.96%).
- March to April 2023: INR 6,500,000 to approximately INR 10,235,002 (+57.46%).

Property-type composition changes substantially around March:

- Residential-land share among valid sale-price rows rises from 34.21% in February to 58.58% in March, then falls to 34.44% in April.
- Residential-land median minimum price changes from INR 5,995,300 in February to INR 2,260,000 in March and INR 3,800,000 in April.
- Apartment and independent-house/villa medians do not always move in the same direction as the overall median.

**Diagnosis:** Both composition shifts and within-category changes appear relevant. The aggregate medians should not be interpreted as direct evidence of market-wide price movements.

**Limitation:** February has 38 valid sale-price rows and March has 169. Locality-specific medians based on very small counts are unstable.

## Finding 3 — Final-two-month concentration (AN-04)

July and August contain 6,978 of the 9,162 in-window rows, or 76.16%. July has 3,447 rows and August has 3,531 rows.

August is a partial month, with observed postings through August 26.

**Diagnosis:** The concentration is a valid characteristic of the frozen snapshot and deserves explicit reporting. It must not be treated as market share or used to extrapolate August.

**Limitation:** Listing counts alone do not distinguish market activity from source coverage or collection effects.

## Additional data-quality observations

- Several records produce extreme price/area ratios when `MIN_PRICE` is divided by a numeric area extracted from `AREA`, including records with very small or very large reported areas.
- Multiple records share property type, locality, area, and price signatures while having distinct property IDs. These may reflect repeated templates or multiple similar listings; signature equality does not establish exact duplication.
- The official `PRICE_SQFT` metric remains unverified. The derived price/area ratio in the audit is a review proxy, not a replacement metric.

These observations are candidates for manual review. They are not grounds for automatic removal.

## Reproducibility and decision

- Preserve the raw CSV and its frozen checksum.
- Keep August marked as partial.
- Do not balance monthly counts for the primary analysis.
- Do not deduplicate based solely on property ID or price/area signatures.
- Do not alter anomaly thresholds without further evidence.
- Keep the current deterministic anomaly rules and document their limitations.
