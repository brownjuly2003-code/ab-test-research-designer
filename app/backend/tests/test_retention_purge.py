"""Retention purge + topology/RED diagnostics (audit F-12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.backend.app.http_runtime import build_runtime_summary, create_runtime_counters
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository


def _repo(tmp_path) -> ProjectRepository:
    db_path = tmp_path / "retention.sqlite3"
    return ProjectRepository(f"sqlite:///{db_path.as_posix()}")


def test_purge_retention_dry_run_and_delete(tmp_path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now(UTC)
    old = (now - timedelta(days=40)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()

    with repo._connect() as connection:  # noqa: SLF001 — test fixture
        connection.execute(
            """
            INSERT INTO projects (
                id, project_name, payload_json, payload_schema_version, created_at, updated_at
            )
            VALUES ('exp-1', 'Retention fixture', '{}', 1, ?, ?)
            """,
            (recent, recent),
        )
        connection.execute(
            """
            INSERT INTO exposures (id, experiment_id, user_id, variation_index, created_at, occurred_at)
            VALUES ('e-old', 'exp-1', 'u1', 0, ?, ?)
            """,
            (old, old),
        )
        connection.execute(
            """
            INSERT INTO exposures (id, experiment_id, user_id, variation_index, created_at, occurred_at)
            VALUES ('e-new', 'exp-1', 'u2', 0, ?, ?)
            """,
            (recent, recent),
        )
        connection.execute(
            """
            INSERT INTO conversions (
                id, experiment_id, user_id, metric, value, idempotency_key, created_at, occurred_at
            )
            VALUES ('c-old', 'exp-1', 'u1', 'primary', 1.0, NULL, ?, ?)
            """,
            (old, old),
        )
        connection.commit()

    cutoff = (now - timedelta(days=30)).isoformat()
    dry = repo.purge_retention_data(
        exposures_before=cutoff,
        conversions_before=cutoff,
        dry_run=True,
    )
    assert dry["exposures"] == 1
    assert dry["conversions"] == 1

    applied = repo.purge_retention_data(
        exposures_before=cutoff,
        conversions_before=cutoff,
        dry_run=False,
    )
    assert applied["exposures"] == 1
    assert applied["conversions"] == 1

    with repo._connect() as connection:  # noqa: SLF001
        remaining = connection.execute("SELECT id FROM exposures ORDER BY id").fetchall()
        ids = [row["id"] if "id" in row.keys() else row[0] for row in remaining]
        assert ids == ["e-new"]


def test_build_runtime_summary_red_fields() -> None:
    counters = create_runtime_counters()
    counters["total_requests"] = 4
    counters["success_responses"] = 3
    counters["client_error_responses"] = 1
    counters["process_time_ms_sum"] = 40.0
    counters["process_time_ms_count"] = 4
    counters["process_time_ms_max"] = 20.0
    summary = build_runtime_summary(counters)
    assert summary["process_time_ms_avg"] == 10.0
    assert summary["process_time_ms_max"] == 20.0
    assert summary["error_rate"] == 0.25


def test_diagnostics_exposes_topology_and_retention(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "diag.sqlite3"
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AB_ENV", "local")
    monkeypatch.setenv("AB_RETENTION_EXPOSURES_DAYS", "90")
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    # Clear cached settings between env mutations.
    from app.backend.app import config as config_module

    config_module.get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/v1/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["topology"]["supported"] == "single_instance"
    assert payload["topology"]["rate_limit_state"] == "in_process"
    assert payload["retention"]["exposures_days"] == 90
    assert payload["retention"]["auto_purge_enabled"] is True
    assert "process_time_ms_avg" in payload["runtime"]
    assert "error_rate" in payload["runtime"]
    config_module.get_settings.cache_clear()
