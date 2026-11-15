# FIRETRACE — Project Progress

Each checkpoint lists what was verified and the commit hash. A phase is only marked
complete after its tests and checks have actually run.

## Scope

FIRETRACE is a **global** satellite fire intelligence platform (scope correction,
2026-11-14). It has no geographic restriction or default region. Andhra Pradesh, India
is at most an optional example preset. Coverage claims are limited to data actually
imported and verified. See `docs/architecture/ARCHITECTURE.md`.

## Data coverage (verified)

| Platform | Product | Areas | Date range | Source files | Verified |
|---|---|---|---|---|---|
| NOAA-20 VIIRS | VIIRS_NOAA20_NRT (C2, NRT) | bbox 76.7,12.6,84.8,19.9 (example area, roughly Andhra Pradesh) | 2026-11-11..2026-11-13 | 1 Area API response | Yes — 462 detections, 0 invalid; inspected (columns, codes, bbox bounds, unique ids); re-run skipped |
| Terra + Aqua MODIS | MODIS_NRT (C6.1, NRT) | bbox -150,-30,-140,-20 (open South Pacific) | 2026-11-12 | 1 Area API response | Yes — header only, 0 detections, recorded as a covered zero |

| Terra + Aqua MODIS | FIRMS archive (C6/C6.1 SP, then NRT) | country India | Terra 2000-11-01, Aqua 2002-07-04 .. 2026-11-07 | DL_FIRE_M-C61_850389.zip | Yes — 1,923,991 detections, totals checked |
| Suomi-NPP VIIRS | FIRMS archive (C2 SP, then NRT) | country India | 2012-01-20..2026-11-07 | DL_FIRE_SV-C2_850390.zip | Yes — 8,758,389 detections, totals checked |

This is the entire imported dataset. FIRETRACE has **no global coverage**; history exists
for India only. Automated tests still use
only fixtures labelled SYNTHETIC TEST DATA.

## Environment assessment (2026-11-14, build sandbox)

| Item | Found | Spec requirement | Status |
|---|---|---|---|
| Python | 3.13.18 | 3.12 preferred | OK (3.12 targeted for Windows) |
| Node / npm | 22.23.4 / 10.9.9 | installed compatible | OK |
| Git | 2.43.0 | required | OK |
| pandas / numpy / scipy | 3.0.5 / 2.5.3 / 1.18.1 | required | Available |
| pydantic / pytest / uvicorn | 2.13.5 / 9.1.1 / 0.54.0 | required | Available |
| ruff | present | required | Available |
| FastAPI, SQLAlchemy, httpx | missing | required | **BLOCKED — package installs refused** |
| GeoPandas, Shapely, PyProj | missing | required | **BLOCKED — package installs refused** |
| pyarrow, DuckDB | missing | required for global storage (ADR-0001) | **BLOCKED — package installs refused** |
| Vite, React-Leaflet, Leaflet, Recharts, Vitest, Testing Library | missing | required | **BLOCKED — npm registry unreachable** |
| NASA FIRMS (API + archive) | unreachable from build shell | real data required | **BLOCKED — no outbound access to FIRMS** |

Decision (2026-11-14): development continues in a new session with package installs
enabled. Real data is imported later on the user's Windows PC.

## Architecture decisions

