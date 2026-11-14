"""Performance benchmark on SYNTHETIC TEST DATA in a separate, throw-away workspace.

Run from the backend folder:

    python -m app.cli.benchmark --rows 2000000 --workdir ..\\benchmark_work

Generates random detections (clearly synthetic: global random positions, fixed
brightness values), then times: import (chunked), compaction, verification, aggregate
build, and area queries. Reports elapsed time and peak process memory. The workspace is
never your real data store; delete it yourself afterwards.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.analytics.series import AreaBBox
from app.core.config import Settings
from app.database.session import init_db, make_engine, make_session_factory
from app.harmonization.aggregate_store import AggregateStore
from app.ingestion.coverage import bbox_coverage
from app.ingestion.importer import ImportOptions, import_file
from app.services import area_analysis as aa
from app.storage.compaction import compact_partition, partition_dirs, verify_store
from app.storage.observation_store import ObservationStore

START = date(2024, 1, 1)
DAYS = 730


def peak_memory_mb() -> float:
    """Peak resident memory of this process (Windows: PeakWorkingSetSize)."""
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p  # 64-bit handle, not int
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(Counters),
            ctypes.c_ulong,
        ]
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return float("nan")
        return counters.PeakWorkingSetSize / 1024**2
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def write_synthetic_csv(path: Path, rows: int, seed: int, viirs: bool) -> None:
    """SYNTHETIC TEST DATA in the FIRMS column layout (not NASA observations)."""
    rng = np.random.default_rng(seed)
    days = rng.integers(0, DAYS, rows)
    frame = pd.DataFrame(
        {
            "latitude": np.round(rng.uniform(-60, 70, rows), 5),
            "longitude": np.round(rng.uniform(-180, 180, rows), 5),
            ("bright_ti4" if viirs else "brightness"): 330.0,
            "scan": 0.4,
            "track": 0.4,
            "acq_date": [str(START + timedelta(days=int(d))) for d in days],
            "acq_time": rng.integers(0, 24, rows) * 100 + rng.integers(0, 60, rows),
            "satellite": rng.choice(["N", "N20"] if viirs else ["T", "A"], rows),
            "instrument": "VIIRS" if viirs else "MODIS",
            "confidence": rng.choice(["l", "n", "h"], rows)
            if viirs
            else rng.integers(0, 101, rows),
            "version": "2" if viirs else "6.1",
            ("bright_ti5" if viirs else "bright_t31"): 290.0,
            "frp": np.round(rng.gamma(1.5, 5.0, rows), 2),
            "daynight": rng.choice(["D", "N"], rows),
        }
    )
    frame["acq_time"] = frame["acq_time"].map(lambda t: f"{t:04d}")
    frame.to_csv(path, index=False)


def run(argv: list[str] | None = None, out=print) -> int:
    parser = argparse.ArgumentParser(description="FIRETRACE benchmark (synthetic data).")
    parser.add_argument("--rows", type=int, default=2_000_000)
    parser.add_argument("--rows-per-file", type=int, default=500_000)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--chunk-rows", type=int, default=200_000)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    work = args.workdir.resolve()
    # Never delete or reuse anything: the work folder must be new or empty.
    if work.exists() and any(work.iterdir()):
        out(f"ERROR {work} is not empty; give a new folder (it is never deleted for you)")
        return 2
    (work / "inbox").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(work / 'bench.sqlite').as_posix()}",
        raw_data_dir=str(work / "raw"),
        processed_data_dir=str(work / "processed"),
        ingest_chunk_rows=args.chunk_rows,
    )
    engine = make_engine(settings.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(work / "processed")
    results: dict[str, object] = {"rows_requested": args.rows, "chunk_rows": args.chunk_rows}

    def timed(name: str, fn):
        t0 = time.perf_counter()
        value = fn()
        results[name] = {
            "seconds": round(time.perf_counter() - t0, 2),
            "peak_memory_mb": round(peak_memory_mb(), 1),
        }
        stats = results[name]
        out(f"{name:<22} {stats['seconds']:>8.2f} s   peak {stats['peak_memory_mb']:.0f} MB")
        return value

    files = []

    def generate():
        n_files = max(1, -(-args.rows // args.rows_per_file))
        for i in range(n_files):
            rows = min(args.rows_per_file, args.rows - i * args.rows_per_file)
            path = work / "inbox" / f"SYNTHETIC_{'viirs' if i % 2 == 0 else 'modis'}_{i:03d}.csv"
            write_synthetic_csv(path, rows, seed=i, viirs=i % 2 == 0)
            files.append(path)

    timed("generate_csv", generate)
    coverage = [bbox_coverage(-180, -90, 180, 90, START, START + timedelta(days=DAYS - 1))]

    def import_all():
        written = 0
        for path in files:
            result = import_file(
                path,
                session_factory=sessions,
                store=store,
                raw_dir=work / "raw",
                options=ImportOptions(coverage=coverage, chunk_rows=args.chunk_rows),
            )
            written += result.rows_written
        return written

    written = timed("import", import_all)
    results["rows_written"] = written
    results["files_before_compaction"] = len(store.all_files())
    timed("compact", lambda: [compact_partition(store, k) for k, _ in partition_dirs(store)])
    results["files_after_compaction"] = len(store.all_files())
    reports = timed("verify", lambda: verify_store(store))
    results["duplicates"] = sum(r.duplicate_ids for r in reports)
    results["misplaced"] = sum(r.misplaced_rows for r in reports)
    aggregates = AggregateStore(work / "processed", settings.grid_resolution_m)
    timed("aggregate_build", aggregates.build_stale)

    aoi = AreaBBox(70, 10, 90, 30)
    cov = [
        {
            "platform": p,
            "processing_status": "SP",
            "start_date": START,
            "end_date": START + timedelta(days=DAYS - 1),
            "extent_type": "bbox",
            "extent_value": json.dumps({"west": -180, "south": -90, "east": 180, "north": 90}),
            "basis": "user_declared",
        }
        for p in ("Terra", "Aqua", "Suomi-NPP", "NOAA-20")
    ]
    platforms = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20"]

    def area_queries():
        ctx = aa.context(aggregates, cov, aoi, START, START + timedelta(days=DAYS - 1), platforms)
        series = aa.series(ctx)
        page = aa.hotspot_page(
            ctx,
            work / "processed",
            page=1,
            page_size=500,
            confidence=None,
            day_night=None,
            include_source=False,
        )
        return len(series), page["total"]

    months, in_area = timed("area_query_20x20deg", area_queries)
    results["area_months"] = months
    results["area_detections"] = in_area
    results["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    (work / "benchmark_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    out(
        f"rows written {written}; files {results['files_before_compaction']} -> "
        f"{results['files_after_compaction']}; duplicates {results['duplicates']}; "
        f"misplaced {results['misplaced']}; area detections {in_area}"
    )
    out(f"results: {work / 'benchmark_results.json'}")
    return 0 if results["duplicates"] == 0 and results["misplaced"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
