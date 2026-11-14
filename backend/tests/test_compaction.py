"""Compaction, recovery, verification and benchmark tests. ALL DATA IS SYNTHETIC TEST DATA."""

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from app.cli.benchmark import run as benchmark  # noqa: E402
from app.cli.compact import run as compact_cli  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.harmonization.aggregate_store import AggregateStore  # noqa: E402
from app.ingestion.coverage import bbox_coverage  # noqa: E402
from app.ingestion.importer import ImportOptions, import_file  # noqa: E402
from app.storage.compaction import (  # noqa: E402
    CompactionError,
    compact_partition,
    partition_dirs,
    recover_compaction,
    verify_store,
)
from app.storage.observation_store import ObservationStore  # noqa: E402

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"


def rows(n: int, offset: int = 0) -> str:
    return "".join(
        f"{15 + (offset + i) * 0.001:.5f},80.00000,330,0.4,0.4,2026-11-11,0739,N20,VIIRS,n,2.0NRT,290,{i + 1}.0,D\n"
        for i in range(n)
    )


@pytest.fixture
def env(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}")
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(tmp_path / "processed")
    spec = bbox_coverage(70, 10, 90, 25, date(2026, 11, 11), date(2026, 11, 11), "api_request")
    for i in range(3):
        path = tmp_path / f"SYNTHETIC_{i}.csv"
        path.write_text(HEADER + rows(4, offset=i * 4), encoding="utf-8")
        import_file(path, session_factory=sessions, store=store, raw_dir=tmp_path / "raw",
                    options=ImportOptions(coverage=[spec], chunk_rows=1, flush_rows=1))  # fmt: skip
    return store, tmp_path


def all_ids(store: ObservationStore) -> list[str]:
    return sorted(pd.concat([pd.read_parquet(f) for f in store.all_files()])["observation_id"])


def test_compaction_merges_files_without_changing_data(env):
    store, tmp_path = env
    before_ids, before_files = all_ids(store), len(store.all_files())
    assert before_files == 12  # flush_rows=1 forces one file per row (worst case)
    totals_before = AggregateStore(tmp_path / "processed").build_stale()
    for key, _ in partition_dirs(store):
        compact_partition(store, key)
    assert len(store.all_files()) == 1
    assert all_ids(store) == before_ids
    aggregates = AggregateStore(tmp_path / "processed")
    assert aggregates.stale_months()  # compacted file is newer → rebuild
    assert aggregates.build_stale() == totals_before
    assert int(aggregates.read()["detections"].sum()) == 12
    report = verify_store(store)
    assert [(r.files, r.rows, r.duplicate_ids, r.misplaced_rows) for r in report] == [(1, 12, 0, 0)]


def test_compaction_refuses_duplicates_and_leaves_partition_unchanged(env):
    store, _ = env
    key, directory = partition_dirs(store)[0]
    first = sorted(directory.glob("*.parquet"))[0]
    (directory / "zz-duplicate.parquet").write_bytes(first.read_bytes())
    files_before = sorted(p.name for p in directory.glob("*.parquet"))
    with pytest.raises(CompactionError, match="duplicated observation_id"):
        compact_partition(store, key)
    assert sorted(p.name for p in directory.glob("*.parquet")) == files_before
    assert verify_store(store)[0].duplicate_ids == 1


def test_recovery_finishes_or_rolls_back_interrupted_swaps(env):
    store, _ = env
    key, directory = partition_dirs(store)[0]
    ids = all_ids(store)
    # Crash after "partition → .old" but before ".compacting → partition":
    staging = directory.parent / f".{directory.name}.compacting"
    staging.mkdir()
    merged = pd.concat([pd.read_parquet(f) for f in directory.glob("*.parquet")])
    merged.to_parquet(staging / "part-compacted.parquet", index=False)
    os.replace(directory, directory.parent / f".{directory.name}.old")
    assert store.all_files() == []  # hidden dirs are invisible: never double counted
    assert recover_compaction(store) == [key.relative_path().as_posix().replace("/", os.sep)]
    assert all_ids(store) == ids and len(store.all_files()) == 1
    # Leftover staging with an intact partition is discarded:
    leftover = directory.parent / f".{directory.name}.compacting"
    leftover.mkdir()
    recover_compaction(store)
    assert not leftover.exists() and all_ids(store) == ids


def test_verify_detects_misplaced_rows(env):
    store, _ = env
    _, directory = partition_dirs(store)[0]
    wrong = directory.parent.parent / "12" / directory.name
    wrong.mkdir(parents=True)
    first = sorted(directory.glob("*.parquet"))[0]
    os.replace(first, wrong / first.name)
    reports = {r.partition: r for r in verify_store(store)}
    assert reports[f"VIIRS/2026/12/{directory.name}"].misplaced_rows == 1


def test_compact_command(env):
    store, tmp_path = env
    settings = Settings(_env_file=None, processed_data_dir=str(tmp_path / "processed"))
    lines: list[str] = []
    assert compact_cli([], settings=settings, out=lines.append) == 0
    assert "compacted 1 partition(s)" in lines
    assert lines[-1] == "partitions 1, files 1, rows 12, duplicate ids 0, misplaced rows 0"


def test_benchmark_small_run_and_refuses_non_empty_folder(tmp_path: Path):
    work = tmp_path / "bench"
    lines: list[str] = []
    code = benchmark(["--rows", "600", "--rows-per-file", "300", "--chunk-rows", "200",
                      "--workdir", str(work)], out=lines.append)  # fmt: skip
    assert code == 0, lines
    results = json.loads((work / "benchmark_results.json").read_text(encoding="utf-8"))
    assert results["rows_written"] == 600
    assert results["files_after_compaction"] <= results["files_before_compaction"]
    assert results["duplicates"] == 0 and results["misplaced"] == 0
    assert benchmark(["--rows", "10", "--workdir", str(work)], out=lines.append) == 2


def test_benchmark_uniform_spread_reports_partitions_and_progress(tmp_path: Path):
    work = tmp_path / "bench_uniform"
    lines: list[str] = []
    code = benchmark(["--rows", "300", "--rows-per-file", "300", "--chunk-rows", "200",
                      "--spread", "uniform", "--workdir", str(work)], out=lines.append)  # fmt: skip
    assert code == 0, lines
    results = json.loads((work / "benchmark_results.json").read_text(encoding="utf-8"))
    assert results["spread"] == "uniform"
    assert results["rows_written"] == 300
    assert results["partitions"] > 0
    assert any(line.startswith("  importing SYNTHETIC_") for line in lines)
    assert "spread uniform;" in lines[-2]


def test_clustered_positions_are_concentrated_and_valid():
    import numpy as np

    from app.cli.benchmark import synthetic_positions

    rng = np.random.default_rng(0)
    lat, lon = synthetic_positions(rng, 20000, "clustered")
    assert lat.min() >= -90 and lat.max() <= 90
    assert lon.min() >= -180 and lon.max() < 180
    tiles = {(int((a + 90) // 10), int((o + 180) // 10)) for a, o in zip(lat, lon, strict=True)}
    u_lat, u_lon = synthetic_positions(np.random.default_rng(0), 20000, "uniform")
    u_tiles = {
        (int((a + 90) // 10), int((o + 180) // 10)) for a, o in zip(u_lat, u_lon, strict=True)
    }
    assert len(tiles) < len(u_tiles)
