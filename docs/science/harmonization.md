# Harmonization methodology

Status: stages A–C implemented (Phase 3a). Stages D–G (baselines, anomalies,
cross-sensor calibration, validation) follow in Phase 3b. Everything below has been
tested with SYNTHETIC TEST DATA; real-data checks are listed in `PROJECT_PROGRESS.md`.

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

## Not yet done

Stage D (sensor-specific baselines and robust anomalies), Stage E (MODIS–VIIRS overlap
matching and calibration), Stage F (harmonized index), Stage G (validation report).
Polygon AOIs (Shapely) and country/admin boundaries are added with the AOI system.
