# DATA SUBCONTRACT — Hyderabad Housing-Trends Application

**Parent:** `CONTRACT.md` v2.0.0-draft
**Status:** Draft. Source fingerprint and defects D1–D5 are verified; D6–D7 are ported from v1 in Phase 3.
**Scope:** Source freeze, defects, the canonical population and filter cascade, month derivation, identity, and reproducibility checks. The parent controls the output contract, window and loops. In a conflict, update this file rather than silently changing the parent.

## 1. Source and frozen input

| Item | Contract value |
|---|---|
| Raw path | `data/raw/hyderabad.csv` |
| Rows / columns | 9,487 / 55 |
| SHA-256 | `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a` (also in `data/raw/CHECKSUMS.txt`) |
| Origin | Kaggle `arvanshul/gurgaon-real-estate-99acres-com` ("Indian Real Estate – 99acres.com"; covers Gurgaon, Hyderabad, Mumbai, Kolkata). Scraper: `github.com/arv-anshul/99acres-scrape` |
| Licence | CDLA-Sharing-1.0 |
| Scrape date | ≈ 26 Aug 2023 (latest `POSTING_DATE`) |
| Mutability | Read-only |

The brief's recommended 99acres dataset (`arnabk123/...`) covers Gurgaon only and does not contain Hyderabad; this is recorded so a grader reading "gurgaon" in the slug is not misled.

This is a single-point scrape: older months contain only listings still live on the scrape date. Observed counts are not inventory, transactions or a census, and the July–August concentration must not be presented as a market surge.

## 2. Verified defects and handling

| ID | Defect (evidence) | Handling |
|---|---|---|
| D1 | `MIN_AREA_SQFT`/`MAX_AREA_SQFT` hold **square metres** despite the name: ratio of the `AREA` display string to `MIN_AREA_SQFT` is 10.7639 at both p5 and p95 over 3,531 rows | Area is parsed from the `AREA` string (`"<n> sq.ft."`); the named columns are never used for ₹/sqft |
| D2 | `MIN_PRICE`/`MAX_PRICE` carry the int32 sentinel 2,147,483,647 on 5 rows and 0 on 75 rows | Excluded (§3, filter 5) |
| D3 | `PREFERENCE` mixes sale S=7,927, rent R=1,467, PG P=93 | Sale only |
| D4 | `BEDROOM_NUM` missing on 2,814 rows, 2,806 of them `Residential Land` (structural, not missing data) | Dwellings only (§3, filter 2) |
| D5 | Area-entry errors in the tail (a 27 sq ft villa at ₹2.15 cr = ₹796,296/sq ft; a 285,599 sq ft one) | **Deliberately kept** in the canonical frame. Detecting them is the Analysis agent's targeted recomputation (loop C2); filtering them here would make C2 decorative. Plausibility bounds remain available via `apply_plausibility=True` for ablation only |
| D6 | **[P3]** `PRICE` text "Price on Request" (4 rows in the current canonical frame) | Excluded (§3, filter 4) |
| D7 | `PROP_ID` is not unique (one ID on two canonical rows) | Both rows kept; **[P4]** `listing_id` made unique (§5) |

`TRANSACT_TYPE` code meanings are not verified and the field is not used.

## 3. Canonical population and filter cascade

Filters run in this order. Each stage's remaining and dropped counts are written to `data/snapshot/canonical_reject_log.csv` by `RejectLog`.

| # | Filter | Rows remaining (current, pre-P3) |
|---|---|---:|
| 0 | raw rows | 9,487 |
| 1 | `PREFERENCE == "S"` | 7,927 |
| 2 | `PROPERTY_TYPE` in dwelling types | 5,085 |
| 3 | `POSTING_DATE` parses (Unix ms) | 4,975 |
| 4 | **[P3]** `PRICE` is not "Price on Request" | — |
| 5 | `MIN_PRICE` numeric, `> 0`, `!= 2147483647`; **[P3]** same for `MAX_PRICE`, and `MIN_PRICE <= MAX_PRICE` | 4,917 |
| 6 | Area parses from `AREA` and `> 0` | 4,578 |

