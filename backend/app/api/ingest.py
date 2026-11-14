"""Ingestion endpoints: file upload, FIRMS Area API fetch, import history."""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import ServicesDep, check_dates
from app.api.serialize import to_jsonable
from app.api.system import TransportDep
from app.database.models import IngestionRun, SourceFile
from app.ingestion.coverage import bbox_coverage, country_coverage
from app.ingestion.firms_api import FirmsApiError
from app.ingestion.firms_api_plan import BBox, parse_source
from app.ingestion.firms_csv import FirmsFormatError
from app.ingestion.firms_schema import Platform, ProcessingStatus
from app.ingestion.importer import ImportOptions, import_file, recover_interrupted_runs
from app.services.firms_fetch import fetch_and_import

router = APIRouter(prefix="/ingest", tags=["ingestion"])

MAX_UPLOAD_BYTES = 2 * 1024**3  # 2 GiB
MAX_API_DAYS = 31  # larger fetches: python -m app.cli.fetch_firms
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@router.post("/upload")
async def upload(
    services: ServicesDep,
    file: Annotated[UploadFile, File(description="FIRMS .csv or .zip")],
    platform: Annotated[str | None, Form()] = None,
    status: Annotated[str | None, Form()] = None,
    bbox: Annotated[str | None, Form(description="coverage west,south,east,north")] = None,
    country: Annotated[str | None, Form(description="coverage country")] = None,
    start: Annotated[date | None, Form(description="coverage start")] = None,
    end: Annotated[date | None, Form(description="coverage end")] = None,
) -> dict:
    """Import an uploaded FIRMS file. Coverage is only recorded if declared (or from
    archive file names); otherwise it is 'unknown' and zero activity is not inferred."""
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in (".csv", ".zip"):
        raise HTTPException(400, "only .csv and .zip FIRMS files are accepted")
    try:
        declared_platform = Platform(platform) if platform else None
        declared_status = ProcessingStatus(status) if status else None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    coverage = []
    if bbox or country:
        if not (start and end):
            raise HTTPException(400, "coverage bbox/country needs start and end dates")
        check_dates(start, end)
        try:
            if bbox:
                w, s, e, n = (float(v) for v in bbox.split(","))
                coverage.append(bbox_coverage(w, s, e, n, start, end))
            if country:
                coverage.append(country_coverage(country, start, end))
        except ValueError as exc:
            raise HTTPException(400, f"invalid coverage: {exc}") from exc

    inbox = services.raw.parent / "uploads"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f"{uuid.uuid4().hex[:12]}_{_SAFE_NAME.sub('_', name)}"
    tmp = target.with_suffix(target.suffix + ".partial")
    size = 0
    with tmp.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                handle.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "file larger than 2 GiB; use the import command")
            handle.write(chunk)
    os.replace(tmp, target)

    await run_in_threadpool(recover_interrupted_runs, services.sessions, services.store)
    options = ImportOptions(
        declared_platform=declared_platform,
        declared_status=declared_status,
        coverage=coverage,
        chunk_rows=services.settings.ingest_chunk_rows,
        tile_degrees=services.settings.partition_tile_degrees,
    )
    try:
        result = await run_in_threadpool(
            import_file, target, session_factory=services.sessions, store=services.store,
            raw_dir=services.raw, options=options, source_name=name,
        )  # fmt: skip
    except FirmsFormatError as exc:
        raise HTTPException(422, f"not a valid FIRMS file: {exc}") from exc
    return to_jsonable(result.__dict__ | {"bytes": size})


class FirmsRequest(BaseModel):
    sources: list[str] = Field(min_length=1, examples=[["VIIRS_NOAA20_NRT"]])
    bbox: str | None = Field(None, description="west,south,east,north; omit with world=true")
    world: bool = False
    start: date
    end: date
    check_availability: bool = True


@router.post("/firms")
def firms(request: FirmsRequest, services: ServicesDep, transport: TransportDep) -> dict:
    """Fetch FIRMS Area API data (≤ 31 days per call) and import it with api_request
    coverage. The MAP_KEY is used only on the server."""
    from app.cli.fetch_firms import make_client

    check_dates(request.start, request.end, MAX_API_DAYS)
    if request.end > datetime.now(UTC).date():
        raise HTTPException(400, "end date is in the future")
    if bool(request.bbox) == request.world:
        raise HTTPException(400, "give either bbox or world=true")
    try:
        sources = [parse_source(s) for s in request.sources]
        bbox = BBox.parse(request.bbox) if request.bbox else None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not services.settings.firms_map_key_configured:
        raise HTTPException(503, "FIRMS_MAP_KEY is not configured on the server")
    try:
        with make_client(services.settings, transport) as client:
            recover_interrupted_runs(services.sessions, services.store)
            outcome = fetch_and_import(
                client, services.settings, sources, bbox, request.start, request.end,
                session_factory=services.sessions, store=services.store,
                check_available=request.check_availability,
            )  # fmt: skip
    except FirmsApiError as exc:
        raise HTTPException(502, str(exc)) from exc
    return to_jsonable({"warnings": outcome.warnings, "windows": outcome.windows})


@router.get("/history")
def history(
    services: ServicesDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    with services.sessions() as session:
        total = session.scalar(select(func.count()).select_from(IngestionRun))
        rows = session.execute(
            select(IngestionRun, SourceFile)
            .join(SourceFile, IngestionRun.source_file_id == SourceFile.id)
            .order_by(IngestionRun.started_utc.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [
            {
                "run_id": run.id,
                "status": run.status,
                "file": source.original_name,
                "sha256": source.sha256,
                "started_utc": run.started_utc,
                "finished_utc": run.finished_utc,
                "declared_platform": run.declared_platform,
                "declared_status": run.declared_status,
                "rows_read": run.rows_read,
                "rows_valid": run.rows_valid,
                "rows_invalid": run.rows_invalid,
                "rows_duplicate_in_file": run.rows_duplicate_in_file,
                "rows_already_stored": run.rows_already_stored,
                "rows_written": run.rows_written,
                "error": run.error,
            }
            for run, source in rows
        ]
    return to_jsonable({"total": total, "page": page, "page_size": page_size, "items": items})
