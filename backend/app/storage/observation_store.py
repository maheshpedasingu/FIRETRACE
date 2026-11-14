"""Partitioned Parquet store for canonical hotspot observations.

Layout (under ``processed_data_dir``)::

    observations/<sensor>/<YYYY>/<MM>/<tile>/part-<run_id>-<seq>.parquet
    _staging/<run_id>/<sensor>/<YYYY>/<MM>/<tile>/part-<run_id>-<seq>.parquet

An import writes only into its own staging folder. ``commit_run`` then moves the
files into ``observations/`` (same drive, so each move is atomic per file), and is
safe to re-run after an interruption. ``discard_run`` deletes a failed run's staging
folder, so a failed import never leaves partial data in the store.

Plain directory names are used (not ``key=value`` hive names) so the partition
columns also stay inside each file and no reader has to reconcile the two.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd

from app.ingestion.firms_schema import CANONICAL_COLUMNS
from app.storage.partitioning import PartitionKey

TEXT_COLUMNS = (
    "observation_id",
    "source_record_id",
    "sensor",
    "platform",
    "instrument",
    "product",
    "collection",
    "collection_version",
    "processing_status",
    "confidence_raw",
    "confidence_class",
    "acquisition_time_utc",
    "day_night",
    "source_file",
    "source_member",
    "source_checksum",
    "source_attributes",
)
FLOAT_COLUMNS = (
    "latitude",
    "longitude",
    "frp_mw",
    "brightness_temperature",
    "brightness_temperature_secondary",
    "scan",
    "track",
)


def coerce_for_storage(frame: pd.DataFrame) -> pd.DataFrame:
    """Give every canonical column a fixed type so all Parquet files share one schema."""
    out = frame[list(CANONICAL_COLUMNS)].copy()
    for column in TEXT_COLUMNS:
        out[column] = out[column].astype("string")
    for column in FLOAT_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="raise").astype("float64")
    out["hotspot_type"] = out["hotspot_type"].astype("Int64")
    out["source_row_number"] = out["source_row_number"].astype("int64")
    out["acquisition_date"] = pd.to_datetime(out["acquisition_date"]).dt.date
    out["acquisition_datetime_utc"] = pd.to_datetime(out["acquisition_datetime_utc"], utc=True)
    out["ingestion_timestamp"] = pd.to_datetime(out["ingestion_timestamp"], utc=True)
    return out.reset_index(drop=True)


class ObservationStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.final_dir = self.root / "observations"
        self.staging_dir = self.root / "_staging"

    # -- reading ---------------------------------------------------------------------

    def partition_files(self, key: PartitionKey) -> list[Path]:
        directory = self.final_dir / key.relative_path()
        return sorted(directory.glob("*.parquet")) if directory.is_dir() else []

    def existing_ids(self, key: PartitionKey) -> set[str]:
        """observation_ids already committed to one partition."""
        ids: set[str] = set()
        for path in self.partition_files(key):
            column = pd.read_parquet(path, columns=["observation_id"])["observation_id"]
            ids.update(column.astype(str))
        return ids

    def all_files(self) -> list[Path]:
        return sorted(self.final_dir.rglob("*.parquet")) if self.final_dir.is_dir() else []

    # -- writing ---------------------------------------------------------------------

    def stage(self, run_id: str, key: PartitionKey, frame: pd.DataFrame) -> Path:
        directory = self.staging_dir / run_id / key.relative_path()
        directory.mkdir(parents=True, exist_ok=True)
        sequence = len(list(directory.glob("*.parquet")))
        path = directory / f"part-{run_id}-{sequence:05d}.parquet"
        tmp = path.with_suffix(".parquet.partial")
        coerce_for_storage(frame).to_parquet(tmp, index=False, engine="pyarrow")
        os.replace(tmp, path)
        return path

    def staged_runs(self) -> list[str]:
        if not self.staging_dir.is_dir():
            return []
        return sorted(p.name for p in self.staging_dir.iterdir() if p.is_dir())

    def commit_run(self, run_id: str) -> int:
        """Move a run's staged files into the store. Idempotent; returns files moved."""
        run_dir = self.staging_dir / run_id
        if not run_dir.is_dir():
            return 0
        moved = 0
        for staged in sorted(run_dir.rglob("*.parquet")):
            target = self.final_dir / staged.relative_to(run_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            moved += 1
        shutil.rmtree(run_dir)
        return moved

    def discard_run(self, run_id: str) -> None:
        shutil.rmtree(self.staging_dir / run_id, ignore_errors=True)
