# Harmonized calendar on real data: India 2000–2026

First validation of FIRETRACE on real multi-year data (2026-11-15, user's Windows PC,
branch `phase7-harmonized`). Data: FIRMS Archive Downloads for India, MODIS C6.1
(Terra, Aqua) 2000-11-01 to 2026-11-07 and VIIRS S-NPP C2 2012-01-20 to 2026-11-02 —
see `docs/DATA_PROVENANCE.md` (datasets 3–4). Area: bbox 68.1, 6.7, 97.4, 35.7 with
"Inside country = India". Period 2000-11-01 to 2026-11-07.

## Totals and coverage (checked against NASA's files)

| Platform | Detections | Months complete / partial / missing | Edges |
|---|---|---|---|
| Terra | 596,463 (594,430 SP + 2,033 NRT) | 312 / 1 / 0 | Nov 2026 partial (period ends 7 Nov) |
| Aqua | 1,327,528 (1,322,914 + 4,614) | 291 / 2 / 20 | missing before 2002-07 (pre-launch, not zero); Jul 2002 partial (from the 4th) |
| Suomi-NPP | 8,758,389 | 177 / 2 / 134 | missing before 2012; Jan 2012 partial (from the 20th); Nov 2026 partial (record ends 2 Nov) |
| NOAA-20 / NOAA-21 | — (not imported) | 0 / 0 / 313 | shown as unknown, never zero |

Dashboard total 10,682,380 = sum of both imports. SP→NRT handover months (MODIS Sep 2026,
VIIRS Aug 2026) are complete with no gap or drop.

## Conversion fits

MODIS (Terra+Aqua) units — factor converts the source into MODIS (Terra+Aqua) detections:

| Source | Factor | Train / validation months | Validation RMSE (% of mean) | Log correlation |
|---|---|---|---|---|
| Aqua | 1.429 | 195 / 96 | 1,440 (21%) | 1.00 |
| Terra | 3.329 | 195 / 96 | 3,355 (49%) | 0.96 |
| Suomi-NPP | 0.142 | 117 / 60 | 1,637 (24%) | 0.99 |

Suomi-NPP units:

| Source | Factor | Train / validation months | Validation RMSE (% of mean) | Log correlation |
|---|---|---|---|---|
| MODIS (Terra+Aqua) | 7.040 | 117 / 60 | 11,527 (23%) | 0.99 |
| Aqua | 10.193 | 117 / 60 | 21,238 (43%) | 0.98 |
| Terra | 22.756 | 117 / 60 | 20,255 (41%) | 0.97 |

## Observations

- VIIRS S-NPP records about 7× the MODIS (Terra+Aqua) detections over India, a ratio
  that is stable across years (yearly ratios about 6.3–7.7) — the property a single
  conversion factor needs. Both sensors agree on the high years (e.g. 2016, 2021).
- Converting Terra alone (2000-11 to 2002-06, before Aqua) carries about 49% error:
  those months are marked ≈ with their uncertainty.
- Seasonality matches the known Indian fire regime: main peak in March–April, second
  peak in November (post-harvest residue burning), minimum in the monsoon.
- Latest complete month (October 2026) is 0.35× (MODIS units) and 0.44× (VIIRS units)
  the median October; recent Octobers (2024, 2025) are also low in both sensors.
- Detection matching (±15 min, last 12 months) finds 0 Terra–S-NPP pairs and 114 of
  60,666 Aqua–S-NPP pairs: Terra overpasses in the morning, and Aqua's afternoon
  overpass no longer coincides closely with Suomi-NPP's. Matching is a diagnostic,
  not used by the calibration.

## Bugs found on this data and fixed (all in phase 7)

Archive VIIRS format (`SNPP` instrument/satellite, `bright_t31` as I5), MODIS `6.03`
collection label, SP coverage covering NRT months, false zeros before a launch or after
a platform's end, months cut short by the period treated as complete, Overview crash
once SP data existed, and out-of-memory on decades of data (now streamed one month at a
time: peak ~0.6 GB, see `performance.md`).

## Limits

One area only. The factors are specific to India's fire regime and to this period; they
must be refitted for any other area (FIRETRACE always fits per area). NOAA-20/21 were
not imported, so they have no factors here.
