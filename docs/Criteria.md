# Criteria Agent

## Responsibility

The Criteria Agent normalizes structured user filters into a typed `FilterSpec` and chooses one geographic query mode:

- `EXACT_LOCALITY`: match one or more exact source-known localities; do not set `geo_radius_km`.
- `GEO_RADIUS`: require exactly one source-known centre locality and a radius in `(0, 100]` km.

City, locality-to-city relationships, property types, and the supported BHK domain are loaded from the frozen CSV. The file SHA-256 must match the global pinned snapshot before the catalog is accepted. Locality and property type matching ignores case and repeated whitespace but emits the canonical spelling from the source.

## Fixed calendar window

Omitting dates uses the source period `2022-09` through `2023-08` inclusive, exactly 12 calendar months. Explicit dates must supply both `start_month` and `end_month` in `YYYY-MM` format and must match that exact source window. Relative dates such as “last 12 months”, other windows, partial bounds, and malformed dates fail with stable error codes. The criteria agent never anchors the period to the current date.

## Supported structured request fields

`city` (required); `locality` or `localities` (required); optional `bhk` / list; optional `property_type` / `property_types`; optional `min_price_inr`, `max_price_inr`; optional `geo_radius_km`; optional `start_month`, `end_month`; and optional `query_mode` as an assertion. Unknown keys fail closed. Prices must be finite positive numeric INR amounts and the minimum cannot exceed the maximum. BHK values must be whole numbers within the source-derived supported domain (1–10 where observed).

## Stable error codes

Includes `source_missing`, `snapshot_integrity_error`, `source_schema_error`, `unsupported_city`, `unsupported_locality`, `unsupported_property_type`, `unsupported_bhk`, `invalid_price`, `invalid_price_range`, `invalid_geo_radius`, `missing_geographic_scope`, `ambiguous_geo_radius_center`, `invalid_date_format`, `incomplete_date_window`, `unsupported_date_window`, `unsupported_query_mode`, and `query_mode_mismatch`.

## Boundary with the current runtime contract

This module produces its own `FilterSpec` / `QueryMode` typed pair. The existing contract-v1 `AnalysisFilters.validate()` intentionally rejects nonempty filter fields, and the runtime currently uses `query_mode` for `structured` / `natural_language`. This agent therefore does not claim that the downstream scanner applies these new filters. Wiring it into the analysis pipeline requires an explicit global-contract/schema revision and a scanner implementation that honors the selected scope.
