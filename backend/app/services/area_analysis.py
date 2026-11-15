"""Area analytics used by the REST API, built on the verified analytics modules."""

from __future__ import annotations

import calendar as _calendar
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.analytics.area_stream import AreaAggregates, stream_area
from app.analytics.baselines import assess, assess_all, harmonized_index
from app.analytics.calendar import build_calendar
from app.analytics.distributions import distributions_from_totals
from app.analytics.observations import iter_observations
from app.analytics.series import (
    AreaBBox,
    drop_superseded,
)
from app.analytics.yearly import yearly_summary
from app.harmonization.aggregate_store import AggregateStore
from app.harmonization.cross_sensor import match_detections, monthly_calibration
from app.harmonization.harmonized import harmonize
from app.ingestion.firms_schema import CANONICAL_COLUMNS, Platform

MODIS = [Platform.TERRA.value, Platform.AQUA.value]
VIIRS = [Platform.SUOMI_NPP.value, Platform.NOAA_20.value, Platform.NOAA_21.value]
MATCHING_DAYS = 366


@dataclass
class AreaContext:
    """Everything one area/period query needs, computed by reading the aggregates one
    month at a time (app.analytics.area_stream): only small results are held, so
    memory stays bounded for decades of data. Shared by every endpoint of a page."""

    aoi: AreaBBox
    start: date
    end: date
    platforms: list[str]
    coverage: list[dict]
    data: AreaAggregates

    def sp_days(self) -> dict[str, set[date]]:
        return self.data.sp_days

    def monthly(self) -> pd.DataFrame:
        return self.data.series.copy()

    def totals(self) -> pd.DataFrame:
        """Per-platform totals for the selected platforms (area, period, superseded)."""
        t = self.data.totals
        return t[t["platform"].isin(self.platforms)].reset_index(drop=True)


def _area_key(aoi: AreaBBox) -> tuple:
    geometry = getattr(aoi, "geometry", None)
    return (aoi.west, aoi.south, aoi.east, aoi.north, aoi.country,
            geometry.wkb_hex if geometry is not None else None)  # fmt: skip


class _ContextCache:
    """A few recent AreaContexts. Concurrent requests for the same key wait for one
    computation instead of each loading decades of aggregates."""

    def __init__(self, size: int = 3) -> None:
        self.size = size
        self._items: OrderedDict[tuple, AreaContext] = OrderedDict()
        self._guard = threading.Lock()
        self._building: dict[tuple, threading.Lock] = {}

    def get(self, key: tuple, build) -> AreaContext:
        with self._guard:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
            lock = self._building.setdefault(key, threading.Lock())
        with lock:
            with self._guard:
                if key in self._items:
                    return self._items[key]
            value = build()
            with self._guard:
                self._items[key] = value
                self._items.move_to_end(key)
                while len(self._items) > self.size:
                    self._items.popitem(last=False)
                self._building.pop(key, None)
            return value

    def clear(self) -> None:
        with self._guard:
            self._items.clear()


_CONTEXTS = _ContextCache()


def context(
    aggregates: AggregateStore,
    coverage: list[dict],
    aoi: AreaBBox,
    start: date,
    end: date,
    platforms: list[str],
    generation_token: str | None = None,
) -> AreaContext:
    """Area context. With a store generation token (API), aggregates are refreshed only
    when stored data changed and the context is cached; without one (CLI), it is built
    fresh after rebuilding any stale aggregates."""

    def build() -> AreaContext:
        data = stream_area(aggregates, aoi, start, end, coverage, list(platforms))
        return AreaContext(aoi, start, end, list(platforms), coverage, data)

    if generation_token is None:
        aggregates.build_stale()
        return build()
    aggregates.ensure_fresh(generation_token)
    key = (str(aggregates.root), generation_token, _area_key(aoi), start, end,
           tuple(platforms))  # fmt: skip
    return _CONTEXTS.get(key, build)


def series(ctx: AreaContext) -> pd.DataFrame:
    return ctx.monthly()


# Columns every caller needs: platform filter and the SP-supersedes-NRT rule.
REQUIRED_DETECTION_COLUMNS = ("platform", "processing_status", "acquisition_date")


