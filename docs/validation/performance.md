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

Measured on the user's Windows PC (Python venv, pandas 3.1.1 with pyarrow), commit
a72caa9, SYNTHETIC TEST DATA, `--spread clustered`, 2 years, 10° tiles × month partitions.
Both runs: duplicates 0, misplaced rows 0.

| Date | Rows | Partitions | Files before → after compaction | Import | Compact | Verify | Aggregates | Area query (20°×20°, 2 y) | Peak memory |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-14 | 200,000 (1 VIIRS file) | 3,300 | 3,300 → 3,300 | 17.0 s | 0.3 s | 64.1 s | 54.2 s | 20.4 s (1,468 detections) | 775 MB |
| 2026-11-14 | 2,000,000 (2 VIIRS + 2 MODIS files of 500,000) | 7,463 | 14,183 → 7,463 | 359.3 s | 406.4 s | 54.8 s | 154.3 s | 51.5 s (14,608 detections) | 1,641 MB |

Findings:

- Import throughput at 2M rows was about 5,600 rows/s, including the duplicate check
  against rows already stored (the 2nd file of each sensor reads the ids of ~3,500
  existing partitions). Memory stayed bounded at 1.6 GB peak for 2M rows.
- On this machine each Parquet file costs roughly 10–20 ms to open or create regardless
  of its size, so **file count, not row count, dominates** verify, aggregate and query
  time. Partition layout (10° × month) multiplies files for sparse, global data.
- Compaction is the slowest maintenance step (~0.11 s per partition with two files). It
  is optional and crash-safe; run it after large imports, not after each one.
- Extrapolation, NOT measured: at 5,600 rows/s a 100-million-row multi-decade archive
  would take about 5 hours to import. This must be confirmed with real imported data.

Possible improvements, deferred (not needed for correctness): keep a per-partition id
index instead of re-reading Parquet ids; coarser partitions (yearly) for archive data;
parallel aggregate builds.

First attempt (2026-11-14, Windows, 2,000,000 rows): CSV generation 12.42 s, peak 267 MB;
the import was stopped by hand after several minutes. Cause: one Parquet file per
partition **per 200,000-row chunk**; uniformly random global points touch ~15,500
partitions (10° tile × month over 2 years), i.e. ~15,000 tiny files per chunk. Fixed by
buffering rows per partition, converting types once per flush, writing partitions from a
single Arrow table, and reading existing ids with pyarrow. Note that uniformly random
global points are a worst case: real detections cluster in far fewer partitions.

Second attempt (2026-11-14, Windows, commit 9808fcf, 200,000 rows, uniform spread): CSV
generation 1.05 s, peak 172 MB; the import was stopped by hand after about 6 minutes,
inside `stage_many` writing partition files. 200,000 uniform points over 2 years fall in
about 11,000 partitions (13 × 36 tiles × 24 months), i.e. about 18 rows per file, so the
run measures per-file overhead (directory creation, Parquet write, rename, on-access
scanning) rather than row throughput. Changes: partitions are written as zero-copy slices
of one sorted Arrow table; the import reports progress after each flush; the benchmark's
default spread is now `clustered` (60 fixed synthetic hotspot centres, σ 1.5°), and the
uniform worst case stays available as `--spread uniform`. The results record the spread
and partition count so the two are never compared as if alike.

Sandbox reference only (not the target): the CSV parser alone processed about 63,000
rows/s with < 1 GB peak memory at 200,000-row chunks (pandas without pyarrow).

## Store integrity

`python -m app.cli.compact` recovers interrupted compactions, merges each partition's
small files into one, and verifies the whole store: per partition, duplicated
observation_ids and rows whose sensor/date/position do not match the partition path must
both be 0. `--verify-only` only reports. Compaction is crash-safe: the merged partition
is built in a hidden directory and swapped in; every reader skips hidden directories.

## Dashboard on real data (2026-11-15)

With 10.7 million real detections for India (MODIS 2000–2026, VIIRS S-NPP 2012–2026)
every dashboard page was slow: each API request rescanned ~4,500 observation files for
stale aggregates and re-read every aggregate month, Overview and Analytics read all
individual detections, and a page sends several requests at once. Changes (phase 7i):
store-generation marker gating the aggregate check (with a build lock), one cached area
context shared by concurrent requests, summary statistics from cell-day aggregates (FRP
median / percentiles from the last 12 months of the period, labelled in the UI), and
hotspot totals from aggregates.

Opening the dashboard on that area and period then made the laptop stop responding
(out of memory): each request still loaded every cell-day of the area and period at
once, several GB per copy. Phase 7j computes area statistics one aggregate month at a
time and keeps only small results (`app/analytics/area_stream.py`); memory no longer
grows with the length of the period. Measured with `python -m app.cli.area_profile` on the user's PC (commit aacddcb),
India bbox + country, 2000-11-01 to 2026-11-07, 10,682,380 detections:

| Step | Time | Peak memory |
|---|---|---|
| aggregates up to date | 0.8 s | 115 MB |
| area context (streamed, ~490 aggregate months) | 44.2 s | 604 MB |
| overview summary | 4.2 s | 604 MB |
| harmonized calendar | 0.8 s | 604 MB |
| yearly table | 0.1 s | 604 MB |

The area context is built once per area and period and shared by all dashboard
requests; the dashboard then loaded Overview, Calendar (both unit choices) and
Analytics without memory problems.

