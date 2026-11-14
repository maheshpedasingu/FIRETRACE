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

Installation and startup instructions will be added once they have been verified.
