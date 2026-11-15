"""End-to-end import tests (SQLite + Parquet).

ALL CSV CONTENT HERE IS SYNTHETIC TEST DATA — invented values in the FIRMS column
layout, not NASA observations. Requires sqlalchemy and pyarrow (skipped otherwise).
"""

import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from sqlalchemy import func, select  # noqa: E402

from app.database.models import (  # noqa: E402
    CoverageRecord,
    IngestionRun,
    InvalidRecord,
    RunStatus,
    SourceFile,
)
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.ingestion.coverage import bbox_coverage, country_coverage  # noqa: E402
from app.ingestion.firms_csv import FirmsFormatError  # noqa: E402
from app.ingestion.importer import (  # noqa: E402
    ImportOptions,
    import_file,
    recover_interrupted_runs,
)
from app.storage.observation_store import ObservationStore  # noqa: E402

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROW_A = "9.12345,2.54321,340.1,0.39,0.36,2023-01-15,1302,N,VIIRS,n,2.0NRT,295.2,5.4,D\n"
ROW_B = "-16.50000,179.95000,330.0,0.4,0.4,2023-03-02,2359,N20,VIIRS,h,2,290.0,10.1,N\n"
ROW_C = "65.00000,-179.90000,310.0,0.5,0.4,2024-06-30,0001,N21,VIIRS,l,2.0URT,280.0,,N\n"
ROW_BAD = "95.0,10.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,5,D\n"


@pytest.fixture
def env(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}")
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(tmp_path / "processed")
    raw_dir = tmp_path / "raw"
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    def run(name: str, text: str | None = None, path: Path | None = None, **opts):
        if path is None:
            path = inbox / name
            path.write_text(text, encoding="utf-8")
        return import_file(
            path,
            session_factory=sessions,
            store=store,
            raw_dir=raw_dir,
            options=ImportOptions(**opts),
        )

    def stored() -> pd.DataFrame:
        files = store.all_files()
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

    return run, stored, sessions, store, inbox, raw_dir


def test_import_writes_partitioned_parquet_with_provenance(env):
    run, stored, sessions, store, *_ = env
    result = run("SYNTHETIC_a.csv", HEADER + ROW_A + ROW_B + ROW_C)
    assert result.status == RunStatus.COMPLETED
    assert (result.rows_read, result.rows_valid, result.rows_written) == (3, 3, 3)
    assert result.files_written == 3  # three different sensor/month/tile partitions
    data = stored()
    assert len(data) == 3
    assert set(data["platform"]) == {"Suomi-NPP", "NOAA-20", "NOAA-21"}
    assert data["source_checksum"].nunique() == 1
    rel = sorted(p.relative_to(store.final_dir).parent.as_posix() for p in store.all_files())
    assert rel == ["VIIRS/2023/01/r09c018", "VIIRS/2023/03/r07c035", "VIIRS/2024/06/r15c000"]
    assert not store.staged_runs()


def test_rows_are_buffered_into_one_file_per_partition(env):
    run, stored, _, store, *_ = env
    text = HEADER + ROW_A + ROW_B + ROW_C + ROW_A.replace("1302", "1303")
    result = run("SYNTHETIC_buffered.csv", text, chunk_rows=1)  # 4 chunks
    assert result.rows_written == 4
    assert len(store.all_files()) == 3  # one per partition, not one per chunk


def test_buffer_is_flushed_when_the_row_limit_is_reached(env):
    run, stored, _, store, *_ = env
    text = HEADER + "".join(ROW_A.replace("1302", f"13{i:02d}") for i in range(5))
    result = run("SYNTHETIC_flush.csv", text, chunk_rows=1, flush_rows=2)
    assert result.rows_written == 5
    assert len(store.all_files()) == 3  # flushes after rows 2 and 4, then the last row
    assert len(stored()) == 5 and stored()["observation_id"].is_unique


def test_identical_file_imported_twice_does_not_change_counts(env):
    run, stored, sessions, *_ = env
    first = run("SYNTHETIC_a.csv", HEADER + ROW_A + ROW_B)
    second = run("SYNTHETIC_a_copy.csv", HEADER + ROW_A + ROW_B)
    assert first.status == RunStatus.COMPLETED
    assert second.status == RunStatus.SKIPPED_DUPLICATE_FILE
    assert len(stored()) == 2
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(SourceFile)) == 1
        assert s.scalar(select(func.count()).select_from(IngestionRun)) == 2


