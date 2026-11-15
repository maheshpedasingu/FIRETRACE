# FIRETRACE — final report

Specification: FIRETRACE Master Engineering Specification (45-hour sprint), §18, as
amended by the global-scope correction of 2026-11-14. Report date: 2026-11-15 (v1.1.0;
v1.0.0 on 2026-11-14).
All verification was done on the user's Windows 11 PC; nothing below is claimed unless
it was run there.

## 1. What was built

FIRETRACE (Fire Intelligence and Historical Activity Monitoring System) is a local web
application that imports NASA FIRMS MODIS (Terra, Aqua; C6.1) and VIIRS 375 m
(Suomi-NPP, NOAA-20, NOAA-21; C2) active-fire detections for any area on Earth, keeps
their full provenance, aggregates them on an equal-area 1 km grid per sensor and
platform, and presents a coverage-aware historical burning-activity calendar, analytics,
experimental anomaly and cross-sensor diagnostics, and CSV exports.

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy/SQLite (metadata), partitioned
  Parquet via pandas/pyarrow (observations and aggregates), Shapely (polygons).
- Frontend: React 19, TypeScript, Vite, Tailwind CSS, Leaflet, Recharts.
- Command-line tools for bulk work: import, fetch, area summary, anomaly report, export,
  compaction/verification, benchmark.

## 2. Implemented features

| Area | Features |
|---|---|
| Ingestion | Chunked CSV/ZIP parsing of FIRMS files (Area API, archive tool, yearly country archives); MODIS/VIIRS adapters; validation with reasons for every invalid row; SHA-256 provenance; duplicate detection within and across files; crash-safe staged commits; FIRMS Area API client with availability check, 5-day windows, antimeridian splitting, transaction budget, retries and resumable downloads |
| Storage | SQLite metadata; Parquet partitioned by sensor / year / month / 10° tile; buffered writes; compaction with recovery; store verification |
| Coverage | Coverage registry from requests and archive names; complete / partial / missing months; zeros only where covered |
| Harmonization | EPSG:6933 1 km grid; cell-day aggregates per platform and processing status; incremental aggregate store; NRT→SP supersession |
| Analytics | Monthly series; calendar (value / zero / partial / uncovered / missing); yearly totals and YoY for complete years; FRP / confidence / day-night distributions; experimental baselines, modified z, HAI, MODIS–VIIRS calibration and detection matching; validation report (JSON + Markdown) |
| AOI | Bounding boxes (antimeridian-aware), GeoJSON polygons validated with Shapely, saved AOIs, example presets with no default region |
| API | All §11 endpoints: health, sensors, availability, upload and FIRMS ingestion, history, hotspots (paginated), summary, calendar, monthly, yearly, anomalies, sensor comparison, AOIs, CSV/zip/report exports (`docs/api/README.md`) |
| Dashboard | Overview with imported coverage, Map (area drawing, sensor-encoded detections), Calendar heatmap with non-colour state cues, Analytics charts, Data explorer, Ingestion, Export; colours checked for colour-vision deficiency and contrast; timestamps shown in UTC |
| Exports | Hotspot CSV, calendar CSV (long and grid), analytics JSON, each with a provenance sidecar |
| Security | MAP_KEY only in git-ignored `backend/.env`, redacted from errors, never sent to the frontend |

## 2a. Added in v1.1 (harmonized calendar)

A single harmonized burning-activity calendar per area: MODIS (Terra+Aqua) or Suomi-NPP
is the reference unit; every other source gets one conversion factor fitted on
completely covered overlap months and tested on held-out years; factors with too little
overlap are `unavailable`, and factors whose held-out error exceeds 100% of the mean are
`rejected` — neither is ever applied. Each month records its source, factor and
uncertainty. Also: latest complete month vs history, typical fire season, PNG/SVG image
downloads of calendars and charts, "Point + radius (km)" areas, "Inside country" for
FIRMS country downloads, platform record periods (no false zeros before a launch or after
an end), SP/NRT coverage split, streamed area statistics (India 2000–2026 in ~0.6 GB),
and a store-generation cache.

## 3. Satellite datasets actually processed

| Product | Platform | Area | Detections |
|---|---|---|---|
| VIIRS_NOAA20_NRT (C2) | NOAA-20 | bbox 76.7, 12.6, 84.8, 19.9 | 462 (0 invalid) |
| MODIS_NRT (C6.1) | Terra, Aqua | bbox −150, −30, −140, −20 | 0 (covered zero) |

