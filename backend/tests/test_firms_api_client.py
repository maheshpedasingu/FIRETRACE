"""FIRMS API client and fetch-command tests against a simulated FIRMS server.

No real network calls. Every response body here is SYNTHETIC TEST DATA in the FIRMS
CSV layout, and the MAP_KEY is a fake value.
"""

from datetime import date
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pyarrow")

from sqlalchemy import select  # noqa: E402

from app.cli.fetch_firms import run  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.models import CoverageRecord  # noqa: E402
from app.database.session import make_engine, make_session_factory  # noqa: E402
from app.ingestion.firms_api import (  # noqa: E402
    FirmsApiClient,
    FirmsApiError,
    check_availability,
    download_area,
)
from app.ingestion.firms_api_plan import (  # noqa: E402
    BBox,
    DateWindow,
    TransactionBudget,
    parse_source,
)

FAKE_KEY = "fa4efa4efa4efa4efa4efa4efa4efa4e"  # SYNTHETIC
VIIRS_HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
MODIS_HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n"
VIIRS_ROW = "15.1,80.2,330.1,0.4,0.4,{d},0130,N20,VIIRS,n,2.0NRT,290.0,4.2,N\n"
AVAILABILITY = "data_id,min_date,max_date\nVIIRS_NOAA20_NRT,2026-08-01,2026-11-13\nMODIS_NRT,2026-08-01,2026-11-13\n"


class FakeFirms:
    """Simulated FIRMS endpoints; records every request path."""

    def __init__(self, failures_before_success: int = 0, status: int = 503):
        self.paths: list[str] = []
        self.failures = failures_before_success
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if self.failures > 0:
            self.failures -= 1
            return httpx.Response(self.status, text="temporarily unavailable")
        if "/data_availability/" in path:
            return httpx.Response(200, text=AVAILABILITY)
        if "/area/csv/" in path:
            parts = path.split("/")
            source, start = parts[-4], parts[-1]
            if source.startswith("MODIS"):
                return httpx.Response(200, text=MODIS_HEADER)  # no detections
            return httpx.Response(200, text=VIIRS_HEADER + VIIRS_ROW.format(d=start))
        return httpx.Response(404, text="unknown path")


