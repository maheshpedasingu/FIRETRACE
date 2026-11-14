# FIRETRACE REST API

FastAPI, served by `python -m uvicorn app.main:app --port 8000` from `backend/`.
Interactive OpenAPI documentation: http://127.0.0.1:8000/docs (schema at `/openapi.json`).

All analytics are per platform (Terra, Aqua, Suomi-NPP, NOAA-20, NOAA-21); MODIS and
VIIRS counts are never summed. Missing values are `null`, never 0. NRT records are
superseded by SP records per platform-day. The FIRMS MAP_KEY stays on the server and is
never returned.

## Common area parameters

`start`, `end` (UTC dates, required), and exactly one of `bbox=west,south,east,north`
(west > east crosses the antimeridian) or `aoi_id` (saved AOI). Optional `country`
(matches archive country coverage) and repeatable `platform`. Invalid input → HTTP 400
with a message; unknown AOI → 404.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness; reports whether a MAP_KEY is configured (never the key) |
| GET | `/api/sensors` | platforms, sensor, product, collection, nominal pixel, FIRMS sources |
| GET | `/api/data/availability` | live FIRMS availability (if key) + imported coverage + latest import |
| POST | `/api/ingest/upload` | multipart FIRMS `.csv`/`.zip` (≤ 2 GiB); optional platform, status, coverage bbox/country + start/end |
| POST | `/api/ingest/firms` | JSON `{sources, bbox or world, start, end}`; ≤ 31 days per call (larger: CLI) |
| GET | `/api/ingest/history` | import runs with counts, paginated |
| GET | `/api/hotspots` | detections, paginated (`page`, `page_size` ≤ 5000); filters `confidence`, `daynight`; `include_source` adds the original row |
| GET | `/api/hotspots/summary` | totals, per-platform detections / unique cells / coverage months, distributions |
| GET | `/api/calendar` | years × months per platform with states value / zero / partial / uncovered / missing |
| GET | `/api/analytics/monthly` | coverage-aware monthly series |
| GET | `/api/analytics/yearly` | yearly totals, year-over-year for complete years |
| GET | `/api/analytics/anomalies` | EXPERIMENTAL modified z per platform (`target=YYYY-MM`) + harmonized index |
| GET | `/api/analytics/sensor-comparison` | EXPERIMENTAL MODIS–VIIRS calibration and detection matching |
| GET / POST | `/api/aoi` | list / save AOIs (`bbox` or GeoJSON Polygon/MultiPolygon, validated with Shapely) |
| GET | `/api/export/csv` | `kind=hotspots|calendar`; `bundle=true` adds the provenance JSON in a zip |
| GET | `/api/export/report` | EXPERIMENTAL report, `format=json|md` |

## Status codes

400 invalid parameters · 404 unknown AOI · 409 duplicate AOI name · 413 upload too large ·
422 file is not FIRMS data · 502 FIRMS request failed · 503 MAP_KEY not configured.
