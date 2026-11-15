"""Area statistics read one aggregate month at a time (bounded memory for decades).

Loading every cell-day of a large area and long period at once (e.g. India 2000–2026:
millions of rows, several GB per copy) exhausted the memory of the user's laptop. Here each
sensor-month aggregate file is read, restricted to the area and period, superseded
(SP over NRT per platform-day), reduced to small per-month statistics and released.
What is kept is small: per platform-month statistics, per-platform totals, unique-cell
ids, and the SP days used for detection-level queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.analytics.series import (
    _CELL_KEY,
    AreaBBox,
    covered_days,
    drop_superseded,
    month_stats,
    series_from_stats,
)
from app.harmonization.aggregate_store import AggregateStore

TOTAL_SUM_COLUMNS = [
    "detections", "day_detections", "night_detections", "unknown_daynight_detections",
    "frp_sum_mw", "frp_count", "confidence_low", "confidence_nominal", "confidence_high",
    "confidence_missing",
]  # fmt: skip


@dataclass
class AreaAggregates:
    series: pd.DataFrame  # platform × month (series_from_stats)
    totals: pd.DataFrame  # one row per platform with detections in the area and period
    sp_days: dict[str, set[date]]


def select_month(
    cells: pd.DataFrame, aoi: AreaBBox, start: date, end: date, sp_cov: dict[str, set[date]]
) -> tuple[pd.DataFrame, dict[str, set[date]]]:
    """One month's cell-days in the area and period with NRT superseded by SP.

    Returns the selection and the SP days used (coverage SP days plus days with SP
    records in this month), matching select_cell_days on the whole period."""
    if cells.empty:
        return cells, {}
    dates = pd.to_datetime(cells["acquisition_date"]).dt.date
    mask = (dates >= start) & (dates <= end)
    mask &= aoi.contains_points(cells["cell_lat"], cells["cell_lon"])
    sel = cells[mask.to_numpy()].copy()
    if sel.empty:
        return sel, {}
    sel["acquisition_date"] = pd.to_datetime(sel["acquisition_date"]).dt.date
    sp: dict[str, set[date]] = {}
    for platform in set(sel["platform"].astype(str)) | set(sp_cov):
        days = set(sp_cov.get(platform, set()))
        is_sp = (sel["platform"] == platform) & (sel["processing_status"] == "SP")
        days |= set(sel.loc[is_sp, "acquisition_date"])
        sp[platform] = days
    return drop_superseded(sel, sp), sp


def stream_area(
    aggregates: AggregateStore,
    aoi: AreaBBox,
    start: date,
    end: date,
    coverage: list[dict],
    platforms: list[str],
) -> AreaAggregates:
    platform_set = set(platforms)
    coverage_platforms = {r["platform"] for r in coverage if r.get("platform")}
    sp_cov = {
        p: covered_days(coverage, aoi, p, start, end, status="SP") for p in coverage_platforms
    }
    stats_parts: list[pd.DataFrame] = []
    sums: dict[str, dict[str, float]] = {}
    frp_max: dict[str, float] = {}
    first: dict[str, date] = {}
    last: dict[str, date] = {}
    cells: dict[str, list[np.ndarray]] = {}
    sp_days: dict[str, set[date]] = {p: set(d) for p, d in sp_cov.items()}

    for path in aggregates.month_paths(start=start, end=end):
        sel, sp = select_month(pd.read_parquet(path), aoi, start, end, sp_cov)
        for platform, days in sp.items():
            sp_days.setdefault(platform, set()).update(days)
        if sel.empty:
            continue
        stats_parts.append(month_stats(sel))
        sel = sel[sel["platform"].astype(str).isin(platform_set).to_numpy()]
        for platform, g in sel.groupby(sel["platform"].astype(str), sort=False):
            acc = sums.setdefault(platform, dict.fromkeys(TOTAL_SUM_COLUMNS, 0.0))
            for column in TOTAL_SUM_COLUMNS:
                acc[column] += float(g[column].sum())
            if int(g["frp_count"].sum()):
                frp_max[platform] = max(
                    frp_max.get(platform, -np.inf), float(g["frp_max_mw"].max())
                )
            lo, hi = min(g["acquisition_date"]), max(g["acquisition_date"])
            first[platform] = min(first.get(platform, lo), lo)
            last[platform] = max(last.get(platform, hi), hi)
            keys = g["cell_col"].to_numpy("int64") * _CELL_KEY + g["cell_row"].to_numpy("int64")
            cells.setdefault(platform, []).append(np.unique(keys))

    stats = (
        pd.concat(stats_parts, ignore_index=True) if stats_parts else month_stats(pd.DataFrame())
    )
    series = series_from_stats(stats, aoi, start, end, coverage, platforms)
    rows = []
    for platform in sorted(sums):
        acc = sums[platform]
        rows.append(
            {
                "platform": platform,
                **{c: (acc[c] if c == "frp_sum_mw" else int(acc[c])) for c in TOTAL_SUM_COLUMNS},
                "frp_max_mw": frp_max.get(platform, np.nan),
                "unique_cells": int(np.unique(np.concatenate(cells[platform])).size),
                "first_date": first[platform],
                "last_date": last[platform],
            }
        )
    totals = pd.DataFrame(rows, columns=["platform", *TOTAL_SUM_COLUMNS, "frp_max_mw",
                                         "unique_cells", "first_date", "last_date"])  # fmt: skip
    return AreaAggregates(series, totals, sp_days)
