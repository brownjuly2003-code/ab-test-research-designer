"""One artifact root, resolved once, shared by the CLI and the API.

Three call sites used to hold their own ``Path(".trialmark") / "artifacts"``.
That path resolves against the current working directory, so a CLI run and an
API server started from different directories wrote and read two different
trees, and ``GET /api/v2/runs/{id}:bundle`` answered 404 for a run that had
just succeeded (audit F-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backend.app.config import DEFAULT_ARTIFACT_ROOT, get_settings
from app.backend.app.evidence.cli import _artifact_root
from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository
from app.backend.tests.evidence_run_fixtures import completed_asos_run


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN", "AB_ARTIFACT_ROOT"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def test_artifact_root_defaults_to_the_working_directory_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    root = get_settings().artifact_root

    assert root.is_absolute()
    assert root == (tmp_path / DEFAULT_ARTIFACT_ROOT).resolve()
    get_settings.cache_clear()


def test_artifact_root_env_var_is_resolved_to_an_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A relative override is still pinned once, not re-resolved per call site."""
    _clean_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", "evidence/artifacts")
    get_settings.cache_clear()

    root = get_settings().artifact_root

    assert root == (tmp_path / "evidence" / "artifacts").resolve()
    get_settings.cache_clear()


def test_artifact_root_ignores_a_blank_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", "   ")
    get_settings.cache_clear()

    assert get_settings().artifact_root == (tmp_path / DEFAULT_ARTIFACT_ROOT).resolve()
    get_settings.cache_clear()


def test_cli_artifact_root_falls_back_to_the_configured_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    assert _artifact_root(None) == (tmp_path / "artifacts").resolve()
    get_settings.cache_clear()


def test_cli_explicit_artifact_root_still_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", str(tmp_path / "configured"))
    get_settings.cache_clear()

    assert _artifact_root(tmp_path / "explicit") == tmp_path / "explicit"
    get_settings.cache_clear()


def test_api_serves_a_run_written_from_another_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The F-05 regression: the server no longer has to be started where the run was made."""
    database_path = tmp_path / "workbench.sqlite3"
    artifact_root = tmp_path / "shared" / "artifacts"
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()

    run = completed_asos_run()
    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        assert LifecycleEvidenceRunStore(repository, artifact_root).create(run) is True
    finally:
        repository.close()

    _clean_env(monkeypatch)
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_ARTIFACT_ROOT", str(artifact_root))
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            response = client.get(f"/api/v2/runs/{run.run_id}:bundle")
            readiness = client.get("/readyz").json()
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    artifact_check = next(check for check in readiness["checks"] if check["name"] == "artifact_root")
    assert artifact_check["ok"] is True
    assert str(artifact_root.resolve()) in artifact_check["detail"]


def test_readiness_reports_an_unwritable_artifact_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A root whose nearest existing ancestor is a file cannot ever be created."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")

    _clean_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_ARTIFACT_ROOT", str(blocker / "artifacts"))
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            payload = client.get("/readyz").json()
    finally:
        get_settings.cache_clear()

    artifact_check = next(check for check in payload["checks"] if check["name"] == "artifact_root")
    assert artifact_check["ok"] is False
    assert "not a directory" in artifact_check["detail"]
    assert payload["status"] == "degraded"
