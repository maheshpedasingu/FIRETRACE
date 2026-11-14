# Storage and import pipeline

Modules: `app/storage/` (partitioning, Parquet store), `app/database/` (SQLite
metadata), `app/ingestion/importer.py`, `app/ingestion/coverage.py`,
`app/cli/import_archive.py`.

## Layout

```
data/raw/<sha256[:16]>_<original name>          original files, unchanged
data/processed/observations/<sensor>/<YYYY>/<MM>/<tile>/part-<run>-<seq>.parquet
data/processed/_staging/<run>/...               in-progress imports only
data/firetrace.sqlite                           metadata
```

Tiles are 10°×10° (`PARTITION_TILE_DEGREES`), named `rRRcCCC` with rows from the south
pole and columns from 180°W. A detection's partition depends only on fields inside its
`observation_id` (sensor, date, coordinates), so duplicates always meet in the same
partition.

## Metadata tables

| Table | Contents |
|---|---|
| `source_files` | SHA-256 (unique), original name, raw-store path, size, first seen |
| `ingestion_runs` | one row per import attempt: status, declared platform/status, row counts (read, valid, invalid, duplicate in file, already stored, written), files written, error |
| `invalid_records` | every rejected row: run, ZIP member, row number, all reasons, original row as JSON |
| `coverage` | what each import covers: platform, processing status, dates, extent (bbox / country / unknown), basis, note |

Run statuses: `running` → `committing` → `completed`, or `failed`, or
`skipped_duplicate_file`.

## Guarantees

| Rule | How |
|---|---|
| Same file imported twice does not change counts | SHA-256 lookup; a completed earlier run means a `skipped_duplicate_file` run and no data change |
| Same detection from two files stored once | `observation_id` anti-join against the partition's stored ids; counted as `already_stored` |
| Duplicates inside one file counted, not stored | per-file id set; counted as `duplicate_in_file` |
| No partial data after a failure | rows are staged per run and moved into the store only after the whole file parsed; failures delete the staging folder |
| Crash recovery | `committing` runs are finished, `running` runs rolled back, at the start of every CLI import |
| Rejected rows never silently lost | saved to `invalid_records` after each chunk |
| Missing ≠ zero | coverage comes only from the request (declared bbox/country + dates, API request, or archive file name). Otherwise it is recorded as `unknown` and zero activity must not be inferred. Detection spread inside a file is never used as coverage. |

Coverage rows are written for each platform/processing status present in the file,
plus a declared platform. A platform with no rows and no declaration is not claimed.

## NRT and standard-processing records

NRT and SP versions of a detection have different `observation_id`s (the version is
part of the identity) and may differ slightly in position, so they cannot be matched
one-to-one. Both are stored. Analytics must not add them together: where SP coverage
exists for a platform, area and date, NRT records there are excluded at query time.
That query-time rule is implemented with the analytics (Phase 4) and is not yet
present.

## Known limitations

- New rows are buffered per partition and written in flushes (`flush_rows`, default
  500,000): each flush converts types once, builds one Arrow table and writes one file per
  partition by row selection. Data spread over many partitions still yields one file per
  partition per flush; `python -m app.cli.compact` merges them (crash-safe, verified).
- Single-process use only: two imports must not run at the same time.
- Runs recovered from `committing` have no coverage rows; re-declare coverage if needed.

## Command line

From `backend/` with the virtual environment active:

```powershell
python -m app.cli.import_archive <files-or-folders> [--platform NOAA-20] [--status SP]
    [--bbox W,S,E,N | --country NAME] [--start YYYY-MM-DD --end YYYY-MM-DD]
```
