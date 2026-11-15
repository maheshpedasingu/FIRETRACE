"""Cell-day aggregate store, rebuilt incrementally from the observation store.

Layout: ``<processed>/aggregates/cell_days_<res>m/<sensor>/<YYYY>/<MM>.parquet`` —
one file per sensor-month. A month is rebuilt when any observation file of that
sensor-month is newer than its aggregate file, or when the aggregate is missing.
Each month is built tile by tile (bounded memory) and combined exactly; the output is
written to a temporary file and moved into place, so a crash never leaves a partial
aggregate.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.harmonization.cell_days import OBSERVATION_COLUMNS, aggregate, combine
from app.storage.files import visible_parquet_files


@dataclass(frozen=True)
class MonthKey:
    sensor: str
    year: int
    month: int


_BUILD_LOCKS: dict[str, threading.RLock] = {}
_BUILD_LOCKS_GUARD = threading.Lock()


def _build_lock(root: Path) -> threading.RLock:
    with _BUILD_LOCKS_GUARD:
        return _BUILD_LOCKS.setdefault(str(Path(root).resolve()), threading.RLock())


class AggregateStore:
    def __init__(self, processed_dir: Path, resolution_m: int = 1000) -> None:
        self.observations = Path(processed_dir) / "observations"
        self.root = Path(processed_dir) / "aggregates" / f"cell_days_{resolution_m}m"
        self.resolution_m = resolution_m
        self._fresh_for: str | None = None

    def month_path(self, key: MonthKey) -> Path:
        return self.root / key.sensor / f"{key.year:04d}" / f"{key.month:02d}.parquet"

    def _observation_months(self) -> dict[MonthKey, list[Path]]:
        months: dict[MonthKey, list[Path]] = {}
        if not self.observations.is_dir():
            return months
        for path in visible_parquet_files(self.observations):
            sensor, year, month = path.relative_to(self.observations).parts[:3]
            months.setdefault(MonthKey(sensor, int(year), int(month)), []).append(path)
        return months

    def stale_months(self) -> list[MonthKey]:
        stale = []
        for key, files in sorted(
            self._observation_months().items(),
            key=lambda kv: (kv[0].sensor, kv[0].year, kv[0].month),
        ):
            target = self.month_path(key)
            newest = max(f.stat().st_mtime for f in files)
            if not target.exists() or target.stat().st_mtime < newest:
                stale.append(key)
        return stale

    def build_month(self, key: MonthKey) -> int:
        """(Re)build one sensor-month. Returns the number of cell-day rows."""
        files = self._observation_months().get(key, [])
        by_tile: dict[str, list[Path]] = {}
        for path in files:
            by_tile.setdefault(path.parent.name, []).append(path)
        parts = []
        for tile_files in by_tile.values():
            frame = pd.concat(
                [pd.read_parquet(f, columns=OBSERVATION_COLUMNS) for f in sorted(tile_files)],
                ignore_index=True,
            )
            parts.append(aggregate(frame, self.resolution_m))
        result = combine(parts, self.resolution_m)
        target = self.month_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".parquet.partial")
        result.to_parquet(tmp, index=False, engine="pyarrow")
        os.replace(tmp, target)
        return len(result)

    def build_stale(self) -> dict[MonthKey, int]:
        # One builder at a time per store (concurrent API requests would otherwise
        # write the same month file simultaneously).
        with _build_lock(self.root):
            return {key: self.build_month(key) for key in self.stale_months()}

    def ensure_fresh(self, generation_token: str) -> None:
        """Build stale months only when the store generation changed since the last
        check by this process: scanning thousands of files on every request is slow."""
        with _build_lock(self.root):
            if self._fresh_for == generation_token:
                return
            for key in self.stale_months():
                self.build_month(key)
            self._fresh_for = generation_token

    def month_paths(self, sensors: list[str] | None = None, start=None, end=None) -> list[Path]:
        """Aggregate files of whole months overlapping start..end (one per sensor-month)."""
        if not self.root.is_dir():
            return []
        paths = []
        for path in sorted(self.root.rglob("*.parquet")):
            sensor, year, month_file = path.relative_to(self.root).parts
            if sensors and sensor not in sensors:
                continue
            year, month = int(year), int(month_file.split(".")[0])
            if start is not None and (year, month) < (start.year, start.month):
                continue
            if end is not None and (year, month) > (end.year, end.month):
                continue
            paths.append(path)
        return paths

    def read(self, sensors: list[str] | None = None, start=None, end=None) -> pd.DataFrame:
        """Read cell-days, limited to whole months overlapping start..end. Loads all of
        them at once: for large areas and long periods use area_stream.stream_area."""
        frames = [pd.read_parquet(p) for p in self.month_paths(sensors, start, end)]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