Both via the FIRMS Area API (v1.0). Added for v1.1, FIRMS Archive Download for the
country India, 2000-11-01 to 2026-11-07:

| Product | Platform | Detections |
|---|---|---:|
| MODIS C6/C6.1 (SP to 2026-08, NRT after) | Terra | 596,463 |
| MODIS C6/C6.1 (SP to 2026-08, NRT after) | Aqua | 1,327,528 |
| VIIRS 375 m C2 (SP to 2026-07, NRT after) | Suomi-NPP | 8,758,389 |
| | **Total** | **10,682,380** |

Details: `docs/DATA_PROVENANCE.md`.

## 4. Actual date coverage

- NOAA-20 VIIRS NRT: 2026-11-11 to 2026-11-13 over the first area only.
- Terra and Aqua MODIS NRT: 2026-11-12 over the second area only.
- v1.1: India (country download) — Terra from 2000-11-01, Aqua from 2002-07-04,
  Suomi-NPP from 2012-01-20, all to 2026-11-07.
- Nothing else. FIRETRACE supports global areas and full sensor history but **does not
  hold global coverage**; NOAA-20/21 history was not imported. All other months show as
  missing, not zero.

FIRMS service availability observed live on 2026-11-14 (not imported): SP data to
2026-07-31 (VIIRS) and 2026-08-31 (MODIS); Suomi-NPP NRT to 2026-11-02
(`docs/architecture/firms-api.md`).

## 5. Harmonization methodology

Summary in `docs/science/METHODOLOGY.md`; details in `docs/science/harmonization.md`.
Original measurements preserved (A); equal-area 1 km grid (B); UTC cell-day aggregates
per platform (C); per-platform same-month baselines with modified z (D); area-specific
MODIS–VIIRS scale factor with train/validation split and detection matching (E); HAI as
a mean of per-sensor anomaly scores, never a sum of raw counts (F); validation report
(G). D–G are experimental.

## 6. Validation results

| Check | Result |
|---|---|
| Real NOAA-20 import | 462 rows, 0 invalid; columns, codes and bbox bounds inspected; re-import skipped by checksum |
| Store verification (real store) | 0 duplicate ids, 0 misplaced rows |
| Real-data area summary | Nov 2026: 386 cell-days, 363 unique cells, partial coverage 3/14 days |
| Real-data anomaly report | All platforms "not assessed (incomplete_coverage)" — correct for 3 days of data |
| Empty FIRMS window | Recorded as a covered zero for Terra and Aqua |
| Grid | EPSG:6933 implementation within 1 mm of PyProj; global extent and ellipsoid area reproduced |
| MODIS confidence classes | Match MODIS C6/C6.1 User's Guide Table 11; boundary test 0/29/30/79/80/100 |
| Performance (synthetic) | 2,000,000 rows: import 359 s, compaction 406 s, verify 55 s, aggregates 154 s, 20°×20° 2-year query 51 s, peak 1.64 GB; 0 duplicates, 0 misplaced (`docs/validation/performance.md`) |
| v1.1 real India data (26 years) | Imported totals match NASA's files; seasonality March–April and November; fits in MODIS units Aqua 1.429 (21%), Terra 3.329 (49%), Suomi-NPP 0.142 (24%, log correlation 0.99) (`docs/validation/india_harmonization.md`) |
| v1.1 Punjab circle (100 km, 2012–2026) | November peak (crop-residue burning) and its decline since 2021; Terra factor rejected (196% held-out error) |
| v1.1 memory and speed (India 2000–2026) | Area context 44 s, peak 604 MB; summary 4 s; harmonized calendar 0.8 s (`docs/validation/performance.md`) |
| Still experimental | Harmonization factors, anomalies and HAI: validated on one country only |

## 7. Test results

On the Windows PC, clean clone of `phase6-delivery` (commit de125b8, 2026-11-14):
backend pytest **187 passed, 0 warnings**; ruff clean; `npm ci` 0 vulnerabilities;
Vitest **25 passed**; `tsc --noEmit` + `vite build` succeeded (main chunk 259.95 kB, Map
and Analytics lazy-loaded); `GET /api/health` ok without a MAP_KEY.

