# Prompt for Lovable — dashboard UI

Paste everything inside the box below into Lovable as **one message**. It is
written to be built in a single pass (the free plan has few messages a day):
front end only, no backend, no login, no database, with the project's real
results embedded as sample data. The working application remains the
Streamlit dashboard (`app.py`); this UI presents the same report and results.

````text
Build a clean, professional, single-page web dashboard in ONE pass. Front end only: React + TypeScript + Tailwind + shadcn/ui + Recharts. Do NOT add a backend, Supabase, authentication, a database, payments or any external API. All data comes from two local JSON files that you create from the samples at the end of this prompt (src/data/report.json and src/data/relations.json). Keep the number of elements small: no hero section, no marketing copy, no images, no emojis, no gradients, no animations beyond subtle hover states.

## What the app is
"Hyderabad Housing Trends" — a multi-agent application that reports how residential asking prices (median ₹ per sq ft) moved over 12 months for user-chosen criteria, and a metamorphic-testing view of how reliably the system behaves. Data: a frozen snapshot of 99acres.com Hyderabad listings (scraped 26 Aug 2023).

## Visual design
- Fonts: body and headings in the serif stack `"Times New Roman", Georgia, serif`; all numbers, IDs, months and code in `Consolas, "Courier New", monospace`. Headings semibold, generous line height, base size 15px.
- Colours: page #FAFAF7, cards #FFFFFF with a 1px #E5E5E0 border and 8px radius, text #1A1A1A, secondary text #5F5F5A, one accent #1F5F5B (deep teal) for primary actions and the main chart line. Status colours, muted: ADEQUATE #2E7D4F, LIMITED #B7791F, NO DATA #9A9A94, violation/red #B03A2E.
- Layout: top bar (title left; small "Frozen snapshot · SHA-256 9e81698…" in monospace right). Below it a left sidebar 300px wide with the criteria form, and a main area with three tabs: Trend, Relations, Data & method. Max content width 1280px. Responsive: on narrow screens the sidebar collapses into a "Criteria" sheet.

## Sidebar — search criteria (compact form)
1. City: select (Hyderabad, Secunderabad).
2. Retrieval algorithm: segmented control "Exact locality" | "Radius". Exact locality shows a searchable multi-select of localities (Gachibowli, Kondapur, Kokapet, Narsingi, Kollur, Nallagandla, Puppalaguda, Tellapur, Nanakramguda, Financial District). Radius shows radius (km slider 1–40, default 5) and centre latitude/longitude inputs (defaults 17.4401, 78.3489).
3. BHK: toggle chips 1, 2, 3, 4, 5+ (multi-select).
4. Price band: min and max inputs in ₹ lakh, optional.
5. Window ends: month select (2023-03 … 2023-08, default 2023-08); show "12 months: Sep 2022 – Aug 2023" under it.
6. Display units: two small toggles, "₹ lakh / ₹ crore" and "sq ft / sq m". These change only how values are displayed, never the underlying numbers (percentages and rankings must not change when toggled).
7. Primary button "Run analysis". Since there is no backend, it loads report.json and shows a small muted note: "Showing the saved result for 3 BHK · Gachibowli; connect the Python service for live runs." Validate inputs inline (e.g. min price must be below max) with short messages under the field.

## Tab 1 — Trend (default)
- A row of four stat cards:
  1. "Median ₹/sqft move": yoy_median_psf_pct formatted with sign and one decimal, subtitle "between the first and last sufficient month (spans {yoy_span_months} months)".
  2. "Listings analysed": n_price_valid_total, subtitle "{n_listings_total} matched; the rest lack a usable price".
  3. "Coverage": count of months with coverage_status ADEQUATE out of 12, plus a badge with coverage_verdict (ACCEPT green / LIMITED amber).
  4. "Outliers rejected": n_rejected_outliers, subtitle "by the critique feedback loop".
- One line chart (Recharts) of median ₹/sqft per month: teal line with dots; null months leave a gap (do not draw zero); months that are not sufficient drawn with hollow dots and a lighter line; the partial month (is_partial_month) gets a dashed vertical marker labelled "partial: data to 26 Aug". Directly under it, a small bar chart sharing the x-axis with listing_count per month (grey bars) and price_valid_count (teal bars). Tooltips show all values for the month in monospace.
- Monthly table: Month · Listings · Price-valid · Median ₹/sqft · Coverage (status badge). Null shown as "—".
- "Summary" card: the narrative text, and under it the relaxations as a short list titled "How your query was widened".
- "Most expensive localities": a numbered list of locality_rankings (top 5).
- Collapsible card "Agent trace (loops firing)": a vertical timeline from trace[]. Each step shows its number, agent name (monospace) and the detail. Steps whose detail contains "cycle 1" get a small teal tag "Cycle 1 · coverage → retrieval"; "cycle 2" gets "Cycle 2 · critique → analysis". This shows the feedback loops actually running.

