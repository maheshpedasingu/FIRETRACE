"""Stage D/F: sensor-specific monthly baselines, robust anomalies, harmonized index.

Baselines are computed per platform and calendar month from earlier years only, using
months with *complete* coverage. Robust statistics are used because fire counts are
skewed and heavy-tailed:

    median, MAD = median(|x - median|)
    modified z = 0.6745 * (x - median) / MAD          (Iglewicz & Hoaglin, 1993)

|modified z| >= 3.5 is the outlier threshold recommended by Iglewicz & Hoaglin.
When MAD = 0 (e.g. most years had no detections) z is undefined: it is left blank, and
the empirical percentile rank among the history years is reported instead.

The Harmonized Activity Index (HAI) is experimental. It is the mean of the modified z
scores of the contributing sensors, where each sensor's score is the mean over its
platforms (so three VIIRS satellites do not outvote MODIS). It is a dimensionless
anomaly score relative to each platform's own history — never a fire count.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ingestion.firms_schema import PLATFORM_SENSOR, Platform

MODIFIED_Z_FACTOR = 0.6745
OUTLIER_THRESHOLD = 3.5
DEFAULT_MIN_HISTORY_YEARS = 5


@dataclass(frozen=True)
class BaselineResult:
    platform: str
    year: int
    month: int
    metric: str
    value: float
    coverage_status: str
    history_years: int
    median: float
    mad: float
    p10: float
    p90: float
    modified_z: float
    percentile_rank: float
    status: str  # assessed | insufficient_history | incomplete_coverage | zero_dispersion
    label: str  # unusually high | unusually low | within normal range | not assessed


def assess(
    series: pd.DataFrame,
    platform: str,
    year: int,
    month: int,
    metric: str = "detections",
    min_history_years: int = DEFAULT_MIN_HISTORY_YEARS,
) -> BaselineResult:
    """Compare one platform-month with the same calendar month in earlier years."""
    p = series[series["platform"] == platform]
    target = p[(p["year"] == year) & (p["month"] == month)]
    value = float(target[metric].iloc[0]) if len(target) else np.nan
    coverage = str(target["coverage_status"].iloc[0]) if len(target) else "missing"
    history = p[(p["month"] == month) & (p["year"] < year) & (p["coverage_status"] == "complete")][
        metric
    ].astype(float)
    n = int(history.notna().sum())
    nan = float("nan")
    if n:
        med = float(history.median())
        mad = float((history - med).abs().median())
        p10, p90 = (float(v) for v in history.quantile([0.1, 0.9]))
    else:
        med = mad = p10 = p90 = nan
    rank = (
        float((history < value).mean() * 100 + (history == value).mean() * 50)
        if n and not np.isnan(value)
        else nan
    )

    def result(z: float, status: str, label: str) -> BaselineResult:
        return BaselineResult(platform, year, month, metric, value, coverage, n, med, mad,
                              p10, p90, z, rank, status, label)  # fmt: skip

    if coverage != "complete" or np.isnan(value):
        return result(nan, "incomplete_coverage", "not assessed")
    if n < min_history_years:
        return result(nan, "insufficient_history", "not assessed")
    if mad == 0:
        return result(nan, "zero_dispersion", "not assessed")
    z = MODIFIED_Z_FACTOR * (value - med) / mad
    if z >= OUTLIER_THRESHOLD:
        label = "unusually high"
    elif z <= -OUTLIER_THRESHOLD:
        label = "unusually low"
    else:
        label = "within normal range"
    return result(z, "assessed", label)


def assess_all(
    series: pd.DataFrame,
    metric: str = "detections",
    min_history_years: int = DEFAULT_MIN_HISTORY_YEARS,
) -> pd.DataFrame:
    rows = [
        assess(series, platform, int(year), int(month), metric, min_history_years).__dict__
        for platform, year, month in series[["platform", "year", "month"]].itertuples(index=False)
    ]
    return pd.DataFrame(rows)


def harmonized_index(assessments: pd.DataFrame) -> pd.DataFrame:
    """Experimental HAI per month from per-platform modified z scores."""
    rows = []
    for (year, month), group in assessments.groupby(["year", "month"], sort=True):
        usable = group[group["status"] == "assessed"]
        sensor_scores = {}
        for platform, z in zip(usable["platform"], usable["modified_z"], strict=True):
            sensor = PLATFORM_SENSOR[Platform(platform)].value
            sensor_scores.setdefault(sensor, []).append(float(z))
        per_sensor = {s: float(np.mean(v)) for s, v in sensor_scores.items()}
        hai = float(np.mean(list(per_sensor.values()))) if per_sensor else float("nan")
        rows.append(
            {
                "year": int(year),
                "month": int(month),
                "hai": hai,
                "sensors": ",".join(sorted(per_sensor)),
                "platforms": ",".join(sorted(usable["platform"])),
                "modis_z": per_sensor.get("MODIS", float("nan")),
                "viirs_z": per_sensor.get("VIIRS", float("nan")),
                "sensor_disagreement": (
                    abs(per_sensor["MODIS"] - per_sensor["VIIRS"])
                    if len(per_sensor) == 2
                    else float("nan")
                ),
                "not_assessed": ",".join(
                    f"{p}:{s}"
                    for p, s in zip(group["platform"], group["status"], strict=True)
                    if s != "assessed"
                ),
                "status": "experimental" if per_sensor else "unavailable",
            }
        )
    return pd.DataFrame(rows)
