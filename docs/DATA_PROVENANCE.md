# Data provenance

This document lists where FIRETRACE data comes from, how its origin is kept, and exactly
which real datasets have been processed. It is updated whenever real data is imported.

## Sources

| Source | Products | Used for | Access |
|---|---|---|---|
| NASA FIRMS Area API | MODIS_NRT, MODIS_SP, VIIRS_SNPP_NRT/SP, VIIRS_NOAA20_NRT/SP, VIIRS_NOAA21_NRT | Recent data and keyed backfill | `python -m app.cli.fetch_firms` or `POST /api/ingest/firms`; needs a free MAP_KEY |
| NASA FIRMS data availability service | `ALL` | Which products and dates the API can return | `GET /api/data/availability` |
| NASA FIRMS archive (yearly per-country summaries, Archive Download Tool) | MODIS C6.1 and VIIRS C2 SP/NRT CSV and ZIP | Historical record | Downloaded by the user, imported with `python -m app.cli.import_archive` or `POST /api/ingest/upload` |

Product definitions, collection versions and attribute meanings follow NASA Earthdata,
"FIRMS active fire data attributes (MODIS, VIIRS)", and the MODIS C6/C6.1 and VIIRS C2
375 m Active Fire User's Guides. Required citations: see the FIRMS citation policy on
the NASA Earthdata FIRMS pages.

Out of scope: Landsat, GOES and burned-area products offered by FIRMS.

## How provenance is kept

1. **Original file**: every imported file is copied unchanged into `data/raw/`, named by
   its SHA-256 checksum. A file with a known checksum is not imported twice.
2. **Import run**: SQLite tables `source_files` and `ingestion_runs` record the original
   file name (as given by the user or the API request), checksum, size, start and end
   time, row counts (read / valid / invalid / duplicate / written) and status.
3. **Request**: API downloads record the product, area, dates and request time
   (`api_request` coverage); the MAP_KEY is never stored or logged.
4. **Every detection** carries source file, ZIP member, 1-based row number, file
   SHA-256, ingestion time and the complete original row as JSON. Values are never
   altered; derived fields (UTC time, platform, confidence class, processing status) are
   stored beside them.
5. **Invalid rows** are kept in `invalid_records` with every failing reason. Nothing is
   dropped silently.
6. **Coverage** (which area, dates and platforms an import covered) is taken only from
   the request or archive file name, never inferred from detections. Without it the
   coverage is `unknown`, and no zero is ever reported for it.
7. **Exports** carry a `.provenance.json` sidecar with area, period, filters, platforms,
   rows per platform, NRT rows superseded by SP, source files with SHA-256, and caveats.

## Real data processed (complete list, as of 2026-11-14)

| # | Product | Platform | Area | UTC dates | Detections | Invalid | Result |
|---|---|---|---|---|---|---|---|
| 1 | VIIRS_NOAA20_NRT (C2, NRT, version `2.0NRT`) | NOAA-20 | bbox 76.7, 12.6, 84.8, 19.9 (approx. Andhra Pradesh, India; an example area) | 2026-11-11 to 2026-11-13 | 462 | 0 | Imported; re-import skipped by checksum; store verified (0 duplicate ids, 0 misplaced rows); November 2026: 386 cell-days, 363 unique 1 km cells, partial coverage (3 of 14 days) |
| 2 | MODIS_NRT (C6.1, NRT) | Terra, Aqua | bbox −150, −30, −140, −20 (open South Pacific) | 2026-11-12 | 0 | 0 | Header-only response; recorded as a covered zero for both platforms |

Both came from the FIRMS Area API on the user's Windows PC. **This is all the real data
FIRETRACE has processed.** There is no global coverage, no multi-year history and no
standard-processing (SP) data yet. Every other result in this repository (tests,
benchmarks) uses data labelled SYNTHETIC TEST DATA.

Live FIRMS observations made while fetching (2026-11-14) are in
`docs/architecture/firms-api.md` (availability columns, end dates per product, DAY_RANGE
limit of 5, header-only empty responses, real column layout).

## Not stored in the repository

`data/raw/`, `data/processed/`, `data/uploads/`, `data/downloads/`, exports and
`backend/.env` are git-ignored. Real data stays on the user's machine; the repository
contains code, documentation and synthetic test fixtures only.
