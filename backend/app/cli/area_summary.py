"""Monthly per-platform activity for an area, coverage-aware.

Run from the backend folder:

    python -m app.cli.area_summary --bbox 76.7,12.6,84.8,19.9 --start 2026-11-01 --end 2026-11-30
    python -m app.cli.area_summary --rebuild-only        # just refresh aggregates

Refreshes stale cell-day aggregates first (only months whose observations changed).
Output values are satellite detections and active 1 km cells — not fire counts.
'missing' months have no covering import: their counts are blank, not zero.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.analytics.area_stream import stream_area
from app.analytics.series import AreaBBox
from app.cli.args import attach_negative_values
from app.core.config import Settings, get_settings
from app.database.models import CoverageRecord
from app.database.session import init_db, make_engine, make_session_factory
from app.harmonization.aggregate_store import AggregateStore
from app.ingestion.firms_schema import Platform


def load_coverage(settings: Settings) -> list[dict]:
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        rows = session.scalars(select(CoverageRecord)).all()
        return [
            {
                "platform": r.platform,
                "processing_status": r.processing_status,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "extent_type": r.extent_type,
                "extent_value": r.extent_value,
                "basis": r.basis,
            }
            for r in rows
        ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coverage-aware monthly activity for an area.")
    parser.add_argument("--bbox", help="west,south,east,north")
    parser.add_argument("--country", help="name of a country AOI (matches archive coverage)")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument(
        "--platform", action="append", choices=[p.value for p in Platform], default=None
    )
    parser.add_argument("--rebuild-only", action="store_true")
    parser.add_argument("--csv", type=Path, help="also write the table to this CSV file")
    return parser


def run(argv: list[str] | None = None, *, settings: Settings | None = None, out=print) -> int:
    raw = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(attach_negative_values(raw))
    settings = settings or get_settings()
    store = AggregateStore(Path(settings.processed_data_dir), settings.grid_resolution_m)

    built = store.build_stale()
    for key, n in built.items():
        out(f"rebuilt {key.sensor} {key.year}-{key.month:02d}: {n} cell-days")
    if args.rebuild_only:
        return 0
    if not (args.bbox and args.start and args.end):
        out("ERROR: --bbox, --start and --end are required")
        return 2

    west, south, east, north = (float(v) for v in args.bbox.split(","))
    aoi = AreaBBox(west, south, east, north, country=args.country)
    platforms = args.platform or [p.value for p in Platform]
    # One aggregate month at a time: memory stays bounded for decades of data.
    table = stream_area(store, aoi, args.start, args.end, load_coverage(settings), platforms).series
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        out(table.to_string(index=False))
    if args.csv:
        table.to_csv(args.csv, index=False)
        out(f"written {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
