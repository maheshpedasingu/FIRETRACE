# Changelog

## [Unreleased]
### Added (Phase 7, harmonized calendar)
- Harmonized burning activity calendar (`GET /api/calendar/harmonized`, dashboard
  Calendar → "Harmonized (one calendar)", CSV export with provenance): one continuous
  series in MODIS (Terra+Aqua)- or Suomi-NPP-equivalent units, with per-month source,
  conversion factor, validation uncertainty, history comparison and the conversion fits.
- Latest month vs the median of earlier complete years, and the typical fire season.
- Dashboard "Inside country" field and an India example, so FIRMS country downloads
  count as coverage for areas inside that country.

### Fixed (Phase 7)
- Coverage no longer starts before a platform's first FIRMS record (e.g. Aqua before
  4 July 2002), which would otherwise show false real zeros for archive requests that
  reach back before a satellite's launch; likewise after its last record (Suomi-NPP
  ends 2026-11-02). NOAA-21 data start corrected to 2023-03-01 (FIRMS Archive Download).
- Archive files mixing SP and NRT records: SP coverage now ends on the last SP day and
  NRT covers the days after it. Before, SP appeared to cover the NRT months and the
  SP-supersedes-NRT rule would have dropped real NRT detections.
- Multi-decade queries: the monthly series groups rows once instead of scanning per
  month; MODIS–VIIRS detection matching uses the last 366 days of the period so memory
  stays bounded (the monthly calibration still uses the whole period).

## [1.0.0] - 2026-11-14
### Added (release)
- MIT `LICENSE`; dashboard screenshots in `docs/screenshots/` and the README.

### Added (Phase 6b)
- `docs/FINAL_REPORT.md` (spec §18), `docs/DATA_PROVENANCE.md`,
  `docs/science/METHODOLOGY.md`; documentation index in the README.
- Test of MODIS confidence class boundaries (0/29/30/79/80/100).

### Changed (Phase 6b)
- MODIS confidence thresholds checked against the MODIS C6/C6.1 Active Fire User's
  Guide v1.0, Table 11 (implementation unchanged; it already matched).
- README: status, verified clean-clone install, removed the empty `scripts/` entry.

### Fixed (Phase 6b)
- Overview per-platform table showed 0 detections for platforms with no imported
  coverage of the area; it now shows "—" (unknown), keeping 0 for covered areas.
- Table columns in the dashboard had no gap between right- and left-aligned headers.
- Dev dependency `httpx2` (pinned 2.16.0 with `httpcore2`, `truststore`): Starlette's
  TestClient uses it, removing its httpx deprecation warning. Application code keeps httpx.

### Changed (Phase 6a, performance)
- Imports buffer rows per partition and write each partition as a slice of one Arrow
  table, with progress output. Benchmark: clustered spread by default, `--spread uniform`
  as the worst case. Windows results in `docs/validation/performance.md`.

### Added (Phase 6a)
- Crash-safe partition compaction with recovery and store verification (`python -m app.cli.compact`).
- Synthetic performance benchmark in an isolated folder (`python -m app.cli.benchmark`).

### Changed
- API timestamps from the database carry an explicit UTC offset; the dashboard shows
  `YYYY-MM-DD HH:MM UTC`. Store readers skip hidden directories.

### Added (Phase 5b)
- Dashboard: overview, map with area drawing and sensor-encoded detections, calendar heatmap
  with non-colour state cues, analytics charts, data explorer, ingestion and export pages.
  Colour encodings validated for colour-vision deficiency. Docs: `docs/architecture/frontend.md`.

### Added (Phase 5a)
- REST API covering every endpoint of the specification (§11) with validation, pagination,
  saved AOIs (bbox or Shapely-validated GeoJSON polygons), upload and FIRMS ingestion, CSV /
  zip-with-provenance / report exports. Documentation: `docs/api/README.md`.

### Fixed
- Calendar grid no longer fills float columns with text (Pandas4Warning).

### Added (Phase 4)
- Burning activity calendar with explicit cell states (value / zero / partial / uncovered /
  missing) and anomaly overlay; yearly totals with year-over-year change for complete years;
  FRP, confidence and day/night distributions; streamed hotspot CSV, calendar CSV/grid and
  analytics JSON exports with provenance sidecars (`python -m app.cli.export`).
- One shared NRT/SP supersession rule for series, calendars, distributions and exports.

### Added (Phase 3b)
- Per-platform monthly baselines with robust modified-z anomalies and explicit
  insufficient-history / incomplete-coverage / zero-dispersion states; experimental harmonized
  activity index; MODIS–VIIRS monthly calibration (train/validation) and detection matching;
  JSON/Markdown validation report via `python -m app.cli.anomaly_report`.

### Added (Phase 3a)
- EPSG:6933 equal-area grid (configurable resolution), per-platform cell-day aggregates with
  incremental rebuild, coverage-aware monthly area series, `python -m app.cli.area_summary`.
  Methodology: `docs/science/harmonization.md`.

### Fixed
- `--bbox` values starting with '-' (west/south hemispheres) were read as options.
- `data/downloads/` and `data/reference/` are now ignored by Git.

### Added
- First real data: 462 NOAA-20 VIIRS NRT detections (2026-11-11..13, example area) and a
  verified zero-detection MODIS window. Live FIRMS findings in `docs/architecture/firms-api.md`.
- FIRMS Area API client and `python -m app.cli.fetch_firms`: availability check, date windows,
  antimeridian split, transaction budget, retries, resumable downloads, import with `api_request`
  coverage. Docs: `docs/architecture/firms-api.md`.
- Storage: partitioned Parquet observation store (sensor/year/month/10° tile) with staging and
  atomic commit; SQLite metadata (source files, runs, invalid records, coverage); importer with
  file- and detection-level duplicate prevention and crash recovery; `python -m app.cli.import_archive`.
  Docs: `docs/architecture/storage.md`.
- FIRMS CSV parser: canonical hotspot schema, MODIS (Terra/Aqua) and VIIRS (Suomi-NPP, NOAA-20, NOAA-21)
  identification from documented codes, row validation with reasons, chunked CSV and ZIP
  streaming, SHA-256 provenance and immutable raw-file store. Docs: `docs/science/ingestion.md`.

## [0.1-foundation] — 2026-11-14
### Added
- FastAPI app with `GET /api/health` (reports whether a MAP_KEY is configured, never the key).
- React + TypeScript + Vite + Tailwind shell showing backend status and an empty-coverage notice.
- Pinned dependencies: `backend/requirements.txt`, `frontend/package-lock.json`.
- Verified on Windows: pytest 4 passed, ruff clean, Vitest 2 passed, production build OK.

### Changed
- Scope corrected to a global platform: any country, region, bbox or polygon worldwide;
  full MODIS/VIIRS history. Andhra Pradesh is only an optional example preset.
- Storage design: SQLite metadata + partitioned Parquet/DuckDB observation store (ADR-0001).

### Added
- `docs/architecture/ARCHITECTURE.md` (global ingestion, coverage registry, storage, AOI model).
- `docs/IMPLEMENTATION_PLAN.md` (45-hour plan with a global synthetic test matrix).
- Repository structure, `.gitignore`, `.env.example`, progress log and README.