def test_overlapping_files_store_each_detection_once(env):
    run, stored, *_ = env
    run("SYNTHETIC_a.csv", HEADER + ROW_A + ROW_B)
    result = run("SYNTHETIC_b.csv", HEADER + ROW_B + ROW_C)
    assert result.rows_already_stored == 1
    assert result.rows_written == 1
    assert len(stored()) == 3
    assert stored()["observation_id"].is_unique


def test_duplicate_rows_inside_one_file_are_counted_not_stored_twice(env):
    run, stored, *_ = env
    result = run("SYNTHETIC_dup.csv", HEADER + ROW_A + ROW_A + ROW_B, chunk_rows=1)
    assert result.rows_duplicate_in_file == 1
    assert result.rows_written == 2
    assert len(stored()) == 2


def test_invalid_rows_are_recorded_with_reasons(env):
    run, stored, sessions, *_ = env
    result = run("SYNTHETIC_bad.csv", HEADER + ROW_A + ROW_BAD)
    assert (result.rows_valid, result.rows_invalid) == (1, 1)
    with sessions() as s:
        records = s.scalars(select(InvalidRecord)).all()
        assert len(records) == 1
        assert "latitude" in records[0].reason
        assert records[0].source_row_number == 2
        assert '"latitude":"95.0"' in records[0].source_attributes


def test_failed_import_leaves_no_partial_data(env):
    run, stored, sessions, store, *_ = env
    text = HEADER + ROW_A + ROW_B + "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17\n"
    with pytest.raises(FirmsFormatError):
        run("SYNTHETIC_broken.csv", text, chunk_rows=1)
    assert stored().empty
    assert not store.staged_runs()
    with sessions() as s:
        run_row = s.scalars(select(IngestionRun)).one()
        assert run_row.status == RunStatus.FAILED
        assert "Malformed CSV" in run_row.error


def test_failed_file_can_be_reimported_after_fix(env):
    run, stored, *_ = env
    with pytest.raises(FirmsFormatError):
        run("SYNTHETIC_x.csv", HEADER + ROW_A + "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17\n")
    result = run("SYNTHETIC_x_fixed.csv", HEADER + ROW_A)
    assert result.status == RunStatus.COMPLETED and len(stored()) == 1


def test_raw_file_is_kept_unchanged(env):
    run, _, sessions, _, inbox, raw_dir = env
    text = HEADER + ROW_A
    run("SYNTHETIC_raw.csv", text)
    with sessions() as s:
        source = s.scalars(select(SourceFile)).one()
    assert Path(source.stored_path).read_text(encoding="utf-8") == text
    assert Path(source.stored_path).parent == raw_dir


def test_declared_bbox_coverage_recorded_per_platform(env):
    run, _, sessions, *_ = env
    spec = bbox_coverage(0, 0, 10, 10, date(2023, 1, 15), date(2023, 1, 15), basis="api_request")
    run("SYNTHETIC_api.csv", HEADER + ROW_A, coverage=[spec])
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    assert [(r.platform, r.processing_status, r.extent_type, r.basis) for r in rows] == [
        ("Suomi-NPP", "NRT", "bbox", "api_request")
    ]


def test_archive_with_sp_and_nrt_splits_coverage_at_the_last_sp_day(env):
    """Archive downloads: SP for older months, NRT for the latest ones (SYNTHETIC)."""
    run, _, sessions, *_ = env
    sp1 = "10.00000,20.00000,330,0.4,0.4,2023-01-10,0700,N,VIIRS,n,2,290,1.0,D\n"
    sp2 = "10.10000,20.00000,330,0.4,0.4,2023-02-20,0700,N,VIIRS,n,2,290,1.0,D\n"
    nrt = "10.20000,20.00000,330,0.4,0.4,2023-03-05,0700,N,VIIRS,n,2.0NRT,290,1.0,D\n"
    spec = country_coverage("Synthetic Land", date(2023, 1, 1), date(2023, 3, 31))
    run("SYNTHETIC_archive.csv", HEADER + sp1 + nrt + sp2, coverage=[spec])
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    got = sorted((r.processing_status, r.start_date, r.end_date) for r in rows)
    assert got == [
        ("NRT", date(2023, 2, 21), date(2023, 3, 31)),
        ("SP", date(2023, 1, 1), date(2023, 2, 20)),
    ]


