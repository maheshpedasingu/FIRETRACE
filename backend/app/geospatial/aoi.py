"""Areas of interest from GeoJSON, validated with Shapely.

Accepted: GeoJSON Polygon or MultiPolygon (geometry, Feature, or single-feature
FeatureCollection) in WGS 84 longitude/latitude. Rules:
- coordinates within ±180 / ±90, at least a non-zero area, valid geometry (no
  self-intersections) — invalid input is rejected with the reason, never "fixed";
- polygons spanning more than 180° of longitude are rejected: an antimeridian-crossing
  area must be given as a bbox with west > east, or split into two polygons.

Analytics use the polygon's bounding box for coverage checks (coverage must contain the
whole bbox, which is conservative) and exact point-in-polygon tests for selection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

from app.analytics.series import AreaBBox


class AOIError(ValueError):
    pass


def _geometry(geojson: dict) -> dict:
    kind = geojson.get("type")
    if kind == "FeatureCollection":
        features = geojson.get("features") or []
        if len(features) != 1:
            raise AOIError("FeatureCollection must contain exactly one feature")
        return _geometry(features[0])
    if kind == "Feature":
        return geojson.get("geometry") or {}
    return geojson


def parse_polygon(geojson: dict | str):
    """Validated Shapely (Multi)Polygon from GeoJSON."""
    import shapely
    from shapely.geometry import shape

    if isinstance(geojson, str):
        try:
            geojson = json.loads(geojson)
        except json.JSONDecodeError as exc:
            raise AOIError(f"Invalid GeoJSON: {exc}") from exc
    geometry = _geometry(geojson)
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise AOIError("AOI geometry must be a GeoJSON Polygon or MultiPolygon")
    try:
        geom = shape(geometry)
    except Exception as exc:  # malformed coordinate arrays
        raise AOIError(f"Invalid polygon coordinates: {exc}") from exc
    west, south, east, north = geom.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise AOIError("Coordinates must be longitude -180..180 and latitude -90..90")
    if east - west > 180:
        raise AOIError(
            "Polygon spans more than 180° of longitude. For an area crossing the "
            "antimeridian use a bbox with west > east, or split it into two polygons."
        )
    if not geom.is_valid:
        raise AOIError(f"Invalid polygon: {shapely.is_valid_reason(geom)}")
    if geom.area <= 0:
        raise AOIError("Polygon has zero area")
    return geom


@dataclass(frozen=True)
class AreaPolygon(AreaBBox):
    """An AreaBBox that also holds an exact polygon for point selection."""

    geometry: object = field(default=None, compare=False, hash=False)

    @classmethod
    def from_geojson(cls, geojson: dict | str, country: str | None = None) -> AreaPolygon:
        geom = parse_polygon(geojson)
        west, south, east, north = geom.bounds
        return cls(west, south, east, north, country=country, geometry=geom)

    def contains_points(self, lat: pd.Series, lon: pd.Series) -> pd.Series:
        import shapely

        in_bbox = super().contains_points(lat, lon)
        result = pd.Series(False, index=lat.index)
        if in_bbox.any():
            sub_lat, sub_lon = lat[in_bbox], lon[in_bbox]
            inside = shapely.contains_xy(self.geometry, sub_lon.to_numpy(float),
                                         sub_lat.to_numpy(float))  # fmt: skip
            inside |= shapely.intersects_xy(self.geometry, sub_lon.to_numpy(float),
                                            sub_lat.to_numpy(float))  # fmt: skip
            result.loc[in_bbox[in_bbox].index] = inside
        return result

    def to_geojson(self) -> dict:
        import shapely

        return json.loads(shapely.to_geojson(self.geometry))
