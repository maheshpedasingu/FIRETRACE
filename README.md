# FIRETRACE

**Fire Intelligence and Historical Activity Monitoring System** — an Earth-observation
platform that integrates NASA FIRMS MODIS (Terra, Aqua; C6.1) and VIIRS 375 m
(Suomi-NPP, NOAA-20, NOAA-21; C2) active-fire detections into a sensor-aware,
harmonized historical burning-activity calendar.

> Status: foundation stage. See `PROJECT_PROGRESS.md` for verified checkpoints.
> Nothing in this repository is claimed to work until it is listed as verified there.

## Scientific ground rules

- Active-fire detections are not fire incidents; FRP is not burned area.
- Missing observations are never treated as zero activity.
- Raw MODIS and VIIRS counts are never added together without sensor-aware normalization.
- No synthetic data is ever presented as NASA observations. Unit-test fixtures are
  labelled `SYNTHETIC TEST DATA`.

## Layout

```
backend/   FastAPI service, ingestion, harmonization, analytics (Python)
frontend/  React + TypeScript + Vite dashboard
data/      raw/ (untouched source files), processed/, samples/
docs/      architecture, science methodology, API, validation reports
scripts/   helper scripts
```

## Configuration

Copy `.env.example` to `backend/.env` and set `FIRMS_MAP_KEY`. Credentials stay on the
backend and are never exposed to the frontend. Without a key, historical data can be
loaded by uploading FIRMS archive CSV files.

Installation and startup instructions will be added once they have been verified.
