"""Read individual detections for an area and period, one stored file at a time."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pandas as pd

from app.analytics.series import AreaBBox


def observation_files(processed: Path, start: date, end: date, sensors: list[str] | None = None):
    root = Path(processed) / "observations"
    if not root.is_dir():
        return []
    files = []
    for path in sorted(root.rglob("*.parquet")):
        sensor, year, month = path.relative_to(root).parts[:3]
        if sensors and sensor not in sensors:
            continue
        ym = (int(year), int(month))
        if (start.year, start.month) <= ym <= (end.year, end.month):
            files.append(path)
    return files


def iter_observations(
    processed: Path,
    aoi: AreaBBox,
    start: date,
    end: date,
    sensors: list[str] | None = None,
    columns: list[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield detections inside the area and date range, file by file (bounded memory)."""
    needed = None
    if columns is not None:
        needed = list(dict.fromkeys([*columns, "latitude", "longitude", "acquisition_date"]))
    for path in observation_files(processed, start, end, sensors):
        frame = pd.read_parquet(path, columns=needed)
        dates = pd.to_datetime(frame["acquisition_date"]).dt.date
        mask = (dates >= start) & (dates <= end)
        mask &= aoi.contains_points(frame["latitude"], frame["longitude"])
        selected = frame[mask.to_numpy()]
        if len(selected):
            yield selected[columns] if columns is not None else selected
