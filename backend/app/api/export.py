"""Export endpoints: hotspot / calendar CSV and analytics report (JSON or Markdown)."""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.background import BackgroundTask

from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS
from app.analytics.report import build_report, to_markdown
from app.api.analytics import AreaDep, Metric, _ctx
from app.api.deps import ServicesDep
from app.api.serialize import to_jsonable
from app.exports.writers import export_hotspots, write_csv, write_provenance
from app.services import area_analysis as aa

router = APIRouter(prefix="/export", tags=["export"])


def _cleanup(*paths) -> BackgroundTask:
    def remove() -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    return BackgroundTask(remove)


@router.get("/csv")
def export_csv(
    services: ServicesDep,
    area: AreaDep,
    kind: Literal["hotspots", "calendar", "harmonized_calendar"] = "hotspots",
    confidence: Annotated[list[Literal["low", "nominal", "high"]] | None, Query()] = None,
    daynight: Annotated[list[Literal["D", "N"]] | None, Query()] = None,
    metric: Metric = "detections",
    reference: Literal["modis", "viirs"] = "modis",
    bundle: Annotated[bool, Query(description="zip with the provenance JSON")] = False,
):
    """CSV download. ``bundle=true`` returns a zip with the CSV and its provenance file."""
    ctx = _ctx(services, area)
    work = services.processed / "exports_tmp"
    work.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"firetrace_{kind}_{stamp}.csv"
    csv_path = work / f"{uuid.uuid4().hex[:8]}_{name}"
    details = {
        "area": {
            "bbox": [ctx.aoi.west, ctx.aoi.south, ctx.aoi.east, ctx.aoi.north],
            "country": ctx.aoi.country,
        },  # fmt: skip
        "period": {"start": ctx.start, "end": ctx.end},
        "platforms": ctx.platforms,
    }
    if kind == "hotspots":
        stats = export_hotspots(aa.iter_detections(ctx, services.processed), csv_path,
                                confidence=confidence, day_night=daynight)  # fmt: skip
        details |= {"kind": "filtered hotspot detections",
                    "filters": {"confidence": confidence, "day_night": daynight,
                                "nrt_superseded_by_sp": True}, **stats}  # fmt: skip
    elif kind == "calendar":
        write_csv(aa.calendar_table(ctx, metric, DEFAULT_MIN_HISTORY_YEARS), csv_path)
        details |= {"kind": "activity calendar (long format)", "metric": metric}
    else:
        result = aa.harmonized_calendar(ctx, reference, metric, DEFAULT_MIN_HISTORY_YEARS)
        write_csv(result["cells"], csv_path)
        details |= {
            "kind": "harmonized activity calendar (EXPERIMENTAL)",
            "metric": metric,
            "unit": result["unit"],
            "reference": result["reference_source"],
            "conversion_fits": result["fits"],
            "caveat": "Statistical bridge between sensors (constant factor per source, "
            "ratio of sums on training years, validated on held-out years); not a "
            "physical correction. Per-platform calendars remain the primary record.",
        }
    provenance = write_provenance(csv_path, details)
    if not bundle:
        return FileResponse(csv_path, media_type="text/csv", filename=name,
                            background=_cleanup(csv_path, provenance))  # fmt: skip
    zip_path = csv_path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(csv_path, name)
        zf.write(provenance, name + ".provenance.json")
    return FileResponse(zip_path, media_type="application/zip", filename=name[:-4] + ".zip",
                        background=_cleanup(csv_path, provenance, zip_path))  # fmt: skip


@router.get("/report")
def export_report(
    services: ServicesDep,
    area: AreaDep,
    metric: Metric = "detections",
    target: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    format: Literal["json", "md"] = "json",
):
    """EXPERIMENTAL anomaly / validation report for the area."""
    ctx = _ctx(services, area)
    series = aa.series(ctx)
    anomalies = aa.anomalies(ctx, metric, DEFAULT_MIN_HISTORY_YEARS, target)
    comparison = aa.sensor_comparison(ctx, services.processed, metric, 15.0,
                                      services.settings.grid_resolution_m)  # fmt: skip
    report = build_report(
        area={
            "bbox": [ctx.aoi.west, ctx.aoi.south, ctx.aoi.east, ctx.aoi.north],
            "country": ctx.aoi.country,
        },  # fmt: skip
        period={"start": str(ctx.start), "end": str(ctx.end), "target": anomalies["target"]},
        metric=metric,
        series=series,
        target=pd.DataFrame(anomalies["assessments"]),
        hai=anomalies["harmonized_index"],
        calibrations=comparison["calibration"],
        matching=comparison["matching"],
        settings={
            "grid_resolution_m": services.settings.grid_resolution_m,
            "min_history_years": DEFAULT_MIN_HISTORY_YEARS,
            "tolerance_minutes": 15.0,
        },  # fmt: skip
    )
    if format == "md":
        return PlainTextResponse(to_markdown(report), media_type="text/markdown")
    return JSONResponse(json.loads(json.dumps(to_jsonable(report), default=str)))
