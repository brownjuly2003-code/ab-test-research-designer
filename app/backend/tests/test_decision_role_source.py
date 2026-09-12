"""Where a deciding role comes from, and what happens when it cannot be honoured.

A decision record has always named the role its author acted in. Until now that
role had exactly one source -- the frozen policy's first entry -- and the record
could not say so. These tests pin the three sources apart: a role carried by an
issued API key (`credential`), a role the caller states about itself
(`asserted`), and no role at all (`policy_default`). They also pin the two
refusals: a role outside the policy, and a policy that wants more approvals than
one call can record.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.backend.app.config import get_settings
from app.backend.app.evidence.cli import main
from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.evidence.pipeline import run_protocol
from app.backend.app.evidence.protocol_io import freeze
from app.backend.app.evidence.report import render_report_html
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository

ASOS_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evidence" / "asos"
SOURCE_PATH = ASOS_FIXTURE_ROOT / "d53f0e.parquet"
ADMIN_TOKEN = "test-admin-token-role-source"
POLICY_ROLE = "benchmark_reviewer"
SECOND_ROLE = "accountable_owner"


def _supported_protocol() -> dict[str, Any]:
    with zipfile.ZipFile(ASOS_FIXTURE_ROOT / "bundles" / "d53f0e.tmk") as archive:
        protocol: dict[str, Any] = json.loads(archive.read("protocol/protocol.json"))
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    protocol["analysis"]["random_seed"] = 20260901
    protocol["estimand"]["effect_measure"] = "risk_difference"
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = "assignment_v1"
    assert protocol["decision"]["approval_policy"] == {
        "roles": [POLICY_ROLE],
        "minimum_approvals": 1,
    }
    return protocol


def _quorum_protocol() -> dict[str, Any]:
    protocol = _supported_protocol()
    # Two roles, because preflight blocks a policy asking for more approvals
    # than it has roles -- that would be a finding, not a decidable run.
    protocol["decision"]["approval_policy"] = {
        "roles": [POLICY_ROLE, SECOND_ROLE],
        "minimum_approvals": 2,
    }
    return protocol


def _write_protocol(path: Path, protocol: dict[str, Any]) -> Path:
    path.write_bytes(
        yaml.safe_dump(protocol, allow_unicode=True, sort_keys=True).encode("utf-8")
    )
    return path


class _MemoryRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, CompletedEvidenceRun] = {}

    def create(self, run: CompletedEvidenceRun) -> bool:
        if run.run_id in self.runs:
            return False
        self.runs[run.run_id] = run
        return True

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        return self.runs.get(run_id)


def _analysis_run(protocol: dict[str, Any]) -> CompletedEvidenceRun:
    build = StatsKernelBuild(
        git_commit="a" * 40,
        build_digest="sha256:" + hashlib.sha256(b"role-source-build").hexdigest(),
        dependency_lock_digest="sha256:" + hashlib.sha256(b"role-source-lock").hexdigest(),
    )
    with patch(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        return_value=build,
    ):
        run = run_protocol(
            freeze(protocol),
            SOURCE_PATH,
            principal="role-source-test",
            out_store=_MemoryRunStore(),
        )
    assert run.kind == "analysis"
    return run


def _persist(database_path: Path, artifact_root: Path, run: CompletedEvidenceRun) -> None:
    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        assert LifecycleEvidenceRunStore(repository, artifact_root).create(run) is True
    finally:
        repository.close()


def _decision_document(archive_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        envelope = json.loads(archive.read("decision/statement.dsse.json"))
    statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
    return cast(dict[str, Any], statement["predicate"])


def _cli_environment(
    monkeypatch: pytest.MonkeyPatch,
    database_path: Path,
) -> None:
    monkeypatch.delenv("AB_DATABASE_URL", raising=False)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.delenv("USER", raising=False)
    get_settings.cache_clear()


def _cli_analysis_run(
    tmp_path: Path,
    protocol: dict[str, Any],
    artifact_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> str:
    protocol_path = _write_protocol(tmp_path / "protocol.yaml", protocol)
    assert (
        main(
            [
                "run",
                "--protocol",
                str(protocol_path),
                "--source",
                str(SOURCE_PATH),
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(tmp_path / "analysis.tmk"),
            ]
        )
        == 0
    )
    return cast(str, json.loads(capsys.readouterr().out)["run_id"])


def _decide_arguments(
    run_id: str,
    artifact_root: Path,
    destination: Path,
    *,
    role: str | None = None,
) -> list[str]:
    arguments = [
        "decide",
        "--run",
        run_id,
        "--verdict",
        "ship",
        "--rationale",
        "The verified evidence satisfies the frozen decision policy.",
        "--artifact-root",
        str(artifact_root),
        "--out",
        str(destination),
    ]
    if role is not None:
        arguments += ["--role", role]
    return arguments


def test_cli_decide_without_a_role_records_role_source_policy_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _cli_environment(monkeypatch, tmp_path / "trialmark.sqlite3")
    try:
        run_id = _cli_analysis_run(tmp_path, _supported_protocol(), artifact_root, capsys)
        destination = tmp_path / "decision.tmk"
        assert main(_decide_arguments(run_id, artifact_root, destination)) == 0
        assert json.loads(capsys.readouterr().out)["valid"] is True
    finally:
        get_settings.cache_clear()

    decided_by = _decision_document(destination)["decided_by"]
    assert decided_by == {
        "actor_ref": "local-operator",
        "role": POLICY_ROLE,
        "role_source": "policy_default",
    }


def test_cli_decide_with_a_policy_role_records_role_source_asserted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _cli_environment(monkeypatch, tmp_path / "trialmark.sqlite3")
    try:
        run_id = _cli_analysis_run(tmp_path, _supported_protocol(), artifact_root, capsys)
        destination = tmp_path / "decision.tmk"
        assert (
            main(_decide_arguments(run_id, artifact_root, destination, role=POLICY_ROLE))
            == 0
        )
        assert json.loads(capsys.readouterr().out)["valid"] is True
    finally:
        get_settings.cache_clear()

    # Same role as the policy default resolves to, but the record says the
    # caller named it. Nothing on this path verifies the claim.
    assert _decision_document(destination)["decided_by"] == {
        "actor_ref": "local-operator",
        "role": POLICY_ROLE,
        "role_source": "asserted",
    }


def test_cli_decide_with_an_unlisted_role_reports_role_not_permitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _cli_environment(monkeypatch, tmp_path / "trialmark.sqlite3")
    destination = tmp_path / "decision.tmk"
    try:
        run_id = _cli_analysis_run(tmp_path, _supported_protocol(), artifact_root, capsys)
        assert (
            main(_decide_arguments(run_id, artifact_root, destination, role="impostor"))
            == 1
        )
        payload = json.loads(capsys.readouterr().out)
    finally:
        get_settings.cache_clear()

    assert payload["valid"] is False
    assert payload["error"]["code"] == "role_not_permitted"
    assert "impostor" in payload["error"]["message"]
    assert not destination.exists()


def test_cli_decide_reports_approval_quorum_unmet_when_the_policy_wants_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "artifacts"
    _cli_environment(monkeypatch, tmp_path / "trialmark.sqlite3")
    destination = tmp_path / "decision.tmk"
    try:
        run_id = _cli_analysis_run(tmp_path, _quorum_protocol(), artifact_root, capsys)
        assert main(_decide_arguments(run_id, artifact_root, destination)) == 1
        payload = json.loads(capsys.readouterr().out)
    finally:
        get_settings.cache_clear()

    assert payload["valid"] is False
    assert payload["error"]["code"] == "approval_quorum_unmet"
    assert "2 approvals" in payload["error"]["message"]
    # The refusal is the whole point: no half-approved bundle is written.
    assert not destination.exists()


def _api_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    database_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AB_DATABASE_URL", raising=False)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_ADMIN_TOKEN", ADMIN_TOKEN)
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _issue_key(client: TestClient, *, role: str | None) -> str:
    payload: dict[str, Any] = {"name": "decider", "scope": "write"}
    if role is not None:
        payload["role"] = role
    response = client.post(
        "/api/v1/keys",
        json=payload,
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == role
    return cast(str, body["plaintext_key"])


def _decide_over_http(client: TestClient, run_id: str, key: str) -> Any:
    return client.post(
        f"/api/v2/runs/{run_id}/decisions",
        json={
            "verdict": "ship",
            "rationale": "The verified evidence satisfies the frozen decision policy.",
        },
        headers={"Authorization": f"Bearer {key}"},
    )


def test_api_key_role_records_role_source_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "credential.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    run = _analysis_run(_supported_protocol())
    _persist(database_path, artifact_root, run)
    _api_environment(monkeypatch, tmp_path, database_path)

    try:
        with TestClient(create_app()) as client:
            key = _issue_key(client, role=POLICY_ROLE)
            response = _decide_over_http(client, run.run_id, key)
            assert response.status_code == 201, response.text
            decided_by = response.json()["decisions"][0]["decided_by"]
    finally:
        get_settings.cache_clear()

    assert decided_by["actor_ref"] == "decider"
    assert decided_by["role"] == POLICY_ROLE
    assert decided_by["role_source"] == "credential"


def test_api_key_without_a_role_records_role_source_policy_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "default.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    run = _analysis_run(_supported_protocol())
    _persist(database_path, artifact_root, run)
    _api_environment(monkeypatch, tmp_path, database_path)

    try:
        with TestClient(create_app()) as client:
            key = _issue_key(client, role=None)
            response = _decide_over_http(client, run.run_id, key)
            assert response.status_code == 201, response.text
            decided_by = response.json()["decisions"][0]["decided_by"]
    finally:
        get_settings.cache_clear()

    assert decided_by["role"] == POLICY_ROLE
    assert decided_by["role_source"] == "policy_default"


def test_api_key_with_an_unlisted_role_is_role_not_permitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "impostor.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    run = _analysis_run(_supported_protocol())
    _persist(database_path, artifact_root, run)
    _api_environment(monkeypatch, tmp_path, database_path)

    try:
        with TestClient(create_app()) as client:
            key = _issue_key(client, role="impostor")
            response = _decide_over_http(client, run.run_id, key)
            assert response.status_code == 403, response.text
            body = response.json()
            # The run is unchanged: a refused role records nothing.
            portfolio = client.get(
                "/api/v2/runs",
                headers={"Authorization": f"Bearer {key}"},
            ).json()
    finally:
        get_settings.cache_clear()

    assert body["error_code"] == "role_not_permitted"
    assert [item["run_id"] for item in portfolio["runs"]] == [run.run_id]


def test_api_decision_reports_approval_quorum_unmet_with_409(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "quorum.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    run = _analysis_run(_quorum_protocol())
    _persist(database_path, artifact_root, run)
    _api_environment(monkeypatch, tmp_path, database_path)

    try:
        with TestClient(create_app()) as client:
            key = _issue_key(client, role=POLICY_ROLE)
            response = _decide_over_http(client, run.run_id, key)
            assert response.status_code == 409, response.text
            body = response.json()
    finally:
        get_settings.cache_clear()

    assert body["error_code"] == "approval_quorum_unmet"
    assert "2 approvals" in body["detail"]


def test_role_source_survives_a_database_created_before_the_role_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / f"legacy-{uuid.uuid4().hex}.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        # The api_keys table exactly as it was shipped before the role column.
        # CREATE TABLE IF NOT EXISTS is a no-op on it, so only the migration
        # can supply the column.
        connection.execute(
            """
            CREATE TABLE api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                rate_limit_requests INTEGER,
                rate_limit_window_seconds INTEGER
            )
            """
        )

    repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
    try:
        issued = repository.create_api_key(
            name="upgraded",
            scope="write",
            role=POLICY_ROLE,
        )
        authenticated = repository.authenticate_api_key(issued["plaintext_key"])
    finally:
        repository.close()

    with closing(sqlite3.connect(database_path)) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(api_keys)").fetchall()
        }

    assert "role" in columns
    assert issued["role"] == POLICY_ROLE
    assert authenticated is not None
    assert authenticated["role"] == POLICY_ROLE


def test_report_html_names_the_role_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "report.sqlite3"
    artifact_root = tmp_path / ".trialmark" / "artifacts"
    run = _analysis_run(_supported_protocol())
    _persist(database_path, artifact_root, run)
    _api_environment(monkeypatch, tmp_path, database_path)

    try:
        with TestClient(create_app()) as client:
            key = _issue_key(client, role=POLICY_ROLE)
            response = _decide_over_http(client, run.run_id, key)
            assert response.status_code == 201, response.text
            child_run_id = response.json()["run_id"]
            repository = ProjectRepository(f"sqlite:///{database_path.as_posix()}")
            try:
                store = LifecycleEvidenceRunStore(repository, artifact_root)
                child = store.get(child_run_id)
            finally:
                repository.close()
    finally:
        get_settings.cache_clear()

    assert child is not None
    report = render_report_html(child).decode("utf-8")
    assert "<dt>Decided by</dt>" in report
    assert "credential: role carried by the issued credential" in report
    assert "decider" in report
