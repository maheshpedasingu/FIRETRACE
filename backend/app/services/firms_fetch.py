"""Download FIRMS Area API windows and import them (used by the REST API).

Same building blocks and rules as ``app.cli.fetch_firms``: availability check, date
windows of at most FIRMS_AREA_MAX_DAY_RANGE days, antimeridian split, byte-for-byte
downloads, import with coverage = requested bbox and dates for every platform of the
source (basis 'api_request').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.core.config import Settings
from app.ingestion.coverage import bbox_coverage
from app.ingestion.firms_api import FirmsApiClient, check_availability, download_area
from app.ingestion.firms_api_plan import BBox, DateWindow, SourceInfo
from app.ingestion.importer import ImportOptions, SessionFactory, import_file
from app.storage.observation_store import ObservationStore


@dataclass
class FetchOutcome:
    warnings: list[str] = field(default_factory=list)
    windows: list[dict] = field(default_factory=list)


def fetch_and_import(
    client: FirmsApiClient,
    settings: Settings,
    sources: list[SourceInfo],
    bbox: BBox | None,
    start: date,
    end: date,
    *,
    session_factory: SessionFactory,
    store: ObservationStore,
    check_available: bool = True,
) -> FetchOutcome:
    outcome = FetchOutcome()
    download_dir = Path(settings.raw_data_dir).parent / "downloads" / "firms_api"
    availability = client.data_availability() if check_available else None
    for source in sources:
        if availability is not None:
            whole = DateWindow(start, (end - start).days + 1)
            warning = check_availability(availability, source, whole)
            if warning:
                outcome.warnings.append(warning)
        for item in download_area(
            client, source, bbox, start, end, download_dir, settings.firms_area_max_day_range
        ):
            b = item.bbox
            options = ImportOptions(
                declared_platform=source.declared_platform,
                declared_status=source.status,
                coverage=[
                    bbox_coverage(
                        b.west,
                        b.south,
                        b.east,
                        b.north,
                        item.window.start,
                        item.window.end,
                        basis="api_request",
                    )  # fmt: skip
                ],
                coverage_platforms=source.platforms,
                chunk_rows=settings.ingest_chunk_rows,
                tile_degrees=settings.partition_tile_degrees,
            )
            result = import_file(
                item.path,
                session_factory=session_factory,
                store=store,
                raw_dir=Path(settings.raw_data_dir),
                options=options,
            )
            outcome.windows.append(
                {
                    "source": source.source,
                    "area": item.area,
                    "start": item.window.start,
                    "end": item.window.end,
                    "file": item.path.name,
                    "download_reused": item.reused,
                    "import_status": result.status,
                    "rows_valid": result.rows_valid,
                    "rows_invalid": result.rows_invalid,
                    "rows_already_stored": result.rows_already_stored,
                    "rows_written": result.rows_written,
                    "message": result.error,
                }
            )
    return outcome
