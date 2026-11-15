"""REST API tests against a temporary store and a simulated FIRMS server.

ALL DETECTIONS AND FIRMS RESPONSES ARE SYNTHETIC TEST DATA. The MAP_KEY is fake.
Requires fastapi, httpx, sqlalchemy, pyarrow and shapely (runs on the Windows target).
"""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

for module in ("fastapi", "httpx", "sqlalchemy", "pyarrow", "shapely"):
    pytest.importorskip(module)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.system import get_firms_transport  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

FAKE_KEY = "fa4efa4efa4efa4efa4efa4efa4efa4e"
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
ROWS = (
    "15.10000,80.20000,330,0.4,0.4,2026-11-11,0739,N20,VIIRS,n,2.0NRT,290,5.0,D\n"
    "15.10010,80.20010,331,0.4,0.4,2026-11-11,0739,N20,VIIRS,l,2.0NRT,290,1.0,D\n"
    "18.00000,78.00000,332,0.4,0.4,2026-11-12,2005,N20,VIIRS,h,2.0NRT,290,3.0,N\n"
)
AREA = {"bbox": "76,12,85,20", "start": "2026-11-01", "end": "2026-11-14"}
MODIS_HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n"


def fake_firms(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if "/data_availability/" in path:
        return httpx.Response(
            200, text="data_id,min_date,max_date\nMODIS_NRT,2026-01-01,2030-12-31\n"
        )
    if "/area/csv/" in path:
        return httpx.Response(200, text=MODIS_HEADER)  # no detections
    return httpx.Response(404, text="unknown")


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        firms_map_key=FAKE_KEY,
        firms_api_base="https://firms.example/api",
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}",
        raw_data_dir=str(tmp_path / "data" / "raw"),
        processed_data_dir=str(tmp_path / "data" / "processed"),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_firms_transport] = lambda: httpx.MockTransport(fake_firms)
    with TestClient(app) as c:
        c.settings = settings
        yield c


def upload(client, text=HEADER + ROWS, name="SYNTHETIC.csv", coverage=True):
    data = {"bbox": "70,10,90,25", "start": "2026-11-11", "end": "2026-11-12"} if coverage else {}
    return client.post("/api/ingest/upload", files={"file": (name, text.encode(), "text/csv")},
                       data=data)  # fmt: skip


def test_sensors_lists_five_platforms_separately(client):
    body = client.get("/api/sensors").json()
    assert [s["platform"] for s in body] == ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"]
    assert {s["sensor"] for s in body} == {"MODIS", "VIIRS"}


def test_upload_import_duplicate_and_history(client):
    first = upload(client)
    assert first.status_code == 200, first.text
    assert (first.json()["status"], first.json()["rows_written"]) == ("completed", 3)
    again = upload(client, name="SYNTHETIC_copy.csv")
    assert again.json()["status"] == "skipped_duplicate_file"
    history = client.get("/api/ingest/history").json()
    # provenance shows the user's original file name, not the internal upload copy name
    assert history["total"] == 2
    assert {item["file"] for item in history["items"]} == {"SYNTHETIC.csv"}
    item = client.get("/api/hotspots", params=AREA | {"page_size": 1}).json()["items"][0]
    assert item["source_file"] == "SYNTHETIC.csv"
    raw_files = [p.name for p in Path(client.settings.raw_data_dir).iterdir()]
    assert len(raw_files) == 1 and raw_files[0].endswith("_SYNTHETIC.csv")


def test_upload_rejects_wrong_type_and_invalid_content(client):
    assert upload(client, name="x.txt").status_code == 400
    bad = upload(client, text="hello,world\n1,2\n", name="SYNTHETIC_bad.csv")
    assert bad.status_code == 422 and "FIRMS" in bad.json()["detail"]


def test_hotspots_pagination_filters_and_validation(client):
    upload(client)
    page1 = client.get("/api/hotspots", params=AREA | {"page_size": 2}).json()
    page2 = client.get("/api/hotspots", params=AREA | {"page_size": 2, "page": 2}).json()
    assert (page1["total"], len(page1["items"]), len(page2["items"])) == (3, 2, 1)
    assert "source_attributes" not in page1["items"][0]
    high = client.get("/api/hotspots", params=AREA | {"confidence": "high"}).json()
    assert high["total"] == 1 and high["items"][0]["day_night"] == "N"
    with_src = client.get("/api/hotspots", params=AREA | {"include_source": "true"}).json()
    assert json.loads(with_src["items"][0]["source_attributes"])["satellite"] == "N20"
    assert client.get("/api/hotspots", params=AREA | {"bbox": "1,2,3"}).status_code == 400
    assert client.get("/api/hotspots", params=AREA | {"aoi_id": 1}).status_code == 400
    assert client.get("/api/hotspots", params=AREA | {"end": "2026-10-01"}).status_code == 400
    assert client.get("/api/hotspots", params=AREA | {"platform": "Landsat"}).status_code == 400


