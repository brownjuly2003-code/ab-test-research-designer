from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, cast

from pydantic import ValidationError

from app.backend.app.evidence.artifact_store import (
    ArtifactStoreCorruptionError,
    FileArtifactStore,
)
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
)
from app.backend.app.evidence.sql_job_store import (
    EvidenceJobSchemaError,
    SqlEvidenceBackend,
    ensure_evidence_schema,
)

_RUN_COLUMNS = """
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


class EvidenceRunStoreCorruptionError(RuntimeError):
    """Raised when stored metadata or content-addressed bytes do not validate."""


class EvidenceRunSchemaError(RuntimeError):
    """Raised when the shared evidence schema cannot support completed runs."""


class EvidenceRunOriginError(RuntimeError):
    """Raised when a run is not sealed from its exact running job revision."""


class EvidenceRunConflictError(RuntimeError):
    """Raised when an immutable run or artifact identity already means something else."""


class _SqlCursor(Protocol):
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class _SqlConnection(Protocol):
    def execute(self, sql: str, params: Any = None) -> _SqlCursor: ...


def _run_values(run: CompletedEvidenceRun) -> tuple[Any, ...]:
    return (
        run.run_id,
        run.origin_job_id,
        run.origin_job_revision,
        run.protocol_revision_id,
        run.kind,
        run.status,
        run.started_at,
        run.completed_at,
        run.sealed_at,
        run.runner_digest,
        len(run.required_capabilities),
        len(run.artifacts),
        run.record_digest,
    )


def _same_artifact_metadata(row: Any, artifact: EvidenceRunArtifact, storage_key: str) -> bool:
    return (
        row["digest"] == artifact.digest
        and row["media_type"] == artifact.media_type
        and int(row["size"]) == artifact.size
        and row["storage_key"] == storage_key
    )


class SqlEvidenceRunStore:
    """Append-only SQLite/PostgreSQL metadata over content-addressed files."""

    def __init__(
        self,
        backend: SqlEvidenceBackend,
        artifact_store: FileArtifactStore,
    ) -> None:
        if backend.backend_name not in {"sqlite", "postgres"}:
            raise ValueError(f"unsupported evidence run backend: {backend.backend_name}")
        self._backend = backend
        self._artifact_store = artifact_store
        try:
            ensure_evidence_schema(backend)
        except EvidenceJobSchemaError as error:
            raise EvidenceRunSchemaError(str(error)) from error

    def _connection(self) -> AbstractContextManager[Any]:
        return self._backend._transaction()

    def _existing_record_digest(
        self,
        connection: _SqlConnection,
        run_id: str,
    ) -> str | None:
        row = connection.execute(
            "SELECT record_digest FROM evidence_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return str(row["record_digest"]) if row is not None else None

    def _assert_origin(
        self,
        connection: _SqlConnection,
        run: CompletedEvidenceRun,
    ) -> None:
        suffix = " FOR UPDATE" if self._backend.backend_name == "postgres" else ""
        row = connection.execute(
            "SELECT job_id, revision, status, kind, protocol_revision_id "
            f"FROM evidence_jobs WHERE job_id = ?{suffix}",
            (run.origin_job_id,),
        ).fetchone()
        if row is None or (
            int(row["revision"]) != run.origin_job_revision
            or row["status"] != "running"
            or row["kind"] != run.kind
            or row["protocol_revision_id"] != run.protocol_revision_id
        ):
            raise EvidenceRunOriginError(
                f"run requires its exact running origin job revision: {run.origin_job_id}"
            )

    def create(self, run: CompletedEvidenceRun) -> bool:
        stored_artifacts = tuple(
            (
                artifact,
                self._artifact_store.put(
                    artifact.payload,
                    expected_digest=artifact.digest,
                ),
            )
            for artifact in run.artifacts
        )
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            if self._backend.backend_name == "sqlite":
                connection.execute("BEGIN IMMEDIATE")
            existing_digest = self._existing_record_digest(connection, run.run_id)
            if existing_digest is not None:
                if existing_digest != run.record_digest:
                    raise EvidenceRunConflictError(
                        f"run ID already has different immutable content: {run.run_id}"
                    )
                return False

            self._assert_origin(connection, run)
            placeholders = ", ".join("?" for _ in range(13))
            inserted = connection.execute(
                f"""
                INSERT INTO evidence_runs ({_RUN_COLUMNS})
                VALUES ({placeholders})
                ON CONFLICT (run_id) DO NOTHING
                """,
                _run_values(run),
            )
            if inserted.rowcount != 1:
                existing_digest = self._existing_record_digest(connection, run.run_id)
                if existing_digest != run.record_digest:
                    raise EvidenceRunConflictError(
                        f"run ID changed concurrently: {run.run_id}"
                    )
                return False

            for ordinal, capability in enumerate(run.required_capabilities):
                connection.execute(
                    "INSERT INTO evidence_run_capabilities "
                    "(run_id, ordinal, capability) VALUES (?, ?, ?)",
                    (run.run_id, ordinal, capability),
                )
            for ordinal, (artifact, storage_key) in enumerate(stored_artifacts):
                connection.execute(
                    """
                    INSERT INTO evidence_artifacts (digest, media_type, size, storage_key)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (digest) DO NOTHING
                    """,
                    (
                        artifact.digest,
                        artifact.media_type,
                        artifact.size,
                        storage_key,
                    ),
                )
                artifact_row = connection.execute(
                    "SELECT digest, media_type, size, storage_key "
                    "FROM evidence_artifacts WHERE digest = ?",
                    (artifact.digest,),
                ).fetchone()
                if artifact_row is None or not _same_artifact_metadata(
                    artifact_row,
                    artifact,
                    storage_key,
                ):
                    raise EvidenceRunConflictError(
                        f"artifact digest has conflicting metadata: {artifact.digest}"
                    )
                connection.execute(
                    """
                    INSERT INTO run_artifacts
                        (run_id, ordinal, path, role, schema_id, artifact_digest)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        ordinal,
                        artifact.path,
                        artifact.role,
                        artifact.schema_id,
                        artifact.digest,
                    ),
                )
        return True

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            run_row = connection.execute(
                f"SELECT {_RUN_COLUMNS} FROM evidence_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                return None
            capability_rows = connection.execute(
                "SELECT ordinal, capability FROM evidence_run_capabilities "
                "WHERE run_id = ? ORDER BY ordinal",
                (run_id,),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT
                    run_artifacts.ordinal,
                    run_artifacts.path,
                    run_artifacts.role,
                    run_artifacts.schema_id,
                    evidence_artifacts.digest,
                    evidence_artifacts.media_type,
                    evidence_artifacts.size,
                    evidence_artifacts.storage_key
                FROM run_artifacts
                JOIN evidence_artifacts
                  ON evidence_artifacts.digest = run_artifacts.artifact_digest
                WHERE run_artifacts.run_id = ?
                ORDER BY run_artifacts.ordinal
                """,
                (run_id,),
            ).fetchall()

        try:
            if int(run_row["required_capability_count"]) != len(capability_rows):
                raise ValueError("stored capability count does not match its rows")
            if int(run_row["artifact_count"]) != len(artifact_rows):
                raise ValueError("stored artifact count does not match its rows")
            if [int(row["ordinal"]) for row in capability_rows] != list(
                range(len(capability_rows))
            ):
                raise ValueError("stored capability ordinals are not contiguous")
            if [int(row["ordinal"]) for row in artifact_rows] != list(
                range(len(artifact_rows))
            ):
                raise ValueError("stored artifact ordinals are not contiguous")
            artifacts = tuple(
                EvidenceRunArtifact.model_validate(
                    {
                        "path": row["path"],
                        "role": row["role"],
                        "media_type": row["media_type"],
                        "schema_id": row["schema_id"],
                        "size": int(row["size"]),
                        "digest": row["digest"],
                        "payload": self._artifact_store.get(
                            str(row["storage_key"]),
                            expected_digest=str(row["digest"]),
                            expected_size=int(row["size"]),
                        ),
                    }
                )
                for row in artifact_rows
            )
            return CompletedEvidenceRun.model_validate(
                {
                    "run_id": run_row["run_id"],
                    "origin_job_id": run_row["origin_job_id"],
                    "origin_job_revision": int(run_row["origin_job_revision"]),
                    "protocol_revision_id": run_row["protocol_revision_id"],
                    "kind": run_row["kind"],
                    "status": run_row["status"],
                    "started_at": run_row["started_at"],
                    "completed_at": run_row["completed_at"],
                    "sealed_at": run_row["sealed_at"],
                    "runner_digest": run_row["runner_digest"],
                    "required_capabilities": tuple(
                        str(row["capability"]) for row in capability_rows
                    ),
                    "artifacts": artifacts,
                    "record_digest": run_row["record_digest"],
                }
            )
        except (
            ArtifactStoreCorruptionError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            raise EvidenceRunStoreCorruptionError(
                f"stored evidence run is invalid: {run_id}"
            ) from error

    def list_run_ids(self) -> list[str]:
        """Return persisted run identities in stable creation order."""

        with self._connection() as raw_connection:
            connection = cast(_SqlConnection, raw_connection)
            rows = connection.execute(
                "SELECT run_id FROM evidence_runs ORDER BY sealed_at, run_id"
            ).fetchall()
        return [str(row["run_id"]) for row in rows]


__all__ = [
    "EvidenceRunConflictError",
    "EvidenceRunOriginError",
    "EvidenceRunSchemaError",
    "EvidenceRunStoreCorruptionError",
    "SqlEvidenceRunStore",
]
