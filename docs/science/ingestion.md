# FIRMS CSV ingestion — rules and assumptions

Module: `backend/app/ingestion/firms_csv.py` (schema tables in `firms_schema.py`).
Status: implemented and tested with SYNTHETIC TEST DATA; verified on real FIRMS Area API
files (one VIIRS NOAA-20 NRT file with 462 detections and one header-only MODIS NRT
file; see `docs/DATA_PROVENANCE.md`). Yearly archive files have not been imported yet.

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
| Confidence | Raw value always kept. VIIRS `l/n/h` → low/nominal/high. MODIS 0–100 % → low 0 ≤ C < 30, nominal 30 ≤ C < 80, high 80 ≤ C ≤ 100 (MODIS C6/C6.1 Active Fire User's Guide v1.0, FAQ 8.4.3, Table 11). |
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

1. Done (2026-11-14): MODIS confidence class thresholds checked against the MODIS
   C6/C6.1 Active Fire Product User's Guide v1.0, Table 11; the implementation matches.
2. Partly done (2026-11-15): a real FIRMS Archive Download for India (VIIRS S-NPP C2,
   2012-01-20 to 2026-11-02) uses `satellite` = `instrument` = `SNPP`, MODIS-style
   column names `brightness` / `bright_t31` for the VIIRS I4 / I5 temperatures, a
   `type` column (0–3) in the standard-processing file only, and splits standard (to
   2026-07-31, version `2`) and NRT (from 2026-08-01, version `2.0NRT`) into
   `fire_archive_*` and `fire_nrt_*` members. These are accepted. The MODIS C6.1
   Archive Download for India (2000-11-01 to 2026-11-07) uses `satellite` Terra / Aqua,
   `instrument` MODIS, version `6.03` (Collection 6) or `61.03` (Collection 6.1) for
   standard processing (to 2026-08-31) and `6.1NRT` after it, and confirms the first
   records: Terra 2000-11-01, Aqua 2002-07-04. Still unconfirmed: archive codes for
   NOAA-20/21 and yearly per-country summary files; unknown values are rejected, never
   guessed.
3. Done: end-to-end import throughput on the Windows target is in
   `docs/validation/performance.md` (about 5,600 rows/s at 2 million rows, including
   duplicate checks and partitioned writes).

## Implementation note: pandas string backends

pandas 3 stores text with pyarrow when it is installed (as on the Windows target) and as
Python objects otherwise (as in the build sandbox). With pyarrow, values written into a
text column lose any Python subclass (e.g. enum members become plain `str`). An early
version relied on enum identity after `Series.map` and rejected every VIIRS row on
Windows while passing in the sandbox. All lookup tables used with pandas now map to plain
strings, and a regression test checks this. Tests must be run on the Windows target
before any parser change is merged.
