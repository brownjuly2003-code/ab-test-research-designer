from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol, cast

from pydantic import ValidationError

from app.backend.app.evidence.jobs import EvidenceJob

EVIDENCE_SCHEMA_VERSION: Final[int] = 3
_EVIDENCE_MIGRATION_LOCK_KEY: Final[int] = 0x4556_4A53
_UNFINISHED_STATUSES: Final[tuple[str, ...]] = (
    "queued",
    "running",
    "cancel_requested",
)
_JOB_COLUMNS: Final[str] = """
    job_id,
    kind,
    protocol_revision_id,
    request_digest,
    status,
    revision,
    attempt_count,
    created_at,
    updated_at,
    started_at,
    finished_at,
    lease_token,
    lease_expires_at,
    cancel_requested_at,
    publication_run_id,
    publication_bundle_id,
    publication_artifact_ref,
    failure_code,
    failure_message,
    failure_retryable
"""
_RUN_COLUMNS: Final[str] = """
    run_id,
    origin_job_id,
    origin_job_revision,
    protocol_revision_id,
    kind,
    status,
    started_at,
    completed_at,
    sealed_at,
    runner_digest,
    required_capability_count,
    artifact_count,
    record_digest
"""
_RUN_CAPABILITY_COLUMNS: Final[str] = "run_id, ordinal, capability"
_ARTIFACT_COLUMNS: Final[str] = "digest, media_type, size, storage_key"
_RUN_ARTIFACT_COLUMNS: Final[str] = """
    run_id,
    ordinal,
    path,
    role,
    schema_id,
    artifact_digest
"""
_EVIDENCE_SCHEMA_LEDGER_DDL: Final[str] = """
    CREATE TABLE IF NOT EXISTS evidence_schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )
"""


class EvidenceJobStoreCorruptionError(RuntimeError):
    """Raised when a relational row cannot be validated as an EvidenceJob."""


class EvidenceJobSchemaError(RuntimeError):
    """Raised when the evidence migration ledger or table shape is invalid."""


class _SqlCursor(Protocol):
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class _SqlConnection(Protocol):
    def execute(self, sql: str, params: Any = None) -> _SqlCursor: ...


class SqlEvidenceBackend(Protocol):
    backend_name: str

    def _transaction(self) -> AbstractContextManager[Any]: ...


@dataclass(frozen=True)
class _EvidenceMigration:
    version: int
    name: str
    statements: tuple[str, ...]


_EVIDENCE_MIGRATIONS: Final[tuple[_EvidenceMigration, ...]] = (
    _EvidenceMigration(
        version=1,
        name="evidence_jobs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS evidence_jobs (
                job_id TEXT NOT NULL PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('preflight', 'analysis')),
                protocol_revision_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'queued',
                        'running',
                        'cancel_requested',
                        'succeeded',
                        'failed',
                        'cancelled'
                    )
                ),
                revision INTEGER NOT NULL CHECK (revision >= 0),
                attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                lease_token TEXT,
                lease_expires_at TEXT,
                cancel_requested_at TEXT,
                publication_run_id TEXT,
                publication_bundle_id TEXT,
                publication_artifact_ref TEXT,
                failure_code TEXT,
                failure_message TEXT,
                failure_retryable INTEGER CHECK (
                    failure_retryable IS NULL OR failure_retryable IN (0, 1)
                )
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_evidence_jobs_unfinished
            ON evidence_jobs (status, created_at, job_id)
            """,
        ),
    ),
    _EvidenceMigration(
        version=2,
        name="completed_evidence_runs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS evidence_runs (
                run_id TEXT NOT NULL PRIMARY KEY,
                origin_job_id TEXT NOT NULL,
                origin_job_revision INTEGER NOT NULL CHECK (origin_job_revision >= 1),
                protocol_revision_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('preflight', 'analysis')),
                status TEXT NOT NULL CHECK (status = 'succeeded'),
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                sealed_at TEXT NOT NULL,
                runner_digest TEXT NOT NULL,
                required_capability_count INTEGER NOT NULL CHECK (
                    required_capability_count >= 2
                ),
                artifact_count INTEGER NOT NULL CHECK (
                    artifact_count >= 2 AND artifact_count <= 512
                ),
                record_digest TEXT NOT NULL,
                FOREIGN KEY (origin_job_id) REFERENCES evidence_jobs (job_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_run_capabilities (
                run_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                capability TEXT NOT NULL,
                PRIMARY KEY (run_id, ordinal),
                UNIQUE (run_id, capability),
                FOREIGN KEY (run_id) REFERENCES evidence_runs (run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_artifacts (
                digest TEXT NOT NULL PRIMARY KEY,
                media_type TEXT NOT NULL,
                size INTEGER NOT NULL CHECK (size >= 0 AND size <= 16777216),
                storage_key TEXT NOT NULL UNIQUE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS run_artifacts (
                run_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                path TEXT NOT NULL,
                role TEXT NOT NULL CHECK (
                    role IN (
                        'protocol',
                        'amendments',
                        'run',
                        'source',
                        'metric',
                        'query',
                        'finding',
                        'estimate',
                        'decision',
                        'report',
                        'schema'
                    )
                ),
                schema_id TEXT,
                artifact_digest TEXT NOT NULL,
                PRIMARY KEY (run_id, path),
                UNIQUE (run_id, ordinal),
                FOREIGN KEY (run_id) REFERENCES evidence_runs (run_id),
                FOREIGN KEY (artifact_digest) REFERENCES evidence_artifacts (digest)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_evidence_runs_protocol
            ON evidence_runs (protocol_revision_id, completed_at, run_id)
            """,
        ),
    ),
    _EvidenceMigration(
        version=3,
        name="method_artifact_role",
        statements=(
            """
            CREATE TABLE run_artifacts_v3 (
                run_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                path TEXT NOT NULL,
                role TEXT NOT NULL CHECK (
                    role IN (
                        'protocol',
                        'amendments',
                        'run',
                        'source',
                        'metric',
                        'method',
                        'query',
                        'finding',
                        'estimate',
                        'decision',
                        'report',
                        'schema'
                    )
                ),
                schema_id TEXT,
                artifact_digest TEXT NOT NULL,
                PRIMARY KEY (run_id, path),
                UNIQUE (run_id, ordinal),
                FOREIGN KEY (run_id) REFERENCES evidence_runs (run_id),
                FOREIGN KEY (artifact_digest) REFERENCES evidence_artifacts (digest)
            )
            """,
            """
            INSERT INTO run_artifacts_v3
                (run_id, ordinal, path, role, schema_id, artifact_digest)
            SELECT run_id, ordinal, path, role, schema_id, artifact_digest
            FROM run_artifacts
            """,
            "DROP TABLE run_artifacts",
            "ALTER TABLE run_artifacts_v3 RENAME TO run_artifacts",
        ),
    ),
)


