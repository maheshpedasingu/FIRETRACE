# Harmonization methodology

Status: stages A–G implemented (Phases 3a and 3b). Stages D–G are **experimental**:
they are tested with SYNTHETIC TEST DATA only and have not been validated on real
multi-year data, because no historical archive has been imported yet. Real-data checks
are listed in `PROJECT_PROGRESS.md`.

## Stage A — original measurements are preserved

Detections are stored unchanged in the observation store (one record per FIRMS row,
original row kept as JSON). Harmonization only ever reads them.

## Stage B — common spatial representation

- Grid: EPSG:6933 (WGS 84 / NSIDC EASE-Grid 2.0 Global), Lambert cylindrical
  equal-area, standard parallel 30°. Formulas: Snyder (1987), USGS PP 1395 — forward
  projection, inverse via authalic-latitude series. Implemented in NumPy
  (`app/geospatial/ease_grid.py`) and cross-checked against PyProj to < 1 mm in tests.
- Checks: x at 180° = 17,367,530.45 m (EASE-Grid 2.0 global extent); total projected
  area = 510,065,621.7 km² (WGS 84 ellipsoid surface).
- Cells: squares of `GRID_RESOLUTION_M` (default 1000 m) in projected x/y, identified
  by integer (column, row). Equal area everywhere; shape distorted away from ±30°
  (narrow east–west near the poles).
- MODIS (~1 km pixels) and VIIRS (375 m pixels) detections are both assigned by their
  pixel-centre coordinates. A grid cell is a counting unit, **not a fire perimeter**,
  and one MODIS pixel can overlap several 1 km cells while its centre falls in one.

## Stage C — temporal normalization and aggregation

- Dates and times are UTC (from FIRMS `acq_date` / `acq_time`).
- Cell-day aggregate: one row per sensor × platform × processing status × UTC day ×
  cell, with detections, day/night/unknown split, FRP sum / max / number of FRP values,
  and confidence-class counts (`app/harmonization/cell_days.py`). Platforms and
  processing statuses are never mixed.
- Stored per sensor-month in `data/processed/aggregates/cell_days_<res>m/`, rebuilt
  only for months whose observations changed, tile by tile (bounded memory) and combined
  exactly; partial builds never replace a good file.

## Area series (per platform)

`app/analytics/series.py`, command `python -m app.cli.area_summary`.

| Measure | Meaning |
|---|---|
| `detections` | satellite active-fire detections — not fires |
| `cell_days` | active (cell, day) pairs: repeated detections of a cell on one day count once |
| `unique_cells` | distinct cells active at least once in the month |
| `days_covered` / `coverage_status` | days on which imports covered the whole area: `complete`, `partial`, `missing` |

- A month without detections is **0 only if covered**; otherwise its values are blank.
  Detections from imports with unknown coverage are counted, but the month stays
  `missing` because absence elsewhere is unknown.
- Coverage counts for an area only if a coverage record contains the whole area: a
  bbox containing it (antimeridian-aware) or, for archive files, the same country.