def make_client(handler, retries=2, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    budget = TransactionBudget(5000, 600, sleep=sleeps.append)
    return FirmsApiClient(
        FAKE_KEY,
        base_url="https://firms.example/api",
        timeout=5,
        max_retries=retries,
        budget=budget,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )


def test_area_request_path_matches_documented_shape():
    fake = FakeFirms()
    with make_client(fake) as client:
        body = client.area_csv(
            parse_source("VIIRS_NOAA20_NRT"), "76,12,85,20", DateWindow(date(2026, 11, 1), 5)
        )
    assert body.startswith(b"latitude")
    assert fake.paths == [f"/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/76,12,85,20/5/2026-11-01"]


def test_retries_on_503_then_succeeds():
    fake = FakeFirms(failures_before_success=2)
    sleeps: list[float] = []
    with make_client(fake, retries=2, sleeps=sleeps) as client:
        client.area_csv(parse_source("VIIRS_NOAA20_NRT"), "world", DateWindow(date(2026, 11, 1), 1))
    assert len(fake.paths) == 3
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_retries_and_never_leaks_key():
    fake = FakeFirms(failures_before_success=10)
    with make_client(fake, retries=1) as client, pytest.raises(FirmsApiError) as err:
        client.area_csv(parse_source("MODIS_NRT"), "world", DateWindow(date(2026, 11, 1), 1))
    assert "after 2 attempts" in str(err.value)
    assert FAKE_KEY not in str(err.value)


def test_client_error_fails_immediately_with_redacted_message():
    def handler(request):
        return httpx.Response(400, text=f"Invalid MAP_KEY {FAKE_KEY}")

    with make_client(handler) as client, pytest.raises(FirmsApiError) as err:
        client.area_csv(parse_source("MODIS_NRT"), "world", DateWindow(date(2026, 11, 1), 1))
    assert "HTTP 400" in str(err.value)
    assert FAKE_KEY not in str(err.value)


@pytest.mark.parametrize("body", ["", "   \n", "Invalid request"])
def test_empty_or_non_csv_response_is_an_error_not_zero(body):
    with make_client(lambda r: httpx.Response(200, text=body)) as client:
        with pytest.raises(FirmsApiError):
            client.area_csv(parse_source("MODIS_NRT"), "world", DateWindow(date(2026, 11, 1), 1))


def test_missing_key_is_rejected_before_any_request():
    with pytest.raises(FirmsApiError, match="not configured"):
        FirmsApiClient(
            "",
            base_url="https://firms.example/api",
            timeout=5,
            max_retries=0,
            budget=TransactionBudget(10, 60),
        )


def test_availability_parsing_and_window_check():
    with make_client(FakeFirms()) as client:
        rows = client.data_availability()
    source = parse_source("VIIRS_NOAA20_NRT")
    assert check_availability(rows, source, DateWindow(date(2026, 11, 1), 5)) is None
    with pytest.raises(FirmsApiError, match="available"):
        check_availability(rows, source, DateWindow(date(2026, 7, 1), 5))
    warning = check_availability(
        rows, parse_source("VIIRS_NOAA21_NRT"), DateWindow(date(2026, 11, 1), 1)
    )
    assert "could not be confirmed" in warning


def test_download_is_resumable(tmp_path: Path):
    fake = FakeFirms()
    source = parse_source("VIIRS_NOAA20_NRT")
    with make_client(fake) as client:
        first = download_area(
            client, source, BBox(76, 12, 85, 20), date(2026, 11, 1), date(2026, 11, 7), tmp_path, 5
        )
        calls = len(fake.paths)
        second = download_area(
            client, source, BBox(76, 12, 85, 20), date(2026, 11, 1), date(2026, 11, 7), tmp_path, 5
        )
    assert [w.window.days for w in first] == [5, 2]
    assert not any(w.reused for w in first) and all(w.reused for w in second)
    assert len(fake.paths) == calls  # nothing downloaded again
    assert first[0].path.read_bytes().startswith(b"latitude")


def test_fetch_command_downloads_imports_and_records_api_coverage(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        firms_map_key=FAKE_KEY,
        firms_api_base="https://firms.example/api",
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}",
        raw_data_dir=str(tmp_path / "raw"),
        processed_data_dir=str(tmp_path / "processed"),
        firms_area_max_day_range=5,
    )
    transport = httpx.MockTransport(FakeFirms())
    lines: list[str] = []
    argv = [
        "--source", "VIIRS_NOAA20_NRT", "--source", "MODIS_NRT",
        "--bbox", "76,12,85,20", "--start", "2026-11-01", "--end", "2026-11-02",
    ]  # fmt: skip
    code = run(
        argv, settings=settings, transport=transport, today=date(2026, 11, 14), out=lines.append
    )
    assert code == 0, lines
    assert sum("COMPLETED" in line for line in lines) == 2

    sessions = make_session_factory(make_engine(settings.database_url))
    with sessions() as s:
        rows = s.scalars(select(CoverageRecord)).all()
    covered = sorted((r.platform, r.processing_status, r.basis) for r in rows)
    # MODIS window had zero detections, but Terra and Aqua are still covered:
    assert covered == [
        ("Aqua", "NRT", "api_request"),
        ("NOAA-20", "NRT", "api_request"),
        ("Terra", "NRT", "api_request"),
    ]

    # Running the same command again changes nothing.
    lines2: list[str] = []
    run(argv, settings=settings, transport=transport, today=date(2026, 11, 14), out=lines2.append)
    assert sum("SKIPPED_DUPLICATE_FILE" in line for line in lines2) == 2


def test_fetch_command_rejects_future_end_date(tmp_path: Path):
    settings = Settings(_env_file=None, firms_map_key=FAKE_KEY)
    lines: list[str] = []
    argv = ["--source", "MODIS_NRT", "--world", "--start", "2026-11-14", "--end", "2026-11-20"]
    code = run(argv, settings=settings, today=date(2026, 11, 14), out=lines.append)
    assert code == 2 and "future" in lines[0]


def test_fetch_command_without_key_explains_setup():
    lines: list[str] = []
    code = run(
        ["--availability"], settings=Settings(_env_file=None, firms_map_key=None), out=lines.append
    )
    assert code == 2 and "not configured" in lines[0]
