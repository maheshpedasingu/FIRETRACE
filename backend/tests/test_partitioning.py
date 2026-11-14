"""Partitioning tests. Coordinates and dates are SYNTHETIC TEST DATA."""

from datetime import date

import pandas as pd
import pytest

from app.storage.partitioning import PartitionKey, iter_partitions, tile_ids


def test_tile_ids_cover_globe_edges():
    lat = pd.Series([-90.0, 90.0, 0.0, -0.00001, 45.0])
    lon = pd.Series([-180.0, 180.0, 0.0, -0.00001, 179.99999])
    assert tile_ids(lat, lon).tolist() == [
        "r00c000",  # south pole, 180°W
        "r17c035",  # north pole, +180° folds into the last column
        "r09c018",  # equator / prime meridian
        "r08c017",  # just south-west of 0,0
        "r13c035",  # just west of the antimeridian
    ]


def test_antimeridian_neighbours_get_different_tiles():
    tiles = tile_ids(pd.Series([65.0, 65.0]), pd.Series([179.9, -179.9]))
    assert tiles.tolist() == ["r15c035", "r15c000"]


def test_tile_degrees_must_divide_180():
    with pytest.raises(ValueError):
        tile_ids(pd.Series([0.0]), pd.Series([0.0]), tile_degrees=7)


def test_iter_partitions_groups_by_sensor_month_tile():
    frame = pd.DataFrame(
        {
            "sensor": ["VIIRS", "VIIRS", "MODIS", "VIIRS"],
            "acquisition_date": [
                date(2023, 1, 15),
                date(2023, 1, 31),
                date(2023, 1, 15),
                date(2023, 2, 1),
            ],
            "latitude": [9.1, 9.9, 9.1, 9.1],
            "longitude": [2.5, 2.6, 2.5, 2.5],
        }
    )
    parts = {key: len(part) for key, part in iter_partitions(frame)}
    assert parts == {
        PartitionKey("MODIS", 2023, 1, "r09c018"): 1,
        PartitionKey("VIIRS", 2023, 1, "r09c018"): 2,
        PartitionKey("VIIRS", 2023, 2, "r09c018"): 1,
    }
    key = PartitionKey("VIIRS", 2023, 1, "r09c018")
    assert key.relative_path().as_posix() == "VIIRS/2023/01/r09c018"


def test_iter_partitions_empty_frame():
    assert list(iter_partitions(pd.DataFrame())) == []
