# FIRETRACE Architecture — Global Satellite Fire Intelligence Platform

Status: design baseline (2026-11-14). Nothing here is claimed to work until it is
listed as verified in `PROJECT_PROGRESS.md`.

## 1. Scope

FIRETRACE is global by design:

- **Spatial:** any country, first-level administrative region, bounding box or custom
  polygon on Earth, including areas crossing the antimeridian.
- **Temporal:** MODIS C6.1 (Terra from Nov 2000, Aqua from Jul 2002) and VIIRS 375 m C2
  (Suomi-NPP from Jan 2012, NOAA-20, NOAA-21) from their earliest records to the present.
  Actual availability is discovered at runtime, never hard-coded.
- **No default region.** The application has no built-in geographic restriction or
  default AOI baked into code. Example AOIs (e.g. Andhra Pradesh, India) are optional
  presets stored as data, removable without code changes.

**Coverage honesty rule:** global *capability* is not global *coverage*. The system only
reports coverage for the sensor, area and date combinations it has actually ingested
(see §5). Until real FIRMS data is imported and verified, the coverage registry is empty
and the UI says so.

## 2. Component overview

```
                ┌──────────────────────────────────────────────────────────┐
                │ Frontend (React + TS + Vite, Leaflet, Recharts)          │
                │ global map · AOI picker · calendar · analytics · export  │
                └──────────────▲───────────────────────────────────────────┘
                               │ REST (no secrets ever sent to browser)
                ┌──────────────┴───────────────────────────────────────────┐
                │ FastAPI backend                                           │
                │  api/ · services/ · analytics/ · harmonization/ · exports/│
                └──────┬───────────────┬──────────────────────┬────────────┘
                       │               │                      │
           ┌───────────▼───┐  ┌────────▼─────────┐  ┌─────────▼──────────┐
           │ SQLite         │  │ Observation store │  │ Aggregate store     │
           │ metadata:      │  │ partitioned       │  │ daily/monthly       │
           │ ingestions,    │  │ Parquet           │  │ per grid cell ×     │
           │ coverage,      │  │ sensor/year/month/│  │ platform (Parquet)  │
           │ AOIs, files    │  │ 10° tile          │  │                     │
           └───────────────┘  └───────▲───────────┘  └─────────▲──────────┘
                                      │ chunked writes         │ incremental rebuild
                       ┌──────────────┴────────────────────────┴─────────┐
                       │ Ingestion pipeline (streaming, idempotent)       │
                       │  Path A: FIRMS Area API (keyed, tiled, budgeted) │
                       │  Path B: FIRMS archive files (yearly country     │
                       │          CSVs, Archive Download Tool exports,    │
                       │          uploads) — zip/CSV streamed in chunks   │
                       └──────────────────────────────────────────────────┘
                                      ▲
                               data/raw/ (immutable originals + checksums)
```

## 3. Storage design (ADR-0001)

The spec names SQLite. A global 2000–present archive is on the order of hundreds of
millions of detections, which SQLite row storage cannot query interactively on a
16 GB CPU-only machine. Decision:

| Store | Technology | Contents |
|---|---|---|
| Metadata | SQLite (SQLAlchemy) | source files, checksums, ingestion runs, invalid-record reports, coverage registry, saved AOIs, calibration runs |
| Observations | Partitioned Parquet: `observations/<sensor>/<YYYY>/<MM>/<tile>/` (plain directory names; partition columns stay inside the files) | canonical hotspot records + preserved source attributes |
| Aggregates | Parquet | daily and monthly counts per (platform, grid cell): detections, day/night split, FRP sum/max, confidence-class counts |
| Query engine | DuckDB (in-process, CPU) | predicate- and partition-pruned scans; never loads the archive into RAM |

`tile` is a 10°×10° lat/lon tile id (648 tiles). An AOI query reads only the
sensor/year/month/tile partitions that intersect the AOI and date range.

SQLite remains available for small regional installs; the storage interface is
abstracted so the observation backend can be swapped. New dependencies required:
`pyarrow`, `duckdb` (to be pinned after a verified install).

## 4. Ingestion workflows

### Path A — FIRMS Area API (recent data and keyed backfill)

- Endpoint shape: `/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north|world}/{DAY_RANGE}[/{YYYY-MM-DD}]`.
- Sources include `MODIS_NRT`, `MODIS_SP`, `VIIRS_SNPP_NRT`, `VIIRS_SNPP_SP`,
  `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT` (and any SP variants the availability
  service reports). The source list is read from `/api/data_availability/`, not hard-coded.
- **Maximum DAY_RANGE is configurable** (`FIRMS_AREA_MAX_DAY_RANGE`). NASA's API page
  shows 1–10; some third-party descriptions say 1–5. Default 5 until verified against
  the live service.
