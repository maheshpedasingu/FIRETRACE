# Performance and store integrity

## How to measure

```powershell
cd backend
python -m app.cli.benchmark --rows 2000000 --workdir ..\benchmark_work
```

The benchmark uses **SYNTHETIC TEST DATA** (random global positions over 2024–2025, half
VIIRS, half MODIS files) in its own new folder; it refuses a non-empty folder and never
deletes anything. Steps timed: CSV generation, chunked import, compaction, store
verification, aggregate build, and an area query (20° × 20°, 2 years, 4 platforms).
Memory is the process peak working set (Windows `GetProcessMemoryInfo`).

Results are written to `benchmark_results.json` in the work folder and recorded below.

## Results

| Date | Machine | Rows | Import | Compact | Verify | Aggregates | Area query | Peak memory |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | not yet measured |

First attempt (2026-11-14, Windows, 2,000,000 rows): CSV generation 12.42 s, peak 267 MB;
the import was stopped by hand after several minutes. Cause: one Parquet file per
partition **per 200,000-row chunk**; uniformly random global points touch ~15,500
partitions (10° tile × month over 2 years), i.e. ~15,000 tiny files per chunk. Fixed by
buffering rows per partition, converting types once per flush, writing partitions from a
single Arrow table, and reading existing ids with pyarrow. Note that uniformly random
global points are a worst case: real detections cluster in far fewer partitions.

Sandbox reference only (not the target): the CSV parser alone processed about 63,000
rows/s with < 1 GB peak memory at 200,000-row chunks (pandas without pyarrow).

## Store integrity

`python -m app.cli.compact` recovers interrupted compactions, merges each partition's
small files into one, and verifies the whole store: per partition, duplicated
observation_ids and rows whose sensor/date/position do not match the partition path must
both be 0. `--verify-only` only reports. Compaction is crash-safe: the merged partition
is built in a hidden directory and swapped in; every reader skips hidden directories.
