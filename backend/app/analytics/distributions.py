"""Per-platform FRP statistics and confidence / day-night distributions.

Computed from individual detections (not cell-day aggregates), so medians and
percentiles are exact. FRP (MW) is the radiative power of a detected pixel; it is not
burned area, and MODIS (~1 km) and VIIRS (375 m) FRP are not directly comparable.
Missing FRP is excluded from FRP statistics and counted separately.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def platform_distributions(observations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if observations.empty:
        return pd.DataFrame()
    for platform, group in observations.groupby("platform", sort=True):
        frp = pd.to_numeric(group["frp_mw"], errors="coerce")
        valid = frp.dropna()
        conf = group["confidence_class"].astype("object").fillna("missing").astype(str)
        daynight = group["day_night"].astype("object").fillna("").astype(str)

        def pct(q: float, values: pd.Series = valid) -> float:
            return float(values.quantile(q)) if len(values) else np.nan

        rows.append(
            {
                "platform": platform,
                "detections": len(group),
                "frp_values": len(valid),
                "frp_missing": int(frp.isna().sum()),
                "frp_sum_mw": float(valid.sum()) if len(valid) else np.nan,
                "frp_mean_mw": float(valid.mean()) if len(valid) else np.nan,
                "frp_median_mw": pct(0.5),
                "frp_p90_mw": pct(0.9),
                "frp_p99_mw": pct(0.99),
                "frp_max_mw": float(valid.max()) if len(valid) else np.nan,
                "confidence_low": int((conf == "low").sum()),
                "confidence_nominal": int((conf == "nominal").sum()),
                "confidence_high": int((conf == "high").sum()),
                "confidence_missing": int((~conf.isin(["low", "nominal", "high"])).sum()),
                "day": int((daynight == "D").sum()),
                "night": int((daynight == "N").sum()),
                "daynight_unknown": int((~daynight.isin(["D", "N"])).sum()),
            }
        )
    return pd.DataFrame(rows)


def distributions_from_cell_days(
    cell_days: pd.DataFrame, frp_detections: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Per-platform distributions from cell-day aggregates (exact counts, FRP sum / mean /
    max), with FRP median and percentiles from ``frp_detections`` (individual detections,
    possibly a shorter period) because percentiles cannot be recovered from sums."""
    if cell_days.empty:
        return pd.DataFrame()
    rows = []
    for platform, g in cell_days.groupby("platform", sort=True):
        detections = int(g["detections"].sum())
        frp_values = int(g["frp_count"].sum())
        frp_sum = float(g["frp_sum_mw"].sum())
        detail = (
            pd.to_numeric(
                frp_detections.loc[frp_detections["platform"] == platform, "frp_mw"],
                errors="coerce",
            ).dropna()
            if frp_detections is not None and len(frp_detections)
            else pd.Series(dtype="float64")
        )

        def pct(q: float, values: pd.Series = detail) -> float:
            return float(values.quantile(q)) if len(values) else np.nan

        rows.append(
            {
                "platform": platform,
                "detections": detections,
                "frp_values": frp_values,
                "frp_missing": detections - frp_values,
                "frp_sum_mw": frp_sum if frp_values else np.nan,
                "frp_mean_mw": frp_sum / frp_values if frp_values else np.nan,
                "frp_median_mw": pct(0.5),
                "frp_p90_mw": pct(0.9),
                "frp_p99_mw": pct(0.99),
                "frp_percentile_detections": int(len(detail)),
                "frp_max_mw": float(g["frp_max_mw"].max()) if frp_values else np.nan,
                "confidence_low": int(g["confidence_low"].sum()),
                "confidence_nominal": int(g["confidence_nominal"].sum()),
                "confidence_high": int(g["confidence_high"].sum()),
                "confidence_missing": int(g["confidence_missing"].sum()),
                "day": int(g["day_detections"].sum()),
                "night": int(g["night_detections"].sum()),
                "daynight_unknown": int(g["unknown_daynight_detections"].sum()),
            }
        )
    return pd.DataFrame(rows)
