# FIRMS Area API client

Modules: `app/ingestion/firms_api_plan.py` (pure planning), `app/ingestion/firms_api.py`
(HTTP), `app/cli/fetch_firms.py` (command).

## Requests

`/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north | world}/{DAY_RANGE}/{DATE}`
returns `DATE .. DATE + DAY_RANGE - 1`. Always called with an explicit date, so
results are reproducible. Availability: `/api/data_availability/csv/{MAP_KEY}/ALL`.

| Concern | Behaviour |
|---|---|
| Sources | `MODIS_NRT/SP` (Terra + Aqua), `VIIRS_SNPP_NRT/SP`, `VIIRS_NOAA20_NRT/SP`, `VIIRS_NOAA21_NRT/SP`; anything else rejected |
| Date windows | range split into windows of at most `FIRMS_AREA_MAX_DAY_RANGE` days (default 5; NASA's page says 1–10, other sources 1–5 — to be verified live) |
| Antimeridian | bbox with west > east is split into two requests |
| Transaction budget | token bucket, `FIRMS_TRANSACTIONS_PER_WINDOW` per `FIRMS_TRANSACTION_WINDOW_SECONDS` (default 5000 / 600 s, as reported by third-party API descriptions); one token per requested day |
| Errors | timeouts, connection errors, HTTP 429 and 5xx retried with backoff 2, 4, 8… s up to `FIRMS_MAX_RETRIES`; other HTTP errors fail at once |
| Response check | must be FIRMS CSV (header with `latitude` and `acq_date`); an empty body is an error, never zero detections |
| Secrets | MAP_KEY only from `backend/.env`; redacted from every error message; never sent to the frontend |
| Availability | requested range checked against the availability table; if its format cannot be read, a warning is printed instead of guessing |
| Resume | each window saved byte-for-byte to `data/downloads/firms_api/`; existing files are reused |
| Import | each window imported with coverage = requested bbox and dates, basis `api_request`, for every platform of the source (so MODIS windows with zero detections still cover Terra and Aqua) |

## Open items to verify live

1. Maximum accepted DAY_RANGE.
2. Column names of the availability table.
3. What FIRMS returns for a window with no detections (header only is expected).
