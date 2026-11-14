# FIRETRACE

**Fire Intelligence and Historical Activity Monitoring System** — a global
Earth-observation platform that integrates NASA FIRMS MODIS (Terra, Aqua; C6.1) and
VIIRS 375 m (Suomi-NPP, NOAA-20, NOAA-21; C2) active-fire detections into a
sensor-aware, harmonized historical burning-activity calendar for any area on Earth.

> Status: foundation stage. See `PROJECT_PROGRESS.md` for verified checkpoints.
> Nothing in this repository is claimed to work until it is listed as verified there.

## Scope

- Any country, first-level region, bounding box or custom polygon worldwide, including
  areas that cross the antimeridian.
- MODIS and VIIRS history from each sensor's earliest available record to the present.
- No built-in geographic restriction. Example regions (such as Andhra Pradesh, India)
  are optional presets only.
- **Coverage is reported, not assumed.** FIRETRACE only reports data coverage for
  sensors, areas and dates that have actually been imported and verified.

See `docs/architecture/ARCHITECTURE.md` and `docs/IMPLEMENTATION_PLAN.md`.

## Scientific ground rules

- Active-fire detections are not fire incidents; FRP is not burned area.
- Missing observations are never treated as zero activity.
- Raw MODIS and VIIRS counts are never added together without sensor-aware normalization.
- No synthetic data is ever presented as NASA observations. Test fixtures are labelled
  `SYNTHETIC TEST DATA`.

## Data sources

- **FIRMS Area API** (recent data and keyed backfill): needs a MAP_KEY.
- **FIRMS historical archive** (global history): yearly per-country CSV summaries and
  Archive Download Tool exports, imported from files.

## Layout

```
backend/   FastAPI service, ingestion, harmonization, analytics (Python)
frontend/  React + TypeScript + Vite dashboard
data/      raw/ (untouched source files), processed/ (partitioned store), samples/
docs/      architecture, science methodology, API, validation reports
scripts/   setup and bulk-import helpers
```

## Configuration

Copy `.env.example` to `backend/.env` and set `FIRMS_MAP_KEY`. Credentials stay on the
backend and are never exposed to the frontend.

## Installation (Windows PowerShell)

Requirements: Git, Python 3.12, Node.js 24 (npm 11). No GPU or Docker needed.

The pinned versions below were verified on Windows on 2026-11-14. A clean-clone install
from these exact commands has not yet been re-run; that check is part of final delivery.

```powershell
git clone https://github.com/maheshpedasingu/FIRETRACE.git
cd FIRETRACE\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd ..\frontend
npm ci
```

If `Activate.ps1` is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Running

Backend (terminal 1):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

Frontend (terminal 2):

```powershell
cd frontend
npm run dev
```

- Dashboard: http://localhost:5173
- Health check: http://127.0.0.1:8000/api/health
- API docs (OpenAPI): http://127.0.0.1:8000/docs

## Importing FIRMS files

From `backend/` with the virtual environment active:

```powershell
python -m app.cli.import_archive E:\path\to\firms_downloads
```

See `docs/architecture/storage.md` for options (platform, coverage bbox/country and dates).

## Fetching recent data from the FIRMS API

Needs `FIRMS_MAP_KEY` in `backend/.env`. From `backend/`:

```powershell
python -m app.cli.fetch_firms --availability
python -m app.cli.fetch_firms --source VIIRS_NOAA20_NRT --bbox 76.7,12.6,84.8,19.9 --start 2026-11-10 --end 2026-11-12
python -m app.cli.fetch_firms --source MODIS_NRT --world --start 2026-11-12 --end 2026-11-12
```

The bbox above is only an example area. See `docs/architecture/firms-api.md`.

## Area summary

From `backend/`: monthly detections and active 1 km cells per satellite for an area,
with coverage status (blank = no data, not zero):

```powershell
python -m app.cli.area_summary --bbox 76.7,12.6,84.8,19.9 --start 2026-11-01 --end 2026-11-14
```

## Anomaly and validation report (experimental)

```powershell
python -m app.cli.anomaly_report --bbox 76.7,12.6,84.8,19.9 --start 2012-01-01 --end 2026-10-31 --target 2026-10
```

Needs several years of imported, fully covered data per platform; otherwise each
platform is reported as not assessed with the reason. Method: `docs/science/harmonization.md`.

## Exports

```powershell
python -m app.cli.export hotspots  --bbox 76.7,12.6,84.8,19.9 --start 2026-11-01 --end 2026-11-14 --out ..\exports\hotspots.csv
python -m app.cli.export calendar  --bbox 76.7,12.6,84.8,19.9 --start 2026-01-01 --end 2026-11-14 --out ..\exports\calendar.csv --grid
python -m app.cli.export analytics --bbox 76.7,12.6,84.8,19.9 --start 2026-01-01 --end 2026-11-14 --out ..\exports\analytics.json
```

Each file gets a `.provenance.json` sidecar. See `docs/science/analytics.md`.

## Maintenance and performance

```powershell
python -m app.cli.compact                 # merge small files, verify the store
python -m app.cli.compact --verify-only   # report only
python -m app.cli.benchmark --rows 2000000 --workdir ..\benchmark_work   # synthetic data, new folder
```

See `docs/validation/performance.md`.

## Tests and checks

```powershell
cd backend;  python -m pytest -q; python -m ruff check .
cd ..\frontend; npm test; npm run build
```
