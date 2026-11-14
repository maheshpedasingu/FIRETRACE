"""Coverage claims for an import: where and when zero detections mean zero activity.

Only the request that produced a file defines its coverage. The spread of the
detections inside a file never does: an empty area inside a file's bounding box may
simply not have been requested.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath


@dataclass(frozen=True)
class CoverageSpec:
    extent_type: str  # "bbox" | "country" | "unknown"
    extent_value: str | None
    start_date: date | None
    end_date: date | None
    basis: str  # "api_request" | "user_declared" | "archive_filename" | "none"
    note: str | None = None


def bbox_coverage(
    west: float,
    south: float,
    east: float,
    north: float,
    start: date,
    end: date,
    basis: str = "user_declared",
) -> CoverageSpec:
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west,south,east,north within ±180/±90 and south < north")
    if end < start:
        raise ValueError("coverage end date is before start date")
    note = "crosses the antimeridian (west > east)" if west > east else None
    value = json.dumps({"west": west, "south": south, "east": east, "north": north})
    return CoverageSpec("bbox", value, start, end, basis, note)


def country_coverage(
    country: str, start: date, end: date, basis: str = "user_declared"
) -> CoverageSpec:
    if end < start:
        raise ValueError("coverage end date is before start date")
    return CoverageSpec("country", country.strip(), start, end, basis)


UNKNOWN_COVERAGE = CoverageSpec(
    "unknown",
    None,
    None,
    None,
    "none",
    "Request extent unknown: zero activity must not be inferred from this import.",
)

# FIRMS yearly per-country archive member, e.g. "modis/2020/modis_2020_Honduras.csv".
_ARCHIVE_NAME = re.compile(
    r"^(?P<sensor>modis|viirs[^_]*)_(?P<year>\d{4})_(?P<country>.+)\.csv$", re.IGNORECASE
)


def coverage_from_archive_name(member_name: str) -> CoverageSpec | None:
    """Country/year coverage parsed from a yearly per-country archive file name.

    The calendar year is the claimed period. Whether the file is complete for that
    year (e.g. the current, unfinished year) is not verified, and the note says so.
    """
    match = _ARCHIVE_NAME.match(PurePosixPath(member_name).name)
    if not match:
        return None
    year = int(match["year"])
    if not 2000 <= year <= 2100:
        return None
    country = match["country"].replace("_", " ").strip()
    return CoverageSpec(
        "country",
        country,
        date(year, 1, 1),
        date(year, 12, 31),
        "archive_filename",
        "Country and year parsed from the FIRMS archive file name; "
        "completeness for the year not verified.",
    )
