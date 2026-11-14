"""Saved areas of interest (GeoJSON polygons or bboxes)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import ServicesDep, parse_bbox
from app.api.serialize import to_jsonable
from app.database.models import SavedAOI
from app.geospatial.aoi import AOIError, parse_polygon

router = APIRouter(prefix="/aoi", tags=["areas of interest"])


class AOICreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    bbox: str | None = Field(None, description="west,south,east,north (west > east crosses 180°)")
    geojson: dict | None = Field(None, description="GeoJSON Polygon / MultiPolygon / Feature")
    country: str | None = Field(None, description="set if the area is a whole country")


def _out(row: SavedAOI) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "bbox": [row.west, row.south, row.east, row.north],
        "geojson": json.loads(row.geojson) if row.geojson else None,
        "country": row.country,
        "created_utc": row.created_utc,
    }


@router.get("")
def list_aois(services: ServicesDep) -> list[dict]:
    with services.sessions() as session:
        rows = session.scalars(select(SavedAOI).order_by(SavedAOI.name)).all()
        return to_jsonable([_out(r) for r in rows])


@router.post("", status_code=201)
def create_aoi(body: AOICreate, services: ServicesDep) -> dict:
    if (body.bbox is None) == (body.geojson is None):
        raise HTTPException(400, "give exactly one of 'bbox' or 'geojson'")
    if body.bbox is not None:
        area = parse_bbox(body.bbox)
        kind, geojson = "bbox", None
        west, south, east, north = area.west, area.south, area.east, area.north
    else:
        try:
            geom = parse_polygon(body.geojson)
        except AOIError as exc:
            raise HTTPException(400, str(exc)) from exc
        import shapely

        kind, geojson = "polygon", shapely.to_geojson(geom)
        west, south, east, north = geom.bounds
    with services.sessions() as session:
        if session.scalar(select(SavedAOI).where(SavedAOI.name == body.name)):
            raise HTTPException(409, f"an AOI named {body.name!r} already exists")
        row = SavedAOI(name=body.name, kind=kind, west=west, south=south, east=east,
                       north=north, geojson=geojson, country=body.country,
                       created_utc=datetime.now(UTC))  # fmt: skip
        session.add(row)
        session.commit()
        return to_jsonable(_out(row))