## Tab 2 — Relations (metamorphic testing)
- Short intro line: "Each relation transforms the input, re-runs the system and checks the outputs relate as stated. Unit = base input (72), seeds 11, 23, 47; 95% Wilson intervals."
- A segmented control: "Deterministic" | "With local model (LLM)".
- One table: ID · Family (small badge: Invariance / Monotonic / Directional) · Transformation · Bases · Violation rate · 95% CI. Render the CI as a thin horizontal bar on a 0–1 scale with the interval shaded and a dot at the rate; rate 0 shows a green "holds" label; M1raw shows a grey tag "counter-example". Sort by family then ID.
- Below the table, three small cards for the most-violated relations (M1raw, M1, D2) showing their one-line verdict from relations.json.

## Tab 3 — Data & method
- "Data source" card as a definition list: dataset, origin, licence, scrape date, raw rows, canonical listings, price-valid listings, snapshot SHA-256 (monospace, truncated with copy button).
- "Agent architecture" card: a simple SVG diagram of six boxes in a flow: Criteria → Retrieval ×4 → Coverage → Analysis → Critique → Aggregator, with two curved arrows drawn in the accent colour and labelled: "Cycle 1: widen criteria (coverage < target)" from Coverage back to Retrieval, and "Cycle 2: recompute flagged months" from Critique back to Analysis. Under it one sentence each for: feedback loop, conditional step, genuine dependency (query mode chooses a different retrieval algorithm).
- "Reproduce" card: a code block with `python scripts/headline_table.py --v2 --check` and `python scripts/replay_llm_sweep.py`.

## Quality bar
Accessible (labels on every input, visible focus rings, colour never the only signal), keyboard navigable, no layout shift on tab change, numbers right-aligned in tables, Indian number formatting (₹10,145; 1,23,456 style for lakh values), consistent 8px spacing scale. Code split into small components (CriteriaPanel, StatCards, TrendChart, MonthlyTable, AgentTrace, RelationsTable, DataSource, ArchitectureDiagram) and a typed data layer (src/types.ts) so the JSON can later come from an API.

## src/data/report.json (use exactly)
{
  "criteria": {"city": "Hyderabad", "query_mode": "EXACT_LOCALITY", "localities": ["Gachibowli"], "bhk": [3], "price_min_lakh": null, "price_max_lakh": null, "window_end": "2023-08"},
  "window_months": ["2022-09","2022-10","2022-11","2022-12","2023-01","2023-02","2023-03","2023-04","2023-05","2023-06","2023-07","2023-08"],
  "monthly": [
    {"month":"2022-09","listing_count":2,"price_valid_count":2,"median_price_per_sqft_inr":7916.4,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2022-10","listing_count":0,"price_valid_count":0,"median_price_per_sqft_inr":null,"coverage_status":"NO_DATA_IN_SNAPSHOT","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2022-11","listing_count":1,"price_valid_count":1,"median_price_per_sqft_inr":9000.0,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2022-12","listing_count":2,"price_valid_count":2,"median_price_per_sqft_inr":10190.8,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-01","listing_count":5,"price_valid_count":4,"median_price_per_sqft_inr":10352.8,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-02","listing_count":1,"price_valid_count":1,"median_price_per_sqft_inr":9490.6,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-03","listing_count":8,"price_valid_count":7,"median_price_per_sqft_inr":11038.6,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-04","listing_count":12,"price_valid_count":11,"median_price_per_sqft_inr":10000.0,"coverage_status":"LIMITED","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-05","listing_count":39,"price_valid_count":34,"median_price_per_sqft_inr":10495.3,"coverage_status":"ADEQUATE","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-06","listing_count":59,"price_valid_count":49,"median_price_per_sqft_inr":10790.9,"coverage_status":"ADEQUATE","month_is_sufficient":false,"is_partial_month":false},
    {"month":"2023-07","listing_count":298,"price_valid_count":279,"median_price_per_sqft_inr":10217.4,"coverage_status":"ADEQUATE","month_is_sufficient":true,"is_partial_month":false},
    {"month":"2023-08","listing_count":269,"price_valid_count":242,"median_price_per_sqft_inr":10145.9,"coverage_status":"ADEQUATE","month_is_sufficient":true,"is_partial_month":true}
  ],
  "yoy_median_psf_pct": -0.70,
  "yoy_span_months": 2,
  "n_listings_total": 696,
  "n_price_valid_total": 632,
  "coverage_score": 0.333,
  "coverage_verdict": "LIMITED",
  "n_rejected_outliers": 17,
  "locality_rankings": ["Nanakramguda", "Gachibowli", "P Janardhan Reddy Nagar", "Kondapur", "Financial District"],
  "relaxations": ["Localities widened by the 15 nearest neighbouring localities", "BHK widened from 3 to 2–4"],
  "narrative": "Over the twelve months to August 2023, 3 BHK homes around Gachibowli moved −0.7% in median asking price per sq ft, measured across the two months with enough listings. 632 of 696 matching listings had a usable price; your query was too narrow and was widened to nearby localities and 2–4 BHK. August 2023 is a partial month (data to 26 August).",
  "trace": [
    {"step":7,"agent":"RetrievalMerge","detail":"4 agents, round 0: 120 listings"},
    {"step":8,"agent":"CoverageAgent","detail":"coverage 0.17 (2 of 7 attainable months) → RETRY: add 15 neighbouring localities (cycle 1)"},
    {"step":14,"agent":"RetrievalMerge","detail":"round 1: 432 listings"},
    {"step":15,"agent":"CoverageAgent","detail":"coverage 0.25 → RETRY: BHK 3 → 2–4 (cycle 1)"},
    {"step":21,"agent":"RetrievalMerge","detail":"round 2: 696 listings"},
    {"step":22,"agent":"CoverageAgent","detail":"coverage 0.33 → LIMITED: proceed and report the gap"},
    {"step":23,"agent":"AnalysisAgent","detail":"full analysis: move −4.45%"},
    {"step":24,"agent":"CritiqueAgent","detail":"5 months flagged → REJECTED: recompute flagged months (cycle 2)"},
    {"step":25,"agent":"AnalysisAgent","detail":"targeted recomputation: 17 outliers rejected, move −0.70%"},
    {"step":26,"agent":"CritiqueAgent","detail":"no new problems → APPROVED"}
  ],
  "source": {"dataset": "99acres.com residential listings, Hyderabad slice", "origin": "Kaggle: arvanshul/gurgaon-real-estate-99acres-com (multi-city archive)", "licence": "CDLA-Sharing-1.0", "scrape_date": "26 Aug 2023", "raw_rows": 9487, "canonical_listings": 4975, "price_valid_listings": 4574, "sha256": "9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a"}
}

