"""Pure planning helpers for FIRMS Area API downloads (no network code here).

Area API request shape (FIRMS API page):
  /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north | world}/{DAY_RANGE}/{DATE}
  returns data for DATE .. DATE + DAY_RANGE - 1.
The maximum DAY_RANGE is a setting (FIRMS_AREA_MAX_DAY_RANGE) because published
values differ (1-10 on NASA's page, 1-5 in third-party descriptions).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.ingestion.firms_schema import Platform, ProcessingStatus

WORLD = "world"


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not (-180 <= self.west <= 180 and -180 <= self.east <= 180):
            raise ValueError("bbox longitudes must be within -180..180")
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError("bbox latitudes must be within -90..90 with south < north")

    @classmethod
    def parse(cls, text: str) -> BBox:
        parts = [float(v) for v in text.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must be 'west,south,east,north'")
        return cls(*parts)

    def area_param(self) -> str:
        return ",".join(_fmt(v) for v in (self.west, self.south, self.east, self.north))

    def split_antimeridian(self) -> list[BBox]:
        """A bbox with west > east crosses 180°; FIRMS gets two requests instead."""
        if self.west <= self.east:
            return [self]
        return [
            BBox(self.west, self.south, 180.0, self.north),
            BBox(-180.0, self.south, self.east, self.north),
        ]


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))


@dataclass(frozen=True)
class DateWindow:
    start: date
    days: int

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days - 1)


def plan_windows(start: date, end: date, max_day_range: int) -> list[DateWindow]:
    """Split the inclusive range start..end into windows of at most max_day_range days."""
    if end < start:
        raise ValueError("end date is before start date")
    if max_day_range < 1:
        raise ValueError("max_day_range must be at least 1")
    windows, cursor = [], start
    while cursor <= end:
        days = min(max_day_range, (end - cursor).days + 1)
        windows.append(DateWindow(cursor, days))
        cursor += timedelta(days=days)
    return windows


@dataclass(frozen=True)
class SourceInfo:
    source: str
    platforms: tuple[Platform, ...]
    status: ProcessingStatus

    @property
    def declared_platform(self) -> Platform | None:
        return self.platforms[0] if len(self.platforms) == 1 else None


_SOURCE_RE = re.compile(r"^(?P<family>MODIS|VIIRS_SNPP|VIIRS_NOAA20|VIIRS_NOAA21)_(?P<st>NRT|SP)$")
_FAMILY_PLATFORMS = {
    "MODIS": (Platform.TERRA, Platform.AQUA),
    "VIIRS_SNPP": (Platform.SUOMI_NPP,),
    "VIIRS_NOAA20": (Platform.NOAA_20,),
    "VIIRS_NOAA21": (Platform.NOAA_21,),
}


def parse_source(source: str) -> SourceInfo:
    """Map a FIRMS SOURCE id (e.g. VIIRS_NOAA20_NRT) to platforms and processing status.

    MODIS sources include both Terra and Aqua; the row's satellite code tells them
    apart. Unknown source ids are rejected rather than guessed.
    """
    match = _SOURCE_RE.match(source.strip().upper())
    if not match:
        raise ValueError(
            f"Unsupported FIRMS source {source!r}; expected MODIS_/VIIRS_SNPP_/"
            "VIIRS_NOAA20_/VIIRS_NOAA21_ followed by NRT or SP"
        )
    return SourceInfo(
        match.group(0),
        _FAMILY_PLATFORMS[match["family"]],
        ProcessingStatus(match["st"]),
    )


class TransactionBudget:
    """Token bucket: at most ``limit`` transactions per ``window_seconds``.

    Each Area API day counts as one transaction (multi-day requests are reported to
    count as several), so a request for N days acquires N tokens.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("limit and window must be positive")
        self.limit, self.window = limit, float(window_seconds)
        self._clock, self._sleep = clock, sleep
        self._tokens = float(limit)
        self._updated = clock()

    def _refill(self) -> None:
        now = self._clock()
        rate = self.limit / self.window
        self._tokens = min(self.limit, self._tokens + (now - self._updated) * rate)
        self._updated = now

    def acquire(self, n: int = 1) -> float:
        """Block until n tokens are available. Returns seconds waited."""
        if n > self.limit:
            raise ValueError(f"request needs {n} transactions; budget limit is {self.limit}")
        waited = 0.0
        self._refill()
        while self._tokens < n:
            delay = (n - self._tokens) * self.window / self.limit
            self._sleep(delay)
            waited += delay
            self._refill()
        self._tokens -= n
        return waited


def redact(text: str, secret: str | None) -> str:
    """Remove a secret (the MAP_KEY) from any text that may be logged or shown."""
    if secret:
        text = text.replace(secret, "***MAP_KEY***")
    return text


def area_filename(source: str, area: str, window: DateWindow) -> str:
    safe_area = area.replace(",", "_").replace("-", "m").replace(".", "p")
    return f"firms_area_{source}_{safe_area}_{window.start.isoformat()}_{window.days}d.csv"