- NRT vs SP: per platform and day, if SP data covers the area or SP rows exist, NRT rows
  for that day are dropped. Days with only NRT use NRT. (Limit: SP rows that cover only
  part of the area on a day still cause that day's NRT rows to be dropped.)
- Selection uses cell centres, so cells straddling the area boundary are in or out as a
  whole (edge effect ≤ one cell width).
- Platforms are reported side by side and are never added together.

## Stage D — sensor-specific baselines and robust anomalies

`app/analytics/baselines.py`. For each platform, area and calendar month:

- History = the same calendar month in **earlier** years, using only months with
  `complete` coverage. Partial and missing months never enter a baseline.
- Statistics: median, MAD = median(|x − median|), 10th/90th percentiles, and the
  empirical percentile rank of the target value.
- Anomaly: modified z = 0.6745 · (x − median) / MAD (Iglewicz & Hoaglin, 1993);
  |z| ≥ 3.5 is labelled *unusually high/low*, otherwise *within normal range*.
  No other scaling constants are used.
- Not assessed, with the reason stated: target month not completely covered
  (`incomplete_coverage`); fewer than `--min-history-years` (default 5) history years
  (`insufficient_history`); MAD = 0 (`zero_dispersion`, percentile rank still given).
- Metric selectable: detections, unique cells or cell-days. Each platform is compared
  only with its own history, so MODIS and VIIRS sensitivity differences do not bias it.
- Sensor transitions: a platform's baseline only contains years in which that platform
  operated and was covered; a new satellite (e.g. NOAA-21 from 2023) reports
  insufficient history until it has enough years.

## Stage E — cross-sensor comparison (experimental)

`app/harmonization/cross_sensor.py`. For each MODIS platform × VIIRS platform pair:

1. **Monthly calibration**: months where both platforms have complete coverage of the
   area are paired. A single factor VIIRS ≈ k · MODIS is estimated on training years
   (ratio of sums) and evaluated on held-out validation years (default: the last two
   overlapping years) with bias, MAE, RMSE, correlation of log(1 + count) and the
   residuals. Fewer than 12 training or 6 validation months → `unavailable`; no factor
   is reported. The factor is specific to the area and period.
2. **Detection matching**: a MODIS detection is matched if a VIIRS detection lies in the
   same or an adjacent 1 km cell within `--tolerance-minutes` (default 15). Reported:
   detections per sensor, matched count and fraction, and, for ≥ 3 matched pairs with
   FRP, the median ratio of summed VIIRS FRP to MODIS FRP and its Spearman correlation.
   FIRMS contains detections only, so this measures agreement where both detected fire,
   **not** a detection probability. FRP ratios reflect different pixel sizes (≈1 km vs
   375 m) and are diagnostics, not a calibration. Matching groups by UTC day, so pairs
   straddling midnight UTC are not matched.

## Stage F — harmonized activity index (experimental)

HAI = mean over sensors of (mean modified z over that sensor's assessed platforms).
Averaging within a sensor first stops three VIIRS satellites from outvoting MODIS. The
report lists contributing sensors and platforms, the MODIS and VIIRS scores, their
disagreement, and every platform that was not assessed with its reason. HAI is a
dimensionless anomaly score relative to each platform's own history; it is **not** a
calibrated physical fire count and does not add raw MODIS and VIIRS counts.

## Harmonized calendar (experimental, v1.1)

The per-platform calendars stay the original record. The harmonized calendar adds ONE
continuous series in the units of a reference sensor, so the record from 2000 (MODIS)
continues seamlessly into the VIIRS era (`app/harmonization/harmonized.py`,
`GET /api/calendar/harmonized`).

1. **Platform data periods.** Coverage never starts before a platform's first FIRMS
   record (Terra 2000-11-01, Aqua 2002-07-04, Suomi-NPP 2012-01-20, NOAA-20 2018-04-01,
   NOAA-21 2023-03-01; Suomi-NPP ends 2026-11-02; sources in
   `app/analytics/platform_periods.py`). Without this, an
   archive request reaching back before a launch would create false zeros.
2. **Sources.** Every platform, plus *MODIS (Terra+Aqua)*: the sum of Terra and Aqua for
   months where both are completely covered.
3. **Reference unit.** `reference=modis` (default): MODIS (Terra+Aqua) detections, the
   longest record. `reference=viirs`: Suomi-NPP detections, the finer record.
4. **Conversion factors.** For every other source, `reference ≈ factor × source`,
   fitted as a ratio of sums over months where both are completely covered, on training
   years. Every third overlap year (the 2nd, 5th, …) is held out for validation: bias,
   MAE, RMSE, RMSE relative to the mean, and the correlation of log(1 + count). At least
   12 training and 6 validation months are required; otherwise no factor is produced and
   months that would need it are shown as missing with the reason.
5. **Month value.** Sources are tried in a fixed priority order (reference first, then
   the other sensor's platforms); the first one with complete coverage and a factor gives
   the value. If none is complete, a partially covered source gives a `partial` value;
   detections without coverage give an `uncovered` lower bound; otherwise `missing`.
   Each month records its source, raw value, factor and relative uncertainty (the
   factor's relative validation RMSE; 0 for reference months).
6. **History comparison.** The harmonized series gets the same modified z against the
   same calendar month in earlier complete years (min. 5 years), and the dashboard shows
   the latest month against the median of earlier complete years.

Limits: one constant factor per source and area cannot represent every season, fire
type or change in the satellites' orbits (Terra and Aqua drift late in their missions);
VIIRS detects many small fires that MODIS misses, so the factor depends on the local
fire regime and must be fitted per area. Months converted from another sensor are
marked (≈) and carry their uncertainty. It is a statistical bridge, not a physical
correction.

## Stage G — validation report

`python -m app.cli.anomaly_report` writes JSON and Markdown to
`data/processed/reports/`: coverage per platform, target-month assessment, HAI,
calibration results with sample sizes and error metrics, matching diagnostics, the full
monthly series and a list of limitations. The report is labelled EXPERIMENTAL until
the methods are validated on real multi-year data.

## Not yet done

Validation of the harmonized calendar and the baselines on real multi-year archives
(needs imported FIRMS history). GeoJSON polygon
AOIs are supported (Shapely); no country or admin-1 boundary dataset is bundled.
