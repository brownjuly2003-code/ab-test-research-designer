"""F-02: the PostgreSQL upgrade path, and the readiness check that used to lie about it.

`CREATE TABLE IF NOT EXISTS` is a no-op on an existing table, so `occurred_at` (added to
`exposures`/`conversions` on 2026-06-26, tables created 2026-06-14) never reached a database
provisioned in between. Readiness did not catch it: it compared `repository.schema_version`
with the same constant echoed back through the diagnostics summary.

The runner logic is exercised here against a stub connection — no container needed, because
what matters (which migrations are pending, what SQL runs, what gets recorded) is decided in
Python. The live `old schema -> migrate -> current` drill against a real PostgreSQL lives in
`test_postgres_backend.py`, which CI runs with testcontainers.
"""

from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository._migrations import (
    EXPECTED_POSTGRES_SCHEMA_VERSION,
    MIGRATION_ADVISORY_LOCK_KEY,
    POSTGRES_MIGRATIONS,
    apply_pending_migrations,
    pending_migrations,
    read_applied_schema_version,
)


class _StubConnection:
    """Records every statement; answers the version query with `applied_version`."""

    def __init__(self, applied_version: int) -> None:
        self.applied_version = applied_version
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> Any:
        self.statements.append((" ".join(sql.split()), params))
        if "MAX(version)" in sql:
            row = {"version": self.applied_version}
            return _StubCursor(row)
        return _StubCursor(None)

    def sql_text(self) -> str:
        return "\n".join(sql for sql, _ in self.statements)


class _StubCursor:
    def __init__(self, row: Any) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


def test_migration_versions_are_unique_and_ascending() -> None:
    versions = [migration.version for migration in POSTGRES_MIGRATIONS]

    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))
    assert EXPECTED_POSTGRES_SCHEMA_VERSION == versions[-1]


def test_every_migration_statement_is_idempotent() -> None:
    """A migration must be safe on a fresh database, where _init_db already built the objects."""
    idempotent_markers = ("IF NOT EXISTS", "IS NULL", "SET NOT NULL", "IF EXISTS")

    for migration in POSTGRES_MIGRATIONS:
        for statement in migration.statements:
            assert any(marker in statement for marker in idempotent_markers), (
                f"migration {migration.version} ({migration.name}) has a statement that would "
                f"fail or double-apply on an up-to-date database: {statement}"
            )


def test_pending_migrations_selects_only_newer_versions() -> None:
    assert pending_migrations(0) == POSTGRES_MIGRATIONS
    assert pending_migrations(EXPECTED_POSTGRES_SCHEMA_VERSION) == ()
    assert all(m.version > 13 for m in pending_migrations(13))


def test_read_applied_schema_version_reads_the_database_not_the_constant() -> None:
    connection = _StubConnection(applied_version=13)

    assert read_applied_schema_version(connection) == 13


def test_apply_pending_migrations_runs_the_backfill_and_records_the_version() -> None:
    """A database one version behind gets the statements, the record, and the lock."""
    connection = _StubConnection(applied_version=13)

    applied = apply_pending_migrations(connection, applied_at="2026-07-12T00:00:00+00:00")

    assert applied == (EXPECTED_POSTGRES_SCHEMA_VERSION,)
    sql = connection.sql_text()
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
    assert "ALTER TABLE exposures ADD COLUMN IF NOT EXISTS occurred_at TEXT" in sql
    assert "UPDATE exposures SET occurred_at = created_at WHERE occurred_at IS NULL" in sql
    assert "ALTER TABLE exposures ALTER COLUMN occurred_at SET NOT NULL" in sql
    assert "ALTER TABLE conversions ADD COLUMN IF NOT EXISTS occurred_at TEXT" in sql
    assert "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)" in sql

    recorded = [params for stmt, params in connection.statements if stmt.startswith("INSERT INTO schema_migrations")]
    assert recorded == [(EXPECTED_POSTGRES_SCHEMA_VERSION, "event_time_occurred_at", "2026-07-12T00:00:00+00:00")]


def test_apply_pending_migrations_is_a_no_op_on_a_current_database() -> None:
    connection = _StubConnection(applied_version=EXPECTED_POSTGRES_SCHEMA_VERSION)

    applied = apply_pending_migrations(connection, applied_at="2026-07-12T00:00:00+00:00")

    assert applied == ()
    assert "ALTER TABLE" not in connection.sql_text()
    assert "INSERT INTO schema_migrations" not in connection.sql_text()


def test_apply_pending_migrations_takes_and_releases_the_advisory_lock() -> None:
    """Two replicas booting at once must serialise, not race the same ALTER."""
    connection = _StubConnection(applied_version=0)

    apply_pending_migrations(connection, applied_at="2026-07-12T00:00:00+00:00")

    lock_calls = [(sql, params) for sql, params in connection.statements if "advisory" in sql]
    assert lock_calls == [
        ("SELECT pg_advisory_lock(?)", (MIGRATION_ADVISORY_LOCK_KEY,)),
        ("SELECT pg_advisory_unlock(?)", (MIGRATION_ADVISORY_LOCK_KEY,)),
    ]


def test_advisory_lock_is_released_even_when_a_migration_fails() -> None:
    """A failed migration must not leave the lock held — the next boot would hang forever."""

    class _FailingConnection(_StubConnection):
        def execute(self, sql: str, params: Any = None) -> Any:
            if sql.startswith("ALTER TABLE"):
                raise RuntimeError("relation does not exist")
            return super().execute(sql, params)

    connection = _FailingConnection(applied_version=0)

    try:
        apply_pending_migrations(connection, applied_at="2026-07-12T00:00:00+00:00")
    except RuntimeError:
        pass
    else:  # pragma: no cover - the stub always raises
        raise AssertionError("the failing migration should have propagated")

    assert ("SELECT pg_advisory_unlock(?)", (MIGRATION_ADVISORY_LOCK_KEY,)) in connection.statements
