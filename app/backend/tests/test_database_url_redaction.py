"""F-01: a PostgreSQL DSN carries its password inline.

These tests pin the invariant that the DSN never reaches a log line, a readiness
payload or a diagnostics payload — the three channels where it used to surface.
"""

import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.logging_utils import configure_logging, log_event
from app.backend.app.main import create_app
from app.backend.app.redaction import database_host, mask_inline_credentials, redact_database_url
from app.backend.app.repository._postgres import PostgresBackend, _PostgresRow

SECRET = "sup3r-s3cret-pw"
DSN = f"postgresql://ab_user:{SECRET}@db.internal:5432/ab_prod"


def test_redact_database_url_drops_credentials_but_keeps_host_and_database() -> None:
    redacted = redact_database_url(DSN)

    assert SECRET not in redacted
    assert "ab_user" not in redacted
    assert redacted == "postgresql://***@db.internal:5432/ab_prod"


def test_redact_database_url_handles_unencoded_at_sign_in_password() -> None:
    # Splitting on the FIRST `@` would leave `ss@db.internal` behind and leak the tail.
    redacted = redact_database_url("postgresql://ab_user:p@ss@db.internal:5432/ab_prod")

    assert "p@ss" not in redacted
    assert "ss@db.internal" not in redacted
    assert redacted == "postgresql://***@db.internal:5432/ab_prod"


def test_redact_database_url_masks_password_query_parameter() -> None:
    redacted = redact_database_url(f"postgresql://db.internal/ab_prod?password={SECRET}&sslmode=require")

    assert SECRET not in redacted
    assert "sslmode=require" in redacted


def test_redact_database_url_leaves_credential_free_urls_untouched() -> None:
    sqlite_url = "sqlite:///D:/AB_TEST/app/backend/data/projects.sqlite3"

    assert redact_database_url(sqlite_url) == sqlite_url
    assert redact_database_url("postgresql://db.internal:5432/ab_prod") == "postgresql://db.internal:5432/ab_prod"
    assert redact_database_url("") == ""


def test_database_host_returns_host_without_userinfo() -> None:
    assert database_host(DSN) == "db.internal:5432"
    assert database_host("postgresql://db.internal/ab_prod") == "db.internal"
    assert database_host("") == ""


def test_dsn_is_masked_in_captured_logs(caplog) -> None:
    configure_logging(level="INFO", log_format="plain")
    logger = logging.getLogger("app.backend.tests.dsn_logging")
    root_logger = logging.getLogger()

    caplog.set_level(logging.INFO)
    root_logger.addHandler(caplog.handler)

    log_event(logger, logging.INFO, "application started", db_path=DSN)
    logger.info("connecting to %s", DSN)

    rendered = [record.getMessage() for record in caplog.records] + [
        repr(getattr(record, "fields", {})) for record in caplog.records
    ]

    assert all(SECRET not in entry for entry in rendered)


def test_postgres_diagnostics_summary_never_serializes_the_dsn() -> None:
    """Runs the real `get_diagnostics_summary` body against a stub connection.

    A live PostgreSQL is not needed to prove the leak: the password only ever
    entered the payload through `database_url` / `netloc`, both of which are
    computed here, not fetched.
    """
    counts = {"db_size_bytes": 4096}

    class _StubConnection:
        def __enter__(self) -> "_StubConnection":
            return self

        def __exit__(self, *_: object) -> bool:
            return False

        def execute(self, sql: str, *_: object) -> Any:
            if "pg_database_size" in sql:
                row = _PostgresRow(counts)
            elif "MAX(updated_at)" in sql:
                row = _PostgresRow({"updated_at": "2026-07-11T00:00:00+00:00"})
            elif "MAX(version)" in sql:
                # The summary reads the applied schema version out of the database (F-02).
                row = _PostgresRow({"version": 14})
            else:
                row = _PostgresRow({"count": 0})
            return SimpleNamespace(fetchone=lambda: row)

    backend = SimpleNamespace(
        database_url=DSN,
        schema_version=14,
        workspace_schema_version=3,
        workspace_signing_key=None,
        _run_write_probe=lambda: (True, "BEGIN succeeded"),
        _connect=lambda: _StubConnection(),
    )

    summary = PostgresBackend.get_diagnostics_summary(backend)  # type: ignore[arg-type]
    serialized = json.dumps(summary)

    assert SECRET not in serialized
    assert "ab_user" not in serialized
    assert summary["db_path"] == "postgresql://***@db.internal:5432/ab_prod"
    assert summary["db_parent_path"] == "db.internal:5432"


def test_readyz_does_not_disclose_the_database_location() -> None:
    settings = get_settings()
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code in {200, 503}
    body = response.text
    assert settings.db_path not in body
    assert settings.database_url not in body
    assert Path(settings.frontend_dist_path).as_posix() not in body


def test_diagnostics_hides_operator_detail_from_read_scope_sessions(monkeypatch) -> None:
    """A read-scope caller (every anonymous visitor on the public demo) gets no locations."""
    write_token = "write-token-for-diagnostics-test"
    monkeypatch.setenv("AB_PUBLIC_DEMO", "true")
    monkeypatch.setenv("AB_API_TOKEN", write_token)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        client = TestClient(create_app())

        anonymous = client.get("/api/v1/diagnostics")
        assert anonymous.status_code == 200
        payload = anonymous.json()

        assert payload["auth"]["session_scope"] == "read"
        assert payload["storage"]["db_path"] is None
        assert payload["storage"]["db_parent_path"] is None
        assert payload["storage"]["disk_free_bytes"] is None
        assert payload["frontend"]["dist_path"] is None
        assert payload["llm"]["base_url"] is None
        assert payload["network"]["trusted_proxies"] is None
        # The health facts a read-scope consumer legitimately needs stay present.
        assert payload["storage"]["write_probe_ok"] is True
        assert payload["storage"]["schema_version"] >= 1
        assert settings.db_path not in anonymous.text

        operator = client.get(
            "/api/v1/diagnostics",
            headers={"Authorization": f"Bearer {write_token}"},
        )
        assert operator.status_code == 200
        operator_payload = operator.json()

        assert operator_payload["auth"]["session_scope"] == "write"
        assert operator_payload["storage"]["db_path"] == settings.db_path
        assert operator_payload["frontend"]["dist_path"] == settings.frontend_dist_path
        assert operator_payload["llm"]["base_url"] == settings.llm_base_url
        assert operator_payload["network"]["trusted_proxies"] == list(settings.trusted_proxies)
    finally:
        get_settings.cache_clear()


def test_mask_inline_credentials_is_a_second_layer_for_free_text() -> None:
    masked = mask_inline_credentials(f"could not connect to postgresql://ab_user:{SECRET}@db.internal:5432/ab_prod")

    assert SECRET not in masked
    assert "***@db.internal" in masked
