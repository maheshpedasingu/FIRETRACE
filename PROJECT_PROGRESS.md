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

This is the entire imported dataset. FIRETRACE has **no global or historical coverage
yet**; standard-processing (SP) archives have not been imported. Automated tests still use
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
| 5a. REST API — all spec §11 endpoints, saved AOIs (Shapely-validated GeoJSON), strict JSON (no NaN), upload/FIRMS ingestion, CSV/zip/report exports (branch `phase5-api`) | Awaiting verification on Windows PC | Sandbox: 4 new tests pass; 18 API/geometry tests need FastAPI, Shapely, pyarrow and run only on Windows | see git log |

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

Open item: pytest warning — Starlette reports that using `httpx` with its test client is
deprecated and suggests `httpx2`. To be investigated before changing test dependencies.

Pinned versions: `backend/requirements.txt` (pip freeze of the verified environment) and
`frontend/package-lock.json`.
