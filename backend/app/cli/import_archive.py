"""Import FIRMS CSV/ZIP files into FIRETRACE.

Run from the backend folder:

    python -m app.cli.import_archive <file-or-folder> [...] [options]

Folders are scanned (recursively) for .csv and .zip files. Each file is imported
independently; one failing file does not stop the others. Re-importing an identical
file is recorded and skipped.

Coverage (where zero detections may be read as zero activity) comes from, in order:
--bbox/--country with --start/--end, else country/year in FIRMS yearly archive file
names, else it is recorded as unknown.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from app.core.config import get_settings
from app.database.session import init_db, make_engine, make_session_factory
from app.ingestion.coverage import bbox_coverage, country_coverage
from app.ingestion.firms_schema import Platform, ProcessingStatus
from app.ingestion.importer import ImportOptions, import_file, recover_interrupted_runs
from app.storage.observation_store import ObservationStore

SUFFIXES = (".csv", ".zip")


def _files(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.suffix.lower() in SUFFIXES))
        elif path.is_file():
            found.append(path)
        else:
            raise SystemExit(f"Not found: {path}")
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import NASA FIRMS CSV/ZIP files.")
    parser.add_argument("paths", nargs="+", type=Path, help="files or folders")
    parser.add_argument("--platform", choices=[p.value for p in Platform])
    parser.add_argument("--status", choices=[s.value for s in ProcessingStatus])
    parser.add_argument("--bbox", help="coverage bbox west,south,east,north")
    parser.add_argument("--country", help="coverage country name")
    parser.add_argument("--start", type=date.fromisoformat, help="coverage start YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="coverage end YYYY-MM-DD")
    parser.add_argument("--chunk-rows", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    coverage = []
    if args.bbox or args.country:
        if not (args.start and args.end):
            raise SystemExit("--bbox/--country need --start and --end")
        if args.bbox:
            west, south, east, north = (float(v) for v in args.bbox.split(","))
            coverage.append(bbox_coverage(west, south, east, north, args.start, args.end))
        if args.country:
            coverage.append(country_coverage(args.country, args.start, args.end))

    options = ImportOptions(
        declared_platform=Platform(args.platform) if args.platform else None,
        declared_status=ProcessingStatus(args.status) if args.status else None,
        coverage=coverage,
        chunk_rows=args.chunk_rows or settings.ingest_chunk_rows,
        tile_degrees=settings.partition_tile_degrees,
    )

    engine = make_engine(settings.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(Path(settings.processed_data_dir))
    raw_dir = Path(settings.raw_data_dir)

    recovered = recover_interrupted_runs(sessions, store)
    if recovered:
        print(f"Recovered {len(recovered)} interrupted run(s): {', '.join(recovered)}")

    failures = 0
    for path in _files(args.paths):
        try:
            result = import_file(
                path, session_factory=sessions, store=store, raw_dir=raw_dir, options=options
            )
        except Exception as exc:  # report and continue with the next file
            failures += 1
            print(f"FAILED  {path.name}: {type(exc).__name__}: {exc}")
            continue
        print(
            f"{result.status.upper():<24} {path.name}: read {result.rows_read}, "
            f"valid {result.rows_valid}, invalid {result.rows_invalid}, "
            f"duplicate-in-file {result.rows_duplicate_in_file}, "
            f"already-stored {result.rows_already_stored}, written {result.rows_written} "
            f"({result.files_written} files)" + (f" — {result.error}" if result.error else "")
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
