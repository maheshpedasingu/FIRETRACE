"""End-to-end exports. ALL DETECTIONS ARE SYNTHETIC TEST DATA.

Requires sqlalchemy and pyarrow (runs on the Windows target).
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from app.cli.export import run  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.ingestion.coverage import bbox_coverage  # noqa: E402
from app.ingestion.importer import ImportOptions, import_file  # noqa: E402
from app.storage.observation_store import ObservationStore  # noqa: E402

HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
NRT = (
    "15.10000,80.20000,330,0.4,0.4,2026-07-01,0739,N20,VIIRS,n,2.0NRT,290,5.0,D\n"
    "15.20000,80.30000,330,0.4,0.4,2026-07-02,0739,N20,VIIRS,h,2.0NRT,290,6.0,N\n"
)
SP = "15.10010,80.20010,330,0.4,0.4,2026-07-01,0739,N20,VIIRS,n,2,290,4.0,D\n"
OUTSIDE = "45.00000,10.00000,330,0.4,0.4,2026-07-01,0739,N20,VIIRS,n,2.0NRT,290,5.0,D\n"


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
    for name, text, start, end in [
        ("SYNTHETIC_nrt.csv", HEADER + NRT + OUTSIDE, date(2026, 7, 1), date(2026, 7, 2)),
        ("SYNTHETIC_sp.csv", HEADER + SP, date(2026, 7, 1), date(2026, 7, 1)),
    ]:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        spec = bbox_coverage(70, 10, 90, 25, start, end, "api_request")
        import_file(path, session_factory=sessions, store=store, raw_dir=tmp_path / "raw",
                    options=ImportOptions(coverage=[spec]))  # fmt: skip
    return s


AREA = ["--bbox", "76,12,85,20", "--start", "2026-07-01", "--end", "2026-07-31"]


def test_hotspot_export_supersedes_nrt_and_writes_provenance(settings, tmp_path):
    out = tmp_path / "exports" / "hotspots.csv"
    assert run(["hotspots", *AREA, "--out", str(out)], settings=settings, out=lambda _: None) == 0
    data = pd.read_csv(out)
    # 1 July: SP replaces NRT; 2 July: NRT only; the detection at 45N is outside the area
    assert sorted(zip(data.acquisition_date, data.processing_status, strict=True)) == [
        ("2026-07-01", "SP"), ("2026-07-02", "NRT")]  # fmt: skip
    prov = json.loads((tmp_path / "exports" / "hotspots.csv.provenance.json").read_text("utf-8"))
    assert prov["rows"] == 2 and prov["nrt_rows_superseded_by_sp"] == 1
    assert len(prov["source_files"]) == 2


def test_calendar_export_with_grid(settings, tmp_path):
    out = tmp_path / "cal.csv"
    argv = ["calendar", *AREA, "--out", str(out), "--platform", "NOAA-20", "--grid"]
    assert run(argv, settings=settings, out=lambda _: None) == 0
    cal = pd.read_csv(out)
    july = cal[(cal.platform == "NOAA-20") & (cal.month == 7)].iloc[0]
    assert (july.state, july.value, july.days_covered) == ("partial", 2, 2)
    grid = pd.read_csv(tmp_path / "cal_NOAA-20_grid.csv")
    assert grid.loc[0, "Jul"] == "partial:2"


def test_analytics_export(settings, tmp_path):
    out = tmp_path / "analytics.json"
    assert run(["analytics", *AREA, "--out", str(out)], settings=settings, out=lambda _: None) == 0
    payload = json.loads(out.read_text("utf-8"))
    dist = {d["platform"]: d for d in payload["distributions"]}
    assert dist["NOAA-20"]["detections"] == 2  # superseded NRT row not counted
    assert payload["status"].startswith("baselines and anomalies are EXPERIMENTAL")
    assert (tmp_path / "analytics.json.provenance.json").exists()
