"""Partition keys for the observation store: sensor / year / month / lat-lon tile.

A detection's partition depends only on fields that are part of its observation_id
(sensor, date, coordinates), so an identical detection always lands in the same
partition. Duplicate checks therefore only need to look inside one partition.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import NamedTuple

import numpy as np
import pandas as pd


class PartitionKey(NamedTuple):
    sensor: str
    year: int
    month: int
    tile: str

    def relative_path(self) -> PurePosixPath:
        return PurePosixPath(self.sensor, f"{self.year:04d}", f"{self.month:02d}", self.tile)


def tile_ids(lat: pd.Series, lon: pd.Series, tile_degrees: int = 10) -> pd.Series:
    """Tile id 'rRRcCCC' on a regular lat/lon grid of ``tile_degrees`` cells.

    Rows count from the south pole, columns from 180°W. Points exactly on +90° or
    +180° fall into the last row/column, so every valid coordinate has a tile.
    """
    if tile_degrees <= 0 or 180 % tile_degrees:
        raise ValueError("tile_degrees must be a positive divisor of 180")
    n_rows, n_cols = 180 // tile_degrees, 360 // tile_degrees
    rows = np.clip(np.floor((lat.to_numpy(float) + 90) / tile_degrees), 0, n_rows - 1)
    cols = np.clip(np.floor((lon.to_numpy(float) + 180) / tile_degrees), 0, n_cols - 1)
    labels = [f"r{int(r):02d}c{int(c):03d}" for r, c in zip(rows, cols, strict=True)]
    return pd.Series(labels, index=lat.index, dtype="object")


def partition_columns(frame: pd.DataFrame, tile_degrees: int = 10) -> pd.DataFrame:
    """Sensor, year, month and tile for each canonical record."""
    dates = pd.to_datetime(frame["acquisition_date"])
    return pd.DataFrame(
        {
            "sensor": frame["sensor"].astype(str),
            "year": dates.dt.year.astype("int64"),
            "month": dates.dt.month.astype("int64"),
            "tile": tile_ids(frame["latitude"], frame["longitude"], tile_degrees),
        },
        index=frame.index,
    )


def iter_partitions(frame: pd.DataFrame, tile_degrees: int = 10):
    """Yield (PartitionKey, sub-frame) for every partition present in ``frame``."""
    if frame.empty:
        return
    keys = partition_columns(frame, tile_degrees)
    grouped = frame.groupby([keys["sensor"], keys["year"], keys["month"], keys["tile"]], sort=True)
    for (sensor, year, month, tile), part in grouped:
        yield PartitionKey(str(sensor), int(year), int(month), str(tile)), part