def iter_detections(
    ctx: AreaContext, processed, columns=None, supersede: bool = True, start: date | None = None
):
    """Individual detections in the area and period (from ``start`` if given), file by
    file, NRT superseded by SP per platform-day."""
    sp = ctx.sp_days() if supersede else None
    if columns is not None:
        columns = list(dict.fromkeys([*columns, *REQUIRED_DETECTION_COLUMNS]))
    first = max(start, ctx.start) if start is not None else ctx.start
    for frame in iter_observations(processed, ctx.aoi, first, ctx.end, columns=columns):
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
    total = aggregate_total(ctx, confidence, day_night)
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
        if total is not None and seen >= last:
            break  # the page is full and the total is known: stop reading
    return {"total": seen if total is None else total, "page": page,
            "page_size": page_size, "items": items}  # fmt: skip


def aggregate_total(
    ctx: AreaContext, confidence: list[str] | None, day_night: list[str] | None
) -> int | None:
    """Exact number of matching detections from cell-day aggregates, without reading
    individual detections. None when confidence AND day/night filters are combined
    (the aggregates hold each marginal count, not the combination)."""
    if confidence and day_night:
        return None
    t = ctx.totals()
    if not len(t):
        return 0
    if confidence:
        return int(sum(t[f"confidence_{c}"].sum() for c in confidence))
    if day_night:
        names = {"D": "day_detections", "N": "night_detections"}
        return int(sum(t[names[d]].sum() for d in day_night))
    return int(t["detections"].sum())


# FRP median / percentiles need individual detections; for long periods only the last
# FRP_PERCENTILE_DAYS of the period are read (memory and time stay bounded).
FRP_PERCENTILE_DAYS = 366


def summary(ctx: AreaContext, processed) -> dict:
    """Totals and distributions from cell-day aggregates (exact and fast for decades of
    data); FRP percentiles from individual detections of the last year of the period."""
    s = series(ctx)
    totals = ctx.totals()
    frp_start = max(ctx.start, ctx.end - timedelta(days=FRP_PERCENTILE_DAYS - 1))
    frames = list(iter_detections(ctx, processed, columns=["platform", "frp_mw"],
                                  start=frp_start))  # fmt: skip
    frp = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    by_platform = totals.set_index("platform") if len(totals) else totals
    per_platform = []
    for platform in ctx.platforms:
        part = s[s["platform"] == platform]
        per_platform.append(
            {
                "platform": platform,
                "detections": int(part["detections"].fillna(0).sum()),
                "unique_cells": int(by_platform.loc[platform, "unique_cells"])
                if len(totals) and platform in by_platform.index
                else 0,
                "months_complete": int((part["coverage_status"] == "complete").sum()),
                "months_partial": int((part["coverage_status"] == "partial").sum()),
                "months_missing": int((part["coverage_status"] == "missing").sum()),
            }
        )
    return {
        "area": {
            "west": ctx.aoi.west,
            "south": ctx.aoi.south,
            "east": ctx.aoi.east,
            "north": ctx.aoi.north,
            "country": ctx.aoi.country,
        },  # fmt: skip
        "period": {"start": ctx.start, "end": ctx.end},
        "total_detections": int(totals["detections"].sum()) if len(totals) else 0,
        "first_detection_date": min(totals["first_date"]) if len(totals) else None,
        "last_detection_date": max(totals["last_date"]) if len(totals) else None,
        "platforms": per_platform,
        "distributions": distributions_from_totals(totals, frp),
        "frp_percentile_period": {"start": frp_start, "end": ctx.end},
        "note": "Detections are satellite active-fire detections, not individual fires. "
        "Unique cells are counted per platform and never summed across sensors. FRP "
        "median and percentiles use individual detections from frp_percentile_period.",
    }


def calendar_table(ctx: AreaContext, metric: str, min_history_years: int) -> pd.DataFrame:
    return build_calendar(series(ctx), metric, min_history_years)


def harmonized_calendar(
    ctx: AreaContext, reference: str, metric: str, min_history_years: int
) -> dict:
    """EXPERIMENTAL: one calendar in a single reference unit (see harmonization.harmonized)."""
    return harmonize(series(ctx), reference, metric, min_history_years)


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
    # Detection matching reads individual detections, so it is limited to the last
    # MATCHING_DAYS of the period (memory stays bounded for multi-decade queries); the
    # monthly calibration above it uses the whole period.
    match_end = min(ctx.end, month_end)
    match_start = max(ctx.start, match_end - timedelta(days=MATCHING_DAYS - 1))
    frames = list(iter_observations(processed, ctx.aoi, match_start, match_end,
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
    return {
        "status": "EXPERIMENTAL",
        "calibration": calibrations,
        "matching": matching,
        "matching_period": {"start": match_start, "end": match_end},
    }
