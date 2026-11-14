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

Sandbox reference only (not the target): the CSV parser alone processed about 63,000
rows/s with < 1 GB peak memory at 200,000-row chunks (pandas without pyarrow).

## Store integrity

`python -m app.cli.compact` recovers interrupted compactions, merges each partition's
small files into one, and verifies the whole store: per partition, duplicated
observation_ids and rows whose sensor/date/position do not match the partition path must
both be 0. `--verify-only` only reports. Compaction is crash-safe: the merged partition
is built in a hidden directory and swapped in; every reader skips hidden directories.