- Requests are tiled by date window × spatial tile when a world query would be too large.
- Transaction budget: FIRMS limits each MAP_KEY (reported as 5000 transactions per
  10 minutes; multi-day requests count as several). A token-bucket limiter, retry with
  backoff, timeouts and resumable job state are mandatory.
- The MAP_KEY lives only in `backend/.env`.

The Area API is **not** used as the primary global historical source.

### Path B — FIRMS historical archive (global history)

1. **Yearly country summaries** (FIRMS "Download yearly summary by country"): per-sensor,
   per-year ZIPs containing one CSV per country. Covers every country and year, giving a
   global history by importing all country files.
2. **Archive Download Tool exports**: custom country/area/date requests (CSV/JSON/SHP),
   delivered after email authentication. These can include NRT records, which FIRMS
   replaces with standard-quality data after a lag of about 5 months.
3. **User uploads** of either of the above through the UI or a CLI (`python -m app.cli.import_archive`
   pointed at a folder of ZIP/CSV files).

Processing (both paths):

- The original file is copied to `data/raw/` unchanged; its SHA-256 is recorded.
  Re-importing an identical file is a no-op.
- ZIPs are streamed member by member; CSVs are read in chunks (default 200k rows).
- Each chunk goes through validation → canonical mapping → grid assignment → partitioned append.
- Record identity key: (platform, instrument, acq_date, acq_time, latitude, longitude,
  product, version). Exact duplicates are skipped and counted; possible cross-sensor
  or spatial-temporal duplicates are flagged, never deleted.
- **NRT → SP replacement:** when an SP record set covers a (platform, date, tile) that
  holds NRT records, the NRT records are marked `superseded` (not deleted) and excluded
  from analytics, so the same detection is never counted twice.
- Aggregates are rebuilt incrementally, only for the partitions touched by an ingestion run.
- Failed runs are resumable; partial partitions are written to a staging location and
  committed atomically.

## 5. Coverage registry (missing data ≠ zero activity)

Each ingestion records what it **covers**, not only what it contains: platform,
product, processing status, spatial extent (country code, bbox or polygon) and
date range. A day with zero detections inside a covered extent is a valid zero; a day
outside any covered extent is *missing*.

For an AOI and month the calendar reports per platform:
`complete` · `partial` (coverage fraction shown) · `missing` · `not yet launched / decommissioned`.

Platform operating windows come from the availability service plus documented launch
dates, so pre-launch months are never shown as zero.

## 6. Geospatial model

- Input coordinates: WGS84 (EPSG:4326) as delivered by FIRMS.
- Common grid: EASE-Grid 2.0 global equal-area (EPSG:6933), configurable resolution,
  default 1 km. Integer cell indices (col, row) are stored with each record.
- EPSG:6933 is defined to roughly ±86° latitude; detections beyond its valid range are
  kept but flagged as un-gridded (documented limitation).
- A grid cell is a counting unit, not a fire perimeter.
- AOIs are GeoJSON. Selectable types: country (admin-0), first-level region (admin-1),
  bbox, drawn polygon, lat/lon input.
- Boundaries: Natural Earth (public domain) admin-0/admin-1, downloaded by a setup
  script and stored under `data/reference/` with version and checksum. Users can upload
  their own boundary GeoJSON.
- Polygons crossing the antimeridian are split at ±180° before filtering. Geometry
  validation rejects self-intersections and invalid rings with a clear message.
- AOI filtering: partition pruning by tile → bbox prefilter → exact Shapely containment
  (vectorised) on the remaining rows.

## 7. Harmonization and analytics (per-AOI, sensor-aware)

The spec stages A–G apply unchanged, computed for whatever AOI is selected:

- Raw detection counts and unique active grid cells kept per platform.
- Baselines per platform × AOI × calendar month (median, MAD, percentiles) using only
  months with complete coverage. Too few historical years → `insufficient history`.
- Harmonized activity index: combines platform-specific robust anomalies, never raw counts.
- Cross-sensor calibration is estimated only from matched MODIS–VIIRS observations in the
  overlap period, with train/validation split. Calibration may differ by biome and region,
  so global results are reported per region and marked experimental unless validated there.
- Results for an AOI are cached by (AOI geometry hash, filters, data version).

## 8. Global map rendering

- Zoomed out: server-side aggregated grid/density tiles (no per-point rendering of
  millions of detections).
- Zoomed in, or under a point-count threshold: individual hotspots with sensor layers,
  FRP and confidence styling.
- All map queries are paged/limited server-side.

## 9. Exports

Filtered hotspot CSV (streamed, any AOI), calendar CSV, analytics JSON, and a report,
each with a provenance header: source files, products, processing status, coverage and
AOI definition.

## 10. Security

MAP_KEY and Earthdata credentials live only in backend environment variables. No secret
is ever returned by an endpoint or bundled into the frontend.
