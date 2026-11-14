# Historical intelligence: calendar, yearly analytics, distributions, exports

Modules: `app/analytics/calendar.py`, `yearly.py`, `distributions.py`, `observations.py`,
`app/exports/writers.py`; command `python -m app.cli.export`.
Status: tested with SYNTHETIC TEST DATA; checked on the small real dataset listed in
`PROJECT_PROGRESS.md`. Baselines and anomalies remain experimental (see harmonization.md).

## Burning activity calendar

Rows are years, columns January–December, one calendar per platform (MODIS and VIIRS
are never merged into one count). Each cell has a state:

| State | Meaning |
|---|---|
| `value` | complete coverage, ≥ 1 detection |
| `zero` | complete coverage, no detections — a real zero |
| `partial` | only some days covered; the value covers those days only |
| `uncovered` | detections exist but no import covered the whole area; value is a lower bound |
| `missing` | no coverage, no detections — unknown, not zero |
| `outside range` | month outside the requested period (grid view only) |

Where the baseline allows, each cell carries the modified z and label from
harmonization stage D; otherwise the reason it was not assessed. Metric: detections,
unique cells or cell-days.

## Yearly analytics

Per platform and year: completely covered months, total (sum of month values; for
incomplete years this is a partial total), and `complete_year` (12 complete months).
Year-over-year change (absolute and %) is computed only between two complete years of
the same platform; otherwise it is blank with the reason.

## Distributions

From individual detections in the area, after NRT/SP supersession: FRP count, missing
FRP, sum, mean, median, 90th/99th percentile and maximum; confidence classes (low /
nominal / high / missing); day / night / unknown. FRP is per detected pixel in MW, not
burned area, and is not comparable between MODIS and VIIRS without accounting for pixel
size.

## NRT / SP supersession

One shared rule (`series.sp_days_by_platform` + `drop_superseded`) is used for series,
calendars, distributions and exports: on a platform-day where SP data covers the area or
SP records exist, NRT records are excluded. Exports can keep them with `--no-supersede`.

## Exports

| Command | Output |
|---|---|
| `export hotspots` | CSV of canonical detections (source row JSON optional), filtered by area, dates, platform, confidence, day/night; streamed file by file |
| `export calendar` | long-format calendar CSV; `--grid` adds one years × months CSV per platform |
| `export analytics` | JSON with yearly table, distributions, calendar and monthly series |

Every export has `<file>.provenance.json`: area, period, filters, platforms, rows per
platform, NRT rows superseded, source files with SHA-256, and caveats. CSVs stay plain
tables; files are written to a temporary name and moved into place when complete.
