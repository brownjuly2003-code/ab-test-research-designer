from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app


def test_health_endpoint_returns_basic_service_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    git_sha = payload.pop("git_sha")
    # The exact value depends on where the build runs (env stamp, git checkout,
    # bare source tree); the contract is that /health always carries one.
    assert isinstance(git_sha, str) and git_sha
    assert payload == {
        "status": "ok",
        "service": "AB Test Research Designer API",
        "version": "1.2.0",
        "environment": "local",
    }


def test_health_git_sha_prefers_env_stamp(monkeypatch) -> None:
    from app.backend.app.config import get_settings

    monkeypatch.setenv("AB_BUILD_SHA", "stamped-sha-123")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        response = client.get("/health")
        assert response.json()["git_sha"] == "stamped-sha-123"
    finally:
        get_settings.cache_clear()