Dwelling types: `Residential Apartment`, `Independent House/Villa`, `Independent/Builder Floor`, `Studio Apartment`, `Serviced Apartments`.

The counts in the table are audit baselines, not constants: code recomputes them on every load, and **[P3]** the table is updated once filters 4–5 and the timezone rule (§4) are in place. **[P4]** The reject log's stale stage name ("DEFERRED to ScanAgent STRICT") is replaced by the current one ("DEFERRED to Analysis recomputation").

Rows that fail a filter are not deleted from the raw file; they are simply absent from the derived canonical frame and counted in the log.

## 4. Derived fields

| Field | Derivation |
|---|---|
| `listing_id` | currently `PROP_ID`; **[P4]** `PROP_ID` + raw row position, unique |
| `month` | `POSTING_DATE` (ms) → instant → **[P3]** `Asia/Kolkata` → `YYYY-MM` (currently UTC; 18 rows differ) |
| `price_inr` | `MIN_PRICE` |
| `max_price_inr` | **[P3]** `MAX_PRICE` |
| `area_sqft` | parsed from `AREA` (D1) |
| `psf_inr` | `price_inr / area_sqft` |
| `bhk` | bedroom count |
| `locality` | `LOCALITY_NAME` from the embedded `location` field; `"Unknown"` if absent |
| `property_type`, `city` | source values |
| `latitude`, `longitude` | from `MAP_DETAILS`; discarded if outside the Hyderabad box (lat 16.5–18.5, lon 77.5–79.5) |
| `area_sqm_raw` | from `SECONDARY_AREA`; independent restatement used by the Analysis cross-check |
| `price_display_inr` | from the `PRICE` display string; independent restatement used by the Analysis cross-check |
| `age_on_site_days` | whole days from posting time to the reference date; `null` outside 0–1000. Reference is currently `2023-08-26 00:00 UTC`; **[P3]** `LATEST_POSTING` in `Asia/Kolkata` |
| `description` | first 400 characters of `DESCRIPTION`; read only by the Analysis agent's LLM review, never by statistics |

No value is imputed. A field that cannot be parsed is `null` (or `"Unknown"` for locality).

## 5. Identity rules

- `PROP_ID` alone does not identify a listing; a repeated ID is not evidence of a duplicate.
- **[P4]** `listing_id` is unique within the canonical frame and stable across runs on the same snapshot.
- No row is deduplicated. MR I3 (duplicate every listing) creates distinct IDs for the copies (`#dup` suffix), so it tests replication, not deduplication.

## 6. Startup integrity

1. The raw SHA-256 is computed and compared with §1 before loading (`verify_snapshot`). Mismatch → `snapshot_integrity_error`.
2. The frozen canonical CSV's SHA-256 is recorded in `data/snapshot/CHECKSUMS.txt` and regenerated only by `freeze_canonical`, as a reviewed change.
3. `.gitattributes` keeps `data/`, `results/` and `tests/golden/` byte-exact across platforms (`core.autocrlf` previously broke the canonical checksum on Windows).
4. Agents receive the frame in memory; they do not read files.

## 7. Reproducibility checks

| Check | Required result |
|---|---|
| R1 — Raw integrity | SHA-256 equals §1 |
| R2 — Shape | 9,487 rows, 55 columns |
| R3 — Cascade | Each stage count in §3 is reproduced by `load_canonical()` |
| R4 — Canonical freeze | `listings_canonical.csv` SHA-256 equals `data/snapshot/CHECKSUMS.txt` |
| R5 — Identity | **[P4]** `listing_id` unique |
| R6 — Month rule | **[P3]** months derived in `Asia/Kolkata` |
| R7 — No mutation | Raw SHA-256 unchanged after a run |

If a baseline changes, first determine whether the source, timezone logic or a filter changed. Update this file and the parent version only for an intentional, reviewed change; never edit an expected value just to make a test pass.

## 8. Traceability

| This file | Parent |
|---|---|
| §1 Source | §2 |
| §3 Population | §4.1 |
| §4 Month | §4.2, §4.3 |
| §5 Identity | §4.4 |
| §6–7 Integrity | §2, §10 |
