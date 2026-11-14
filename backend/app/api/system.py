"""System endpoints: sensors and data availability (FIRMS + locally imported)."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import ServicesDep
from app.api.serialize import to_jsonable
from app.database.models import CoverageRecord, IngestionRun, RunStatus
from app.ingestion.firms_api import FirmsApiError
from app.ingestion.firms_schema import PLATFORM_PRODUCT, PLATFORM_SENSOR, Platform

router = APIRouter(tags=["system"])

NOMINAL_PIXEL = {"MODIS": "~1 km at nadir", "VIIRS": "375 m at nadir (I-band)"}
FIRMS_SOURCES = {
    Platform.TERRA: ["MODIS_NRT", "MODIS_SP"],
    Platform.AQUA: ["MODIS_NRT", "MODIS_SP"],
    Platform.SUOMI_NPP: ["VIIRS_SNPP_NRT", "VIIRS_SNPP_SP"],
    Platform.NOAA_20: ["VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP"],
    Platform.NOAA_21: ["VIIRS_NOAA21_NRT", "VIIRS_NOAA21_SP"],
}


def get_firms_transport() -> httpx.BaseTransport | None:
    """Overridable in tests (simulated FIRMS); None means the real network."""
    return None


TransportDep = Annotated[httpx.BaseTransport | None, Depends(get_firms_transport)]


@router.get("/sensors")
def sensors() -> list[dict]:
    """Supported satellites. MODIS and VIIRS are kept separate everywhere."""
    return [
        {
            "platform": p.value,
            "sensor": PLATFORM_SENSOR[p].value,
            "product": PLATFORM_PRODUCT[p],
            "collection": "6.1" if PLATFORM_SENSOR[p].value == "MODIS" else "2",
            "nominal_pixel": NOMINAL_PIXEL[PLATFORM_SENSOR[p].value],
            "firms_sources": FIRMS_SOURCES[p],
        }
        for p in Platform
    ]


@router.get("/data/availability")
def availability(services: ServicesDep, transport: TransportDep) -> dict:
    """What FIRMS offers (live, if a MAP_KEY is configured) and what has been imported."""
    from app.cli.fetch_firms import make_client

    firms: dict = {"available": False}
    if services.settings.firms_map_key_configured:
        try:
            with make_client(services.settings, transport) as client:
                firms = {"available": True, "products": client.data_availability()}
        except FirmsApiError as exc:
            firms = {"available": False, "error": str(exc)}
    else:
        firms["error"] = "FIRMS_MAP_KEY not configured on the server"

    with services.sessions() as session:
        rows = session.execute(
            select(
                CoverageRecord.platform,
                CoverageRecord.processing_status,
                CoverageRecord.extent_type,
                func.min(CoverageRecord.start_date),
                func.max(CoverageRecord.end_date),
                func.count(),
            ).group_by(
                CoverageRecord.platform,
                CoverageRecord.processing_status,
                CoverageRecord.extent_type,
            )  # fmt: skip
        ).all()
        last_run = session.scalar(
            select(func.max(IngestionRun.finished_utc)).where(
                IngestionRun.status == RunStatus.COMPLETED
            )
        )
    local = [
        {"platform": p, "processing_status": s, "extent_type": e, "first_date": a,
         "last_date": b, "coverage_records": n}
        for p, s, e, a, b, n in rows
    ]  # fmt: skip
    return to_jsonable(
        {
            "firms": firms,
            "imported_coverage": local,
            "latest_completed_import_utc": last_run,
            "note": "Imported coverage lists what was requested and imported; it is not "
            "global or historical coverage unless those areas and dates were imported.",
        }
    )
