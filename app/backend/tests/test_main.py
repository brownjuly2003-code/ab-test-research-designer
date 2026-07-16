import logging
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import _verify_production_auth, _verify_production_storage

POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/abtest"
WRITE_TOKEN = "production-write-token-24ch"
ADMIN_TOKEN = "production-admin-token-24ch"


class _FakeRepository:
    """Duck-typed stand-in for ProjectRepository (no live database needed)."""

    def __init__(
        self,
        backend_name: str,
        summary: dict[str, Any],
        *,
        active_write_key: bool = False,
    ) -> None:
        self.backend_name = backend_name
        self._summary = summary
        self._active_write_key = active_write_key

    def get_diagnostics_summary(self) -> dict[str, Any]:
        return self._summary

    def has_active_api_keys(self, *, scope: str | None = None) -> bool:
        return self._active_write_key and scope == "write"


def _healthy_repository(*, active_write_key: bool = False) -> _FakeRepository:
    return _FakeRepository(
        "postgres",
        {"write_probe_ok": True, "write_probe_detail": "BEGIN succeeded"},
        active_write_key=active_write_key,
    )


def _production_settings(monkeypatch, **env: str):
    monkeypatch.setenv("AB_ENV", "production")
    monkeypatch.setenv("AB_DATABASE_URL", POSTGRES_URL)
    for token_name in ("AB_API_TOKEN", "AB_READONLY_API_TOKEN", "AB_ADMIN_TOKEN"):
        monkeypatch.delenv(token_name, raising=False)
    monkeypatch.delenv("AB_ALLOW_INSECURE_PRODUCTION", raising=False)
    monkeypatch.delenv("AB_PUBLIC_DEMO", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    settings = get_settings()
    get_settings.cache_clear()
    return settings


def test_verify_production_storage_passes_on_healthy_postgres() -> None:
    repo = _FakeRepository(
        "postgres",
        {"write_probe_ok": True, "write_probe_detail": "BEGIN succeeded"},
    )

    # Should not raise.
    _verify_production_storage(repo)


def test_verify_production_storage_rejects_non_postgres_backend() -> None:
    repo = _FakeRepository("sqlite", {"write_probe_ok": True})

    with pytest.raises(RuntimeError, match="requires the PostgreSQL backend"):
        _verify_production_storage(repo)


def test_verify_production_storage_rejects_failed_write_probe() -> None:
    repo = _FakeRepository(
        "postgres",
        {"write_probe_ok": False, "write_probe_detail": "connection refused"},
    )

    with pytest.raises(RuntimeError, match="connection refused"):
        _verify_production_storage(repo)


def test_verify_production_auth_rejects_a_deployment_with_no_auth_material(monkeypatch) -> None:
    """The F-03 regression: production used to boot with every mutation wide open."""
    settings = _production_settings(monkeypatch)

    with pytest.raises(RuntimeError, match="refuses to start without auth material"):
        _verify_production_auth(settings, _healthy_repository())


def test_verify_production_auth_accepts_a_write_token(monkeypatch) -> None:
    settings = _production_settings(monkeypatch, AB_API_TOKEN=WRITE_TOKEN)

    # Should not raise, and must not need the database to decide.
    _verify_production_auth(settings, _healthy_repository())


def test_verify_production_auth_accepts_an_admin_token(monkeypatch) -> None:
    """Admin-only is a valid bootstrap: it issues the first write key, and until then
    mutating endpoints answer 401 rather than standing open."""
    settings = _production_settings(monkeypatch, AB_ADMIN_TOKEN=ADMIN_TOKEN)

    _verify_production_auth(settings, _healthy_repository())


def test_verify_production_auth_accepts_an_existing_write_api_key(monkeypatch) -> None:
    """The steady state: no shared tokens at all, one active write-scoped key in the database."""
    settings = _production_settings(monkeypatch)

    _verify_production_auth(settings, _healthy_repository(active_write_key=True))


def test_verify_production_auth_rejects_a_readonly_token_alone(monkeypatch) -> None:
    """Nothing is open, but nothing can be written either — a broken config, not a secure one."""
    settings = _production_settings(monkeypatch, AB_READONLY_API_TOKEN="production-readonly-token")

    with pytest.raises(RuntimeError, match="refuses to start without auth material"):
        _verify_production_auth(settings, _healthy_repository())


def test_verify_production_auth_rejects_public_demo_alone(monkeypatch) -> None:
    settings = _production_settings(monkeypatch, AB_PUBLIC_DEMO="true")

    with pytest.raises(RuntimeError, match="refuses to start without auth material"):
        _verify_production_auth(settings, _healthy_repository())


def test_verify_production_auth_escape_hatch_starts_but_warns_loudly(monkeypatch, caplog) -> None:
    settings = _production_settings(monkeypatch, AB_ALLOW_INSECURE_PRODUCTION="true")

    with caplog.at_level(logging.WARNING, logger="app.backend.app.main"):
        _verify_production_auth(settings, _healthy_repository())

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "INSECURE PRODUCTION" in warnings[0].getMessage()
    assert warnings[0].fields["event"] == "insecure_production"


def test_verify_production_auth_escape_hatch_stays_quiet_when_auth_exists(monkeypatch, caplog) -> None:
    """The hatch must not turn a properly secured deployment into a crying-wolf log line."""
    settings = _production_settings(
        monkeypatch,
        AB_ALLOW_INSECURE_PRODUCTION="true",
        AB_API_TOKEN=WRITE_TOKEN,
    )

    with caplog.at_level(logging.WARNING, logger="app.backend.app.main"):
        _verify_production_auth(settings, _healthy_repository())

    assert [record for record in caplog.records if record.levelno == logging.WARNING] == []