def test_archive_download_zip_with_sp_and_nrt_members(env):
    """Archive Download layout: fire_archive_* (SP) + fire_nrt_* (NRT) + Readme (SYNTHETIC)."""
    run, stored, sessions, _, inbox, _ = env
    head = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,"
            "confidence,version,bright_t31,frp,daynight")  # fmt: skip
    sp = head + ",type\n11.0,79.0,335,0.4,0.6,2026-07-31,0712,SNPP,SNPP,n,2,299,2.5,D,0\n"
    nrt = head + "\n11.5,79.5,330,0.4,0.6,2026-08-01,0712,SNPP,SNPP,l,2.0NRT,290,1.0,D\n"
    archive = inbox / "DL_FIRE_SV-C2_SYNTHETIC.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fire_archive_SV-C2_SYNTHETIC.csv", sp)
        zf.writestr("fire_nrt_SV-C2_SYNTHETIC.csv", nrt)
        zf.writestr("Readme.txt", "SYNTHETIC readme")
    spec = country_coverage("Synthetic Land", date(2026, 7, 1), date(2026, 8, 31))
    result = run("unused", path=archive, coverage=[spec])
    assert (result.status, result.rows_written, result.rows_invalid) == (RunStatus.COMPLETED, 2, 0)
    assert sorted(stored()["processing_status"]) == ["NRT", "SP"]
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    assert sorted((r.processing_status, r.start_date, r.end_date) for r in rows) == [
        ("NRT", date(2026, 8, 1), date(2026, 8, 31)),
        ("SP", date(2026, 7, 1), date(2026, 7, 31)),
    ]


def test_coverage_counts_platforms_even_when_rows_were_already_stored(env):
    run, _, sessions, *_ = env
    run("SYNTHETIC_first.csv", HEADER + ROW_A)
    spec = bbox_coverage(0, 0, 10, 10, date(2023, 1, 15), date(2023, 1, 15), basis="api_request")
    second = run("SYNTHETIC_second.csv", HEADER + ROW_A + "\n", coverage=[spec])
    assert second.rows_written == 0 and second.rows_already_stored == 1
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord).where(CoverageRecord.run_id == second.run_id))
        assert [(r.platform, r.basis) for r in rows] == [("Suomi-NPP", "api_request")]


def test_unknown_coverage_when_nothing_declared(env):
    run, _, sessions, *_ = env
    run("SYNTHETIC_plain.csv", HEADER + ROW_A)
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    assert [r.extent_type for r in rows] == ["unknown"]
    assert "must not be inferred" in rows[0].note


def test_archive_zip_coverage_from_member_names(env):
    run, stored, sessions, _, inbox, _ = env
    archive = inbox / "SYNTHETIC_viirs_2023.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("viirs/2023/viirs-snpp_2023_Synthetic_Land.csv", HEADER + ROW_A)
    result = run("unused", path=archive)
    assert result.rows_written == 1
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    assert [(r.extent_type, r.extent_value, r.basis) for r in rows] == [
        ("country", "Synthetic Land", "archive_filename")
    ]
    assert stored().loc[0, "source_member"] == "viirs/2023/viirs-snpp_2023_Synthetic_Land.csv"


def test_recovery_commits_or_discards_interrupted_runs(env):
    run, stored, sessions, store, *_ = env
    first = run("SYNTHETIC_a.csv", HEADER + ROW_A)
    # Simulate a crash during commit: re-stage data under a run marked 'committing'.
    frame = stored()
    from app.storage.partitioning import iter_partitions

    with sessions() as s:
        template = s.get(IngestionRun, first.run_id)
        for run_id, status in (("c" * 32, RunStatus.COMMITTING), ("r" * 32, RunStatus.RUNNING)):
            s.add(
                IngestionRun(
                    id=run_id,
                    source_file_id=template.source_file_id,
                    status=status,
                    started_utc=template.started_utc,
                )
            )
        s.commit()
    for key, part in iter_partitions(frame.assign(observation_id="x" * 32)):
        store.stage("c" * 32, key, part)
        store.stage("r" * 32, key, part.assign(observation_id="y" * 32))
    affected = recover_interrupted_runs(sessions, store)
    assert sorted(affected) == ["c" * 32, "r" * 32]
    ids = set(stored()["observation_id"])
    assert "x" * 32 in ids and "y" * 32 not in ids
    assert not store.staged_runs()
    with sessions() as s:
        assert s.get(IngestionRun, "c" * 32).status == RunStatus.COMPLETED
        assert s.get(IngestionRun, "r" * 32).status == RunStatus.FAILED
