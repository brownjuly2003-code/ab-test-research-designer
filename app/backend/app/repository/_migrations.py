"""Versioned PostgreSQL schema migrations — the upgrade path the schema never had.

``CREATE TABLE IF NOT EXISTS`` (all ``_init_db`` ever ran) creates a *missing* table but is a
no-op on an existing one. So a column added to a table that already exists never reaches a
database provisioned before it. That is not hypothetical: ``occurred_at`` was added to
``exposures`` and ``conversions`` on 2026-06-26 (b15f7bb2); both tables were created on
2026-06-14 (5b9e60b5). Any PostgreSQL database provisioned in that window silently lacks the
column and fails on the first ingestion write — while ``/readyz`` reported green, because it
compared the code's ``schema_version`` constant against the very same constant read back off
the repository object.

Two things fix that, and both live here:

* the missing statements, as explicit numbered migrations;
* the applied version, recorded **in the database**, so readiness compares a fact against an
  expectation instead of a constant against itself.

Fresh databases still get their objects from ``_init_db`` (idempotent CREATE TABLE / CREATE
INDEX IF NOT EXISTS), and every migration below is written to be a no-op on them.

Adding a migration: append a ``Migration`` with the next version, keep every statement
idempotent (``IF NOT EXISTS`` / a ``WHERE`` that matches nothing on a current schema), and let
``EXPECTED_POSTGRES_SCHEMA_VERSION`` follow the last entry. Never edit a shipped migration —
databases that already applied it will not run it again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# Serialises migration runs across replicas: two instances booting at once must not race the
# same ALTER. The key is arbitrary, only its uniqueness to this app matters ("ABMG").
MIGRATION_ADVISORY_LOCK_KEY: Final[int] = 0x4142_4D47

SCHEMA_MIGRATIONS_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


POSTGRES_MIGRATIONS: Final[tuple[Migration, ...]] = (
    Migration(
        version=14,
        name="event_time_occurred_at",
        statements=(
            # A database created before 2026-06-26 has exposures/conversions without
            # occurred_at. Backfill it from created_at — for rows recorded before event time
            # existed, ingestion time is the only event time we have — and then restore the
            # NOT NULL that the current schema declares. On a fresh database the column is
            # already there, the UPDATE matches nothing, and SET NOT NULL is a no-op.
            "ALTER TABLE exposures ADD COLUMN IF NOT EXISTS occurred_at TEXT",
            "UPDATE exposures SET occurred_at = created_at WHERE occurred_at IS NULL",
            "ALTER TABLE exposures ALTER COLUMN occurred_at SET NOT NULL",
            "ALTER TABLE conversions ADD COLUMN IF NOT EXISTS occurred_at TEXT",
            "UPDATE conversions SET occurred_at = created_at WHERE occurred_at IS NULL",
            "ALTER TABLE conversions ALTER COLUMN occurred_at SET NOT NULL",
        ),
    ),
    Migration(
        version=15,
        name="webhook_outbox",
        statements=(
            # F-09: deliveries become a durable outbox. A worker claims due rows
            # under a lease, so retries survive restarts and replicas do not race
            # the same row. Rows mid-flight on an old build become due immediately
            # (epoch fallback sorts before any real ISO timestamp).
            "ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS next_attempt_at TEXT",
            "ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS lease_expires_at TEXT",
            (
                "UPDATE webhook_deliveries "
                "SET next_attempt_at = COALESCE(last_attempt_at, '1970-01-01T00:00:00+00:00') "
                "WHERE next_attempt_at IS NULL AND status IN ('pending', 'retrying')"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_due "
                "ON webhook_deliveries (status, next_attempt_at)"
            ),
        ),
    ),
)

# What the running code requires the database to be. Readiness compares the version actually
# recorded in the database against this; a mismatch means "do not serve traffic".
EXPECTED_POSTGRES_SCHEMA_VERSION: Final[int] = POSTGRES_MIGRATIONS[-1].version


def pending_migrations(applied_version: int) -> tuple[Migration, ...]:
    """Migrations newer than ``applied_version``, in ascending order."""
    return tuple(migration for migration in POSTGRES_MIGRATIONS if migration.version > applied_version)


def read_applied_schema_version(connection: Any) -> int:
    """Highest migration version recorded in the database; 0 when the table is empty.

    Assumes ``schema_migrations`` exists — call ``apply_pending_migrations`` (which creates it)
    at startup before anything reads this.
    """
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
    if row is None:
        return 0
    return int(row["version"])


def apply_pending_migrations(connection: Any, *, applied_at: str) -> tuple[int, ...]:
    """Bring the database up to ``EXPECTED_POSTGRES_SCHEMA_VERSION``. Returns versions applied.

    Runs under a session-level advisory lock so concurrent replicas serialise instead of racing
    the same DDL. The caller's connection context commits on exit.
    """
    connection.execute(SCHEMA_MIGRATIONS_DDL)
    connection.execute("SELECT pg_advisory_lock(?)", (MIGRATION_ADVISORY_LOCK_KEY,))
    try:
        applied: list[int] = []
        for migration in pending_migrations(read_applied_schema_version(connection)):
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, applied_at),
            )
            applied.append(migration.version)
        return tuple(applied)
    finally:
        connection.execute("SELECT pg_advisory_unlock(?)", (MIGRATION_ADVISORY_LOCK_KEY,))
