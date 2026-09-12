from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.backend.app.config import get_settings
from app.backend.app.evidence.abx import BUNDLE_MEDIA_TYPE, verify_bundle
from app.backend.app.evidence.jobs import create_evidence_job
from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.evidence.pipeline import run_protocol
from app.backend.app.evidence.protocol_io import freeze
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from app.backend.app.evidence.storage import EvidenceJobCoordinator
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository
from app.backend.tests.evidence_run_fixtures import completed_asos_run

_ASOS_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evidence" / "asos"


class _MemoryEvidenceRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, CompletedEvidenceRun] = {}

    def create(self, run: CompletedEvidenceRun) -> bool:
        if run.run_id in self.runs:
            return False
        self.runs[run.run_id] = run
        return True

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        return self.runs.get(run_id)


def _supported_asos_protocol() -> dict[str, Any]:
    """The benchmark protocol, edited only as far as `freeze` requires.

    The published ASOS protocol names an analysis method this build does not
    implement, so these four edits are what it takes to run it at all. None of
    them decides whether the run comes back blocked.
    """

    with zipfile.ZipFile(_ASOS_FIXTURE_ROOT / "bundles" / "d53f0e.tmk") as archive:
        protocol: dict[str, Any] = json.loads(archive.read("protocol/protocol.json"))
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    protocol["analysis"]["random_seed"] = 20260901
    protocol["estimand"]["effect_measure"] = "risk_difference"
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = "assignment_v1"
    return protocol


def _run_asos_protocol(protocol: dict[str, Any]) -> CompletedEvidenceRun:
    store = _MemoryEvidenceRunStore()
    build = StatsKernelBuild(
        git_commit="a" * 40,
        build_digest="sha256:"
        + hashlib.sha256(b"persisted-route-test-build").hexdigest(),
        dependency_lock_digest="sha256:"
        + hashlib.sha256(b"persisted-route-test-lock").hexdigest(),
    )
    with patch(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        return_value=build,
    ):
        return run_protocol(
            freeze(protocol),
            _ASOS_FIXTURE_ROOT / "d53f0e.parquet",
            principal="route-test-operator",
            out_store=store,
        )


def _blocked_asos_run() -> CompletedEvidenceRun:
    protocol = _supported_asos_protocol()
    # Dropping the aggregate checkpoint schema is what makes the run report an
    # open finding instead of a proposed decision.
    protocol["telemetry"]["schema_versions"] = [
        schema
        for schema in protocol["telemetry"]["schema_versions"]
        if schema["event_type"] != "aggregate_metric_checkpoint"
    ]
    return _run_asos_protocol(protocol)


def _analysis_asos_run() -> CompletedEvidenceRun:
    """A run that carries a `proposed` decision and no findings."""

    return _run_asos_protocol(_supported_asos_protocol())


def _persist_fixture(
    database_path: Path,
    artifact_root: Path,
    run: CompletedEvidenceRun,
) -> None:
    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        store = LifecycleEvidenceRunStore(repository, artifact_root)
        assert store.create(run) is True
    finally:
        repository.close()


