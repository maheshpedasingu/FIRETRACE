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
