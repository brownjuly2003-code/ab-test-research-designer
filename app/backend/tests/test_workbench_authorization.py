"""Principal-bound authorization for workbench decisions and finding overrides.

Covers docs/specs/workbench-authorization.md: the recorded actor comes from the
authenticated principal (never from the request body), and a principal whose role
is outside the run's frozen ``decision.approval_policy.roles`` is refused with
HTTP 403 / ``role_not_permitted`` — distinguishable from a 409 state conflict.

Two ASOS fixtures are needed: human decisions require a completed ``analysis``
run, finding overrides require a ``preflight`` run that still carries an open
finding. Both are served by the same app so one client exercises both routes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.app.config import get_settings
from app.backend.app.evidence.decisions import (
    RoleNotPermittedError,
    record_human_decision,
)
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.http_runtime import Principal
from app.backend.app.main import create_app
from app.backend.tests.evidence_run_fixtures import completed_asos_run
from app.backend.tests.test_persisted_workbench_routes import (
    _blocked_asos_run,
    _MemoryEvidenceRunStore,
    _persist_fixture,
)

_DECISIONS_PATH = "/api/v2/runs/{run_id}/decisions"

# The ASOS benchmark protocol freezes exactly one approval role.
_PERMITTED_ROLE = "benchmark_reviewer"

_RATIONALE = "The persisted evidence satisfies the frozen decision policy."
_REASON = "The accountable reviewer accepts this known benchmark limitation."


@pytest.fixture(scope="module")
def analysis_run() -> CompletedEvidenceRun:
    """A completed analysis run: the only kind a human decision may target."""

    return completed_asos_run()


@pytest.fixture(scope="module")
def preflight_run() -> CompletedEvidenceRun:
    """A pre-decision run carrying one open finding, the override target."""

    return _blocked_asos_run()


@contextmanager
def _serve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runs: tuple[CompletedEvidenceRun, ...],
) -> Iterator[tuple[FastAPI, TestClient]]:
    database_path = tmp_path / "workbench-auth.sqlite3"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    for run in runs:
        _persist_fixture(database_path, tmp_path / ".trialmark" / "artifacts", run)
    app = create_app()
    try:
        with TestClient(app) as client:
            yield app, client
    finally:
        get_settings.cache_clear()


def _api_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Flatten routes, descending into FastAPI's lazily included sub-routers."""

    for route in routes:
        nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from _api_routes(nested.routes)
        elif getattr(route, "dependant", None) is not None:
            yield route


def _write_auth_dependency(app: FastAPI) -> Callable[..., Any]:
    """The ``require_write_auth`` closure the workbench routes depend on."""

    for route in _api_routes(app.routes):
        if getattr(route, "path", None) != _DECISIONS_PATH:
            continue
        for dependency in route.dependant.dependencies:
            if dependency.name == "principal" and dependency.call is not None:
                return dependency.call
    raise AssertionError("workbench decision route has no principal dependency")


def _bind_principal(app: FastAPI, principal: Principal) -> None:
    app.dependency_overrides[_write_auth_dependency(app)] = lambda: principal


def _open_finding_id(client: TestClient, run_id: str) -> str:
    findings = client.get(f"/api/v2/runs/{run_id}").json()["findings"]
    return str(findings[0]["finding_id"])


def _run_ids(client: TestClient) -> set[str]:
    return {item["run_id"] for item in client.get("/api/v2/runs").json()["runs"]}


def test_actor_ref_in_request_body_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    analysis_run: CompletedEvidenceRun,
    preflight_run: CompletedEvidenceRun,
) -> None:
    with _serve(monkeypatch, tmp_path, (analysis_run, preflight_run)) as (_, client):
        persisted = _run_ids(client)
        finding_id = _open_finding_id(client, preflight_run.run_id)

        decision_response = client.post(
            f"/api/v2/runs/{analysis_run.run_id}/decisions",
            json={
                "verdict": "ship",
                "rationale": _RATIONALE,
                "actor_ref": "audit.impostor_ceo",
            },
        )
        assert decision_response.status_code == 422

        override_response = client.post(
            f"/api/v2/runs/{preflight_run.run_id}/findings/{finding_id}:override",
            json={"reason": _REASON, "actor_ref": "audit.impostor_ceo"},
        )
        assert override_response.status_code == 422

        # Neither rejected request may have recorded a child run.
        assert _run_ids(client) == persisted