def test_persisted_run_portfolio_detail_bundle_and_decision_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "workbench.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    parent = completed_asos_run()
    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        started_at = datetime.fromisoformat(parent.started_at[:-1] + "+00:00")
        sealed_at = datetime.fromisoformat(parent.sealed_at[:-1] + "+00:00")
        coordinator = EvidenceJobCoordinator(repository.create_evidence_job_store())
        coordinator.create(
            create_evidence_job(
                job_id=parent.origin_job_id,
                kind=parent.kind,
                protocol_revision_id=parent.protocol_revision_id,
                request_digest="sha256:" + "a" * 64,
                created_at=started_at - timedelta(seconds=1),
            )
        )
        coordinator.claim(
            parent.origin_job_id,
            lease_token="worker:persisted-workbench-test",
            now=started_at,
            lease_expires_at=sealed_at + timedelta(days=1),
        )
        assert repository.create_evidence_run_store(artifact_root).create(parent) is True
    finally:
        repository.close()

    try:
        with TestClient(create_app()) as client:
            route_paths = set(client.get("/openapi.json").json()["paths"])
            assert {
                "/api/v2/runs",
                "/api/v2/runs/{run_id}",
                "/api/v2/runs/{run_id}:bundle",
                "/api/v2/runs/{run_id}/decisions",
            } <= route_paths
            assert {
                "/api/v2/workbench",
                "/api/v2/workbench:reset",
                "/api/v2/workbench/findings/{finding_id}:remediate",
                "/api/v2/workbench:rerun",
                "/api/v2/workbench/findings/{finding_id}:override",
                "/api/v2/workbench:bundle",
                "/api/v2/bundles:verify",
                "/api/v2/decisions",
            }.isdisjoint(route_paths)

            portfolio_response = client.get("/api/v2/runs")
            assert portfolio_response.status_code == 200
            portfolio = portfolio_response.json()
            assert [item["run_id"] for item in portfolio["runs"]] == [parent.run_id]
            assert portfolio["runs"][0] == {
                "run_id": parent.run_id,
                "protocol_revision_id": parent.protocol_revision_id,
                "kind": "analysis",
                "status": "succeeded",
                "started_at": parent.started_at,
                "completed_at": parent.completed_at,
                "sealed_at": parent.sealed_at,
                "bundle_id": portfolio["runs"][0]["bundle_id"],
                "verdicts": {
                    "integrity": "pass",
                    "schema_conformance": "pass",
                    "reference_integrity": "pass",
                    "lineage": "pass",
                    "privacy_policy": "pass",
                    "signature": "not_present",
                    "statistical_validity": "not_asserted",
                },
            }

            detail_response = client.get(f"/api/v2/runs/{parent.run_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["run_id"] == parent.run_id
            assert (
                detail["protocol"]["protocol"]["protocol_id"]
                == "asos-public-benchmark-d53f0e"
            )
            assert detail["run"]["run_id"] == parent.run_id
            assert [source["source_snapshot_id"] for source in detail["sources"]] == [
                "source_asos_d53f0e_terminal"
            ]
            assert len(detail["metrics"]) == 4
            assert detail["findings"] == []
            assert len(detail["estimates"]) == 4
            assert detail["decisions"] == []
            assert detail["report_available"] is False
            assert detail["bundle"]["bundle_id"] == portfolio["runs"][0]["bundle_id"]

            missing_response = client.get("/api/v2/runs/run_missing")
            assert missing_response.status_code == 404

            bundle_response = client.get(f"/api/v2/runs/{parent.run_id}:bundle")
            assert bundle_response.status_code == 200
            assert bundle_response.headers["content-type"].startswith(BUNDLE_MEDIA_TYPE)
            assert bundle_response.headers["content-disposition"].endswith(
                f'"{parent.run_id}.tmk"'
            )
            downloaded = tmp_path / "downloaded.tmk"
            downloaded.write_bytes(bundle_response.content)
            verification = verify_bundle(downloaded)
            assert verification["valid"] is True
            assert verification["bundle_id"] == portfolio["runs"][0]["bundle_id"]

            decision_response = client.post(
                f"/api/v2/runs/{parent.run_id}/decisions",
                json={
                    "verdict": "ship",
                    "rationale": "The persisted evidence satisfies the frozen decision policy.",
                },
            )
            assert decision_response.status_code == 201
            child = decision_response.json()
            assert child["run_id"] != parent.run_id
            assert child["run"]["parent_run_id"] == parent.run_id
            assert (
                child["decisions"][0]["decided_by"]["actor_ref"]
                == "local-operator"
            )
            assert child["decisions"][0]["human_verdict"] == "ship"

            updated_portfolio = client.get("/api/v2/runs").json()
            assert [item["run_id"] for item in updated_portfolio["runs"]] == [
                parent.run_id,
                child["run_id"],
            ]
            assert client.get(f"/api/v2/runs/{parent.run_id}").json() == detail
    finally:
        get_settings.cache_clear()


def test_persisted_finding_actions_create_verified_append_only_child_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "finding-actions.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    parent = _blocked_asos_run()
    _persist_fixture(database_path, artifact_root, parent)

    try:
        with TestClient(create_app()) as client:
            original = client.get(f"/api/v2/runs/{parent.run_id}").json()
            assert original["findings"]
            finding_id = original["findings"][0]["finding_id"]
            parent_bundle_id = original["bundle"]["bundle_id"]

            remediated_response = client.post(
                f"/api/v2/runs/{parent.run_id}/findings/{finding_id}:remediate"
            )
            assert remediated_response.status_code == 201
            remediated = remediated_response.json()
            assert remediated["run_id"] != parent.run_id
            assert remediated["run"]["parent_run_id"] == parent.run_id
            remediated_finding = next(
                finding
                for finding in remediated["findings"]
                if finding["finding_id"] == finding_id
            )
            assert remediated_finding["state"] == "resolved"

            override_response = client.post(
                f"/api/v2/runs/{parent.run_id}/findings/{finding_id}:override",
                json={
                    "reason": "The accountable reviewer accepts this known benchmark limitation."
                },
            )
            assert override_response.status_code == 201
            overridden = override_response.json()
            assert overridden["run_id"] not in {parent.run_id, remediated["run_id"]}
            assert overridden["run"]["parent_run_id"] == parent.run_id
            overridden_finding = next(
                finding
                for finding in overridden["findings"]
                if finding["finding_id"] == finding_id
            )
            assert overridden_finding["state"] == "overridden"
            assert overridden_finding["override"]["actor_ref"] == "local-operator"

            assert client.get(f"/api/v2/runs/{parent.run_id}").json() == original
            for child in (remediated, overridden):
                bundle_response = client.get(
                    f"/api/v2/runs/{child['run_id']}:bundle"
                )
                destination = tmp_path / f"{child['run_id']}.tmk"
                destination.write_bytes(bundle_response.content)
                verification = verify_bundle(destination)
                assert verification["valid"] is True
                assert verification["verdicts"]["lineage"] == "pass"
                with zipfile.ZipFile(destination) as archive:
                    manifest: dict[str, Any] = json.loads(
                        archive.read("manifest.json")
                    )
                assert manifest["supersedes"] == parent_bundle_id
    finally:
        get_settings.cache_clear()


def test_finding_not_found_outranks_the_run_state_guards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "finding-not-found.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    blocked = _blocked_asos_run()
    analysis = _analysis_asos_run()
    analysis_roles = {artifact.role for artifact in analysis.artifacts}
    assert "decision" in analysis_roles
    assert "finding" not in analysis_roles
    _persist_fixture(database_path, artifact_root, blocked)
    _persist_fixture(database_path, artifact_root, analysis)

    override_body = {"reason": "The accountable reviewer accepts this limitation."}

    try:
        with TestClient(create_app()) as client:
            decided = client.post(
                f"/api/v2/runs/{analysis.run_id}/decisions",
                json={
                    "verdict": "hold",
                    "rationale": "Held until the follow-up readout lands.",
                },
            )
            assert decided.status_code == 201
            decided_run_id = decided.json()["run_id"]

            # A run whose decision is already recorded, one whose decision the
            # pipeline only proposed, and one still carrying an open finding all
            # answer the same way for a finding_id none of them ever carried.
            for run_id in (blocked.run_id, analysis.run_id, decided_run_id):
                for action, body in (
                    ("remediate", None),
                    ("override", override_body),
                ):
                    response = client.post(
                        f"/api/v2/runs/{run_id}/findings/finding_absent:{action}",
                        json=body,
                    )
                    assert response.status_code == 404, (run_id, action)
                    assert "finding_absent" in response.json()["detail"]

            detail = client.get(f"/api/v2/runs/{blocked.run_id}").json()
            finding_id = detail["findings"][0]["finding_id"]

            # The reordering must not soften the state guard for a finding that
            # is really there: acting on a closed one still conflicts.
            remediated = client.post(
                f"/api/v2/runs/{blocked.run_id}/findings/{finding_id}:remediate"
            )
            assert remediated.status_code == 201
            closed_run_id = remediated.json()["run_id"]
            closed = client.post(
                f"/api/v2/runs/{closed_run_id}/findings/{finding_id}:override",
                json=override_body,
            )
            assert closed.status_code == 409
            assert "open finding" in closed.json()["detail"]
    finally:
        get_settings.cache_clear()
