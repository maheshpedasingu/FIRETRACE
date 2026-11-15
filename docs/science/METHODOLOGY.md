# Scientific methodology and limitations

A one-page overview. Details, formulas and references are in:

- `ingestion.md` — FIRMS file rules, sensor/platform identification, confidence classes, identity
- `harmonization.md` — grid, aggregation, baselines, anomalies, cross-sensor comparison, HAI
- `analytics.md` — calendar states, yearly analytics, distributions, exports
- `../DATA_PROVENANCE.md` — sources and the real data actually processed

## What the data is

FIRMS active-fire records are **satellite detections of thermal anomalies** at the
centre of a MODIS (~1 km at nadir) or VIIRS (375 m) pixel at one overpass time. A
detection is not a fire incident, its location is not a fire perimeter, and its fire
radiative power (FRP, MW) is not burned area. Absence of detections means only that
nothing was detected on the overpasses that were observed and imported: clouds, smoke,
overpass timing and small or cool fires all cause omissions.

## Processing chain

1. **Ingest (stage A).** Every FIRMS row is validated and kept with its original values
   and source. Sensor and platform come from documented codes only; unknown codes are
   rejected, not guessed. MODIS confidence 0–100 % is classed low < 30 ≤ nominal < 80 ≤
   high (MODIS C6/C6.1 User's Guide, Table 11); VIIRS uses its own low/nominal/high.
   Processing status (NRT vs standard processing) comes from the version suffix.
2. **Coverage.** Each import records the area, dates and platforms it covered, from the
   request alone. Every month of every area is then *complete*, *partial* or *missing*
   per platform. **A zero is only reported where coverage is complete; missing data is
   never zero.**
3. **Common grid (stage B).** Detections are assigned by pixel centre to 1 km cells of
   the equal-area EPSG:6933 grid (EASE-Grid 2.0), so cells have the same area at every
   latitude. Implemented from Snyder (1987) and checked against PyProj (< 1 mm).
4. **Aggregation (stage C).** Cell-day aggregates per sensor, platform, processing
   status and UTC day: detections, unique active cells, active cell-days, FRP and
   confidence counts. Platforms are never summed together. For each platform-day,
   standard-processing records supersede NRT records.
5. **Baselines and anomalies (stage D, experimental).** Each platform is compared only
   with its own history for the same calendar month, using only completely covered
   months: median, MAD, percentiles and the modified z-score
   0.6745·(x − median)/MAD (Iglewicz & Hoaglin 1993), flagged at |z| ≥ 3.5. Fewer than 5
   history years, incomplete coverage or zero dispersion are reported as *not assessed*
   with the reason.
6. **Cross-sensor comparison (stage E, experimental).** Where MODIS and VIIRS platforms
   both completely cover an area, a single area-specific scale factor is fitted on
   training years and tested on held-out years (bias, MAE, RMSE, log correlation);
   detections are matched within the same or an adjacent cell and ±15 minutes. These are
   diagnostics of agreement, not detection probabilities.
7. **Harmonized activity index (stage F, experimental).** The mean, over sensors, of each
   sensor's mean modified z. It is a dimensionless anomaly score relative to each
   platform's own history, **not a calibrated fire count**, and raw MODIS and VIIRS
   counts are never added.
8. **Harmonized calendar (experimental).** One continuous calendar in the units of a
   reference sensor (MODIS Terra+Aqua by default, or Suomi-NPP VIIRS): months measured
   by other platforms are converted with an area-specific factor fitted where both
   overlap and tested on held-out years; each month shows its source and uncertainty.
   Coverage never starts before a platform's first FIRMS record, so no false zeros
   appear before a satellite's launch. Details: `harmonization.md`.
9. **Calendar and analytics.** Years × months per platform with states value, zero,
   partial, uncovered and missing; yearly totals and year-over-year change only for
   complete years; FRP, confidence and day/night distributions.

## Known limitations

**Data actually processed**
- Only two small real datasets have been processed (see `DATA_PROVENANCE.md`): 3 days
  of NOAA-20 VIIRS NRT data over one area and one MODIS NRT day with no detections.
  FIRETRACE has no global or multi-year coverage yet.
- Baselines, anomalies, cross-sensor calibration and the HAI are tested only with
  SYNTHETIC TEST DATA. They stay labelled experimental until validated on real
  multi-year archives.
- Satellite codes inside yearly per-country archive files are not yet checked on a real
  file; unknown codes would be rejected (reported as invalid), not misclassified.

**Method**
- Detection counts depend on sensor, platform, overpass times, cloud cover and satellite
  lifetime. Counts from different platforms, or from periods with different platforms
  in orbit, are not directly comparable; FIRETRACE reports them side by side.
- MODIS pixels grow strongly off-nadir; assigning by pixel centre places a large pixel's
  detection in one 1 km cell.
- Area selection uses cell centres (edge effect up to one cell width). Bounding boxes and
  GeoJSON polygons are supported; no country or admin-1 boundary dataset is bundled, so
  country areas must be supplied as GeoJSON.
- NRT/SP supersession works per platform-day: SP data covering only part of an area on a
  day still removes that day's NRT records for the area.
- Detection matching groups by UTC day, so pairs straddling midnight UTC are not matched.
- MODIS confidence has regionally varying meaning (NASA guidance); classes are kept
  but not used to drop records unless the user filters by them.

**Performance** (measured, `../validation/performance.md`)
- About 5,600 rows/s import on the test PC at 2 million rows, bounded memory (1.6 GB
  peak). On Windows each Parquet file costs roughly 10–20 ms to open, so sparse global
  data split into many small partitions is slow to verify and aggregate. A
  multi-decade global import is expected to take hours (an extrapolation, not measured).
