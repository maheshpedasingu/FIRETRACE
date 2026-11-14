"""Shared API dependencies: storage services, area and date parameters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.series import AreaBBox
from app.core.config import Settings, get_settings
from app.database.models import CoverageRecord, SavedAOI
from app.database.session import init_db, make_engine, make_session_factory
from app.harmonization.aggregate_store import AggregateStore
from app.ingestion.firms_schema import Platform
from app.storage.observation_store import ObservationStore

PLATFORMS = [p.value for p in Platform]


@dataclass
class Services:
    settings: Settings
    sessions: sessionmaker[Session]
    store: ObservationStore
    aggregates: AggregateStore
    processed: Path
    raw: Path


@lru_cache(maxsize=8)
def _services(database_url: str, processed: str, raw: str, resolution: int) -> Services:
    engine = make_engine(database_url)
    init_db(engine)
    return Services(
        settings=None,  # filled per request
        sessions=make_session_factory(engine),
        store=ObservationStore(Path(processed)),
        aggregates=AggregateStore(Path(processed), resolution),
        processed=Path(processed),
        raw=Path(raw),
    )


def get_services(settings: Annotated[Settings, Depends(get_settings)]) -> Services:
    base = _services(
        settings.database_url,
        settings.processed_data_dir,
        settings.raw_data_dir,
        settings.grid_resolution_m,
    )
    return Services(settings, base.sessions, base.store, base.aggregates, base.processed,
                    base.raw)  # fmt: skip


ServicesDep = Annotated[Services, Depends(get_services)]


def load_coverage(services: Services) -> list[dict]:
    with services.sessions() as session:
        rows = session.scalars(select(CoverageRecord)).all()
        return [
            {
                "platform": r.platform,
                "processing_status": r.processing_status,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "extent_type": r.extent_type,
                "extent_value": r.extent_value,
                "basis": r.basis,
            }
            for r in rows
        ]


def parse_bbox(text: str) -> AreaBBox:
    try:
        west, south, east, north = (float(v) for v in text.split(","))
    except ValueError as exc:
        raise HTTPException(400, "bbox must be 'west,south,east,north' numbers") from exc
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "bbox out of range: lon -180..180, lat -90..90, south < north")
    return AreaBBox(west, south, east, north)


def resolve_area(
    services: Services, bbox: str | None, aoi_id: int | None, country: str | None = None
) -> AreaBBox:
    """An area from a bbox string or a saved AOI id (exactly one)."""
    if (bbox is None) == (aoi_id is None):
        raise HTTPException(400, "give exactly one of 'bbox' or 'aoi_id'")
    if bbox is not None:
        area = parse_bbox(bbox)
        return AreaBBox(area.west, area.south, area.east, area.north, country=country)
    with services.sessions() as session:
        saved = session.get(SavedAOI, aoi_id)
    if saved is None:
        raise HTTPException(404, f"AOI {aoi_id} not found")
    if saved.kind == "polygon":
        from app.geospatial.aoi import AreaPolygon

        return AreaPolygon.from_geojson(saved.geojson, country=country or saved.country)
    return AreaBBox(saved.west, saved.south, saved.east, saved.north,
                    country=country or saved.country)  # fmt: skip


def check_dates(start: date, end: date, max_days: int | None = None) -> None:
    if end < start:
        raise HTTPException(400, "end date is before start date")
    if max_days is not None and (end - start).days + 1 > max_days:
        raise HTTPException(400, f"date range longer than {max_days} days")


def check_platforms(platforms: list[str] | None) -> list[str]:
    if not platforms:
        return PLATFORMS
    unknown = sorted(set(platforms) - set(PLATFORMS))
    if unknown:
        raise HTTPException(400, f"unknown platform(s) {unknown}; expected {PLATFORMS}")
    return platforms


class AreaParams:
    """Common query parameters for area analytics."""

    def __init__(
        self,
        start: Annotated[date, Query(description="first day (UTC), YYYY-MM-DD")],
        end: Annotated[date, Query(description="last day (UTC), YYYY-MM-DD")],
        bbox: Annotated[str | None, Query(description="west,south,east,north")] = None,
        aoi_id: Annotated[int | None, Query(description="saved AOI id")] = None,
        country: Annotated[str | None, Query(description="country name if whole country")] = None,
        platform: Annotated[list[str] | None, Query(description="repeatable")] = None,
    ) -> None:
        check_dates(start, end)
        self.start, self.end = start, end
        self.bbox, self.aoi_id, self.country = bbox, aoi_id, country
        self.platforms = check_platforms(platform)
