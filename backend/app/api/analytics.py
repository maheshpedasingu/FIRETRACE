"""Hotspots, calendar and analytics endpoints (per platform; coverage-aware)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS
from app.api.deps import AreaParams, Services, ServicesDep, load_coverage, resolve_area
from app.api.serialize import to_jsonable
from app.services import area_analysis as aa

router = APIRouter(tags=["analytics"])

Metric = Literal["detections", "unique_cells", "cell_days"]
AreaDep = Annotated[AreaParams, Depends()]


def _ctx(services: Services, area: AreaParams) -> aa.AreaContext:
    aoi = resolve_area(services, area.bbox, area.aoi_id, area.country)
    return aa.context(services.aggregates, load_coverage(services), aoi, area.start, area.end,
                      area.platforms)  # fmt: skip


@router.get("/hotspots")
def hotspots(
    services: ServicesDep,
    area: AreaDep,
    confidence: Annotated[list[Literal["low", "nominal", "high"]] | None, Query()] = None,
    daynight: Annotated[list[Literal["D", "N"]] | None, Query()] = None,
    include_source: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> dict:
    """Paginated detections (NRT superseded by SP per platform-day)."""
    ctx = _ctx(services, area)
    return to_jsonable(
        aa.hotspot_page(
            ctx,
            services.processed,
            page=page,
            page_size=page_size,
            confidence=confidence,
            day_night=daynight,
            include_source=include_source,
        )  # fmt: skip
    )


@router.get("/hotspots/summary")
def hotspots_summary(services: ServicesDep, area: AreaDep) -> dict:
    return to_jsonable(aa.summary(_ctx(services, area), services.processed))


@router.get("/calendar")
def calendar(
    services: ServicesDep,
    area: AreaDep,
    metric: Metric = "detections",
    min_history_years: Annotated[int, Query(ge=1, le=30)] = DEFAULT_MIN_HISTORY_YEARS,
) -> dict:
    """Years × months per platform; states value / zero / partial / uncovered / missing."""
    table = aa.calendar_table(_ctx(services, area), metric, min_history_years)
    return to_jsonable({"metric": metric, "cells": table})


@router.get("/calendar/harmonized")
def harmonized_calendar(
    services: ServicesDep,
    area: AreaDep,
    reference: Literal["modis", "viirs"] = "modis",
    metric: Metric = "detections",
    min_history_years: Annotated[int, Query(ge=1, le=30)] = DEFAULT_MIN_HISTORY_YEARS,
) -> dict:
    """EXPERIMENTAL: one MODIS–VIIRS calendar in a reference sensor's units, with the
    conversion fits (factor, validation error) that produced it."""
    result = aa.harmonized_calendar(_ctx(services, area), reference, metric, min_history_years)
    return to_jsonable(result)


@router.get("/analytics/monthly")
def monthly(services: ServicesDep, area: AreaDep) -> dict:
    return to_jsonable({"months": aa.series(_ctx(services, area))})


@router.get("/analytics/yearly")
def yearly(services: ServicesDep, area: AreaDep, metric: Metric = "detections") -> dict:
    return to_jsonable({"metric": metric, "years": aa.yearly_table(_ctx(services, area), metric)})


@router.get("/analytics/anomalies")
def anomalies(
    services: ServicesDep,
    area: AreaDep,
    metric: Metric = "detections",
    min_history_years: Annotated[int, Query(ge=1, le=30)] = DEFAULT_MIN_HISTORY_YEARS,
    target: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> dict:
    """EXPERIMENTAL: modified z per platform vs its own history, and the HAI."""
    if target:
        month = int(target[5:])
        if not 1 <= month <= 12:
            raise HTTPException(400, "target month must be 01..12")
    return to_jsonable(aa.anomalies(_ctx(services, area), metric, min_history_years, target))


@router.get("/analytics/sensor-comparison")
def sensor_comparison(
    services: ServicesDep,
    area: AreaDep,
    metric: Metric = "detections",
    tolerance_minutes: Annotated[float, Query(gt=0, le=180)] = 15.0,
) -> dict:
    """EXPERIMENTAL: MODIS–VIIRS monthly calibration and detection matching."""
    ctx = _ctx(services, area)
    return to_jsonable(
        aa.sensor_comparison(
            ctx, services.processed, metric, tolerance_minutes, services.settings.grid_resolution_m
        )  # fmt: skip
    )
