# External cross-check: NHB RESIDEX

**Source.** National Housing Bank, *Press Release July–September 2023*,
RESIDEX portal (`residex.nhbonline.org.in`). PDF retained alongside this file.

**Quoted verbatim:**

> "India's eight key primary residential markets witnessed appreciating
> property prices during the Jul-Sep 2023 period. Ahmedabad (6.1%), Bengaluru
> (8.2%), Chennai (1.8%), Delhi (1.8%), **Hyderabad (6.8%)**, Kolkata (9.1%),
> Mumbai (3.6%) & Pune (6.1%) recorded increase in the index on an annual basis
> as per the Housing Price Index published by National Housing Bank."

**Why this index is the right comparator.** NHB publishes two series. The one
quoted — *HPI @ Market Price* — is described in the same release as "based on
**Asking Price** of Unsold & under-construction properties by builders and
developers." Our measure is also an asking-price series (§2, `POSTING_DATE` and
`MIN_PRICE`), so the comparison is methodologically matched rather than
approximate. The alternative series, HPI @ Assessment Price, is based on
lender valuations and would not be comparable.

**Comparison.** Our window is Sep 2022 – Aug 2023; the RESIDEX figure is
year-on-year for the quarter ending Sep 2023, so the periods overlap closely.

| Source | Hyderabad, annual change |
|--------|--------------------------|
| **NHB RESIDEX, HPI @ Market Price** | **+6.8%** |
| our snapshot, n ≥ 75 | **+7.08%** |
| our snapshot, n ≥ 100 | +7.08% |
| our 3 km IT-corridor radius slice | +6.24% |
| **our snapshot, n ≥ 50 (the shipped contract)** | **−6.41%** |

**Conclusion.** Three independent readings of our own data — two sufficiency
thresholds and a radius slice — agree with the official index to within 0.6
percentage points, and at n ≥ 75 to within **0.3**. The n ≥ 50 figure the
shipped contract produces is the outlier, and it has the **wrong sign**.

This converts §9's threshold-sensitivity finding from "the headline is not
robust" into something stronger and more specific: **the headline is wrong, and
the reason is the sufficiency threshold rather than the data.** At a threshold
that excludes the noisiest months, the pipeline recovers the published index
almost exactly — which is simultaneously the strongest validation of the
method in this project and the clearest indictment of the n ≥ 50 choice.

**What we did not do.** We did not retrieve the earlier quarterly releases
(Jul–Sep 2022 and Oct–Dec 2022 returned empty responses from the portal), so we
have one overlapping data point rather than a quarterly series. A full series
would allow a month-by-month comparison instead of a single annual figure.
