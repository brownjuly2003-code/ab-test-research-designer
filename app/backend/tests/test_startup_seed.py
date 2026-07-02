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

        assert len(demo_projects) == 4
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


def _demo_by_name(client: TestClient, name: str) -> dict:
    projects = client.get("/api/v1/projects", params={"status": "all", "limit": 200}).json()["projects"]
    return next(project for project in projects if project["project_name"] == name)


def test_startup_seed_is_idempotent_across_restarts(monkeypatch, temp_db_path) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    get_settings.cache_clear()

    app = create_app()

    # First startup seeds the design demos and their execution data.
    with TestClient(app) as client:
        checkout = _demo_by_name(client, "Demo - Checkout Conversion")
        first_ingestion = client.get(f"/api/v1/experiments/{checkout['id']}/ingestion").json()
    assert first_ingestion["exposures_total"] > 0
    assert first_ingestion["conversions_total"] > 0

    # Second startup must not duplicate projects or re-ingest execution events.
    with TestClient(app) as client:
        response = client.get("/api/v1/projects", params={"status": "all", "limit": 200})
        assert response.status_code == 200
        demo_projects = [
            project
            for project in response.json()["projects"]
            if project["project_name"].startswith("Demo - ")
        ]
        assert len(demo_projects) == 4

        checkout = _demo_by_name(client, "Demo - Checkout Conversion")
        second_ingestion = client.get(f"/api/v1/experiments/{checkout['id']}/ingestion").json()
    assert second_ingestion["exposures_total"] == first_ingestion["exposures_total"]
    assert second_ingestion["conversions_total"] == first_ingestion["conversions_total"]


def test_startup_seed_populates_live_execution_blocks(monkeypatch, temp_db_path) -> None:
    """The seeded demos expose the live-stats surface on the default demo path (T5.1)."""
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        checkout = _demo_by_name(client, "Demo - Checkout Conversion")
        pricing = _demo_by_name(client, "Demo - Pricing Sensitivity")
        onboarding = _demo_by_name(client, "Demo - Onboarding Completion")

        # --- Checkout: the flagship binary demo lights up the full execution surface ---
        live = client.get(f"/api/v1/experiments/{checkout['id']}/live-stats").json()
        decision = client.get(f"/api/v1/experiments/{checkout['id']}/decision").json()
        assert live["srm"]["status"] == "ok"
        # The demo design is sized for the effect its seeded data demonstrates, so this ship is a
        # *planned* fixed-horizon read — not a peek the decision guard would (rightly) refuse.
        assert live["sequential"]["information_fraction"] == 1.0
        assert decision["verdict"] == "ship"
        assert decision["confidence"] == "high"
        assert live["guardrail"]["status"] == "ok"
        assert live["holdout"]["status"] == "ok"
        assert live["stratified"]["status"] == "available"
        assert live["identity_resolution"]["status"] == "active"
        assert live["identity_resolution"]["linked_identities"] == 60
        assert live["exclusions"]["status"] == "active"
        assert live["exclusions"]["total_filtered"] == 9
        assert live["exclusions"]["manual_filtered"] == 8
        assert live["exclusions"]["rate_spike_filtered"] == 1
        assert live["event_timing"]["late"] == 12
        assert live["event_timing"]["out_of_order"] == 3

        # --- Pricing: the continuous demo lights up CUPED + post-stratification ---
        live = client.get(f"/api/v1/experiments/{pricing['id']}/live-stats").json()
        decision = client.get(f"/api/v1/experiments/{pricing['id']}/decision").json()
        assert decision["verdict"] == "ship"
        assert live["cuped"]["status"] == "available"
        assert live["cuped"]["variance_reduction_pct"] > 10.0
        assert live["stratified"]["status"] == "available"
        assert live["guardrail"]["status"] == "ok"

        # --- Onboarding: deliberately inconclusive (honest "still monitoring" state) ---
        decision = client.get(f"/api/v1/experiments/{onboarding['id']}/decision").json()
        assert decision["verdict"] == "keep_running"

        # --- Feed Ad CTR: the ratio demo lights up the delta-method live block (T3.1) ---
        ctr = _demo_by_name(client, "Demo - Feed Ad Click-Through Ratio")
        live = client.get(f"/api/v1/experiments/{ctr['id']}/live-stats").json()
        assert live["metric_type"] == "ratio"
        assert live["srm"]["status"] == "ok"
        comparison = live["comparisons"][0]
        assert comparison["treatment"]["ratio"] > comparison["control"]["ratio"]
        assert comparison["analysis"]["is_significant"] is True
        assert comparison["always_valid"]["is_significant"] is True
        # This demo deliberately stays an *early* read: the ship verdict flows through the
        # anytime-valid path (confidence capped at medium), showcasing the legitimate early stop.
        decision = client.get(f"/api/v1/experiments/{ctr['id']}/decision").json()
        assert decision["verdict"] == "ship"
        assert decision["confidence"] == "medium"
        assert any(reason["code"] == "anytime_valid_confirmed" for reason in decision["reasons"])


def test_startup_seed_disabled_does_not_create_projects(monkeypatch, temp_db_path) -> None:
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "false")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/projects", params={"status": "all", "limit": 200})

    assert response.status_code == 200
    assert response.json()["projects"] == []


def test_restore_keeps_demo_seed_enabled_for_execution_top_up(monkeypatch, temp_db_path) -> None:
    """A restored snapshot must NOT disable the demo seed.

    ``seed_demo_workspace`` is idempotent and tops up execution data (and any newly
    added demo) on top of the restore, so a snapshot predating the execution seed
    (Phase 5) does not leave the hosted demo's live-stats surface empty. Regression
    guard for the ``main.lifespan`` restore branch.
    """
    monkeypatch.setenv("AB_SEED_DEMO_ON_STARTUP", "true")
    monkeypatch.setenv("AB_HF_SNAPSHOT_REPO", "fake/snapshot-repo")
    monkeypatch.setenv("AB_HF_TOKEN", "fake-token")
    # Disable the periodic push loop; the final shutdown push uses the fake below.
    monkeypatch.setenv("AB_HF_SNAPSHOT_INTERVAL_SECONDS", "0")
    get_settings.cache_clear()

    class _FakeSnapshotService:
        """restore_latest() reports success without touching the DB — models a
        restored snapshot that predates the execution seed (designs only / empty)."""

        last_restored_commit = "deadbeef"

        def __init__(self, **_kwargs: object) -> None:
            pass

        async def restore_latest(self) -> bool:
            return True

        async def push_snapshot(self) -> None:
            return None

    monkeypatch.setattr("app.backend.app.main.SnapshotService", _FakeSnapshotService)

    with TestClient(create_app()) as client:
        demo_projects = [
            project
            for project in client.get(
                "/api/v1/projects", params={"status": "all", "limit": 200}
            ).json()["projects"]
            if project["project_name"].startswith("Demo - ")
        ]
        # Seed still ran despite the successful restore.
        assert len(demo_projects) == 4

        checkout = _demo_by_name(client, "Demo - Checkout Conversion")
        ingestion = client.get(f"/api/v1/experiments/{checkout['id']}/ingestion").json()

    # Execution data was topped up after the restore (live-stats surface populated).
    assert ingestion["exposures_total"] > 0
    assert ingestion["conversions_total"] > 0
