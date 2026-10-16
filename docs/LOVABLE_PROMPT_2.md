# Follow-up prompt for Lovable — fixes, new fonts, interactivity

Paste the box below as **one message** in the same Lovable project. It batches
every change so the free plan's daily messages are not spent on small edits.

````text
Update the existing dashboard in ONE pass. Keep the layout, tabs, data files and the minimal style; no backend, no new pages, no login. Make these changes:

## 1. Typography (replace the current fonts everywhere)
- Load from Google Fonts: "IBM Plex Sans" (400, 500, 600) and "IBM Plex Mono" (400, 500).
- All UI text, headings, labels, table text and paragraphs: IBM Plex Sans. Base size 15px, line-height 1.55; card titles 15px/600; page title 20px/600; small helper text 13px in #5F5F5A.
- IBM Plex Mono ONLY for numbers, months, IDs, the SHA and code. Use `font-variant-numeric: tabular-nums` on every number so columns align.
- Remove the serif and Consolas fonts completely; body text must never be monospace.

## 2. Corrections
- Data & method tab: the three control-flow labels are swapped. Use exactly: **Feedback loop** — "Critique sends a rejection with the flagged months back to Analysis, which recomputes only those months (cycle 2)." **Conditional step** — "Coverage decides whether to stop or to widen one criterion and retrieve again, based on how many months have enough listings (cycle 1)." **Genuine dependency** — "The query mode chooses a different retrieval algorithm: exact locality matching or a geographic radius search."
- Relations tab: the three verdict cards must follow the Deterministic / LLM switch. Show each card only when that relation's rate is above 0 in the selected mode, with that mode's rate (in Deterministic mode show M1raw and M1; in LLM mode show M1raw, M1, D2 and D1).

## 3. Make it interactive
a) **Replay the run (Trend tab, agent trace card).** Add a "Replay run" button above the trace. It steps through the trace one step every 0.8 s (with pause and a step slider). Next to the trace, show the small architecture diagram (same six boxes as the Data tab): the active agent's box is highlighted in the accent colour, and when a step is tagged Cycle 1 or Cycle 2 the matching loop arrow animates once. The stat cards update as the replay passes step 23 (move −4.45%) and step 25 (move −0.70%, 17 outliers rejected), so the user sees the feedback loop change the answer.

b) **Linked charts and a month drawer.** Hovering a month on the price chart highlights the same month in the count chart and the table row (shared crosshair). Clicking a month (chart point or table row) opens a right-side drawer with that month: listings, price-valid, median ₹/sqft (in the selected units), coverage status with one sentence explaining it ("ADEQUATE: at least 30 listings with a usable price"), whether it counts toward the year-on-year move, and the partial-month note for 2023-08.

c) **Threshold sensitivity (new card at the bottom of the Trend tab, titled "How sure is the headline?").** A slider "Minimum listings for a month to count" with the steps 10, 20, 25, 30, 40, 50, 60, 75, 100, 150, 200, 300 (default 50). It shows the headline move, the months it spans and the first sufficient month, from sensitivity.json below. A small bar chart shows the headline at every step, with a horizontal reference line at +6.8% labelled "NHB RESIDEX Hyderabad (official index)". Under it one sentence: "At 50 the headline is −6.41%; at 75 it is +8.32%, close to the official +6.8%. The threshold, not the data, decides the sign." Whole-metro figures; label the card "Whole metro, statistics only".

d) **Relations table you can explore.** Add family filter chips (All, Invariance, Monotonic, Directional) and a "Compare" option in the mode switch that shows both modes as two dots per row (grey = deterministic, teal = LLM) on the same 0–1 interval axis. Clicking a row expands it inline to show the fields from relation_details.json: relation, subdomain, tolerance, fault it would expose, and (when present) the diagnosis category as a badge.

e) **Units that visibly react.** When the ₹ lakh / ₹ crore or sq ft / sq m toggles change, animate the changed numbers briefly (150 ms fade) and show a small toast: "Display units changed — percentages and rankings are unchanged (relations I2, I5)."

f) **Export.** A small "Download CSV" icon button on the monthly table and a "Copy summary" button on the Summary card.

g) **Polish.** Skeleton placeholders for 400 ms after "Run analysis"; visible keyboard focus; tooltips on every badge (ADEQUATE / LIMITED / NO DATA / counter-example / holds) explaining it in one sentence.