def ensure_evidence_schema(backend: SqlEvidenceBackend) -> None:
    with backend._transaction() as raw_connection:
        connection = cast(_SqlConnection, raw_connection)
        if backend.backend_name == "sqlite":
            connection.execute("BEGIN IMMEDIATE")
        if backend.backend_name == "postgres":
            connection.execute(
                "SELECT pg_advisory_xact_lock(?)",
                (_EVIDENCE_MIGRATION_LOCK_KEY,),
            )
        connection.execute(_EVIDENCE_SCHEMA_LEDGER_DDL)
        ledger_rows = connection.execute(
            "SELECT version, name FROM evidence_schema_migrations "
            "ORDER BY version"
        ).fetchall()
        stored_migrations = [
            (int(row["version"]), str(row["name"])) for row in ledger_rows
        ]
        expected_migrations = [
            (migration.version, migration.name) for migration in _EVIDENCE_MIGRATIONS
        ]
        if stored_migrations != expected_migrations[: len(stored_migrations)]:
            raise EvidenceJobSchemaError(
                "evidence migration ledger is not a valid ordered prefix"
            )
        applied_version = stored_migrations[-1][0] if stored_migrations else 0
        applied_at = datetime.now(UTC).isoformat()
        for migration in _EVIDENCE_MIGRATIONS:
            if migration.version <= applied_version:
                continue
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO evidence_schema_migrations "
                "(version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, applied_at),
            )
        final_ledger_rows = connection.execute(
            "SELECT version, name FROM evidence_schema_migrations "
            "ORDER BY version"
        ).fetchall()
        final_migrations = [
            (int(row["version"]), str(row["name"]))
            for row in final_ledger_rows
        ]
        if final_migrations != expected_migrations:
            raise EvidenceJobSchemaError(
                "evidence migration ledger does not match the application schema"
            )
        required_shapes = (
            ("evidence_jobs", _JOB_COLUMNS),
            ("evidence_runs", _RUN_COLUMNS),
            ("evidence_run_capabilities", _RUN_CAPABILITY_COLUMNS),
            ("evidence_artifacts", _ARTIFACT_COLUMNS),
            ("run_artifacts", _RUN_ARTIFACT_COLUMNS),
        )
        for table_name, columns in required_shapes:
            try:
                connection.execute(
                    f"SELECT {columns} FROM {table_name} WHERE 1 = 0"
                )
            except Exception as exc:
                raise EvidenceJobSchemaError(
                    f"{table_name} table does not match the required column shape"
                ) from exc


def _serialize_time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _job_values(job: EvidenceJob) -> tuple[Any, ...]:
    publication = job.publication
    failure = job.failure
    return (
        job.job_id,
        job.kind,
        job.protocol_revision_id,
        job.request_digest,
        job.status,
        job.revision,
        job.attempt_count,
        _serialize_time(job.created_at),
        _serialize_time(job.updated_at),
        _serialize_time(job.started_at),
        _serialize_time(job.finished_at),
        job.lease_token,
        _serialize_time(job.lease_expires_at),
        _serialize_time(job.cancel_requested_at),
        publication.run_id if publication is not None else None,
        publication.bundle_id if publication is not None else None,
        publication.artifact_ref if publication is not None else None,
        failure.code if failure is not None else None,
        failure.message if failure is not None else None,
        int(failure.retryable) if failure is not None else None,
    )


