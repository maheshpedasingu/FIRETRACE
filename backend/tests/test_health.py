"""Health endpoint tests.

The MAP_KEY value below is SYNTHETIC TEST DATA, not a real credential.
"""

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

SYNTHETIC_KEY = "SYNTHETIC-TEST-KEY-NOT-REAL-0000"


def _client(settings: Settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_ok_without_key():
    client = _client(Settings(_env_file=None, firms_map_key=None))
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "FIRETRACE"
    assert body["firms_map_key_configured"] is False


def test_health_reports_key_configured_but_never_exposes_it():
    client = _client(Settings(_env_file=None, firms_map_key=SYNTHETIC_KEY))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["firms_map_key_configured"] is True
    assert SYNTHETIC_KEY not in response.text


def test_empty_key_counts_as_not_configured():
    settings = Settings(_env_file=None, firms_map_key="")
    assert settings.firms_map_key_configured is False


def test_openapi_schema_available():
    client = _client(Settings(_env_file=None))
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
