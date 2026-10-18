# Retrieval Agent — frozen Hyderabad snapshot

## Purpose

`app/retrieval_agent.py` applies the Criteria Agent's typed `FilterSpec` to the pinned Hyderabad CSV. It is deterministic and offline. It does not alter the source file and preserves a `source_row_id` based on the zero-based raw CSV row ordinal.

## Input and integrity

```python
from app.criteria_agent import run_criteria_agent
from app.retrieval_agent import RetrievalAgent

criteria = run_criteria_agent({
    "city": "Hyderabad",
    "locality": "Gachibowli",
    "bhk": 2,
    "property_type": "Residential Apartment",
    "min_price_inr": 5_000_000,
    "max_price_inr": 10_000_000,
    "start_month": "2022-09",
    "end_month": "2023-08",
})
result = RetrievalAgent().retrieve(criteria)
selected_rows = result.rows
print(result.to_dict())
```

By default, the agent verifies the raw CSV SHA-256 against `FROZEN_SOURCE_SHA256` before reading it. A mismatch raises `RetrievalError` with code `snapshot_integrity_error`. Tests for synthetic CSVs can inject their calculated SHA explicitly.

## Filtering semantics

1. **Registration-month bounds:** `REGISTER_DATE__U` is parsed as a date/time. Rows whose registration timestamp is invalid are excluded and counted in `invalid_registration_date_rows`. The lower and upper calendar months are inclusive. The current public Criteria Agent intentionally permits only the frozen contract window `2022-09` through `2023-08`. Monthly reporting remains based on localized `POSTING_DATE`; retrieval-date filtering does not redefine the reporting month.
2. **City:** exact case-insensitive match against the top-level `CITY`, with parsed `location.CITY_NAME` used only when the top-level cell is blank.
3. **EXACT_LOCALITY:** matching is whitespace-normalized and case-insensitive. A requested locality name is matched to parsed `location.LOCALITY_NAME`; a source-known locality ID is matched to parsed `location.LOCALITY_ID`. The Criteria Agent now accepts an unambiguous, source-known ID as well as a locality name. Placeholder ID `0` is not catalogued as a usable ID.
4. **GEO_RADIUS:** the centre locality is the one locality in the typed filter spec. Its reference point is the coordinate-wise median of valid `MAP_DETAILS` coordinates for that locality and city. Distances use the haversine great-circle formula and `EARTH_RADIUS_KM = 6371.0088`. Selected rows must have a valid coordinate pair and distance `<= geo_radius_km`. Latitude must be finite and in `[-90, 90]`; longitude must be finite and in `[-180, 180]`.
5. **Structured filters:** requested BHK and property types are exact membership filters. INR price ranges use inclusive interval overlap: a listing matches a requested lower bound if its valid upper price is at least that lower bound, and matches a requested upper bound if its valid lower price is at most that upper bound. Price filters never match rows with invalid bounds (missing, non-finite, non-positive, sentinel or inverted values).
6. **Safe parsing:** source cells in `location` and `MAP_DETAILS` are parsed by `json.loads` or `ast.literal_eval` only. Non-dictionary or malformed payloads are treated as unavailable; there is no call to Python's built-in `eval`.
7. **Stable order and identity:** selected rows retain source order, carry `source_row_id` (zero-based raw row ordinal), and include their original source columns. Equal property IDs or similar listing signatures are not deduplicated.

## Diagnostics

`RetrievalResult.to_dict()` reports the source digest, row counts, selected count, registration-date missing/invalid count, malformed location count, invalid coordinate count, applied month bounds, and geospatial centre coordinates when applicable. It does not embed selected rows unless called with `include_rows=True`.

## Verified examples

Against the pinned snapshot (SHA-256 `9e81698322606c86b4a23e41ace5deecff5e5ed94dc768e9e5e371a2bc48898a`):

- Exact locality `Gachibowli`, BHK 2, `Residential Apartment`, INR band 5,000,000–10,000,000 returns 24 rows. `tests/test_retrieval_agent.py` asserts all 24 `PROP_ID` values in source order, not just the count.
- Exact locality ID `5561` in Hyderabad returns 38 rows in the source registration window.
- Geo radius centred on Kondapur, 2 km, restricted to two-bedroom residential apartments returns 112 rows.

Synthetic test cases check inclusive first/last month boundaries, use of `REGISTER_DATE__U` independently of `POSTING_DATE`, invalid/malformed coordinates, ID/name matching, price/BHK/property filters, checksum mismatch, and that the builtin `eval` is never invoked.

## Integration boundary

This patch delivers the Retrieval Agent and Criteria Agent locality-ID support. It does not change the existing monthly aggregation or graph-backed runtime builder. Wiring this selector into the graph scanner is a separate integration step; until then, callers can use `RetrievalAgent.retrieve(criteria_result)` directly and the public report remains unchanged.
