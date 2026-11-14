"""Area analytics used by the REST API, built on the verified analytics modules."""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.analytics.baselines import assess, assess_all, harmonized_index
from app.analytics.calendar import build_calendar
from app.analytics.distributions import platform_distributions
from app.analytics.observations import iter_observations
from app.analytics.series import (
    AreaBBox,
    drop_superseded,
    monthly_series,
    sp_days_by_platform,
)
from app.analytics.yearly import yearly_summary
from app.harmonization.aggregate_store import AggregateStore
from app.harmonization.cross_sensor import match_detections, monthly_calibration
from app.ingestion.firms_schema import CANONICAL_COLUMNS, Platform

MODIS = [Platform.TERRA.value, Platform.AQUA.value]
VIIRS = [Platform.SUOMI_NPP.value, Platform.NOAA_20.value, Platform.NOAA_21.value]


@dataclass
class AreaContext:
    aoi: AreaBBox
    start: date
    end: date
    platforms: list[str]
    cell_days: pd.DataFrame
    coverage: list[dict]

    def in_area_cells(self) -> pd.DataFrame:
        if self.cell_days.empty:
            return self.cell_days
        mask = self.aoi.contains_points(self.cell_days["cell_lat"], self.cell_days["cell_lon"])
        return self.cell_days[mask.to_numpy()]

    def sp_days(self) -> dict[str, set[date]]:
        return sp_days_by_platform(self.in_area_cells(), self.aoi, self.start, self.end,
                                   self.coverage)  # fmt: skip


def context(
    aggregates: AggregateStore,
    coverage: list[dict],
    aoi: AreaBBox,
    start: date,
    end: date,
    platforms: list[str],
) -> AreaContext:
    aggregates.build_stale()
    return AreaContext(aoi, start, end, platforms, aggregates.read(start=start, end=end), coverage)


def series(ctx: AreaContext) -> pd.DataFrame:
    return monthly_series(ctx.cell_days, ctx.aoi, ctx.start, ctx.end, ctx.coverage, ctx.platforms)


def iter_detections(ctx: AreaContext, processed, columns=None, supersede: bool = True):
    sp = ctx.sp_days() if supersede else None
    for frame in iter_observations(processed, ctx.aoi, ctx.start, ctx.end, columns=columns):
        if sp:
            frame = drop_superseded(frame, sp)
        frame = frame[frame["platform"].isin(ctx.platforms).to_numpy()]
        if len(frame):
            yield frame


def hotspot_page(
    ctx: AreaContext,
    processed,
    *,
    page: int,
    page_size: int,
    confidence: list[str] | None,
    day_night: list[str] | None,
    include_source: bool,
) -> dict:
    """One page of detections plus the total matching count (single streaming pass)."""
    columns = (
        list(CANONICAL_COLUMNS)
        if include_source
        else [c for c in CANONICAL_COLUMNS if c != "source_attributes"]
    )
    first, last = (page - 1) * page_size, page * page_size
    seen, items = 0, []
    for frame in iter_detections(ctx, processed):
        if confidence:
            frame = frame[frame["confidence_class"].isin(confidence).to_numpy()]
        if day_night:
            frame = frame[frame["day_night"].isin(day_night).to_numpy()]
        if frame.empty:
            continue
        lo, hi = max(first - seen, 0), min(last - seen, len(frame))
        if lo < hi:
            items.extend(frame.iloc[lo:hi][columns].to_dict(orient="records"))
        seen += len(frame)
    return {"total": seen, "page": page, "page_size": page_size, "items": items}


def summary(ctx: AreaContext, processed) -> dict:
    s = series(ctx)
    frames = list(iter_detections(ctx, processed,
                                  columns=["platform", "frp_mw", "confidence_class",
                                           "day_night", "acquisition_date"]))  # fmt: skip
    detections = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    cells = ctx.in_area_cells()
    per_platform = []
    for platform in ctx.platforms:
        part = s[s["platform"] == platform]
        cell_part = cells[cells["platform"] == platform] if len(cells) else cells
        per_platform.append(
            {
                "platform": platform,
                "detections": int(part["detections"].fillna(0).sum()),
                "unique_cells": int(cell_part[["cell_col", "cell_row"]].drop_duplicates().shape[0])
                if len(cell_part)
                else 0,
                "months_complete": int((part["coverage_status"] == "complete").sum()),
                "months_partial": int((part["coverage_status"] == "partial").sum()),
                "months_missing": int((part["coverage_status"] == "missing").sum()),
            }
        )
    first = last = None
    if len(detections):
        dates = pd.to_datetime(detections["acquisition_date"]).dt.date
        first, last = dates.min(), dates.max()
    return {
        "area": {
            "west": ctx.aoi.west,
            "south": ctx.aoi.south,
            "east": ctx.aoi.east,
            "north": ctx.aoi.north,
            "country": ctx.aoi.country,
        },  # fmt: skip
        "period": {"start": ctx.start, "end": ctx.end},
        "total_detections": int(len(detections)),
        "first_detection_date": first,
        "last_detection_date": last,
        "platforms": per_platform,
        "distributions": platform_distributions(detections),
        "note": "Detections are satellite active-fire detections, not individual fires. "
        "Unique cells are counted per platform and never summed across sensors.",
    }


def calendar_table(ctx: AreaContext, metric: str, min_history_years: int) -> pd.DataFrame:
    return build_calendar(series(ctx), metric, min_history_years)


def yearly_table(ctx: AreaContext, metric: str) -> pd.DataFrame:
    return yearly_summary(series(ctx), metric)


def anomalies(ctx: AreaContext, metric: str, min_history_years: int, target: str | None) -> dict:
    s = series(ctx)
    if target:
        ty, tm = (int(x) for x in target.split("-"))
    else:
        ty, tm = ctx.end.year, ctx.end.month
    assessed = [assess(s, p, ty, tm, metric, min_history_years).__dict__ for p in ctx.platforms]
    return {
        "status": "EXPERIMENTAL",
        "target": f"{ty}-{tm:02d}",
        "metric": metric,
        "assessments": assessed,
        "harmonized_index": harmonized_index(assess_all(s, metric, min_history_years)),
    }


def sensor_comparison(
    ctx: AreaContext, processed, metric: str, tolerance_minutes: float, resolution_m: int
) -> dict:
    s = series(ctx)
    calibrations, matching = [], []
    month_end = date(
        ctx.end.year, ctx.end.month, _calendar.monthrange(ctx.end.year, ctx.end.month)[1]
    )
    columns = ["platform", "latitude", "longitude", "acquisition_datetime_utc", "frp_mw"]
    frames = list(iter_observations(processed, ctx.aoi, ctx.start, min(ctx.end, month_end),
                                    columns=columns))  # fmt: skip
    obs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    for m in MODIS:
        for v in VIIRS:
            years = sorted(
                set(s[(s.platform == m) & (s.coverage_status == "complete")].year)
                & set(s[(s.platform == v) & (s.coverage_status == "complete")].year)
            )
            validation = years[-2:] if len(years) > 2 else []
            calibrations.append(monthly_calibration(s, m, v, validation, metric).as_dict())
            matching.append(
                {
                    "modis_platform": m,
                    "viirs_platform": v,
                    **match_detections(
                        obs[obs.platform == m],
                        obs[obs.platform == v],
                        tolerance_minutes,
                        resolution_m=resolution_m,
                    ),  # fmt: skip
                }
            )
    return {"status": "EXPERIMENTAL", "calibration": calibrations, "matching": matching}