The release adds a MODIS confidence boundary test and three coverage-display tests:
v1.0.0 is merged only after **188** backend and **28** frontend tests pass on Windows
with ruff clean and a successful build.

Found and fixed during final screenshots: the Overview showed 0 detections for
platforms without imported coverage of the area; it now shows "—" (unknown).

v1.1 (branch `phase7-harmonized`, 2026-11-15): last verified Windows run pytest **223
passed**, Vitest **36 passed**, build OK (7l); later commits add tests. v1.1.0 is merged
only after **224** backend and **46** frontend tests pass on Windows with a successful
build.

All test data is labelled SYNTHETIC TEST DATA.

## 8. Known limitations

See `docs/science/METHODOLOGY.md` § Known limitations. In short: real history imported
for one country (India) and three platforms; one constant conversion factor per source
and area cannot follow every season; no bundled country/admin boundaries;
file count limits speed on Windows; partial-area SP days drop NRT for the whole area;
matching does not cross midnight UTC.

## 9. Installation commands (Windows PowerShell)

```powershell
git clone https://github.com/maheshpedasingu/FIRETRACE.git
cd FIRETRACE\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd ..\frontend
npm ci
```

Optional: copy `.env.example` to `backend\.env` and set `FIRMS_MAP_KEY` to fetch data
from the FIRMS API. Without it, files can still be imported.

## 10. Application startup commands

```powershell
# terminal 1
cd backend; .\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8000
# terminal 2
cd frontend; npm run dev
```

Dashboard http://localhost:5173 · health http://127.0.0.1:8000/api/health · API docs
http://127.0.0.1:8000/docs.

## 11. Git commit history

Feature and fix commits (oldest first): 525e76c structure · b3d71f9 global scope ·
c153be8 health endpoint and shell · 30134a9 pinned dependencies · 1cfe2e4 phase 1 docs ·
6b16ee9 FIRMS parser · 427cfdf pyarrow string fix · 3f85830 store and importer ·
eecf2f2 Area API client · 0f6ebaa negative bbox fix · 36ffc9b grid and aggregates ·
235b283 baselines and cross-sensor · 0aa0a3f calendar and exports · 6a14ae2 REST API ·
7964055 upload provenance fix · 43367d9 dashboard · 777faa8 form validation and lazy
loading · fdafbac compaction and benchmark · 9808fcf buffered imports · a72caa9 slice
writes · 3b8af43 benchmark results · de125b8 httpx2 pin · plus the final documentation
commits of `phase6-delivery`.

Merge commits made on the Windows PC after each verification: 682cad9, c23a298,
e6065b9, b03031c, 0a7df83, bcf740d, adb7936, 5b452c9, f0309fd, b0ac976, f761251, and
the v1.0.0 merge of `phase6-delivery`.

## 12. Git tags

| Tag | Commit | Milestone |
|---|---|---|
| v0.1-foundation | 682cad9 | Health endpoint and frontend shell |
| v0.2-data-ingestion | 0a7df83 | Parser, store, importer, Area API |
| v0.3-harmonization | adb7936 | Grid, aggregates, baselines, cross-sensor |
| v0.4-analytics | 5b452c9 | Calendar, yearly analytics, exports |
| v0.5-dashboard | b0ac976 | REST API and dashboard |
| v0.6-validation | f761251 | Compaction, verification, benchmark |
| v1.0.0 | merge of `phase6-delivery` | Final delivery |
| v1.1.0 | merge of `phase7-harmonized` | Harmonized calendar, real India validation |

## 13. Repository status

`main` on GitHub (https://github.com/maheshpedasingu/FIRETRACE) contains every verified
checkpoint; feature branches are kept. No secrets, `.env` files or real data are
committed. Real data and processed stores live only on the user's machine.

## 14. Next recommended engineering improvements

1. Validate on more regions (another fire regime, e.g. a savanna country) and import
   NOAA-20/21 history; then reconsider the "experimental" labels.
1a. Seasonal (per-month) conversion factors where enough overlap exists.
2. Bundle country and admin-1 boundaries (e.g. Natural Earth) for area selection.
3. Speed for sparse global data: per-partition id index instead of re-reading ids,
   yearly partitions for archive data, parallel aggregate builds, DuckDB queries.
4. Make NRT/SP supersession aware of partial SP area coverage.
5. Allow detection matching across midnight UTC.
6. Background job queue for large uploads and API backfills with progress in the UI.