| ID | Decision | Reason |
|---|---|---|
| ADR-0001 | SQLite for metadata; partitioned Parquet + DuckDB for observations and aggregates | Global 2000–present archive is too large for interactive SQLite row queries on 16 GB CPU-only hardware |
| ADR-0002 | Coverage registry records the spatial/temporal extent of every ingestion | Separates missing data from valid zero activity worldwide |
| ADR-0003 | Area API max DAY_RANGE is configurable, default 5 | Verified live 2026-11-14: FIRMS rejects 10 with "Expects [1..5]" (NASA's page shows 1–10) |

## Development workflow

Code is written in the Claude chat sandbox (no package installs, no network) and
delivered as a git bundle on a feature branch. Verification happens on the Windows
target: tests, lint, type check, build and startup. Only verified work is merged into
`main` and tagged.

## Checkpoints

| Phase | Status | Verification | Commit |
|---|---|---|---|
| 0. Repository structure and config templates | Done | Structure and secret exclusions inspected | 525e76c |
| 0. Global scope — architecture, plan, docs | Done (documentation only) | Docs reviewed | b3d71f9 |
| 1. Foundation — FastAPI `/api/health`, React/Vite/Tailwind shell | **Done — verified 2026-11-14 on Windows** | See Phase 1 results below | c153be8, 30134a9, merge 682cad9, tag `v0.1-foundation` |
| 2a. FIRMS CSV parser — canonical schema, MODIS/VIIRS adapters, validation, chunked CSV/ZIP, SHA-256 provenance | **Done — verified 2026-11-14 on Windows** | pytest 35 passed (incl. 4 health), ruff clean. First run failed 11 VIIRS tests (pyarrow strings dropped enum identity), fixed in 427cfdf. SYNTHETIC TEST DATA only | 6b16ee9, 427cfdf, merge c23a298 |
| 2b. Storage — partitioned Parquet store, SQLite metadata, importer (dedupe, invalid records, coverage, crash recovery), CLI | **Done — verified 2026-11-14 on Windows** | pytest 60 passed on first run, ruff clean. SYNTHETIC TEST DATA only | 3f85830, merge e6065b9 |
| 2c. FIRMS Area API client — availability, date windows, antimeridian split, transaction budget, retries, resumable downloads, import with api_request coverage; `python -m app.cli.fetch_firms` | **Done — verified 2026-11-14 on Windows + live** | Merged by the user after the Windows test run (expected 89 tests; output not shared). Live: availability table, 462 real NOAA-20 detections imported, empty-window zero, DAY_RANGE limit 5, re-run skipped | eecf2f2, merge b03031c |
| 2d. Live-test fixes — negative `--bbox` values, ignore `data/downloads/`, live findings documented | **Done — verified 2026-11-14 on Windows** | pytest 94 passed, ruff clean | 0f6ebaa, merge 0a7df83, tag `v0.2-data-ingestion` |
| 3a. Harmonization stages A–C — EPSG:6933 1 km grid, cell-day aggregates per platform, incremental aggregate store, coverage-aware area series, `python -m app.cli.area_summary` | **Done — verified 2026-11-14 on Windows** | pytest 116 passed, ruff clean. Real data: NOAA-20 Nov 2026 = 462 detections, 386 cell-days, 363 unique cells, partial coverage 3/14 days; other platforms missing | 36ffc9b, merge bcf740d |
| 3b. Harmonization stages D–G — baselines, modified z, experimental HAI, MODIS–VIIRS calibration and matching, validation report | **Done — verified 2026-11-14 on Windows** | pytest 135 passed, ruff clean. Real-data report: all platforms 'not assessed (incomplete_coverage)' — correct for 3 days of data | 235b283, merge adb7936, tag `v0.3-harmonization` |
| 4. Historical intelligence — calendar with cell states and anomalies, yearly totals and YoY, distributions, exports with provenance | **Done — verified 2026-11-14 on Windows** | pytest 153 passed, ruff clean. Real data: 462-row export; NOAA-20 2026 calendar Jan–Oct missing, Nov partial:462. One Pandas4Warning (fixed in 5a) | 0aa0a3f, merge 5b452c9, tag `v0.4-analytics` |
| 5a. REST API — all spec §11 endpoints, saved AOIs (Shapely-validated GeoJSON), strict JSON, upload/FIRMS ingestion, exports | **Done — verified 2026-11-14 on Windows** | pytest 175 passed (first run 174/175: upload provenance name, fixed in 7964055), ruff clean | 6a14ae2, 7964055, merge f0309fd |
| 5b. Dashboard — Overview, Map, Calendar, Analytics, Explorer, Ingestion, Export; validated colour encodings | **Done — verified 2026-11-14 on Windows** | tsc clean; Vitest 23 passed (first run 22/23: native form validation, fixed); build OK, main chunk 259.73 kB with Map and Analytics lazy; pytest 175. Viewed with real data (user report) | 43367d9, 777faa8, merge b0ac976, tag `v0.5-dashboard` |
| 6a. Validation — UTC-labelled timestamps (API + dashboard), crash-safe partition compaction with recovery and store verification (`app.cli.compact`), synthetic benchmark (`app.cli.benchmark`) (branch `phase6-validation`) | **Done — verified 2026-11-14 on Windows** | First Windows run (fdafbac): real store verified (462 rows, 0 duplicates, 0 misplaced); 2M-row benchmark stalled in import (one file per partition per chunk) — fixed with buffered, single-Arrow-table writes. Second run (9808fcf): Vitest 25 passed, build OK (main chunk 259.95 kB); 200k-row uniform benchmark still slow (~11,000 partitions of ~18 rows: per-file overhead) — zero-copy slice writes, import progress output, clustered default spread with `--spread uniform` kept as the worst case. Third run (a72caa9): pytest 187 passed, ruff clean; benchmarks 200k rows (import 17 s, 775 MB) and 2M rows (import 359 s, compact 406 s, verify 55 s, aggregates 154 s, area query 51 s, 1.64 GB peak), both 0 duplicates / 0 misplaced — see docs/validation/performance.md. Final run (3b8af43): pytest 187 passed in 65 s | fdafbac, 9808fcf, a72caa9, 3b8af43, merge f761251, tag `v0.6-validation` |
| 6b. Delivery — httpx2 test-client pin, clean-clone install test, MODIS confidence thresholds checked against the user's guide, data provenance, methodology, final report, uncovered platforms shown as unknown (not 0) on the Overview, version 1.0.0, MIT license, screenshots (branch `phase6-delivery`) | **Done — verified 2026-11-14 on Windows** | Clean clone of de125b8 from GitHub: pip install from requirements.txt, pytest 187 passed with 0 warnings, ruff clean, npm ci 0 vulnerabilities, Vitest 25 passed, build OK, backend health ok without a MAP_KEY. Final screenshots found the Overview showing 0 for uncovered platforms (fixed in 697b2de, confirmed in the dashboard). Merge rule for v1.0.0: pytest 188 passed, ruff clean, Vitest 28 passed and build OK on Windows before merging | de125b8, c1598a8, 36a1e38, 697b2de and the release commit, tag `v1.0.0` |
| 7a. Harmonized calendar — platform data periods (no false zeros before a launch or after a platform's end), SP/NRT coverage split for archive files, "Inside country" for country downloads, bounded matching memory, MODIS (Terra+Aqua) combined source, per-source conversion factors with held-out validation, one calendar in MODIS- or VIIRS-equivalent units, latest month vs history, CSV export (branch `phase7-harmonized`) | **Done — verified 2026-11-15 on Windows** | Real FIRMS archives for India 2000-11 to 2026-11 imported (Terra 596,463; Aqua 1,327,528; Suomi-NPP 8,758,389 — matching NASA's files). Real data exposed and fixed: archive VIIRS `SNPP` codes, MODIS `6.03` label, SP/NRT coverage, partial months treated as complete, Overview crash with SP data, slow pages (generation cache), out of memory (streamed area statistics, peak 604 MB), anomaly target month, chart image export, empty legend entries, and a Terra factor with 196% error over Punjab (now `rejected`). Windows runs: 7l pytest 223 passed, Vitest 36 passed, build OK; dashboard checked on India and on a 100 km Punjab circle; Terra "rejected" confirmed in the dashboard (dea14a1). Merge rule for v1.1.0: pytest 224 passed, Vitest 46 passed and build OK on Windows | e0c636e … 60fc2d6, dea14a1 and the release commit, tag `v1.1.0` |

### Phase 1 verification results (Windows 11 PC, 2026-11-14)

Environment: Python 3.12.7 (venv), Node v24.22.1, npm 11.19.1, Git 2.56.0.windows.2.

| Check | Result |
|---|---|
| `pytest` (backend) | 4 passed, 1 warning |
| `ruff check` | All checks passed |
| `vitest run` (Vitest 5.1.0) | 2 passed |
| `tsc --noEmit` + `vite build` (Vite 8.3.8) | Succeeded (17 modules, JS 221.74 kB / 69.43 kB gzip) |
| Backend startup + `GET /api/health` | `status: ok` (reported by user) |
| Frontend dev server shows backend status | Reported OK by user |

Resolved (Phase 6b): the Starlette pytest warning about `httpx` was removed by pinning
`httpx2` 2.16.0 for the test client, after testing it on Windows (187 passed, 0 warnings).

Pinned versions: `backend/requirements.txt` (pip freeze of the verified environment) and
`frontend/package-lock.json`.
