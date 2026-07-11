"""The production auth gate (audit F-03), end to end through a real app.

Before this gate, `AB_ENV=production` booted happily with no auth material at all:
`http_runtime.auth_enabled()` returned False, `require_write_auth` waved every request
through, and the entire write surface answered anonymous callers with 200. Two bugs fed
that: config never asked for auth material, and `auth_enabled()` ignored `admin_token`,
so an admin-only deployment protected `/api/v1/keys` while leaving project mutations open.

These tests drive `create_app()` in production mode. Production insists on the PostgreSQL
backend, so `_ProductionRepository` stands in for it: real SQLite storage that reports
`backend_name == "postgres"`. The auth gate is storage-agnostic — it reads settings and
asks for one active write key — so nothing under test is faked, and the suite stays
container-free (see `test_postgres_backend.py` for the live-PostgreSQL coverage).
"""

import logging
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository

POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/abtest"
WRITE_TOKEN = "production-write-token-24ch"
ADMIN_TOKEN = "production-admin-token-24ch"
READONLY_TOKEN = "production-readonly-token"


class _ProductionRepository(ProjectRepository):
    """Real SQLite storage that reports the PostgreSQL backend name.

    `_verify_production_storage` refuses to serve unless the backend resolved to
    PostgreSQL; the auth gate this module exercises does not care which engine is
    underneath. Reporting "postgres" gets us past the storage probe without a container.
    """

    backend_name = "postgres"
    supports_snapshots = False


def _production_repository_factory(db_path: Path) -> Any:
    """Patch target for `app.backend.app.main.ProjectRepository`: ignore the DSN, use SQLite."""

    def _create(_database_url: str, **kwargs: Any) -> _ProductionRepository:
        return _ProductionRepository(f"sqlite:///{db_path.as_posix()}", **kwargs)

    return _create


