"""SQLite metadata: source files, ingestion runs, invalid records, coverage."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunStatus:
    RUNNING = "running"
    COMMITTING = "committing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED_DUPLICATE_FILE = "skipped_duplicate_file"


class SourceFile(Base):
    """An original file, stored unchanged in data/raw/ and identified by SHA-256."""

    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_name: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    first_seen_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    runs: Mapped[list[IngestionRun]] = relationship(back_populates="source_file")


class IngestionRun(Base):
    """One attempt to import one source file."""

    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declared_platform: Mapped[str | None] = mapped_column(String(32))
    declared_status: Mapped[str | None] = mapped_column(String(16))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate_in_file: Mapped[int] = mapped_column(Integer, default=0)
    rows_already_stored: Mapped[int] = mapped_column(Integer, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    files_written: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    source_file: Mapped[SourceFile] = relationship(back_populates="runs")
    invalid_records: Mapped[list[InvalidRecord]] = relationship(back_populates="run")
    coverage: Mapped[list[CoverageRecord]] = relationship(back_populates="run")


class InvalidRecord(Base):
    """A source row that failed validation, with every reason and the original row."""

    __tablename__ = "invalid_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_member: Mapped[str | None] = mapped_column(String(512))
    source_row_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    source_attributes: Mapped[str] = mapped_column(Text)

    run: Mapped[IngestionRun] = relationship(back_populates="invalid_records")


class CoverageRecord(Base):
    """What an import claims to cover. Zero activity may only be inferred inside it.

    basis: 'api_request' or 'user_declared' (extent known from the request) or
    'archive_filename' (country/year parsed from a FIRMS file name; completeness not
    verified) or 'none' (unknown extent: zero activity must not be inferred).
    """

    __tablename__ = "coverage"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    platform: Mapped[str | None] = mapped_column(String(32))
    processing_status: Mapped[str | None] = mapped_column(String(16))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    extent_type: Mapped[str] = mapped_column(String(16))  # bbox | country | unknown
    extent_value: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)

    run: Mapped[IngestionRun] = relationship(back_populates="coverage")


class SavedAOI(Base):
    """A named area of interest (GeoJSON polygon or bbox)."""

    __tablename__ = "aois"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # bbox | polygon
    west: Mapped[float] = mapped_column()
    south: Mapped[float] = mapped_column()
    east: Mapped[float] = mapped_column()
    north: Mapped[float] = mapped_column()
    geojson: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(200))
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
