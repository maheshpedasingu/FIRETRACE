"""Partition compaction and store verification.

Each import chunk writes one small Parquet file per partition it touches, so a large
archive produces many small files. Compaction rewrites each partition as one file:

1. read the partition, check that no observation_id is duplicated (if one is, stop with
   an error — data is never dropped silently);
2. write the merged file into a hidden sibling directory ``.<tile>.compacting``;
3. swap directories: ``<tile>`` → ``.<tile>.old``, ``.<tile>.compacting`` → ``<tile>``;
4. delete ``.<tile>.old``.

Readers ignore hidden (dot) directories, so at no point are rows visible twice.
``recover_compaction`` finishes or rolls back a swap interrupted by a crash.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.storage.observation_store import ObservationStore
from app.storage.partitioning import PartitionKey


class CompactionError(RuntimeError):
    pass


@dataclass
class PartitionReport:
    partition: str
    files: int
    rows: int
    duplicate_ids: int
    misplaced_rows: int


def partition_dirs(store: ObservationStore) -> list[tuple[PartitionKey, Path]]:
    result = []
    root = store.final_dir
    if not root.is_dir():
        return result
    for sensor_dir in sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    ):
        for year_dir in sorted(p for p in sensor_dir.iterdir() if p.is_dir() and p.name.isdigit()):
            for month_dir in sorted(
                p for p in year_dir.iterdir() if p.is_dir() and p.name.isdigit()
            ):
                for tile_dir in sorted(
                    p for p in month_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
                ):
                    key = PartitionKey(sensor_dir.name, int(year_dir.name), int(month_dir.name),
                                       tile_dir.name)  # fmt: skip
                    result.append((key, tile_dir))
    return result


def compact_partition(store: ObservationStore, key: PartitionKey) -> tuple[int, int]:
    """Merge one partition into a single file. Returns (files_before, rows)."""
    directory = store.final_dir / key.relative_path()
    files = sorted(directory.glob("*.parquet"))
    if len(files) <= 1:
        return len(files), -1
    frame = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    duplicates = int(frame["observation_id"].duplicated().sum())
    if duplicates:
        raise CompactionError(
            f"{key.relative_path()}: {duplicates} duplicated observation_id(s); "
            "partition left unchanged — investigate before compacting"
        )
    staging = directory.parent / f".{directory.name}.compacting"
    old = directory.parent / f".{directory.name}.old"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    target = staging / f"part-compacted-{stamp}.parquet"
    tmp = target.with_suffix(".parquet.partial")
    frame.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, target)
    if len(pd.read_parquet(target, columns=["observation_id"])) != len(frame):
        shutil.rmtree(staging, ignore_errors=True)
        raise CompactionError(f"{key.relative_path()}: row count changed while writing")
    os.replace(directory, old)
    os.replace(staging, directory)
    shutil.rmtree(old)
    return len(files), len(frame)


def recover_compaction(store: ObservationStore) -> list[str]:
    """Finish or roll back interrupted directory swaps. Returns affected partitions."""
    affected = []
    root = store.final_dir
    if not root.is_dir():
        return affected
    for hidden in sorted(root.rglob(".*")):
        if not hidden.is_dir():
            continue
        if hidden.name.endswith(".compacting"):
            partition = hidden.parent / hidden.name[1 : -len(".compacting")]
            old = hidden.parent / f".{partition.name}.old"
            if not partition.exists() and old.exists():
                os.replace(hidden, partition)  # swap was half done: finish it
                shutil.rmtree(old)
            else:
                shutil.rmtree(hidden)  # partition intact: discard the unfinished copy
            affected.append(str(partition.relative_to(root)))
    for hidden in sorted(root.rglob(".*.old")):
        if not hidden.is_dir():
            continue
        partition = hidden.parent / hidden.name[1 : -len(".old")]
        if partition.exists():
            shutil.rmtree(hidden)  # swap completed, only cleanup was missing
        else:
            os.replace(hidden, partition)  # nothing replaced it: restore
        affected.append(str(partition.relative_to(root)))
    return sorted(set(affected))


def verify_store(store: ObservationStore, tile_degrees: int = 10) -> list[PartitionReport]:
    """Per partition: files, rows, duplicated ids, rows whose fields do not match the path."""
    from app.storage.partitioning import partition_columns

    reports = []
    for key, directory in partition_dirs(store):
        files = sorted(directory.glob("*.parquet"))
        if not files:
            continue
        frame = pd.concat(
            [pd.read_parquet(f, columns=["observation_id", "sensor", "acquisition_date",
                                         "latitude", "longitude"]) for f in files],
            ignore_index=True,
        )  # fmt: skip
        keys = partition_columns(frame, tile_degrees)
        misplaced = int(
            (
                (keys["sensor"] != key.sensor)
                | (keys["year"] != key.year)
                | (keys["month"] != key.month)
                | (keys["tile"] != key.tile)
            ).sum()
        )
        reports.append(
            PartitionReport(
                key.relative_path().as_posix(),
                len(files),
                len(frame),
                int(frame["observation_id"].duplicated().sum()),
                misplaced,
            )
        )
    return reports
