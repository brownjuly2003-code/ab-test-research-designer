from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backend.app.config import get_settings
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from app.backend.app.main import create_app

_TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:"
    + hashlib.sha256(b"workbench-seed-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"workbench-seed-test-lock").hexdigest(),
)


@pytest.fixture(autouse=True)
def _stable_stats_kernel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        lambda: _TEST_BUILD,
    )


def test_demo_startup_seeds_three_persisted_asos_runs_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbench-seed.sqlite3"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_ENV", "local")
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.delenv("AB_DATABASE_URL", raising=False)
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "app.backend.app.main.seed_demo_workspace",
        lambda _settings, _repository: None,
    )
    get_settings.cache_clear()

    app = create_app()
    try:
        with TestClient(app) as client:
            first = client.get("/api/v2/runs").json()
            assert len(first["runs"]) == 3
            assert all(
                run["verdicts"]["lineage"] == "pass" for run in first["runs"]
            )
            details = [
                client.get(f"/api/v2/runs/{run['run_id']}").json()
                for run in first["runs"]
            ]
            assert {
                detail["protocol"]["protocol"]["protocol_id"]
                for detail in details
            } == {
                "asos-public-benchmark-26bd38",
                "asos-public-benchmark-834947",
                "asos-public-benchmark-d53f0e",
            }
            assert all(detail["report_available"] is True for detail in details)

        with TestClient(app) as client:
            second = client.get("/api/v2/runs").json()

        assert second == first
    finally:
        get_settings.cache_clear()