def test_role_outside_approval_policy_is_refused_with_403(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    analysis_run: CompletedEvidenceRun,
    preflight_run: CompletedEvidenceRun,
) -> None:
    with _serve(monkeypatch, tmp_path, (analysis_run, preflight_run)) as (app, client):
        persisted = _run_ids(client)
        finding_id = _open_finding_id(client, preflight_run.run_id)
        _bind_principal(
            app,
            Principal(
                actor_ref="audit_impostor_ceo",
                scopes=frozenset({"write"}),
                role="impostor",
            ),
        )

        decision_response = client.post(
            f"/api/v2/runs/{analysis_run.run_id}/decisions",
            json={"verdict": "ship", "rationale": _RATIONALE},
        )
        assert decision_response.status_code == 403
        assert decision_response.json()["error_code"] == "role_not_permitted"
        assert decision_response.headers["X-Error-Code"] == "role_not_permitted"

        override_response = client.post(
            f"/api/v2/runs/{preflight_run.run_id}/findings/{finding_id}:override",
            json={"reason": _REASON},
        )
        assert override_response.status_code == 403
        assert override_response.json()["error_code"] == "role_not_permitted"

        # The refusal is not a state conflict: the runs are untouched.
        assert _run_ids(client) == persisted
        assert client.get(f"/api/v2/runs/{analysis_run.run_id}").json()["decisions"] == []


def test_permitted_principals_still_record_decisions_and_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    analysis_run: CompletedEvidenceRun,
    preflight_run: CompletedEvidenceRun,
) -> None:
    """False-reject control: the valid open-mode and in-policy paths stay green."""

    with _serve(monkeypatch, tmp_path, (analysis_run, preflight_run)) as (app, client):
        finding_id = _open_finding_id(client, preflight_run.run_id)

        decision_response = client.post(
            f"/api/v2/runs/{analysis_run.run_id}/decisions",
            json={"verdict": "ship", "rationale": _RATIONALE},
        )
        assert decision_response.status_code == 201
        decision = decision_response.json()
        assert decision["decisions"][0]["decided_by"]["actor_ref"] == "local-operator"

        _bind_principal(
            app,
            Principal(
                actor_ref="key-alpha",
                scopes=frozenset({"write"}),
                role=_PERMITTED_ROLE,
            ),
        )
        override_response = client.post(
            f"/api/v2/runs/{preflight_run.run_id}/findings/{finding_id}:override",
            json={"reason": _REASON},
        )
        assert override_response.status_code == 201
        overridden = next(
            finding
            for finding in override_response.json()["findings"]
            if finding["finding_id"] == finding_id
        )
        assert overridden["state"] == "overridden"
        assert overridden["override"]["actor_ref"] == "key-alpha"


def test_service_layer_separates_role_refusal_from_a_malformed_principal(
    analysis_run: CompletedEvidenceRun,
) -> None:
    store = _MemoryEvidenceRunStore()
    store.runs[analysis_run.run_id] = analysis_run

    with pytest.raises(RoleNotPermittedError):
        record_human_decision(
            analysis_run.run_id,
            Principal(
                actor_ref="audit_impostor_ceo",
                scopes=frozenset({"write"}),
                role="impostor",
            ),
            "ship",
            _RATIONALE,
            out_store=store,
        )

    # A missing actor_ref is a different fault and must stay a plain ValueError.
    with pytest.raises(ValueError) as malformed:
        record_human_decision(
            analysis_run.run_id,
            Principal(actor_ref="", scopes=frozenset({"write"})),
            "ship",
            _RATIONALE,
            out_store=store,
        )
    assert not isinstance(malformed.value, RoleNotPermittedError)

    # A principal that declares no role inherits the frozen policy's first role.
    child = record_human_decision(
        analysis_run.run_id,
        Principal(actor_ref="local-operator", scopes=frozenset({"write"})),
        "ship",
        _RATIONALE,
        out_store=store,
    )
    assert child.run_id != analysis_run.run_id