def _replacement_values(job: EvidenceJob) -> tuple[Any, ...]:
    values = _job_values(job)
    return (*values[4:7], *values[8:])


def _optional_publication(row: Any) -> dict[str, Any] | None:
    values = (
        row["publication_run_id"],
        row["publication_bundle_id"],
        row["publication_artifact_ref"],
    )
    if all(value is None for value in values):
        return None
    return {
        "run_id": values[0],
        "bundle_id": values[1],
        "artifact_ref": values[2],
    }


def _optional_failure(row: Any) -> dict[str, Any] | None:
    values = (
        row["failure_code"],
        row["failure_message"],
        row["failure_retryable"],
    )
    if all(value is None for value in values):
        return None
    retryable = values[2]
    if retryable not in (0, 1, False, True):
        raise ValueError("failure_retryable is not a stored boolean")
    return {
        "code": values[0],
        "message": values[1],
        "retryable": bool(retryable),
    }


def _hydrate_job(row: Any) -> EvidenceJob:
    job_id = "<unknown>"
    try:
        job_id = str(row["job_id"])
        return EvidenceJob.model_validate(
            {
                "job_id": row["job_id"],
                "kind": row["kind"],
                "protocol_revision_id": row["protocol_revision_id"],
                "request_digest": row["request_digest"],
                "status": row["status"],
                "revision": row["revision"],
                "attempt_count": row["attempt_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "lease_token": row["lease_token"],
                "lease_expires_at": row["lease_expires_at"],
                "cancel_requested_at": row["cancel_requested_at"],
                "publication": _optional_publication(row),
                "failure": _optional_failure(row),
            }
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise EvidenceJobStoreCorruptionError(
            f"stored evidence job is invalid: {job_id}"
        ) from exc


class SqlEvidenceJobStore:
    """SQLite/PostgreSQL adapter for whole validated EvidenceJob records."""

    def __init__(self, backend: SqlEvidenceBackend) -> None:
        if backend.backend_name not in {"sqlite", "postgres"}:
            raise ValueError(f"unsupported evidence job backend: {backend.backend_name}")
        self._backend = backend
        self._ensure_schema()

    def _connection(self) -> AbstractContextManager[Any]:
        return self._backend._transaction()

    def _ensure_schema(self) -> None:
        ensure_evidence_schema(self._backend)

    def create(self, job: EvidenceJob) -> bool:
        placeholders = ", ".join("?" for _ in range(20))
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            cursor = connection.execute(
                f"""
                INSERT INTO evidence_jobs ({_JOB_COLUMNS})
                VALUES ({placeholders})
                ON CONFLICT (job_id) DO NOTHING
                """,
                _job_values(job),
            )
        return cursor.rowcount == 1

    def get(self, job_id: str) -> EvidenceJob | None:
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            row = connection.execute(
                f"SELECT {_JOB_COLUMNS} FROM evidence_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return _hydrate_job(row) if row is not None else None

    def compare_and_swap(
        self,
        replacement: EvidenceJob,
        *,
        expected_revision: int,
    ) -> bool:
        if replacement.revision != expected_revision + 1:
            raise ValueError("replacement must be the next revision")
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            cursor = connection.execute(
                """
                UPDATE evidence_jobs
                SET status = ?,
                    revision = ?,
                    attempt_count = ?,
                    updated_at = ?,
                    started_at = ?,
                    finished_at = ?,
                    lease_token = ?,
                    lease_expires_at = ?,
                    cancel_requested_at = ?,
                    publication_run_id = ?,
                    publication_bundle_id = ?,
                    publication_artifact_ref = ?,
                    failure_code = ?,
                    failure_message = ?,
                    failure_retryable = ?
                WHERE job_id = ?
                  AND revision = ?
                  AND kind = ?
                  AND protocol_revision_id = ?
                  AND request_digest = ?
                  AND created_at = ?
                """,
                (
                    *_replacement_values(replacement),
                    replacement.job_id,
                    expected_revision,
                    replacement.kind,
                    replacement.protocol_revision_id,
                    replacement.request_digest,
                    _serialize_time(replacement.created_at),
                ),
            )
        return cursor.rowcount == 1

    def list_unfinished(self) -> list[EvidenceJob]:
        placeholders = ", ".join("?" for _ in _UNFINISHED_STATUSES)
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            rows = connection.execute(
                f"""
                SELECT {_JOB_COLUMNS}
                FROM evidence_jobs
                WHERE status IN ({placeholders})
                ORDER BY created_at, job_id
                """,
                _UNFINISHED_STATUSES,
            ).fetchall()
        return [_hydrate_job(row) for row in rows]


__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceJobSchemaError",
    "EvidenceJobStoreCorruptionError",
    "SqlEvidenceJobStore",
    "ensure_evidence_schema",
]