def test_summary_calendar_and_analytics(client):
    upload(client)
    summary = client.get("/api/hotspots/summary", params=AREA).json()
    n20 = next(p for p in summary["platforms"] if p["platform"] == "NOAA-20")
    assert (summary["total_detections"], n20["detections"], n20["unique_cells"]) == (3, 3, 2)
    cal = client.get("/api/calendar", params=AREA | {"platform": "NOAA-20"}).json()
    assert [(c["month"], c["state"], c["value"]) for c in cal["cells"]] == [(11, "partial", 3)]
    monthly = client.get("/api/analytics/monthly", params=AREA).json()["months"]
    terra = next(m for m in monthly if m["platform"] == "Terra")
    assert terra["coverage_status"] == "missing" and terra["detections"] is None  # not 0
    assert client.get("/api/analytics/yearly", params=AREA).status_code == 200
    anomalies = client.get("/api/analytics/anomalies", params=AREA).json()
    assert anomalies["status"] == "EXPERIMENTAL"
    assert {a["status"] for a in anomalies["assessments"]} == {"incomplete_coverage"}
    bad = client.get("/api/analytics/anomalies", params=AREA | {"target": "2026-13"})
    assert bad.status_code == 400
    comparison = client.get("/api/analytics/sensor-comparison", params=AREA).json()
    assert len(comparison["calibration"]) == 6
    assert {c["status"] for c in comparison["calibration"]} == {"unavailable"}


def test_summary_with_standard_processing_data(client):
    """Regression (real India archive): with SP data present, the summary read detections
    without processing_status and the SP-supersedes-NRT step raised KeyError."""
    sp_rows = ROWS.replace(",2.0NRT,", ",2,")  # same SYNTHETIC rows as standard processing
    assert upload(client, HEADER + sp_rows, name="SYNTHETIC_sp.csv").status_code == 200
    summary = client.get("/api/hotspots/summary", params=AREA)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_detections"] == 3


def test_harmonized_calendar_never_converts_without_a_fitted_factor(client):
    upload(client)  # NOAA-20 only: no overlap with MODIS, so no conversion factor exists
    body = client.get("/api/calendar/harmonized", params=AREA).json()
    assert body["status"] == "EXPERIMENTAL"
    assert body["reference_source"] == "MODIS (Terra+Aqua)"
    n20 = next(f for f in body["fits"] if f["source"] == "NOAA-20")
    assert n20["status"] == "unavailable" and n20["factor"] is None
    (nov,) = body["cells"]
    assert (nov["year"], nov["month"], nov["state"], nov["value"]) == (2026, 11, "missing", None)
    assert "NOAA-20" in nov["note"] and "no conversion factor" in nov["note"]
    viirs = client.get("/api/calendar/harmonized", params=AREA | {"reference": "viirs"}).json()
    assert viirs["reference_source"] == "Suomi-NPP"
    bad = client.get("/api/calendar/harmonized", params=AREA | {"reference": "landsat"})
    assert bad.status_code == 422


def test_aoi_create_list_validate_and_use(client):
    upload(client)
    # polygon around the two detections at 15.1N 80.2E only
    square = {
        "type": "Polygon",
        "coordinates": [[[80, 15], [80.5, 15], [80.5, 15.5], [80, 15.5], [80, 15]]],
    }
    created = client.post("/api/aoi", json={"name": "SYNTHETIC square", "geojson": square})
    assert created.status_code == 201, created.text
    aoi_id = created.json()["id"]
    assert (
        client.post("/api/aoi", json={"name": "SYNTHETIC square", "bbox": "0,0,1,1"}).status_code
        == 409
    )
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    assert client.post("/api/aoi", json={"name": "bow", "geojson": bowtie}).status_code == 400
    wide = {
        "type": "Polygon",
        "coordinates": [[[-170, 0], [170, 0], [170, 5], [-170, 5], [-170, 0]]],
    }
    assert (
        "antimeridian"
        in client.post("/api/aoi", json={"name": "wide", "geojson": wide}).json()["detail"]
    )
    assert (
        client.post("/api/aoi", json={"name": "bx", "bbox": "170,-20,-170,-10"}).status_code == 201
    )
    assert [a["name"] for a in client.get("/api/aoi").json()] == ["SYNTHETIC square", "bx"]
    params = {"aoi_id": aoi_id, "start": AREA["start"], "end": AREA["end"]}
    assert client.get("/api/hotspots", params=params).json()["total"] == 2
    assert client.get("/api/hotspots", params=params | {"aoi_id": 999}).status_code == 404


