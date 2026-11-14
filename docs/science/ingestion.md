# FIRMS CSV ingestion — rules and assumptions

Module: `backend/app/ingestion/firms_csv.py` (schema tables in `firms_schema.py`).
Status: implemented and tested with SYNTHETIC TEST DATA only. No real FIRMS file has been
parsed yet; the first real import is a required verification step.

## Inputs

FIRMS active-fire CSV files from the Area API, the Archive Download Tool, and the yearly
per-country archive ZIPs (each `.csv` member is streamed; nothing is extracted to disk).
Files are read in chunks (default 200,000 rows) with every value kept as text first, so
original values are never altered by type inference.

## Sensor and platform identification

1. Sensor from the `instrument` column (`MODIS` / `VIIRS`); if absent, from channel
   columns (`bright_t31` → MODIS, `bright_ti4`/`bright_ti5` → VIIRS). A file mixing
   instruments is rejected.
2. Platform from the documented `satellite` codes: MODIS `A` = Aqua, `T` = Terra (full
   names accepted); VIIRS `N` = Suomi NPP, `N20` = NOAA-20, `N21` = NOAA-21.
3. An import may declare its platform (e.g. from the API `SOURCE`). Rows contradicting
   the declaration are reported invalid. If there is no `satellite` column, the
   declared platform is used; with neither, rows are invalid.
4. **Unrecognised satellite codes are rejected, not guessed.** If real archive files use
   other codes, they must be added to `SATELLITE_CODES` with a cited source.

## Field rules

| Field | Rule |
|---|---|
| Coordinates | Numeric, lat ∈ [−90, 90], lon ∈ [−180, 180]. Antimeridian values are valid. |
| Date / time | `acq_date` YYYY-MM-DD; `acq_time` HHMM UTC, leading zeros optional (`5` → 00:05). Stored as UTC. |
| Confidence | Raw value always kept. VIIRS `l/n/h` → low/nominal/high. MODIS 0–100 → low < 30, nominal 30–79, high ≥ 80. |
| Version | Kept raw. Suffix `NRT`/`RT`/`URT` gives processing status; no suffix = standard processing (SP), as documented by FIRMS. Collection parsed (MODIS 6.1, VIIRS 2); otherwise `unknown`. |
| FRP, brightness, scan, track | Numeric ≥ 0. **Blank stays missing (NaN), never 0.** |
| Day/night | `D` / `N` / blank. |
| Type | 0–3 when present (standard-quality data only). |
| Brightness | MODIS: `brightness` (primary), `bright_t31` (secondary). VIIRS: `bright_ti4` or `brightness` (web services), `bright_ti5`. |

## Provenance and accounting

- Every input row is either a valid canonical record or an invalid record with all
  failing reasons. Nothing is dropped silently. Malformed CSV lines stop the import with
  an error rather than being skipped.
- Each record carries source file, ZIP member, 1-based data-row number, file SHA-256,
  ingestion timestamp and the complete original row as JSON.
- Original files are copied unchanged into `data/raw/` under their checksum.

## Identity and duplicates

`observation_id` = BLAKE2b-128 of (sensor, platform, date, time, latitude and longitude
in 1e-5° units, version string). The same detection imported twice gets the same id.
The version is part of the identity, so an NRT record and its later SP replacement have
different ids; supersession is handled by the storage layer, not by deletion.
Duplicate removal across chunks and files is done in storage (Phase 2b).

## Open verification items

1. MODIS confidence class thresholds come from the MODIS Collection 6 Active Fire
   User's Guide (Giglio et al.) and have not yet been re-checked against the document.
2. The satellite codes used inside yearly per-country archive files must be checked on a
   real file.
3. Throughput in the build sandbox (pandas without pyarrow): about 63,000 rows/s,
   peak memory under 1 GB with 200,000-row chunks. To be re-measured on the Windows target.
