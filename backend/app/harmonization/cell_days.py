"""Stage B/C of harmonization: detections → daily per-cell aggregates per platform.

One output row = one platform × processing status × UTC day × 1 km EPSG:6933 cell
that had at least one detection. Raw detection counts are kept next to the cell, so
both "detections" and "unique active cells" can be reported, and neither is called a
fire incident. Platforms and processing statuses are never mixed in a row.

All columns are additive (sums) or max-combinable, so partial aggregates of the same
month computed from different files can be combined exactly with ``combine``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.geospatial.ease_grid import cell_centers, cell_indices

KEYS = ["sensor", "platform", "processing_status", "acquisition_date", "cell_col", "cell_row"]
SUM_COLUMNS = [
    "detections",
    "day_detections",
    "night_detections",
    "unknown_daynight_detections",
    "frp_sum_mw",
    "frp_count",
    "confidence_low",
    "confidence_nominal",
    "confidence_high",
    "confidence_missing",
]
MAX_COLUMNS = ["frp_max_mw"]
CELL_DAY_COLUMNS = [*KEYS, *SUM_COLUMNS, *MAX_COLUMNS, "cell_lat", "cell_lon"]

OBSERVATION_COLUMNS = [
    "sensor",
    "platform",
    "processing_status",
    "acquisition_date",
    "latitude",
    "longitude",
    "day_night",
    "frp_mw",
    "confidence_class",
]


def _empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in CELL_DAY_COLUMNS})


def aggregate(observations: pd.DataFrame, resolution_m: float = 1000.0) -> pd.DataFrame:
    """Aggregate canonical observations to cell-days (without cell centres)."""
    if observations.empty:
        return _empty()
    obs = observations[OBSERVATION_COLUMNS]
    col, row = cell_indices(
        obs["latitude"].to_numpy(float), obs["longitude"].to_numpy(float), resolution_m
    )
    day_night = obs["day_night"].astype("object").fillna("").astype(str)
    confidence = obs["confidence_class"].astype("object").fillna("").astype(str)
    frp = pd.to_numeric(obs["frp_mw"], errors="coerce")
    frame = pd.DataFrame(
        {
            "sensor": obs["sensor"].astype(str).to_numpy(),
            "platform": obs["platform"].astype(str).to_numpy(),
            "processing_status": obs["processing_status"].astype(str).to_numpy(),
            "acquisition_date": pd.to_datetime(obs["acquisition_date"]).dt.date.to_numpy(),
            "cell_col": col,
            "cell_row": row,
            "detections": 1,
            "day_detections": (day_night == "D").to_numpy(int),
            "night_detections": (day_night == "N").to_numpy(int),
            "unknown_daynight_detections": (~day_night.isin(["D", "N"])).to_numpy(int),
            "frp_sum_mw": frp.fillna(0.0).to_numpy(float),
            "frp_count": frp.notna().to_numpy(int),
            "frp_max_mw": frp.to_numpy(float),
            "confidence_low": (confidence == "low").to_numpy(int),
            "confidence_nominal": (confidence == "nominal").to_numpy(int),
            "confidence_high": (confidence == "high").to_numpy(int),
            "confidence_missing": (~confidence.isin(["low", "nominal", "high"])).to_numpy(int),
        }
    )
    return _group(frame)


def _group(frame: pd.DataFrame) -> pd.DataFrame:
    agg = {c: "sum" for c in SUM_COLUMNS} | {c: "max" for c in MAX_COLUMNS}
    grouped = frame.groupby(KEYS, sort=True, dropna=False).agg(agg).reset_index()
    for column in SUM_COLUMNS:
        if column != "frp_sum_mw":
            grouped[column] = grouped[column].astype("int64")
    return grouped


def combine(parts: list[pd.DataFrame], resolution_m: float = 1000.0) -> pd.DataFrame:
    """Combine partial cell-day aggregates exactly, then add cell centres."""
    parts = [p for p in parts if not p.empty]
    if not parts:
        return _empty()
    merged = _group(pd.concat([p[[*KEYS, *SUM_COLUMNS, *MAX_COLUMNS]] for p in parts]))
    lat, lon = cell_centers(
        merged["cell_col"].to_numpy(), merged["cell_row"].to_numpy(), resolution_m
    )
    merged["cell_lat"] = np.round(lat, 6)
    merged["cell_lon"] = np.round(lon, 6)
    return merged[CELL_DAY_COLUMNS].reset_index(drop=True)
