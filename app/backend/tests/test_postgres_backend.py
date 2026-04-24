from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

try:
    from testcontainers.postgres import PostgresContainer
except ImportError:  # pragma: no cover - exercised when deps are not installed yet
    PostgresContainer = None

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository, create_backend


def test_create_backend_uses_sqlite_backend_for_sqlite_urls() -> None:
    expected_backend = SimpleNamespace(backend_name="sqlite", supports_snapshots=True)

    with patch("app.backend.app.repository.SQLiteBackend", return_value=expected_backend) as sqlite_backend:
        with patch("app.backend.app.repository.PostgresBackend") as postgres_backend:
            backend = create_backend(
                "sqlite:///D:/AB_TEST/app/backend/data/projects.sqlite3",
                busy_timeout_ms=7000,
                journal_mode="WAL",
                synchronous="NORMAL",
                workspace_signing_key="a" * 16,
                pool_size=12,
            )

    assert backend is expected_backend
    sqlite_backend.assert_called_once()
    postgres_backend.assert_not_called()


def test_create_backend_uses_postgres_backend_for_postgresql_urls() -> None:
    expected_backend = SimpleNamespace(backend_name="postgres", supports_snapshots=False)

    with patch("app.backend.app.repository.SQLiteBackend") as sqlite_backend:
        with patch("app.backend.app.repository.PostgresBackend", return_value=expected_backend) as postgres_backend:
            backend = create_backend(
                "postgresql://postgres:postgres@localhost:5432/abtest",
                busy_timeout_ms=7000,
                journal_mode="WAL",
                synchronous="NORMAL",
                workspace_signing_key="a" * 16,
                pool_size=12,
            )

    assert backend is expected_backend
    sqlite_backend.assert_not_called()
    postgres_backend.assert_called_once()


def test_project_repository_delegates_to_selected_backend() -> None:
    backend = SimpleNamespace(
        backend_name="postgres",
        supports_snapshots=False,
        schema_version=7,
        list_projects=lambda include_archived=False: [{"id": "project-1", "include_archived": include_archived}],
    )

    with patch("app.backend.app.repository.create_backend", return_value=backend) as create_backend_mock:
        repository = ProjectRepository(
            "postgresql://postgres:postgres@localhost:5432/abtest",
            pool_size=12,
        )

    assert repository.backend_name == "postgres"
    assert repository.supports_snapshots is False
    assert repository.schema_version == 7
    assert repository.list_projects(include_archived=True) == [{"id": "project-1", "include_archived": True}]
    create_backend_mock.assert_called_once()


def _require_docker() -> None:
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Docker unavailable")


def _postgres_url(container: PostgresContainer) -> str:
    return container.get_connection_url().replace("+psycopg2", "")


def _payload(name: str, metric_type: str) -> dict:
    return {
        "project": {"project_name": name},
        "hypothesis": {
            "hypothesis_statement": f"{name} hypothesis",
            "change_description": f"{name} change",
        },
        "metrics": {"metric_type": metric_type},
    }


def test_postgres_backend_round_trips_project_reads_and_queries() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    with PostgresContainer("postgres:16-alpine") as postgres:
        repository = ProjectRepository(_postgres_url(postgres), pool_size=4)

        binary_project = repository.create_project(_payload("Binary project", "binary"))
        continuous_project = repository.create_project(_payload("Continuous project", "continuous"))

        assert repository.backend_name == "postgres"
        assert repository.supports_snapshots is False
        assert repository.get_project(binary_project["id"])["project_name"] == "Binary project"
        assert repository.query_projects(metric_type="binary")["projects"][0]["id"] == binary_project["id"]
        assert {project["id"] for project in repository.list_projects(include_archived=True)} == {
            binary_project["id"],
            continuous_project["id"],
        }


def test_postgres_backend_handles_concurrent_writes() -> None:
    if PostgresContainer is None:
        pytest.fail("testcontainers is required for Postgres backend tests")
    _require_docker()

    with PostgresContainer("postgres:16-alpine") as postgres:
        repository = ProjectRepository(_postgres_url(postgres), pool_size=6)

        def create(index: int) -> str:
            created = repository.create_project(_payload(f"Project {index}", "binary"))
            return created["id"]

        with ThreadPoolExecutor(max_workers=4) as executor:
            project_ids = list(executor.map(create, range(8)))

        assert len(project_ids) == 8
        assert len(set(project_ids)) == 8
        assert repository.query_projects(limit=20)["total"] == 8


def test_readyz_uses_postgres_checks_without_sqlite_regression(monkeypatch) -> None:
    monkeypatch.setenv("AB_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/abtest")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    get_settings.cache_clear()

    repository = SimpleNamespace(
        backend_name="postgres",
        supports_snapshots=False,
        schema_version=7,
        has_api_keys=lambda: False,
        set_webhook_service=lambda webhook_service: None,
        get_diagnostics_summary=lambda: {
            "db_path": "postgresql://postgres:postgres@localhost:5432/abtest",
            "db_parent_path": "localhost:5432",
            "db_exists": True,
            "db_size_bytes": 1024,
            "disk_free_bytes": 0,
            "schema_version": 7,
            "sqlite_user_version": 7,
            "busy_timeout_ms": 0,
            "journal_mode": "POSTGRES",
            "synchronous": "READ COMMITTED",
            "write_probe_ok": True,
            "write_probe_detail": "BEGIN succeeded",
            "projects_total": 0,
            "archived_projects_total": 0,
            "analysis_runs_total": 0,
            "export_events_total": 0,
            "project_revisions_total": 0,
            "workspace_bundle_schema_version": 3,
            "workspace_signature_enabled": False,
            "latest_project_updated_at": None,
        },
        close=lambda: None,
    )

    with patch("app.backend.app.main.ProjectRepository", return_value=repository):
        with patch("app.backend.app.main.WebhookService") as webhook_service_cls:
            webhook_service = webhook_service_cls.return_value
            webhook_service.shutdown.return_value = None

            with TestClient(create_app()) as client:
                response = client.get("/readyz")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert any(check["name"] == "postgres_storage" and check["ok"] is True for check in checks)
    assert any(check["name"] == "postgres_write_probe" and check["ok"] is True for check in checks)
    assert not any(check["name"] == "sqlite_journal_mode" for check in checks)
    get_settings.cache_clear()
