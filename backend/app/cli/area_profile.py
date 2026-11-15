"""Measure time and peak memory of the dashboard's area queries, from the command line.

Runs, one after another, exactly what the dashboard runs for an area and period (area
context, Overview summary, harmonized calendar, yearly table) and prints elapsed time
and the process's peak memory after each step. Read-only; stop it any time with Ctrl+C.
Use it before opening the dashboard on a very large area or period.

    (one line) python -m app.cli.area_profile --bbox 68.1,6.7,97.4,35.7
        --country India --start 2000-11-01 --end 2026-11-07
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from app.analytics.series import AreaBBox
from app.cli.area_summary import load_coverage
from app.cli.args import attach_negative_values
from app.cli.benchmark import peak_memory_mb
from app.core.config import Settings, get_settings
from app.harmonization.aggregate_store import AggregateStore
from app.ingestion.firms_schema import Platform
from app.services import area_analysis as aa


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bbox", required=True, help="west,south,east,north")
    parser.add_argument("--country", help="country the whole area lies inside")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    return parser


def run(argv: list[str] | None = None, *, settings: Settings | None = None, out=print) -> int:
    raw = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(attach_negative_values(raw))
    settings = settings or get_settings()
    processed = Path(settings.processed_data_dir)
    aggregates = AggregateStore(processed, settings.grid_resolution_m)
    west, south, east, north = (float(v) for v in args.bbox.split(","))
    aoi = AreaBBox(west, south, east, north, country=args.country)
    platforms = [p.value for p in Platform]

    def step(label: str, fn):
        started = time.perf_counter()
        value = fn()
        out(f"{label:<26} {time.perf_counter() - started:8.2f} s   peak {peak_memory_mb():7.0f} MB")
        return value

    step("aggregates up to date", aggregates.build_stale)
    coverage = step("coverage", lambda: load_coverage(settings))
    ctx = step(
        "area context (streamed)",
        lambda: aa.context(aggregates, coverage, aoi, args.start, args.end, platforms),
    )
    summary = step("overview summary", lambda: aa.summary(ctx, processed))
    harmonized = step("harmonized calendar",
                      lambda: aa.harmonized_calendar(ctx, "modis", "detections", 5))  # fmt: skip
    step("yearly table", lambda: aa.yearly_table(ctx, "detections"))
    out(
        f"total detections {summary['total_detections']}; months "
        f"{len(harmonized['cells'])}; first {summary['first_detection_date']}, "
        f"last {summary['last_detection_date']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
