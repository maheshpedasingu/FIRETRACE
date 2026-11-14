"""EPSG:6933 grid tests. Coordinates are SYNTHETIC TEST DATA."""

import numpy as np
import pytest

from app.geospatial.ease_grid import cell_centers, cell_indices, forward, inverse

WGS84_SURFACE_KM2 = 510_065_621.7  # surface area of the WGS 84 ellipsoid
EASE2_GLOBAL_X_MAX_M = 17_367_530.45  # EASE-Grid 2.0 global half-width in metres


def test_x_extent_matches_ease_grid_2_global():
    x, _ = forward(0.0, 180.0)
    assert x == pytest.approx(EASE2_GLOBAL_X_MAX_M, abs=0.01)


def test_projected_plane_area_equals_ellipsoid_surface():
    x_max = forward(0.0, 180.0)[0]
    y_max = forward(90.0, 0.0)[1]
    assert 4 * x_max * y_max / 1e6 == pytest.approx(WGS84_SURFACE_KM2, abs=1.0)


def test_round_trip_is_millimetre_accurate():
    rng = np.random.default_rng(42)
    lat = rng.uniform(-89.9, 89.9, 10_000)
    lon = rng.uniform(-180, 180, 10_000)
    lat2, lon2 = inverse(*forward(lat, lon))
    assert np.abs(lat2 - lat).max() < 1e-7  # ~1 cm
    assert np.abs(lon2 - lon).max() < 1e-9


def test_cell_indices_and_centres():
    col, row = cell_indices(np.array([0.0, -0.000001, 15.1]), np.array([0.0, -0.000001, 80.2]))
    assert col[:2].tolist() == [0, -1] and row[:2].tolist() == [0, -1]
    lat_c, lon_c = cell_centers(col, row)
    # every point lies in the cell whose centre is within ~1 km of it
    assert np.abs(lat_c[2] - 15.1) < 0.01 and np.abs(lon_c[2] - 80.2) < 0.01
    assert cell_indices(lat_c, lon_c)[0].tolist() == col.tolist()


def test_resolution_is_configurable_and_validated():
    col_1km, _ = cell_indices(np.array([10.0]), np.array([10.0]), 1000)
    col_5km, _ = cell_indices(np.array([10.0]), np.array([10.0]), 5000)
    assert col_5km[0] == col_1km[0] // 5
    with pytest.raises(ValueError):
        cell_indices(np.array([0.0]), np.array([0.0]), 0)


def test_matches_pyproj_epsg_6933():
    pyproj = pytest.importorskip("pyproj")
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    rng = np.random.default_rng(7)
    lat = rng.uniform(-85, 85, 2_000)
    lon = rng.uniform(-180, 180, 2_000)
    ref_x, ref_y = transformer.transform(lon, lat)
    x, y = forward(lat, lon)
    assert np.abs(x - ref_x).max() < 0.001  # metres
    assert np.abs(y - ref_y).max() < 0.001
    back = pyproj.Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
    ref_lon, ref_lat = back.transform(ref_x, ref_y)
    lat2, lon2 = inverse(ref_x, ref_y)
    assert np.abs(lat2 - ref_lat).max() < 1e-7
    assert np.abs(lon2 - ref_lon).max() < 1e-9
