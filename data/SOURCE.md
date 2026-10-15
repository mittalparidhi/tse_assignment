# Data source

The provenance record the design note (§3) requires before submission.

| | |
|---|---|
| Raw file | `data/raw/hyderabad.csv` (supplied as `hyderabad(1).csv`) |
| Rows × columns | 9,487 × 55 |
| SHA-256 | `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` (`data/raw/CHECKSUMS.txt`, re-verified on every load) |
| Publisher / origin | Kaggle dataset `arvanshul/gurgaon-real-estate-99acres-com`, titled "Indian Real Estate – 99acres.com". The slug says "gurgaon", but the dataset page describes it as covering "Gurgaon, Hyderabad, Mumbai, Kolkata"; this file is the Hyderabad slice. Scraper: `github.com/arv-anshul/99acres-scrape`. |
| Licence | Community Data License Agreement – Sharing – Version 1.0 (`cdla.io/sharing-1-0/`) |
| Verification | Origin, title and licence checked against the Kaggle dataset page (see `data/raw/Readme.md`, `AI_USE.md` §3.11). The file itself embeds no URL, retrieval date or licence. |
| Not the brief's dataset | The 99acres dataset the brief recommends (`arnabk123/real-estate-data-sourced-from-99acres-com`) covers Gurgaon only and does not contain this file. |
| Scrape date | ≈ 26 Aug 2023: the latest `POSTING_DATE` and `REGISTER_DATE__U` are both 2023-08-26 10:29:05 IST. |
| Cities | `CITY`: Hyderabad 8,762 rows, Secunderabad 725. |
| Modification | None. The canonical snapshot (`data/snapshot/listings_canonical.csv`) is derived deterministically by `src/loading.py`; every exclusion and flag is logged in `canonical_reject_log.csv` and `canonical_price_validity.csv`. |

**Limits to disclose.** A single-point scrape: older months hold only listings
still live on the scrape date, so the dates are historical and highly
concentrated (96.4% of the default window's price-valid listings fall in its
last six months). Prices are asking prices, not transactions. There is no
PIN/postcode column; locality is the geographic key.
