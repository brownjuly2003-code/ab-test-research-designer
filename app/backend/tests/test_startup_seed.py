from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


@pytest.fixture
def temp_db_path(monkeypatch) -> Path:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_startup_seed_populates_demo_projects_with_analysis_and_export(monkeypatch, temp_db_path) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/projects", params={"status": "all", "limit": 200})
        assert response.status_code == 200
        demo_projects = [
            project
            for project in response.json()["projects"]
            if project["project_name"].startswith("Demo - ")
        ]

        assert len(demo_projects) == 3
        assert all(project["last_analysis_run_id"] is not None for project in demo_projects)

        projects_by_name = {project["project_name"]: project for project in demo_projects}
        checkout_project = projects_by_name["Demo - Checkout Conversion"]

        for project in demo_projects:
            history_response = client.get(f"/api/v1/projects/{project['id']}/history")
            assert history_response.status_code == 200
            history_payload = history_response.json()
            assert history_payload["analysis_total"] == 1
            assert history_payload["analysis_runs"][0]["id"] == project["last_analysis_run_id"]

        checkout_history_response = client.get(f"/api/v1/projects/{checkout_project['id']}/history")
        assert checkout_history_response.status_code == 200
        checkout_history = checkout_history_response.json()
        assert checkout_history["export_total"] >= 1
        assert any(event["format"] == "markdown" for event in checkout_history["export_events"])


def test_startup_seed_is_idempotent_across_restarts(monkeypatch, temp_db_path) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    get_settings.cache_clear()

    app = create_app()

    with TestClient(app):
        pass

    with TestClient(app) as client:
        response = client.get("/api/v1/projects", params={"status": "all", "limit": 200})
        assert response.status_code == 200
        demo_projects = [
            project
            for project in response.json()["projects"]
            if project["project_name"].startswith("Demo - ")
        ]
        assert len(demo_projects) == 3


def test_startup_seed_disabled_does_not_create_projects(monkeypatch, temp_db_path) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/projects", params={"status": "all", "limit": 200})

    assert response.status_code == 200
    assert response.json()["projects"] == []
