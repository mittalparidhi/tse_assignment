# Change list for `Assignment1_Design_Note_Final.docx`

Refreshed after the implementation was aligned to your design and the local
model was added. **The fastest route is to read `DESIGN.md` in this repo** — it
is structured to mirror your sections (your six agents, your Reads/Writes
table, your five-column MR table), so most of this is already written there in
final form.

**No blockers.** Item 10 was flagged as one and has since been resolved — in
your favour; see below.

---

## Keep as-is — these are good and we adopted them

- The **six agents with explicit Reads/Writes columns.** Better documentation
  discipline than what the code originally had; it is now the structure of the
  implementation.
- **Cycle 2 as Critique → Analysis**, with the rejection carrying a specific
  complaint and flagged months for targeted recomputation. This was better than
  the original design and replaced it.
- **`query_mode` as the genuine dependency.** A clearer reading of the brief's
  requirement (c) than what we had. Now implemented as exact-locality vs
  haversine radius search.
- The **control-flow requirements table** with its "why necessary" column.
- The **5-column MR table format** — exactly what the brief asks for.
- **LangGraph**, and the explicit termination conditions.

---

## Five substantive corrections — measurement showed the spec was wrong

**1. §2 — add `month_is_sufficient`** (boolean, n ≥ 50), role: "defines the
subdomain for all month-comparing MRs." *Thin months swing ₹4,104 → ₹8,567/sqft
on 21–34 listings; without the flag the system publishes that as a trend.*

**2. §2 — rename `median_days_on_market` → `median_age_on_site_days`**, defined
as median (scrape_date − posting_date) for listings live at the scrape.
*It is right-censored (every listing is still live) and length-biased (slow
listings accumulate in a snapshot), so it overstates time-to-sale. Derivable:
median 37 days, p10 6, p90 108.*

**3. §7 MR4 — the subdomain is unsound.** "Target month has ≥1 listing" does
not exclude a price band. Change to *the band-free projection of each base
input; the band must be removed from both runs.* *Measured: with a band in
place, adding ₹500k to every price made a 15-listing month's median* **fall by
₹1,122,750**. *The unrefined form is retained as `M1raw`, which violates at
0.806–0.861 — by design.*

**4. §7 MR8 — tolerance far too loose.** "Within 1% of k; % changes within
0.5pp" → **relative 1e-9**. *median(k·x) = k·median(x) is exact arithmetic, so
a 1% band hides real bugs.* Also: the band must be scaled alongside the data.

**5. §7 MR5 & MR6 — add a conditionality note.** Monotonicity holds only when
both runs take the same path through cycle 1. *Measured on synthetic data: a
locality* **subset** *returned* **85 → 331** *listings, because the subset
lowered coverage and triggered extra widening.*

---

## Retarget: Dallas → Hyderabad

**6. §1** — make Hyderabad/Secunderabad primary; your own note already
authorises this ("the same architecture can be retargeted to an Indian metro").

**7. §1** — add that **PIN codes are not in the dataset** (no PIN/ZIP/postal
column; the six-digit strings in free text are latitude fragments), so locality
is the filtering convention.

**8. §2** — `$/sqft` → `₹/sqft` throughout.

**9. §3** — replace the Kaggle USA Real Estate Dataset with: 99acres Hyderabad
slice, 9,487 rows × 55 columns, scrape ≈26 Aug 2023, SHA-256 `9e81698…`
verified on every load.

**10. §3 — RESOLVED, and your citation was right.** I had flagged
`arvanshul/gurgaon-real-estate-99acres-com` as a likely transcription error,
reasoning that a Gurgaon dataset could not contain a Hyderabad file, and
suggested citing the brief's dataset instead. **That was wrong and you should
ignore it.** Checking both Kaggle pages:

- `arvanshul/gurgaon-real-estate-99acres-com` is titled **"Indian Real Estate –
  99acres.com"** and its description says it "contains details of properties of
  **Gurgaon, Hyderabad, Mumbai, Kolkata** cities of India" — matching your
  Readme's prose exactly. Licence **CDLA-Sharing-1.0**, exactly as you wrote.
- The brief's recommended dataset, `arnabk123/real-estate-data-sourced-from-99acres-com`,
  describes **Gurgaon only** and does not contain the Hyderabad file.

