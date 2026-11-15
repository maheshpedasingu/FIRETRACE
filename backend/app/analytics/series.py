"""Area-of-interest time series from cell-day aggregates, aware of coverage.

Rules:
- Each platform is reported separately; nothing here adds MODIS and VIIRS counts.
- A month with no detections is 0 only if imports covered the area on its days;
  otherwise it is missing (NaN) — never 0.
- NRT/SP: for each platform and day, if standard-processing (SP) data covers the
  area (coverage row or SP rows present), NRT rows for that day are excluded, so the
  same detections are not counted twice. Days with only NRT use NRT.
- "detections" counts satellite detections, "unique_cells" counts distinct 1 km cells
  active in the month, "cell_days" counts active cell-days. None is a fire count.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.analytics.platform_periods import first_record_day


@dataclass(frozen=True)
class AreaBBox:
    west: float
    south: float
    east: float
    north: float
    country: str | None = None  # set when the AOI is a whole country

    def lon_intervals(self) -> list[tuple[float, float]]:
        if self.west <= self.east:
            return [(self.west, self.east)]
        return [(self.west, 180.0), (-180.0, self.east)]  # crosses the antimeridian

    def contains_points(self, lat: pd.Series, lon: pd.Series) -> pd.Series:
        in_lat = (lat >= self.south) & (lat <= self.north)
        in_lon = pd.Series(False, index=lon.index)
        for lo, hi in self.lon_intervals():
            in_lon |= (lon >= lo) & (lon <= hi)
        return in_lat & in_lon


def _interval_contains(outer: list[tuple[float, float]], inner: tuple[float, float]) -> bool:
    return any(lo <= inner[0] and inner[1] <= hi for lo, hi in outer)


def coverage_contains(row: dict, aoi: AreaBBox) -> bool:
    """Does one coverage record cover the whole AOI?"""
    if row["extent_type"] == "bbox":
        b = json.loads(row["extent_value"])
        cov = AreaBBox(b["west"], b["south"], b["east"], b["north"])
        if not (cov.south <= aoi.south and aoi.north <= cov.north):
            return False
        return all(_interval_contains(cov.lon_intervals(), iv) for iv in aoi.lon_intervals())
    if row["extent_type"] == "country":
        return aoi.country is not None and row["extent_value"].strip().lower() == (
            aoi.country.strip().lower()
        )
    return False  # 'unknown' coverage never supports a zero


def covered_days(
    coverage: list[dict],
    aoi: AreaBBox,
    platform: str,
    start: date,
    end: date,
    status: str | None = None,
) -> set[date]:
    days: set[date] = set()
    # Never count days before the platform's first FIRMS record as covered.
    platform_start = first_record_day(platform)
    if platform_start is not None:
        start = max(start, platform_start)
    for row in coverage:
        if row["platform"] != platform or row["start_date"] is None:
            continue
        if status is not None and row["processing_status"] != status:
            continue
        if not coverage_contains(row, aoi):
            continue
        first, last = max(row["start_date"], start), min(row["end_date"], end)
        day = first
        while day <= last:
            days.add(day)
            day += timedelta(days=1)
    return days


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    months, (y, m) = [], (start.year, start.month)
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def sp_days_by_platform(
    in_area: pd.DataFrame, aoi: AreaBBox, start: date, end: date, coverage: list[dict]
) -> dict[str, set[date]]:
    """Days on which standard-processing (SP) data should be used instead of NRT.

    A platform-day is an SP day if SP coverage contains the area on that day or any SP
    record for that platform exists in the area on that day. ``in_area`` holds records
    already restricted to the area, with platform, processing_status, acquisition_date.
    """
    result: dict[str, set[date]] = {}
    platforms = set(in_area["platform"].unique()) if len(in_area) else set()
    platforms |= {row["platform"] for row in coverage if row.get("platform")}
    for platform in platforms:
        days = covered_days(coverage, aoi, platform, start, end, status="SP")
        if len(in_area):
            is_sp = (in_area["platform"] == platform) & (in_area["processing_status"] == "SP")
            days |= set(pd.to_datetime(in_area.loc[is_sp, "acquisition_date"]).dt.date)
        result[platform] = days
    return result


def drop_superseded(frame: pd.DataFrame, sp_days: dict[str, set[date]]) -> pd.DataFrame:
    """Remove non-SP records on platform-days that have SP data (no double counting)."""
    if frame.empty:
        return frame
    dates = pd.to_datetime(frame["acquisition_date"]).dt.date
    keep = pd.Series(True, index=frame.index)
    for platform, days in sp_days.items():
        if not days:
            continue
        drop = (
            (frame["platform"] == platform)
            & (frame["processing_status"] != "SP")
            & dates.isin(days)
        )
        keep &= ~drop
    return frame[keep.to_numpy()]


def select_cell_days(
    cell_days: pd.DataFrame, aoi: AreaBBox, start: date, end: date, coverage: list[dict]
) -> pd.DataFrame:
    """Cell-days inside the AOI and date range, with NRT superseded by SP per day."""
    if cell_days.empty:
        return cell_days
    dates = pd.to_datetime(cell_days["acquisition_date"]).dt.date
    mask = (dates >= start) & (dates <= end)
    mask &= aoi.contains_points(cell_days["cell_lat"], cell_days["cell_lon"])
    sel = cell_days[mask.to_numpy()].copy()
    sel["acquisition_date"] = pd.to_datetime(sel["acquisition_date"]).dt.date
    return drop_superseded(sel, sp_days_by_platform(sel, aoi, start, end, coverage))


def monthly_series(
    cell_days: pd.DataFrame,
    aoi: AreaBBox,
    start: date,
    end: date,
    coverage: list[dict],
    platforms: list[str],
) -> pd.DataFrame:
    """One row per platform × month with counts and a coverage status."""
    sel = select_cell_days(cell_days, aoi, start, end, coverage)
    rows = []
    for platform in platforms:
        days = covered_days(coverage, aoi, platform, start, end)
        part = sel[sel["platform"] == platform] if not sel.empty else sel
        if len(part):
            stamps = pd.to_datetime(part["acquisition_date"])
            part = part.assign(_year=stamps.dt.year.to_numpy(), _month=stamps.dt.month.to_numpy())
        for year, month in months_between(start, end):
            first = max(date(year, month, 1), start)
            last = min(date(year, month, calendar.monthrange(year, month)[1]), end)
            n_days = (last - first).days + 1
            n_cov = sum(1 for d in days if first <= d <= last)
            m = part[(part["_year"] == year) & (part["_month"] == month)] if len(part) else part
            status = "complete" if n_cov == n_days else "partial" if n_cov else "missing"
            has_rows = not m.empty
            if not has_rows and status == "missing":
                values = dict.fromkeys(
                    [
                        "detections",
                        "cell_days",
                        "unique_cells",
                        "day_detections",
                        "night_detections",
                        "frp_sum_mw",
                        "frp_max_mw",
                    ],
                    np.nan,
                )
                statuses = ""
            else:
                frp_count = int(m["frp_count"].sum()) if has_rows else 0
                values = {
                    "detections": int(m["detections"].sum()) if has_rows else 0,
                    "cell_days": len(m),
                    "unique_cells": int(m[["cell_col", "cell_row"]].drop_duplicates().shape[0])
                    if has_rows
                    else 0,
                    "day_detections": int(m["day_detections"].sum()) if has_rows else 0,
                    "night_detections": int(m["night_detections"].sum()) if has_rows else 0,
                    "frp_sum_mw": float(m["frp_sum_mw"].sum()) if frp_count else np.nan,
                    "frp_max_mw": float(m["frp_max_mw"].max()) if frp_count else np.nan,
                }
                statuses = ",".join(sorted(set(m["processing_status"]))) if has_rows else ""
            rows.append(
                {
                    "platform": platform,
                    "year": year,
                    "month": month,
                    "days_in_range": n_days,
                    "days_covered": n_cov,
                    "coverage_status": status,
                    **values,
                    "processing_status_used": statuses,
                }
            )
    return pd.DataFrame(rows)