def _production_env(monkeypatch, **env: str) -> Path:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_ENV", "production")
    monkeypatch.setenv("AB_DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    for name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN", "AB_ALLOW_INSECURE_PRODUCTION", "AB_PUBLIC_DEMO"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    return db_path


class _WarningCapture(logging.Handler):
    """Collect WARNING records straight off the `app.backend.app.main` logger.

    `caplog` cannot see them: `create_app()` calls `configure_logging()`, which runs
    `logging.basicConfig(force=True)` and drops pytest's capture handler off the root
    logger. A handler attached to the module logger itself survives that reset.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture_startup_warnings() -> _WarningCapture:
    handler = _WarningCapture()
    logging.getLogger("app.backend.app.main").addHandler(handler)
    return handler


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _experiment_payload() -> dict:
    return {
        "project": {
            "project_name": "Checkout redesign",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "We want to test a simplified checkout flow.",
        },
        "hypothesis": {
            "change_description": "Reduce checkout from 4 steps to 2",
            "target_audience": "new users on web",
            "business_problem": "checkout abandonment is high",
            "hypothesis_statement": "If we simplify checkout, conversion will increase.",
            "what_to_validate": "impact on conversion",
            "desired_result": "statistically meaningful uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "new users only",
            "exclusion_criteria": "internal staff",
        },
        "metrics": {
            "primary_metric_name": "purchase_conversion",
            "metric_type": "binary",
            "baseline_value": 0.042,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
            "secondary_metrics": [],
            "guardrail_metrics": [],
        },
        "constraints": {
            "seasonality_present": True,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "medium",
            "technical_constraints": "legacy event logging",
            "legal_or_ethics_constraints": "none",
            "known_risks": "tracking quality",
            "deadline_pressure": "medium",
            "long_test_possible": True,
        },
        "additional_context": {},
    }


def test_production_refuses_to_start_without_auth_material(monkeypatch) -> None:
    """The finding itself: no token, no key, production — the process must not boot."""
    db_path = _production_env(monkeypatch)

    with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
        with pytest.raises(RuntimeError, match="refuses to start without auth material"):
            create_app()

    get_settings.cache_clear()


def test_production_escape_hatch_starts_warns_and_leaves_mutations_open(monkeypatch) -> None:
    """AB_ALLOW_INSECURE_PRODUCTION is the explicit opt-out, and it is honest about the cost:
    the app serves, the log carries a WARNING, and anonymous writes really do go through."""
    db_path = _production_env(monkeypatch, AB_ALLOW_INSECURE_PRODUCTION="true")
    warnings = _capture_startup_warnings()

    try:
        with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
            with TestClient(create_app()) as client:
                anonymous_create = client.post("/api/v1/projects", json=_experiment_payload())
    finally:
        logging.getLogger("app.backend.app.main").removeHandler(warnings)

    assert any("INSECURE PRODUCTION" in record.getMessage() for record in warnings.records)
    assert any(getattr(record, "fields", {}).get("event") == "insecure_production" for record in warnings.records)
    # The whole point of the hatch: this 200 is what the default gate now prevents.
    assert anonymous_create.status_code == 200
    get_settings.cache_clear()


def test_production_admin_token_alone_rejects_anonymous_mutations(monkeypatch) -> None:
    """The auth_enabled() half of F-03.

    An admin-only deployment used to protect /api/v1/keys while every ordinary project
    mutation stayed open, because auth_enabled() never looked at admin_token. Anonymous
    POST/PUT/DELETE must answer 401 — not 200.
    """
    db_path = _production_env(monkeypatch, AB_ADMIN_TOKEN=ADMIN_TOKEN)

    with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
        with TestClient(create_app()) as client:
            anonymous_create = client.post("/api/v1/projects", json=_experiment_payload())
            anonymous_update = client.put("/api/v1/projects/does-not-exist", json=_experiment_payload())
            anonymous_delete = client.delete("/api/v1/projects/does-not-exist")
            anonymous_list = client.get("/api/v1/projects")
            admin_keys = client.get("/api/v1/keys", headers=_bearer(ADMIN_TOKEN))

    assert anonymous_create.status_code == 401
    assert anonymous_update.status_code == 401
    assert anonymous_delete.status_code == 401
    # Auth is on, so reads are closed too: no token, no session.
    assert anonymous_list.status_code == 401
    # ... while the admin token still reaches its own surface.
    assert admin_keys.status_code == 200
    get_settings.cache_clear()


def test_production_admin_token_bootstraps_a_write_key_and_scopes_hold(monkeypatch) -> None:
    """The documented admin-only bootstrap, end to end: mint the first write key, then use it."""
    db_path = _production_env(monkeypatch, AB_ADMIN_TOKEN=ADMIN_TOKEN)

    with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
        with TestClient(create_app()) as client:
            write_key = client.post(
                "/api/v1/keys",
                headers=_bearer(ADMIN_TOKEN),
                json={"name": "Bootstrap write key", "scope": "write"},
            )
            read_key = client.post(
                "/api/v1/keys",
                headers=_bearer(ADMIN_TOKEN),
                json={"name": "Partner read key", "scope": "read"},
            )
            assert write_key.status_code == 200
            assert read_key.status_code == 200

            write_headers = _bearer(write_key.json()["plaintext_key"])
            read_headers = _bearer(read_key.json()["plaintext_key"])

            created = client.post("/api/v1/projects", json=_experiment_payload(), headers=write_headers)
            read_scope_create = client.post("/api/v1/projects", json=_experiment_payload(), headers=read_headers)
            read_scope_list = client.get("/api/v1/projects", headers=read_headers)
            deleted = client.delete(f"/api/v1/projects/{created.json()['id']}", headers=write_headers)

    assert created.status_code == 200
    assert deleted.status_code == 200
    # Read scope cannot change stored state, but may still read it.
    assert read_scope_create.status_code == 403
    assert read_scope_list.status_code == 200
    get_settings.cache_clear()


def test_production_starts_on_an_existing_write_api_key_with_no_shared_tokens(monkeypatch) -> None:
    """The steady state after the admin token is retired: the only auth material is a key in the database."""
    db_path = _production_env(monkeypatch)
    seed_repository = ProjectRepository(str(db_path))
    plaintext_key = seed_repository.create_api_key(name="Existing write key", scope="write")["plaintext_key"]

    with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
        with TestClient(create_app()) as client:
            anonymous_create = client.post("/api/v1/projects", json=_experiment_payload())
            key_create = client.post(
                "/api/v1/projects",
                json=_experiment_payload(),
                headers=_bearer(plaintext_key),
            )

    assert anonymous_create.status_code == 401
    assert key_create.status_code == 200
    get_settings.cache_clear()


def test_production_write_token_mutates_and_readonly_token_is_forbidden(monkeypatch) -> None:
    db_path = _production_env(
        monkeypatch,
        AB_API_TOKEN=WRITE_TOKEN,
        AB_READONLY_API_TOKEN=READONLY_TOKEN,
    )

    with patch("app.backend.app.main.ProjectRepository", _production_repository_factory(db_path)):
        with TestClient(create_app()) as client:
            created = client.post("/api/v1/projects", json=_experiment_payload(), headers=_bearer(WRITE_TOKEN))
            readonly_create = client.post(
                "/api/v1/projects",
                json=_experiment_payload(),
                headers=_bearer(READONLY_TOKEN),
            )
            readonly_list = client.get("/api/v1/projects", headers=_bearer(READONLY_TOKEN))
            anonymous_create = client.post("/api/v1/projects", json=_experiment_payload())

    assert created.status_code == 200
    assert readonly_create.status_code == 403
    assert readonly_list.status_code == 200
    assert anonymous_create.status_code == 401
    get_settings.cache_clear()
