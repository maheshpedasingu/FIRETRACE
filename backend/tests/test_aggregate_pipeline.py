"""End-to-end: import → cell-day aggregates → area summary.

ALL CSV CONTENT IS SYNTHETIC TEST DATA. Requires sqlalchemy and pyarrow.
"""

import os
import time
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from app.cli.area_summary import run as area_summary  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.harmonization.aggregate_store import AggregateStore, MonthKey  # noqa: E402
from app.ingestion.coverage import bbox_coverage  # noqa: E402
from app.ingestion.importer import ImportOptions, import_file  # noqa: E402
from app.storage.observation_store import ObservationStore  # noqa: E402

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROWS_NOV = (
    "15.10000,80.20000,330,0.4,0.4,2026-11-11,0739,N20,VIIRS,n,2.0NRT,290,5.0,D\n"
    "15.10010,80.20010,331,0.4,0.4,2026-11-11,0739,N20,VIIRS,l,2.0NRT,290,1.0,D\n"
    "18.00000,78.00000,332,0.4,0.4,2026-11-12,2005,N20,VIIRS,h,2.0NRT,290,3.0,N\n"
)
ROW_DEC = "16.00000,79.00000,333,0.4,0.4,2026-12-01,0739,N20,VIIRS,n,2.0NRT,290,2.0,D\n"


@pytest.fixture
def env(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}",
        raw_data_dir=str(tmp_path / "raw"),
        processed_data_dir=str(tmp_path / "processed"),
    )
    engine = make_engine(settings.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(tmp_path / "processed")

    def load(name, text, start, end):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        spec = bbox_coverage(70, 10, 90, 25, start, end, basis="api_request")
        return import_file(
            path, session_factory=sessions, store=store, raw_dir=tmp_path / "raw",
            options=ImportOptions(coverage=[spec]),
        )  # fmt: skip

    return settings, load, AggregateStore(tmp_path / "processed")


def test_build_is_incremental_and_exact(env):
    settings, load, aggregates = env
    load("SYNTHETIC_nov.csv", HEADER + ROWS_NOV, date(2026, 11, 11), date(2026, 11, 12))
    assert aggregates.stale_months() == [MonthKey("VIIRS", 2026, 11)]
    built = aggregates.build_stale()
    assert built == {MonthKey("VIIRS", 2026, 11): 2}  # 3 detections → 2 cell-days
    assert aggregates.stale_months() == []

    time.sleep(0.05)
    load("SYNTHETIC_dec.csv", HEADER + ROW_DEC, date(2026, 12, 1), date(2026, 12, 1))
    assert aggregates.stale_months() == [MonthKey("VIIRS", 2026, 12)]  # Nov untouched
    aggregates.build_stale()
    cells = aggregates.read()
    assert int(cells["detections"].sum()) == 4
    assert not list(aggregates.root.rglob("*.partial"))


def test_rebuild_after_new_data_in_same_month(env):
    settings, load, aggregates = env
    load(
        "SYNTHETIC_a.csv",
        HEADER + ROWS_NOV.splitlines(keepends=True)[0],
        date(2026, 11, 11),
        date(2026, 11, 11),
    )
    aggregates.build_stale()
    path = aggregates.month_path(MonthKey("VIIRS", 2026, 11))
    old = path.stat().st_mtime
    os.utime(path, (old - 10, old - 10))  # make the aggregate clearly older
    load("SYNTHETIC_b.csv", HEADER + ROWS_NOV, date(2026, 11, 11), date(2026, 11, 12))
    assert aggregates.stale_months() == [MonthKey("VIIRS", 2026, 11)]
    aggregates.build_stale()
    assert int(aggregates.read()["detections"].sum()) == 3


def test_area_summary_command(env, tmp_path):
    settings, load, _ = env
    load("SYNTHETIC_nov.csv", HEADER + ROWS_NOV, date(2026, 11, 11), date(2026, 11, 12))
    lines: list[str] = []
    out_csv = tmp_path / "summary.csv"
    argv = ["--bbox", "76,12,85,20", "--start", "2026-10-01", "--end", "2026-11-12",
            "--platform", "NOAA-20", "--platform", "Terra", "--csv", str(out_csv)]  # fmt: skip
    assert area_summary(argv, settings=settings, out=lines.append) == 0
    text = "\n".join(lines)
    assert "rebuilt VIIRS 2026-11" in text
    import pandas as pd

    table = pd.read_csv(out_csv)
    nov = table[(table.platform == "NOAA-20") & (table.month == 11)].iloc[0]
    assert (nov.detections, nov.unique_cells, nov.coverage_status) == (3, 2, "partial")
    assert (
        table[(table.platform == "NOAA-20") & (table.month == 10)].iloc[0].coverage_status
        == "missing"
    )
    assert table[table.platform == "Terra"].coverage_status.eq("missing").all()