So both of your claims were correct and are now verified. The only change worth
making is to **note in §3 that the slug is misleading** — a grader who reads
"gurgaon" in the URL will otherwise wonder, and it is also worth recording that
the dataset the brief recommends does not in fact cover Hyderabad.

**11. §3** — Zillow → **NHB RESIDEX**, and it is no longer optional: **we did
it, and it changed a conclusion.** RESIDEX puts Hyderabad at **+6.8%** while
our shipped contract says **−6.41%**; our own data gives **+7.08%** at n ≥ 75.
See `results/residex/cross_check.md`.

**12. §4** — `query_mode`: "exact-ZIP vs radius" → **"exact-locality vs
radius/geo"**. 94.7% of rows carry usable coordinates — worth noting the US
dataset you had chosen has none, so the retarget *enabled* this part of your
design.

---

## Additions from measurement

**13. §3** — add a **Known defects** subsection: `MIN_AREA_SQFT` is square
metres despite its name (ratio 10.7639 at *both* p5 and p95 over 3,531 rows) ·
int32 sentinel 2³¹−1 in price fields · sale/rent/PG mixed (7,927/1,467/93) ·
2,806 of 2,814 missing bedroom counts are `Residential Land`, i.e. structural ·
area-entry errors in the tail (a 27 sqft "villa" at ₹2.15 cr).

**14. §3** — add the **single-point-scrape threat**: **96.5% of the window's
listings fall in its last six months.**

**15. §2** — add the fields the MRs actually assert on: `p25_price_per_sqft`,
`p75_price_per_sqft`, `yoy_median_psf_pct` **with `yoy_span_months`**,
`locality_rankings`, and `currency_unit`/`area_unit`.

**16. §4** — **`Retrieval Agent` → several cooperating Retrieval agents** (four
parallel graph nodes). The brief says "several cooperating agents each scan
listings."

**17. §4** — name which agents use the model: Criteria, Analysis, Critique,
Aggregator — and state explicitly that **all statistics stay deterministic
Python**.

**18. §5** — replace asserted justifications with measured ones. Cycle 1: "3
BHK in Gachibowli" yields **1 sufficient month**; coverage goes **0.083 → 0.167
→ 0.500**. Cycle 2: targeted recomputation shifts **7 of 12 monthly medians**
(up to **+5.50%**) and **changes the locality ranking order**.

**19. §6** — replace "a local model may be used" with the plan as executed:
**Ollama + Qwen2.5-3B-Instruct (Q4_K_M)**, digest `d7f5d340f8953384`,
temperature 0, seeds `[11, 23, 47]`, model pinned as a **third reproducibility
artifact**. A determinism probe returned **20/20 identical** replies.

**20. §6** — add the **four prompt-hygiene constraints** (positions not
identifiers; total-order sort; content dedup; canonical units with counts
withheld). Each was forced by a relation that failed without it — this is the
most interesting part of the LLM design and it is absent from the note.

**21. §7 MR2** — USD-thousands → **₹ lakh *and* ₹ crore** (the brief calls
crore↔lakh "especially instructive"), plus the area unit.

**22. §7 MR3** — add that the **yoy fields are excluded**: doubling flips the
sufficiency flag for months holding 25–49 listings.

**23. §7 MR7** — add to subdomain: *window ends such that both windows lie
inside the observed data range.*

**24. §7** — the catalogue grew to **11 relations** (8 required): the crore
variant (I5) and the retained counter-example (`M1raw`).

---

## One section to add

**25. "Changes from the initial design, and why."** Items 1–5 are all cases
where the design was reasonable and measurement proved it wrong. The brief says
*"An MR is a hypothesis, not an axiom… Reasoning precisely gets you the
grade."* Showing evidence-driven evolution scores better than a note that
merely agrees with the code.

---

## Where the numbers live, if you want to check any of them

| Claim | Source |
|---|---|
| violation rates, three configurations | `results/phaseA_deterministic/`, `results/llm_before_promptfix/`, `results/llm/` |
| threshold sensitivity (93.6 pp, sign flip) | `results/sensitivity/threshold_sensitivity.csv` |
| RESIDEX cross-check | `results/residex/cross_check.md` + the retained PDF |
| determinism probe | `results/llm/determinism_probe.json` |
| controlled experiments behind the diagnosis | `results/diagnosis/` |
| every numeric claim, re-derived | `python scripts/verify_claims.py` |
