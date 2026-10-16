# Data source

> **Credits:** written by Paridhi Mittal; edited by Vidhi Jain. Full attribution: CREDITS.md.

- Dataset: 99acres.com Hyderabad residential listings (multi-city scrape; Mumbai, Hyderabad, Kolkata and Gurgaon files in the original archive)
- Origin: Kaggle — https://www.kaggle.com/datasets/arvanshul/gurgaon-real-estate-99acres-com
  Titled "Indian Real Estate - 99acres.com". The slug says "gurgaon" but the
  dataset description states it "contains details of properties of Gurgaon,
  Hyderabad, Mumbai, Kolkata cities of India" (~10,000 rows per city), which is
  why a Hyderabad file is present. VERIFIED against the dataset page.
  Note: this is NOT the 99acres dataset the assignment brief recommends
  (arnabk123/real-estate-data-sourced-from-99acres-com), whose description
  covers Gurgaon only and does not include Hyderabad.
- Licence / terms: Community Data License Agreement - Sharing - Version 1.0
  (cdla.io/sharing-1-0/). VERIFIED against the dataset page.
- Scrape date: approx. 26 Aug 2023 (latest POSTING_DATE in the file)
- Rows: 9,487; columns: 55
- File: data/raw/hyderabad.csv, SHA-256 in CHECKSUMS.txt. Raw file is never modified.
- Known limits: single-point scrape, so older months contain only listings still live on the scrape date.