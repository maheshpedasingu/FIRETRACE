# FIRETRACE Implementation Plan (global scope)

The 45-hour budget and phase order from the master specification are kept. What changes
is that every phase is built and tested for arbitrary global AOIs. Tests use only small
fixtures labelled **SYNTHETIC TEST DATA**, spread across several continents and edge
locations: antimeridian, high latitudes, Southern Hemisphere and the equator.

| Hours | Phase | Global-scope deliverables | Tag |
|---|---|---|---|
| 0–3 | Foundation | venv, pinned deps (incl. pyarrow, duckdb), Vite app, FastAPI `/api/health`, both verified starting | v0.1-foundation |
| 3–8 | NASA data ingestion | Area API client (availability discovery, tiled date windows, transaction budget, retries); archive importer for yearly country ZIPs and Archive Download Tool CSVs; CLI folder import | v0.2-data-ingestion |
| 8–13 | Canonical data engine | canonical schema, per-platform adapters, checksums, idempotent re-import, NRT→SP supersession, partitioned Parquet writer, coverage registry | — |
| 13–21 | Harmonization | EPSG:6933 grid, daily/monthly cell aggregates, incremental rebuild, per-AOI baselines (median/MAD), harmonized index, overlap matching and calibration diagnostics | v0.3-harmonization |
| 21–27 | Historical intelligence | per-AOI calendar with coverage states, yearly/monthly analytics, anomalies, FRP stats, streamed CSV | v0.4-analytics |
| 27–35 | Full application | global map (density tiles + points), AOI picker (country/admin-1/bbox/polygon/lat-lon, antimeridian-safe), calendar, charts, explorer, ingestion UI, export centre | v0.5-dashboard |
| 35–41 | Validation and repair | full test suites, production build, performance check on a multi-million-row partitioned dataset, error handling | — |
| 41–45 | Final delivery | docs, methodology, provenance, coverage report, screenshots, changelog | v1.0.0 |

## Global-scope test matrix (synthetic fixtures)

- AOIs in South America, Africa, Siberia, Australia, North America and South Asia.
- A polygon crossing the antimeridian (e.g. Chukotka/Alaska, Fiji).
- Detections above 80°N, flagged as outside the grid's valid range.
- Country selection, admin-1 selection, bbox, custom polygon, invalid polygon.
- Missing vs zero: one covered area with no detections, one uncovered area.
- NRT record later replaced by SP: counted once.
- Same archive file imported twice: counts unchanged.
- Chunked import: memory stays bounded while streaming a large synthetic file.

## Real-data verification (on the user's Windows PC)

The real-data acceptance criteria are verified only after real FIRMS data has been
imported with the user's MAP_KEY and/or official archive downloads. The coverage report
generated then (platforms, products, countries/areas, date ranges, gaps) is the only
basis for any coverage claim in the documentation.
