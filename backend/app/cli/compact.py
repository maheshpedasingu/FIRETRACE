"""Compact the observation store and verify its integrity.

Run from the backend folder:

    python -m app.cli.compact               # recover, compact every partition, verify
    python -m app.cli.compact --verify-only # only report

Verification reports, per partition: files, rows, duplicated observation_ids and rows
whose sensor/date/position do not belong in that partition. Both must be 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.storage.compaction import (
    CompactionError,
    compact_partition,
    partition_dirs,
    recover_compaction,
    verify_store,
)
from app.storage.observation_store import ObservationStore


def run(argv: list[str] | None = None, *, settings: Settings | None = None, out=print) -> int:
    parser = argparse.ArgumentParser(description="Compact and verify the observation store.")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    settings = settings or get_settings()
    store = ObservationStore(Path(settings.processed_data_dir))

    for partition in recover_compaction(store):
        out(f"recovered interrupted compaction: {partition}")
    if not args.verify_only:
        compacted = 0
        for key, _ in partition_dirs(store):
            try:
                files, _rows = compact_partition(store, key)
            except CompactionError as exc:
                out(f"ERROR {exc}")
                return 1
            if files > 1:
                compacted += 1
        out(f"compacted {compacted} partition(s)")

    reports = verify_store(store, settings.partition_tile_degrees)
    files = sum(r.files for r in reports)
    rows = sum(r.rows for r in reports)
    duplicates = sum(r.duplicate_ids for r in reports)
    misplaced = sum(r.misplaced_rows for r in reports)
    out(f"partitions {len(reports)}, files {files}, rows {rows}, "
        f"duplicate ids {duplicates}, misplaced rows {misplaced}")  # fmt: skip
    for r in reports:
        if r.duplicate_ids or r.misplaced_rows:
            out(
                f"  PROBLEM {r.partition}: duplicates {r.duplicate_ids}, "
                f"misplaced {r.misplaced_rows}"
            )
    return 1 if duplicates or misplaced else 0


if __name__ == "__main__":
    sys.exit(run())
