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
| Date windows | range split into windows of at most `FIRMS_AREA_MAX_DAY_RANGE` days (default 5 — the live maximum, see below) |
| Antimeridian | bbox with west > east is split into two requests |
| Transaction budget | token bucket, `FIRMS_TRANSACTIONS_PER_WINDOW` per `FIRMS_TRANSACTION_WINDOW_SECONDS` (default 5000 / 600 s, as reported by third-party API descriptions); one token per requested day |
| Errors | timeouts, connection errors, HTTP 429 and 5xx retried with backoff 2, 4, 8… s up to `FIRMS_MAX_RETRIES`; other HTTP errors fail at once |
| Response check | must be FIRMS CSV (header with `latitude` and `acq_date`); an empty body is an error, never zero detections |
| Secrets | MAP_KEY only from `backend/.env`; redacted from every error message; never sent to the frontend |
| Availability | requested range checked against the availability table; if its format cannot be read, a warning is printed instead of guessing |
| Resume | each window saved byte-for-byte to `data/downloads/firms_api/`; existing files are reused |
| Import | each window imported with coverage = requested bbox and dates, basis `api_request`, for every platform of the source (so MODIS windows with zero detections still cover Terra and Aqua) |

## Live findings (Windows target, 2026-11-14, user's MAP_KEY)

1. **Availability table** columns are `data_id, min_date, max_date`. Reported ranges:
   MODIS_SP 2000-11-01..2026-08-31, MODIS_NRT 2026-09-01..2026-11-14,
   VIIRS_SNPP_SP 2012-01-20..2026-07-31, VIIRS_SNPP_NRT 2026-08-01..**2026-11-02**,
   VIIRS_NOAA20_SP 2018-04-01..2026-07-31, VIIRS_NOAA20_NRT 2026-08-01..2026-11-14,
   VIIRS_NOAA21_SP 2023-03-01..2026-07-31, VIIRS_NOAA21_NRT 2024-01-17..2026-11-14.
   The table also lists LANDSAT_NRT, GOES_NRT, BA_MODIS and BA_VIIRS, which are outside
   FIRETRACE's MODIS/VIIRS active-fire scope and are rejected. These ranges change daily;
   the command queries them live rather than storing them.
2. **Maximum DAY_RANGE is 5.** A 10-day request was refused with HTTP 400
   "Invalid day range. Expects [1..5]." (NASA's API page shows 1..10.)
3. **No detections → header only.** MODIS_NRT, bbox -150,-30,-140,-20 (open South
   Pacific), 2026-11-12: the response contained only the CSV header. It imported as
   completed with 0 rows and coverage for Terra and Aqua, so it is a valid zero.
4. **Real VIIRS file** (VIIRS_NOAA20_NRT, bbox 76.7,12.6,84.8,19.9, 2026-11-11..13):
   documented columns, no `type` column (NRT), `acq_time` without leading zeros (e.g.
   `739`), satellite `N20`, version `2.0NRT`, confidence `l/n/h`. 462 rows, 0 invalid.
   A repeat run reused the download and skipped the import (0 written).
5. **Bug found:** `--bbox -150,...` was read as an option by argparse. Fixed by
   attaching negative number lists to `--bbox` in both CLIs.
