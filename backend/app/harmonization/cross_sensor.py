"""Stage E/G: MODIS–VIIRS comparison over their overlap period (experimental).

Two complementary diagnostics, both reported with sample sizes:

1. Monthly count relationship (same area, same month, both platforms with complete
   coverage). A single scale factor  VIIRS ≈ k · MODIS  is estimated on training years
   as a ratio of sums, then evaluated on separate validation years with bias, MAE,
   RMSE and Pearson correlation of log1p values. With too few months the calibration
   is reported as unavailable — no factor is invented.

2. Detection matching. A MODIS detection is "matched" when a VIIRS detection lies in the
   same or a neighbouring 1 km cell within ``tolerance_minutes``. This measures
   agreement where both sensors detected fire; it is NOT a detection probability,
   because FIRMS records contain detections only (no record of overpasses without fire).
   FRP is compared per matched MODIS detection against the summed FRP of its matched
   VIIRS detections; MODIS (~1 km) and VIIRS (375 m) pixel sizes differ, so FRP ratios
   are diagnostics, not a calibration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.geospatial.ease_grid import cell_indices

DEFAULT_MIN_TRAIN_MONTHS = 12
DEFAULT_MIN_VALIDATION_MONTHS = 6


@dataclass(frozen=True)
class CalibrationResult:
    modis_platform: str
    viirs_platform: str
    metric: str
    status: str  # estimated | unavailable
    reason: str
    train_years: str
    validation_years: str
    n_train: int
    n_validation: int
    scale_factor: float  # VIIRS ≈ factor × MODIS (training years)
    bias: float  # mean(predicted − observed) on validation months
    mae: float
    rmse: float
    log_correlation: float
    residuals: list[float]

    def as_dict(self) -> dict:
        return asdict(self)


def monthly_calibration(
    series: pd.DataFrame,
    modis_platform: str,
    viirs_platform: str,
    validation_years: list[int],
    metric: str = "detections",
    min_train: int = DEFAULT_MIN_TRAIN_MONTHS,
    min_validation: int = DEFAULT_MIN_VALIDATION_MONTHS,
) -> CalibrationResult:
    def complete(platform: str) -> pd.DataFrame:
        part = series[(series["platform"] == platform) & (series["coverage_status"] == "complete")]
        return part[["year", "month", metric]].rename(columns={metric: platform})

    pairs = complete(modis_platform).merge(complete(viirs_platform), on=["year", "month"])
    is_val = pairs["year"].isin(validation_years)
    train, val = pairs[~is_val], pairs[is_val]
    nan = float("nan")

    def out(status, reason, factor=nan, bias=nan, mae=nan, rmse=nan, corr=nan, resid=None):
        return CalibrationResult(
            modis_platform, viirs_platform, metric, status, reason,
            ",".join(str(y) for y in sorted(train["year"].unique())),
            ",".join(str(y) for y in sorted(val["year"].unique())),
            len(train), len(val), factor, bias, mae, rmse, corr, resid or [],
        )  # fmt: skip

    if len(train) < min_train or len(val) < min_validation:
        return out(
            "unavailable",
            f"needs ≥{min_train} training and ≥{min_validation} validation months with "
            f"complete coverage for both platforms; have {len(train)} and {len(val)}",
        )
    modis_sum = float(train[modis_platform].sum())
    if modis_sum == 0:
        return out("unavailable", "no MODIS detections in training months")
    factor = float(train[viirs_platform].sum()) / modis_sum
    predicted = factor * val[modis_platform].astype(float)
    observed = val[viirs_platform].astype(float)
    residual = predicted - observed
    corr = (
        float(np.corrcoef(np.log1p(predicted), np.log1p(observed))[0, 1]) if len(val) > 2 else nan
    )
    return out(
        "estimated",
        "ratio of sums on training years; evaluated on held-out validation years",
        factor,
        float(residual.mean()),
        float(residual.abs().mean()),
        float(np.sqrt((residual**2).mean())),
        corr,
        [round(float(r), 3) for r in residual],
    )


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation without SciPy (Pearson correlation of average ranks)."""
    ra = a.rank(method="average").to_numpy(float)
    rb = b.rank(method="average").to_numpy(float)
    if len(ra) < 2 or ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def match_detections(
    modis: pd.DataFrame,
    viirs: pd.DataFrame,
    tolerance_minutes: float = 15.0,
    neighbour_cells: int = 1,
    resolution_m: float = 1000.0,
) -> dict:
    """Match MODIS detections to VIIRS detections nearby in space and time.

    Both frames need latitude, longitude, acquisition_datetime_utc, frp_mw.
    """
    summary = {
        "tolerance_minutes": tolerance_minutes,
        "neighbour_cells": neighbour_cells,
        "modis_detections": len(modis),
        "viirs_detections": len(viirs),
        "modis_matched": 0,
        "match_fraction": float("nan"),
        "frp_pairs": 0,
        "frp_median_ratio_viirs_to_modis": float("nan"),
        "frp_spearman": float("nan"),
        "note": "Agreement where both detected fire; not a detection probability.",
    }
    if modis.empty or viirs.empty:
        return summary

    def prepared(frame: pd.DataFrame) -> pd.DataFrame:
        col, row = cell_indices(frame["latitude"].to_numpy(float),
                                frame["longitude"].to_numpy(float), resolution_m)  # fmt: skip
        times = pd.to_datetime(frame["acquisition_datetime_utc"], utc=True)
        return pd.DataFrame(
            {
                "col": col,
                "row": row,
                "day": times.dt.floor("D").to_numpy(),
                "t": times.to_numpy(),
                "frp": pd.to_numeric(frame["frp_mw"], errors="coerce").to_numpy(float),
            }
        )

    m = prepared(modis).reset_index(drop=True)
    m["modis_id"] = np.arange(len(m))
    v = prepared(viirs)
    shifts = range(-neighbour_cells, neighbour_cells + 1)
    expanded = pd.concat(
        [v.assign(col=v["col"] + dc, row=v["row"] + dr) for dc in shifts for dr in shifts],
        ignore_index=True,
    )
    pairs = m.merge(expanded, on=["day", "col", "row"], suffixes=("_m", "_v"))
    dt = (pairs["t_m"] - pairs["t_v"]).abs() / pd.Timedelta(minutes=1)
    pairs = pairs[dt <= tolerance_minutes]
    matched = pairs["modis_id"].nunique()
    summary["modis_matched"] = int(matched)
    summary["match_fraction"] = matched / len(m)
    frp = pairs.groupby("modis_id").agg(modis_frp=("frp_m", "first"), viirs_frp=("frp_v", "sum"),
                                        n_viirs=("frp_v", "count"))  # fmt: skip
    frp = frp[(frp["modis_frp"] > 0) & (frp["n_viirs"] > 0) & (frp["viirs_frp"] > 0)]
    summary["frp_pairs"] = len(frp)
    if len(frp) >= 3:
        summary["frp_median_ratio_viirs_to_modis"] = float(
            (frp["viirs_frp"] / frp["modis_frp"]).median()
        )
        summary["frp_spearman"] = spearman(frp["modis_frp"], frp["viirs_frp"])
    return summary