## src/data/relations.json (use exactly)
{
  "unit": "base input", "seeds": [11, 23, 47], "base_inputs": 72,
  "relations": [
    {"id":"I1","family":"Invariance","transformation":"Reorder listings","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"I2","family":"Invariance","transformation":"Display ₹→lakh, sq ft→sq m","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"I3","family":"Invariance","transformation":"Duplicate every listing","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"I4","family":"Invariance","transformation":"Relabel listing IDs","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"I5","family":"Invariance","transformation":"Display ₹ lakh→crore","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"M1","family":"Monotonic","transformation":"Add ₹5 lakh in one month (no band)","bases":72,"deterministic":[0.194,0.120,0.300],"llm":[0.375,0.272,0.490],"verdict":"Outlier filter is not shift-invariant (data artifact); the model also judges the shifted prices."},
    {"id":"M1raw","family":"Monotonic","transformation":"Add ₹5 lakh, band kept","bases":71,"deterministic":[0.718,0.605,0.810],"llm":[0.746,0.634,0.833],"counter_example":true,"verdict":"Ill-conceived: the band selects a different population after the shift."},
    {"id":"M2","family":"Monotonic","transformation":"Widen the price band","bases":72,"deterministic":[0,0,0.051],"llm":[0,0,0.051]},
    {"id":"M3","family":"Monotonic","transformation":"Locality subset","bases":36,"deterministic":[0,0,0.096],"llm":[0,0,0.096]},
    {"id":"M4","family":"Monotonic","transformation":"Halve the radius","bases":36,"deterministic":[0,0,0.096],"llm":[0,0,0.096]},
    {"id":"D1","family":"Directional","transformation":"Shift window one month","bases":72,"deterministic":[0,0,0.051],"llm":[0.069,0.030,0.152]},
    {"id":"D2","family":"Directional","transformation":"Scale prices by 1.5","bases":72,"deterministic":[0,0,0.051],"llm":[0.264,0.176,0.376],"verdict":"Ill-conceived for an LLM-judged pipeline: scaling changes the prices the model judges."}
  ]
}
(Each rate array is [rate, CI low, CI high].)
````

## Notes

- **Free plan.** Send the prompt once and review the result before asking for
  changes; batch any fixes into one follow-up message.
- **The numbers are real.** `report.json` is the "3 BHK in Gachibowli" query
  (seed 7) from `tests/golden/deterministic_baseline.json` and REPORT §4.3;
  `relations.json` is REPORT §7.1–7.2. The narrative, relaxation and trace texts are
  condensed from the real output so they fit the cards.
- **Font.** The serif/monospace pairing of the report PDFs
  (`scripts/build_report_pdf.py`).
