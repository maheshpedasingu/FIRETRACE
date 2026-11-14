"""AOI geometry tests (Shapely). Coordinates are SYNTHETIC TEST DATA."""

import pandas as pd
import pytest

pytest.importorskip("shapely")

from app.geospatial.aoi import AOIError, AreaPolygon, parse_polygon  # noqa: E402

TRIANGLE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [0, 10], [0, 0]]]}


def test_polygon_selection_is_exact_not_bbox():
    area = AreaPolygon.from_geojson(TRIANGLE)
    lat = pd.Series([1.0, 9.0, 5.0, 0.0])
    lon = pd.Series([1.0, 9.0, 5.0, 0.0])  # (9,9) is inside the bbox but outside the triangle
    assert area.contains_points(lat, lon).tolist() == [True, False, True, True]
    assert (area.west, area.south, area.east, area.north) == (0, 0, 10, 10)


@pytest.mark.parametrize(
    "geojson",
    [
        {"type": "Feature", "geometry": TRIANGLE, "properties": {}},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": TRIANGLE}]},
    ],
)
def test_feature_wrappers_accepted(geojson):
    assert parse_polygon(geojson).area == pytest.approx(50)


@pytest.mark.parametrize(
    ("geojson", "message"),
    [
        ({"type": "Point", "coordinates": [0, 0]}, "Polygon or MultiPolygon"),
        (
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
            "Invalid polygon",
        ),
        ({"type": "Polygon", "coordinates": [[[0, 0], [200, 0], [0, 5], [0, 0]]]}, "Coordinates"),
        ({"type": "FeatureCollection", "features": []}, "exactly one"),
    ],
)
def test_invalid_geometry_rejected_with_reason(geojson, message):
    with pytest.raises(AOIError, match=message):
        parse_polygon(geojson)
