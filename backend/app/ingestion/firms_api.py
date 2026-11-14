"""HTTP client for the NASA FIRMS Area API and data-availability service.

- The MAP_KEY is read from backend settings only and is redacted from every error.
- Every request first takes tokens from a TransactionBudget (one per requested day).
- Timeouts, transport errors, HTTP 429 and 5xx are retried with exponential backoff;
  other HTTP errors fail immediately.
- A response is accepted only if it looks like a FIRMS CSV (header with latitude and
  acq_date). An empty body is an error, never "zero detections".
- Downloaded responses are saved byte-for-byte; existing files are reused, so an
  interrupted download resumes where it stopped.
"""

from __future__ import annotations

import csv
import io
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from app.ingestion.firms_api_plan import (
    WORLD,
    BBox,
    DateWindow,
    SourceInfo,
    TransactionBudget,
    area_filename,
    plan_windows,
    redact,
)


class FirmsApiError(RuntimeError):
    """FIRMS request failed or returned something that is not FIRMS CSV data."""


@dataclass(frozen=True)
class DownloadedWindow:
    path: Path
    source: SourceInfo
    area: str  # bbox parameter or "world"
    bbox: BBox  # the area as a bbox ("world" = -180,-90,180,90)
    window: DateWindow
    reused: bool


class FirmsApiClient:
    def __init__(
        self,
        map_key: str,
        *,
        base_url: str,
        timeout: float,
        max_retries: int,
        budget: TransactionBudget,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        backoff_seconds: float = 2.0,
    ) -> None:
        if not map_key:
            raise FirmsApiError("FIRMS_MAP_KEY is not configured in backend/.env")
        self._key = map_key
        self._budget = budget
        self._retries = max_retries
        self._sleep = sleep
        self._backoff = backoff_seconds
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FirmsApiClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, transactions: int) -> bytes:
        last_error = "no attempt made"
        for attempt in range(self._retries + 1):
            self._budget.acquire(transactions)
            try:
                response = self._http.get(path)
            except httpx.TransportError as exc:  # timeouts, connection errors
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                elif response.status_code >= 400:
                    raise FirmsApiError(
                        redact(
                            f"FIRMS returned HTTP {response.status_code}: "
                            f"{response.text[:300].strip()}",
                            self._key,
                        )
                    )
                else:
                    return response.content
            if attempt < self._retries:
                self._sleep(self._backoff * 2**attempt)
        raise FirmsApiError(
            redact(
                f"FIRMS request failed after {self._retries + 1} attempts: {last_error}", self._key
            )
        )

    def area_csv(self, source: SourceInfo, area: str, window: DateWindow) -> bytes:
        path = (
            f"/area/csv/{self._key}/{source.source}/{area}/{window.days}/{window.start.isoformat()}"
        )
        body = self._get(path, transactions=window.days)
        _require_firms_csv(body, self._key)
        return body

    def data_availability(self, sensor: str = "ALL") -> list[dict[str, str]]:
        body = self._get(f"/data_availability/csv/{self._key}/{sensor}", transactions=1)
        text = body.decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise FirmsApiError(
                redact(f"Unexpected availability response: {text[:200]!r}", self._key)
            )
        return [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in rows]


def _require_firms_csv(body: bytes, key: str) -> None:
    text = body.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise FirmsApiError(
            "FIRMS returned an empty response. This is not treated as zero detections."
        )
    header = text.splitlines()[0].lower()
    if "latitude" not in header or "acq_date" not in header:
        raise FirmsApiError(redact(f"Response is not FIRMS CSV: {text[:200]!r}", key))


def check_availability(
    rows: list[dict[str, str]], source: SourceInfo, window: DateWindow
) -> str | None:
    """Compare a window with the availability table. Returns a warning, or None.

    The table's column names are not fixed here: a row naming the source plus columns
    containing 'min' and 'max' dates are looked for. If they cannot be found, a warning
    is returned instead of guessing. A window outside the reported range is an error.
    """
    for row in rows:
        if source.source.lower() not in (v.lower() for v in row.values()):
            continue
        min_col = next((k for k in row if "min" in k), None)
        max_col = next((k for k in row if "max" in k), None)
        if not (min_col and max_col):
            break
        try:
            first, last = date.fromisoformat(row[min_col]), date.fromisoformat(row[max_col])
        except ValueError:
            break
        if window.start < first or window.end > last:
            raise FirmsApiError(
                f"{source.source} is available {first}..{last}; "
                f"requested {window.start}..{window.end}"
            )
        return None
    return f"Availability of {source.source} could not be confirmed from the FIRMS table."


def download_area(
    client: FirmsApiClient,
    source: SourceInfo,
    bbox: BBox | None,
    start: date,
    end: date,
    out_dir: Path,
    max_day_range: int,
) -> list[DownloadedWindow]:
    """Download source x area x date windows. ``bbox=None`` means the whole world."""
    out_dir.mkdir(parents=True, exist_ok=True)
    areas = (
        [(WORLD, BBox(-180, -90, 180, 90))]
        if bbox is None
        else [(part.area_param(), part) for part in bbox.split_antimeridian()]
    )
    results: list[DownloadedWindow] = []
    for window in plan_windows(start, end, max_day_range):
        for area, area_bbox in areas:
            path = out_dir / area_filename(source.source, area, window)
            reused = path.exists()
            if not reused:
                body = client.area_csv(source, area, window)
                tmp = path.with_suffix(".csv.partial")
                tmp.write_bytes(body)
                os.replace(tmp, path)
            results.append(DownloadedWindow(path, source, area, area_bbox, window, reused))
    return results
