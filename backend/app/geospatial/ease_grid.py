"""Equal-area grid on EPSG:6933 (WGS 84 / NSIDC EASE-Grid 2.0 Global).

EPSG:6933 is the Lambert cylindrical equal-area projection on the WGS 84 ellipsoid with
standard parallel 30°, central meridian 0°, no false easting/northing. Forward and
inverse formulas follow Snyder (1987), "Map Projections — A Working Manual", USGS
Professional Paper 1395, §10 (ellipsoidal cylindrical equal-area) and eq. 3-18 (inverse
via authalic latitude). They are vectorised with NumPy so millions of points project in
milliseconds; tests cross-check them against PyProj on the target machine.

Grid cells are squares of ``resolution_m`` metres in projected x/y. Because the
projection is equal-area, every cell has the same true area on the ellipsoid. Cell
shapes are distorted away from ±30°: near the poles they become very narrow east-west
and tall north-south. A cell is a counting unit, never a fire perimeter.
"""

from __future__ import annotations

import numpy as np

A = 6378137.0  # WGS 84 semi-major axis (m)
F = 1 / 298.257223563  # WGS 84 flattening
E2 = 2 * F - F * F
E = np.sqrt(E2)
STANDARD_PARALLEL = np.radians(30.0)
K0 = np.cos(STANDARD_PARALLEL) / np.sqrt(1 - E2 * np.sin(STANDARD_PARALLEL) ** 2)


def _q(sin_phi: np.ndarray) -> np.ndarray:
    return (1 - E2) * (
        sin_phi / (1 - E2 * sin_phi**2)
        - (1 / (2 * E)) * np.log((1 - E * sin_phi) / (1 + E * sin_phi))
    )


QP = float(_q(np.array(1.0)))  # q at the pole


def forward(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Geographic degrees → EPSG:6933 metres."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    x = A * K0 * np.radians(lon)
    y = A * _q(np.sin(np.radians(lat))) / (2 * K0)
    return x, y


def inverse(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """EPSG:6933 metres → geographic degrees (series for authalic latitude)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    beta = np.arcsin(np.clip(2 * y * K0 / (A * QP), -1.0, 1.0))
    e4, e6 = E2**2, E2**3
    phi = (
        beta
        + (E2 / 3 + 31 * e4 / 180 + 517 * e6 / 5040) * np.sin(2 * beta)
        + (23 * e4 / 360 + 251 * e6 / 3780) * np.sin(4 * beta)
        + (761 * e6 / 45360) * np.sin(6 * beta)
    )
    lon = np.degrees(x / (A * K0))
    return np.degrees(phi), lon


def cell_indices(
    lat: np.ndarray, lon: np.ndarray, resolution_m: float = 1000.0
) -> tuple[np.ndarray, np.ndarray]:
    """Integer (column, row) of the grid cell containing each point."""
    if resolution_m <= 0:
        raise ValueError("resolution_m must be positive")
    x, y = forward(lat, lon)
    return (
        np.floor(x / resolution_m).astype(np.int64),
        np.floor(y / resolution_m).astype(np.int64),
    )


def cell_centers(
    col: np.ndarray, row: np.ndarray, resolution_m: float = 1000.0
) -> tuple[np.ndarray, np.ndarray]:
    """Geographic (lat, lon) of cell centres."""
    x = (np.asarray(col, dtype=float) + 0.5) * resolution_m
    y = (np.asarray(row, dtype=float) + 0.5) * resolution_m
    return inverse(x, y)


def cell_area_km2(resolution_m: float = 1000.0) -> float:
    return (resolution_m / 1000.0) ** 2
