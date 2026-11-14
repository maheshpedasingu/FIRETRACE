"""Download FIRMS Area API data for an area and date range, then import it.

Run from the backend folder:

    python -m app.cli.fetch_firms --source VIIRS_NOAA20_NRT --bbox 76,12,85,20 \
        --start 2026-11-01 --end 2026-11-10

    python -m app.cli.fetch_firms --source MODIS_NRT --world --start ... --end ...
    python -m app.cli.fetch_firms --availability          # print the FIRMS table

Each request window is saved unchanged under data/downloads/firms_api/ and imported
with coverage = exactly the requested area and dates (basis 'api_request').
Re-running the same command reuses downloaded files and skips files already imported.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.database.session import init_db, make_engine, make_session_factory
from app.ingestion.coverage import bbox_coverage
from app.ingestion.firms_api import (
    FirmsApiClient,
    FirmsApiError,
    check_availability,
    download_area,
)
from app.ingestion.firms_api_plan import BBox, DateWindow, TransactionBudget, parse_source
from app.ingestion.importer import ImportOptions, import_file, recover_interrupted_runs
from app.storage.observation_store import ObservationStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch NASA FIRMS Area API data.")
    parser.add_argument("--source", action="append", default=[], help="e.g. VIIRS_NOAA20_NRT")
    area = parser.add_mutually_exclusive_group()
    area.add_argument("--bbox", help="west,south,east,north (west > east crosses 180°)")
    area.add_argument("--world", action="store_true", help="whole globe")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--no-import", action="store_true", help="download only")
    parser.add_argument(
        "--skip-availability-check", action="store_true", help="do not query availability"
    )
    parser.add_argument("--availability", action="store_true", help="print availability")
    return parser


def make_client(
    settings: Settings,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] | None = None,
) -> FirmsApiClient:
    key = settings.firms_map_key.get_secret_value() if settings.firms_map_key else ""
    kwargs = {"sleep": sleep} if sleep else {}
    budget = TransactionBudget(
        settings.firms_transactions_per_window,
        settings.firms_transaction_window_seconds,
        **kwargs,
    )
    return FirmsApiClient(
        key,
        base_url=settings.firms_api_base,
        timeout=settings.firms_timeout_seconds,
        max_retries=settings.firms_max_retries,
        budget=budget,
        transport=transport,
        **kwargs,
    )


def run(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] | None = None,
    today: date | None = None,
    out=print,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    today = today or datetime.now(UTC).date()

    try:
        client = make_client(settings, transport, sleep)
    except FirmsApiError as exc:
        out(f"ERROR: {exc}")
        return 2

    with client:
        if args.availability:
            rows = client.data_availability()
            for row in rows:
                out(", ".join(f"{k}={v}" for k, v in row.items()))
            return 0

        if not args.source or not args.start or not args.end:
            out("ERROR: --source, --start and --end are required (or use --availability)")
            return 2
        if not (args.bbox or args.world):
            out("ERROR: give --bbox west,south,east,north or --world")
            return 2
        if args.end > today:
            out(f"ERROR: end date {args.end} is in the future (today UTC is {today})")
            return 2
        bbox = BBox.parse(args.bbox) if args.bbox else None
        sources = [parse_source(s) for s in args.source]
        download_dir = Path(settings.raw_data_dir).parent / "downloads" / "firms_api"

        availability = None if args.skip_availability_check else client.data_availability()

        downloads = []
        for source in sources:
            if availability is not None:
                whole = DateWindow(args.start, (args.end - args.start).days + 1)
                warning = check_availability(availability, source, whole)
                if warning:
                    out(f"WARNING: {warning}")
            got = download_area(
                client,
                source,
                bbox,
                args.start,
                args.end,
                download_dir,
                settings.firms_area_max_day_range,
            )
            for item in got:
                state = "reused" if item.reused else "downloaded"
                out(f"{state:<10} {item.path.name}")
            downloads.extend(got)

    if args.no_import:
        return 0

    engine = make_engine(settings.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(Path(settings.processed_data_dir))
    recover_interrupted_runs(sessions, store)
    failures = 0
    for item in downloads:
        b = item.bbox
        options = ImportOptions(
            declared_platform=item.source.declared_platform,
            declared_status=item.source.status,
            coverage=[
                bbox_coverage(
                    b.west,
                    b.south,
                    b.east,
                    b.north,
                    item.window.start,
                    item.window.end,
                    basis="api_request",
                )
            ],
            coverage_platforms=item.source.platforms,
            chunk_rows=settings.ingest_chunk_rows,
            tile_degrees=settings.partition_tile_degrees,
        )
        try:
            result = import_file(
                item.path,
                session_factory=sessions,
                store=store,
                raw_dir=Path(settings.raw_data_dir),
                options=options,
            )
        except Exception as exc:
            failures += 1
            out(f"FAILED  {item.path.name}: {type(exc).__name__}: {exc}")
            continue
        out(
            f"{result.status.upper():<24} {item.path.name}: valid {result.rows_valid}, "
            f"invalid {result.rows_invalid}, already-stored {result.rows_already_stored}, "
            f"written {result.rows_written}"
        )
    return 1 if failures else 0


def main() -> int:
    try:
        return run()
    except (FirmsApiError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
