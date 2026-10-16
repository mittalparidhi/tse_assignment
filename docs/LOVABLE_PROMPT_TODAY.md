# One-message prompt for a low credit balance

Use this when only about one Lovable message is left. It carries the changes
that matter most — the font, the two corrections, and the two features that
show the feedback loop working — and needs only one small data array. The rest
of `LOVABLE_PROMPT_2.md` (threshold slider, relation details, month drawer,
export) and `LOVABLE_PROMPT_3.md` (eight real queries) can follow on another
day, one message each.

````text
Small focused update in ONE pass; do not change anything not listed here. No backend.

1. Fonts. Load "IBM Plex Sans" (400, 500, 600) and "IBM Plex Mono" (400, 500) from Google Fonts. Use IBM Plex Sans for all text (base 15px, line-height 1.55; card titles 600). Use IBM Plex Mono only for numbers, months, IDs, the SHA and code, with font-variant-numeric: tabular-nums. Remove the serif and Consolas fonts; body text must never be monospace.

2. Fix the Data & method labels exactly:
- Feedback loop — "Critique sends a rejection with the flagged months back to Analysis, which recomputes only those months (cycle 2)."
- Conditional step — "Coverage decides whether to stop or to widen one criterion and retrieve again, based on how many months have enough listings (cycle 1)."
- Genuine dependency — "The query mode chooses a different retrieval algorithm: exact locality matching or a geographic radius search."

3. Relations tab: the verdict cards must follow the Deterministic / LLM switch — show a card only when that relation's rate is above 0 in the selected mode, with that mode's rate.

4. "Show before critique" toggle on the price chart: draw this series as a dashed grey line under the final teal line and lightly shade the months where they differ. When on, the first stat card reads "−0.7% (before critique −4.45%, over 3 months)".
before_critique_psf = [7916.4, null, 9000.0, 10190.8, 11705.7, 9490.6, 11074.9, 10000.0, 10495.3, 10665.6, 10217.4, 10190.6]

5. "Replay run" button on the Agent trace card: steps through the trace one step every 0.8 s (pause/resume). Highlight the current step; when a step tagged Cycle 1 or Cycle 2 is reached, flash its tag. When the replay reaches step 25, switch the chart from the before-critique line to the final line over 600 ms, so the user sees the critique loop change the answer.
````

## Order for the following days

1. `LOVABLE_PROMPT_3.md` — the eight real queries with quick-query chips and compare (the biggest gain in interactivity).
2. From `LOVABLE_PROMPT_2.md`, sections 3c–3g only (threshold slider, relations explorer, unit toast, export, polish), with its two data files.