## src/data/sensitivity.json
{"residex_pct": 6.8, "rows": [
 {"min_n":10,"sufficient_months":12,"first":"2022-09","span_months":12,"headline_pct":87.18},
 {"min_n":20,"sufficient_months":12,"first":"2022-09","span_months":12,"headline_pct":87.18},
 {"min_n":25,"sufficient_months":10,"first":"2022-09","span_months":12,"headline_pct":87.18},
 {"min_n":30,"sufficient_months":7,"first":"2022-10","span_months":11,"headline_pct":18.35},
 {"min_n":40,"sufficient_months":6,"first":"2023-03","span_months":6,"headline_pct":-6.41},
 {"min_n":50,"sufficient_months":6,"first":"2023-03","span_months":6,"headline_pct":-6.41},
 {"min_n":60,"sufficient_months":6,"first":"2023-03","span_months":6,"headline_pct":-6.41},
 {"min_n":75,"sufficient_months":5,"first":"2023-04","span_months":5,"headline_pct":8.32},
 {"min_n":100,"sufficient_months":5,"first":"2023-04","span_months":5,"headline_pct":8.32},
 {"min_n":150,"sufficient_months":5,"first":"2023-04","span_months":5,"headline_pct":8.32},
 {"min_n":200,"sufficient_months":4,"first":"2023-05","span_months":4,"headline_pct":3.87},
 {"min_n":300,"sufficient_months":4,"first":"2023-05","span_months":4,"headline_pct":3.87}]}

## src/data/relation_details.json
{
 "I1":{"relation":"Every reported field unchanged","subdomain":"All inputs","tolerance":"Counts exact; values 1e-9","fault":"Order-dependent aggregation; unstable tie-breaks"},
 "I2":{"relation":"Counts, statuses, rankings and % changes identical; ₹/sqft scales by the unit factor","subdomain":"All inputs; band kept in rupees","tolerance":"1e-9","fault":"Hard-coded units; rounding before percentages"},
 "I3":{"relation":"Counts exactly double; monthly medians unchanged","subdomain":"Year-on-year fields excluded","tolerance":"Medians 1e-9; counts exact","fault":"Silent de-duplication; per-row judgments","diagnosis":"Genuine agent fault in the LLM review — fixed (was 0.111)"},
 "I4":{"relation":"Every reported field unchanged","subdomain":"All inputs","tolerance":"Exact","fault":"Logic keyed on listing IDs"},
 "I5":{"relation":"As I2, factor 1/100","subdomain":"Lakh projection of each input","tolerance":"1e-9","fault":"Hard-coded currency"},
 "M1":{"relation":"That month's price medians rise by ₹5 lakh; other months and counts unchanged","subdomain":"Band-free projection","tolerance":"|Δ − X| ≤ 1e-6·X","fault":"Month-bucketing leaks","diagnosis":"Data artifact (outlier filter) + ill-conceived for an LLM judge"},
 "M1raw":{"relation":"As M1, with the price band kept","subdomain":"None — does not hold","tolerance":"As M1","fault":"None; the relation is unsound","diagnosis":"Ill-conceived MR (counter-example)"},
 "M2":{"relation":"Each month's listing count ≥ before","subdomain":"Inputs with a price band","tolerance":"Exact inequality","fault":"Filter inversion; off-by-one bounds"},
 "M3":{"relation":"Each month's listing count ≤ before","subdomain":"Inputs with ≥ 2 localities","tolerance":"Exact inequality","fault":"Shard leakage; widening that breaks set inclusion","diagnosis":"Genuine agent fault — fixed (was 0.250)"},
 "M4":{"relation":"Each month's listing count ≤ before","subdomain":"Radius inputs","tolerance":"Exact inequality","fault":"Wrong distance formula; unlocated rows leaking in"},
 "D1":{"relation":"The 11 overlapping months match exactly","subdomain":"Both windows inside the data","tolerance":"Counts exact; values 1e-9","fault":"Window off-by-one; state carried between runs","diagnosis":"Ill-conceived for an LLM-judged pipeline"},
 "D2":{"relation":"Price medians scale by exactly 1.5; % changes and rankings unchanged","subdomain":"All inputs (band scaled too)","tolerance":"1e-9","fault":"Unit mishandling; non-linear aggregation","diagnosis":"Ill-conceived for an LLM-judged pipeline"}
}
````

## Why these changes

| Change | Reason |
|---|---|
| IBM Plex Sans + Plex Mono | the current page sets *all body text* in Consolas at 11 px, which reads as code; Plex is a clean, professional pair designed for data-heavy interfaces, with tabular figures |
| Swapped control-flow labels | the brief requires the feedback loop, conditional step and genuine dependency to be identified correctly; the page contradicted REPORT §4.1 |
| Verdict cards follow the mode | in Deterministic mode the D2 card showed 0.000 beside an LLM-only verdict |
| Replay run | the brief asks to show "a loop actually firing at run time"; this makes it visible, and shows the critique changing the answer |
| Threshold slider with the RESIDEX line | the report's main threat to validity, made something the user can explore |
| Expandable relations, Compare | the brief's per-MR relation, subdomain, tolerance and fault, one click away; both sweeps on one axis |
| Month drawer, linked hover, unit toast | makes the static data explorable and demonstrates the unit invariances (I2, I5) in the UI itself |
