"""End-to-end anomaly report. ALL DETECTIONS ARE SYNTHETIC TEST DATA.

Requires sqlalchemy and pyarrow (runs on the Windows target).
"""

import json
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from app.cli.anomaly_report import run  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.ingestion.coverage import bbox_coverage  # noqa: E402
from app.ingestion.importer import ImportOptions, import_file  # noqa: E402
from app.storage.observation_store import ObservationStore  # noqa: E402

MODIS_HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n"
MARCH_COUNTS = {2016: 5, 2017: 6, 2018: 4, 2019: 5, 2020: 6, 2021: 5, 2022: 30}


def synthetic_march(year: int, count: int) -> str:
    rows = [
        f"{15 + i * 0.05:.5f},80.00000,330,1.0,1.0,{year}-03-10,0530,A,MODIS,80,6.1,300,{5 + i},D\n"
        for i in range(count)
    ]
    return MODIS_HEADER + "".join(rows)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}",
        raw_data_dir=str(tmp_path / "raw"),
        processed_data_dir=str(tmp_path / "processed"),
    )
    engine = make_engine(s.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    store = ObservationStore(tmp_path / "processed")
    for year, count in MARCH_COUNTS.items():
        path = tmp_path / f"SYNTHETIC_aqua_{year}_03.csv"
        path.write_text(synthetic_march(year, count), encoding="utf-8")
        spec = bbox_coverage(70, 10, 90, 25, date(year, 3, 1), date(year, 3, 31), "api_request")
        import_file(path, session_factory=sessions, store=store, raw_dir=tmp_path / "raw",
                    options=ImportOptions(coverage=[spec]))  # fmt: skip
    return s


def test_anomaly_report_flags_spike_and_writes_files(settings: Settings):
    lines: list[str] = []
    argv = ["--bbox", "76,12,85,20", "--start", "2016-03-01", "--end", "2022-03-31",
            "--target", "2022-03"]  # fmt: skip
    assert run(argv, settings=settings, out=lines.append) == 0
    text = "\n".join(lines)
    assert "Aqua" in text and "unusually high" in text
    assert "Terra" in text and "not assessed (incomplete_coverage)" in text

    reports = Path(settings.processed_data_dir) / "reports"
    md = next(reports.glob("report_*.md")).read_text(encoding="utf-8")
    data = json.loads(next(reports.glob("report_*.json")).read_text(encoding="utf-8"))
    assert "EXPERIMENTAL" in md
    aqua = next(r for r in data["target_assessment"] if r["platform"] == "Aqua")
    assert (aqua["value"], aqua["history_years"], aqua["median"]) == (30.0, 6, 5.0)
    calib = data["cross_sensor_calibration"]
    assert calib and all(c["status"] == "unavailable" for c in calib)  # no VIIRS data
