# Lovable fixes after checking the latest build

The build was checked in the browser on 16 Oct: eight quick queries, closest-match banner, "changed from last
run", before-critique per query, compare, Newsreader headings, the y-axis, dark mode (system default, remembered
choice, no flash) and the unit toast all work; dark mode passes 4.5:1 contrast on all 158 text elements. These are
the only gaps found. Small message — send it as one.

````text
Four small fixes only; change nothing else.

1. Light-mode badge contrast. In light mode the LIMITED badge text (#B77611 on white, 3.7:1) and the NO DATA badge
text (#969690, 3.0:1) are below 4.5:1. Use #8A5A0B for LIMITED text and #5F5F5A for NO DATA text in light mode,
keeping their 15% tinted backgrounds, so both reach at least 4.5:1. Dark mode stays as it is.

2. Sensitivity chart: the "NHB RESIDEX Hyderabad (official index)" label overlaps the bars. Place the label at the
right end, just above the +6.8% reference line, with the card background behind the text, in 12px secondary colour.

3. Make the ₹ lakh / ₹ crore toggle visibly do something. Add a "Median asking price" column to the Monthly detail
table and the month drawer, from the arrays below (values in ₹ lakh per month, aligned with "months"; null = no
data). Show "₹212.4 L" in lakh mode and "₹2.12 Cr" in crore mode. The percentage move and rankings must not change
when toggling.
listing_price_lakh = {"gachibowli-3bhk":[160.06,null,212.4,265.0,208.1,136.0,205.0,210.0,195.0,180.0,185.2,184.5],"kondapur-2bhk":[160.06,null,null,240.0,142.5,136.0,205.0,205.0,183.5,170.0,155.0,162.0],"kokapet-narsingi-3bhk":[null,137.37,213.7,290.0,241.2,186.01,210.0,142.0,146.0,141.2,150.01,155.03],"kollur-tellapur-2-3bhk":[58.68,null,null,74.52,null,101.5,108.75,85.32,90.5,81.11,93.92,97.48],"radius-financial-district-5km":[53.75,72.5,131.2,240.0,241.2,120.0,175.0,142.61,144.03,145.75,151.88,150.0],"radius-kondapur-3km":[57.0,1000.0,212.4,265.0,175.6,136.0,180.0,267.5,160.0,167.0,158.38,169.0],"secunderabad-all":[71.5,null,125.0,55.0,125.0,174.1,75.0,90.0,122.5,88.15,82.53,106.73],"metro-all":[57.88,84.5,49.92,53.01,145.0,110.0,148.77,125.0,124.7,135.0,130.0,136.47]}

4. Trace text: where a trace detail reads "1 months flagged", show "1 month flagged".
````
