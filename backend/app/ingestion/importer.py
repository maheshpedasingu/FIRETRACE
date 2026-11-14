"""Import FIRMS files into the observation store with full provenance.

For one source file:
1. SHA-256 the file. If an earlier import of the same checksum completed, record a
   ``skipped_duplicate_file`` run and change nothing else.
2. Copy the original, unchanged, into the raw store.
3. Stream it through the FIRMS parser in chunks. Invalid rows go to
   ``invalid_records`` with reasons. Valid rows are de-duplicated within the file and
   against what is already stored (per partition), then staged.
4. Commit the staged files into the store, then record coverage and mark the run
   ``completed``. On any error the staged files are deleted and the run is ``failed``.

Memory use is bounded by the chunk size, the write buffer (``flush_rows`` new rows,
default 500,000) and the observation_ids of one file and of the partitions it touches.
Buffering writes each partition once per flush instead of once per chunk; with data
spread over many partitions this is the difference between a few thousand files and
hundreds of thousands (found by the synthetic benchmark, 2026-11-14).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.database.models import (
    CoverageRecord,
    IngestionRun,
    InvalidRecord,
    RunStatus,
    SourceFile,
)
from app.ingestion.coverage import UNKNOWN_COVERAGE, CoverageSpec, coverage_from_archive_name
from app.ingestion.firms_csv import DEFAULT_CHUNK_ROWS, SourceContext, iter_firms_file
from app.ingestion.firms_schema import Platform, ProcessingStatus
from app.ingestion.provenance import sha256_file, store_raw_file
from app.storage.observation_store import ObservationStore
from app.storage.partitioning import PartitionKey, iter_partitions

SessionFactory = Callable[[], Session]
DEFAULT_FLUSH_ROWS = 500_000


@dataclass
class ImportOptions:
    declared_platform: Platform | None = None
    declared_status: ProcessingStatus | None = None
    coverage: list[CoverageSpec] = field(default_factory=list)
    # Platforms the request covered even if they produced no rows (e.g. MODIS_NRT
    # covers Terra and Aqua). Defaults to the declared platform, if any.
    coverage_platforms: tuple[Platform, ...] = ()
    chunk_rows: int = DEFAULT_CHUNK_ROWS
    tile_degrees: int = 10
    # New rows are buffered per partition and written once this many rows are buffered
    # (and at the end of the file). Fewer, larger Parquet files; memory stays bounded.
    flush_rows: int = DEFAULT_FLUSH_ROWS


@dataclass
class ImportResult:
    run_id: str
    status: str
    source_file: str
    sha256: str
    rows_read: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    rows_duplicate_in_file: int = 0
    rows_already_stored: int = 0
    rows_written: int = 0
    files_written: int = 0
    error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _coverage_rows(
    run_id: str,
    options: ImportOptions,
    archive_specs: dict[str, CoverageSpec],
    observed: set[tuple[str, str]],
) -> list[CoverageRecord]:
    """Coverage rows: declared specs, else archive file names, else 'unknown'.

    A coverage row is written for each platform/processing-status actually seen, plus
    each platform the request covered (``coverage_platforms``, else the declared
    platform), so a covered platform with zero detections still counts as covered.
    Platforms neither seen nor covered by the request are not claimed.
    """
    specs = options.coverage or list(archive_specs.values()) or [UNKNOWN_COVERAGE]
    combos = set(observed)
    platforms = options.coverage_platforms or (
        (options.declared_platform,) if options.declared_platform is not None else ()
    )
    status = (options.declared_status or ProcessingStatus.UNKNOWN).value
    for platform in platforms:
        if not any(p == platform.value for p, _ in combos):
            combos.add((platform.value, status))
    if not combos:
        combos = {(None, None)}  # nothing seen, nothing declared: record extent only
    rows = []
    for spec in specs:
        for platform, status in sorted(combos, key=lambda c: (str(c[0]), str(c[1]))):
            rows.append(
                CoverageRecord(
                    run_id=run_id,
                    platform=platform,
                    processing_status=status,
                    start_date=spec.start_date,
                    end_date=spec.end_date,
                    extent_type=spec.extent_type,
                    extent_value=spec.extent_value,
                    basis=spec.basis,
                    note=spec.note,
                )
            )
    return rows


def import_file(
    path: Path,
    *,
    session_factory: SessionFactory,
    store: ObservationStore,
    raw_dir: Path,
    options: ImportOptions | None = None,
    source_name: str | None = None,
) -> ImportResult:
    """Import one file. ``source_name`` is the user's original file name when ``path`` is a
    renamed copy (e.g. an upload); it is what provenance records show."""
    options = options or ImportOptions()
    path = Path(path)
    name = source_name or path.name
    checksum = sha256_file(path)
    run_id = uuid.uuid4().hex
    result = ImportResult(run_id, RunStatus.RUNNING, name, checksum)

    with session_factory() as session:
        source = session.scalar(select(SourceFile).where(SourceFile.sha256 == checksum))
        already_done = source is not None and any(
            run.status == RunStatus.COMPLETED for run in source.runs
        )
        if source is None:
            stored = store_raw_file(path, raw_dir, checksum, name)
            source = SourceFile(
                sha256=checksum,
                original_name=name,
                stored_path=str(stored),
                size_bytes=path.stat().st_size,
                first_seen_utc=_now(),
            )
            session.add(source)
            session.flush()
        run = IngestionRun(
            id=run_id,
            source_file_id=source.id,
            status=RunStatus.SKIPPED_DUPLICATE_FILE if already_done else RunStatus.RUNNING,
            started_utc=_now(),
            declared_platform=options.declared_platform.value
            if options.declared_platform
            else None,
            declared_status=options.declared_status.value if options.declared_status else None,
            rows_read=0,
            rows_valid=0,
            rows_invalid=0,
            rows_duplicate_in_file=0,
            rows_already_stored=0,
            rows_written=0,
            files_written=0,
        )
        if already_done:
            run.finished_utc = _now()
            run.error = "Identical file (same SHA-256) was already imported; nothing changed."
        session.add(run)
        session.commit()
    if already_done:
        result.status = RunStatus.SKIPPED_DUPLICATE_FILE
        result.error = run.error
        return result

    context = SourceContext(
        source_file=name,
        source_checksum=checksum,
        ingestion_timestamp=_now(),
        declared_platform=options.declared_platform,
        declared_status=options.declared_status,
    )
    seen_in_file: set[str] = set()
    partition_ids: dict[PartitionKey, set[str]] = {}
    archive_specs: dict[str, CoverageSpec] = {}
    observed: set[tuple[str, str]] = set()
    committed = False
    buffer: dict[PartitionKey, list[pd.DataFrame]] = {}
    buffered = 0

    def flush() -> None:
        """Write buffered rows: one staged file per partition."""
        nonlocal buffered
        if buffer:
            frames = [frame for parts in buffer.values() for frame in parts]
            store.stage_many(run_id, pd.concat(frames, ignore_index=True), options.tile_degrees)
        buffer.clear()
        buffered = 0

    try:
        with session_factory() as session:
            for chunk in iter_firms_file(path, context, options.chunk_rows):
                if chunk.source_member and chunk.source_member not in archive_specs:
                    spec = coverage_from_archive_name(chunk.source_member)
                    if spec is not None:
                        archive_specs[chunk.source_member] = spec
                result.rows_read += len(chunk.valid) + len(chunk.invalid)
                result.rows_invalid += len(chunk.invalid)
                result.rows_valid += len(chunk.valid)
                if len(chunk.invalid):
                    session.execute(
                        insert(InvalidRecord),
                        [
                            {
                                "run_id": run_id,
                                "source_member": row.source_member,
                                "source_row_number": int(row.source_row_number),
                                "reason": row.reason,
                                "source_attributes": row.source_attributes,
                            }
                            for row in chunk.invalid.itertuples(index=False)
                        ],
                    )

                valid = chunk.valid
                ids = valid["observation_id"].astype(str)
                dup_mask = ids.duplicated() | ids.isin(seen_in_file)
                result.rows_duplicate_in_file += int(dup_mask.sum())
                valid = valid[~dup_mask.to_numpy()]
                seen_in_file.update(valid["observation_id"].astype(str))

                for key, part in iter_partitions(valid, options.tile_degrees):
                    if key not in partition_ids:
                        partition_ids[key] = store.existing_ids(key)
                    known = partition_ids[key]
                    new_mask = ~part["observation_id"].astype(str).isin(known).to_numpy()
                    new = part[new_mask]
                    result.rows_already_stored += len(part) - len(new)
                    # Coverage reflects every platform present in the file, including
                    # rows that were already stored by an earlier import.
                    observed.update(
                        zip(
                            part["platform"].astype(str),
                            part["processing_status"].astype(str),
                            strict=True,
                        )
                    )
                    if len(new):
                        buffer.setdefault(key, []).append(new)
                        buffered += len(new)
                        result.rows_written += len(new)
                if buffered >= options.flush_rows:
                    flush()
                session.commit()  # invalid records are kept even if a later chunk fails
            flush()

        with session_factory() as session:
            run = session.get(IngestionRun, run_id)
            run.status = RunStatus.COMMITTING
            _copy_counts(run, result)
            session.commit()

        result.files_written = store.commit_run(run_id)
        committed = True

        with session_factory() as session:
            run = session.get(IngestionRun, run_id)
            session.add_all(_coverage_rows(run_id, options, archive_specs, observed))
            run.status = RunStatus.COMPLETED
            run.finished_utc = _now()
            _copy_counts(run, result)
            session.commit()
        result.status = RunStatus.COMPLETED
        return result

    except Exception as exc:  # record every failure on the run, then re-raise
        result.error = f"{type(exc).__name__}: {exc}"
        if committed:
            # Data is already in the store: the run stays completed, flagged.
            result.status = RunStatus.COMPLETED
            result.error = f"Data stored, but coverage not recorded: {result.error}"
        else:
            store.discard_run(run_id)
            result.status = RunStatus.FAILED
            result.rows_written = 0
            result.files_written = 0
        with session_factory() as session:
            run = session.get(IngestionRun, run_id)
            if run is not None:
                run.status = result.status
                run.finished_utc = _now()
                run.error = result.error
                _copy_counts(run, result)
                session.commit()
        raise


def _copy_counts(run: IngestionRun, result: ImportResult) -> None:
    run.rows_read = result.rows_read
    run.rows_valid = result.rows_valid
    run.rows_invalid = result.rows_invalid
    run.rows_duplicate_in_file = result.rows_duplicate_in_file
    run.rows_already_stored = result.rows_already_stored
    run.rows_written = result.rows_written
    run.files_written = result.files_written


def recover_interrupted_runs(session_factory: SessionFactory, store: ObservationStore) -> list[str]:
    """Finish or roll back runs left behind by a crash. Returns the affected run ids.

    'committing' runs had finished parsing; their staged files are moved into the store.
    'running' runs had not; their staged files are deleted and the run marked failed.
    """
    affected: list[str] = []
    with session_factory() as session:
        runs = session.scalars(
            select(IngestionRun).where(
                IngestionRun.status.in_([RunStatus.RUNNING, RunStatus.COMMITTING])
            )
        ).all()
        for run in runs:
            if run.status == RunStatus.COMMITTING:
                run.files_written = store.commit_run(run.id)
                run.status = RunStatus.COMPLETED
                run.error = "Recovered after interruption; coverage not recorded."
            else:
                store.discard_run(run.id)
                run.status = RunStatus.FAILED
                run.error = "Interrupted before completion; staged data discarded."
            run.finished_utc = _now()
            affected.append(run.id)
        session.commit()
    for orphan in store.staged_runs():
        if orphan not in affected:
            with session_factory() as session:
                if session.get(IngestionRun, orphan) is None:
                    store.discard_run(orphan)
    return affected