def test_exports(client):
    upload(client)
    csv = client.get("/api/export/csv", params=AREA)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert len(csv.text.strip().splitlines()) == 4  # header + 3
    bundle = client.get("/api/export/csv", params=AREA | {"bundle": "true"})
    names = zipfile.ZipFile(io.BytesIO(bundle.content)).namelist()
    assert len(names) == 2 and any(n.endswith(".provenance.json") for n in names)
    cal = client.get("/api/export/csv", params=AREA | {"kind": "calendar"})
    assert "state" in cal.text.splitlines()[0]
    harm = client.get("/api/export/csv", params=AREA | {"kind": "harmonized_calendar",
                                                        "bundle": "true"})  # fmt: skip
    files = zipfile.ZipFile(io.BytesIO(harm.content))
    csv_name = next(n for n in files.namelist() if n.endswith(".csv"))
    assert "source" in files.read(csv_name).decode().splitlines()[0]
    prov = json.loads(files.read(csv_name + ".provenance.json"))
    assert prov["kind"].startswith("harmonized") and prov["conversion_fits"]
    report = client.get("/api/export/report", params=AREA).json()
    assert report["status"].startswith("EXPERIMENTAL")
    md = client.get("/api/export/report", params=AREA | {"format": "md"})
    assert md.text.startswith("# FIRETRACE")
    tmp = Path(client.settings.processed_data_dir) / "exports_tmp"
    assert not list(tmp.glob("*")), "temporary export files were not cleaned up"


def test_availability_and_firms_fetch_never_leak_key(client):
    avail = client.get("/api/data/availability")
    assert avail.json()["firms"]["available"] is True
    assert FAKE_KEY not in avail.text
    today = datetime.now(UTC).date()
    body = {"sources": ["MODIS_NRT"], "bbox": "-150,-30,-140,-20",
            "start": str(today - timedelta(days=2)), "end": str(today - timedelta(days=1))}  # fmt: skip
    fetched = client.post("/api/ingest/firms", json=body)
    assert fetched.status_code == 200, fetched.text
    window = fetched.json()["windows"][0]
    assert (window["import_status"], window["rows_written"]) == ("completed", 0)
    assert FAKE_KEY not in fetched.text
    local = client.get("/api/data/availability").json()["imported_coverage"]
    assert {c["platform"] for c in local} == {"Terra", "Aqua"}


def test_firms_fetch_validation(client):
    today = datetime.now(UTC).date()
    base = {"sources": ["MODIS_NRT"], "world": True}
    future = base | {"start": str(today), "end": str(today + timedelta(days=3))}
    assert client.post("/api/ingest/firms", json=future).status_code == 400
    too_long = base | {
        "start": str(today - timedelta(days=60)),
        "end": str(today - timedelta(days=1)),
    }
    assert client.post("/api/ingest/firms", json=too_long).status_code == 400
    bad_source = base | {"sources": ["LANDSAT_NRT"], "start": str(today - timedelta(days=2)),
                         "end": str(today - timedelta(days=1))}  # fmt: skip
    assert client.post("/api/ingest/firms", json=bad_source).status_code == 400


def test_firms_fetch_without_key_is_503(client):
    client.settings.firms_map_key = None
    today = datetime.now(UTC).date()
    body = {"sources": ["MODIS_NRT"], "world": True, "start": str(today - timedelta(days=2)),
            "end": str(today - timedelta(days=1))}  # fmt: skip
    assert client.post("/api/ingest/firms", json=body).status_code == 503


def test_openapi_lists_all_spec_endpoints(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    expected = {
        "/api/health", "/api/sensors", "/api/data/availability", "/api/ingest/upload",
        "/api/ingest/firms", "/api/ingest/history", "/api/hotspots", "/api/hotspots/summary",
        "/api/calendar", "/api/calendar/harmonized", "/api/analytics/monthly", "/api/analytics/yearly",
        "/api/analytics/anomalies", "/api/analytics/sensor-comparison", "/api/aoi",
        "/api/export/csv", "/api/export/report",
    }  # fmt: skip
    assert expected <= paths
