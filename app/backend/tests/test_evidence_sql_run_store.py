from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from app.backend.app.evidence.abx import verify_bundle
from app.backend.app.evidence.jobs import create_evidence_job
from app.backend.app.evidence.run_abx import publish_completed_run_abx
from app.backend.app.evidence.sql_job_store import EVIDENCE_SCHEMA_VERSION
from app.backend.app.evidence.sql_run_store import (
    EvidenceRunOriginError,
    EvidenceRunSchemaError,
    EvidenceRunStoreCorruptionError,
    SqlEvidenceRunStore,
)
from app.backend.app.evidence.storage import EvidenceJobCoordinator
from app.backend.app.repository import ProjectRepository
from app.backend.tests.evidence_run_fixtures import completed_asos_run


def _repository(path: Path) -> ProjectRepository:
    return ProjectRepository(str(path), busy_timeout_ms=5000)


def _prepare_running_origin(repository: ProjectRepository) -> None:
    run = completed_asos_run()
    started_at = datetime.fromisoformat(run.started_at[:-1] + "+00:00")
    sealed_at = datetime.fromisoformat(run.sealed_at[:-1] + "+00:00")
    coordinator = EvidenceJobCoordinator(repository.create_evidence_job_store())
    coordinator.create(
        create_evidence_job(
            job_id=run.origin_job_id,
            kind=run.kind,
            protocol_revision_id=run.protocol_revision_id,
            request_digest="sha256:" + "a" * 64,
            created_at=started_at - timedelta(seconds=1),
        )
    )
    coordinator.claim(
        run.origin_job_id,
        lease_token="worker:run-store",
        now=started_at,
        lease_expires_at=sealed_at + timedelta(days=1),
    )


def _downgrade_run_artifacts_to_v2(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE run_artifacts_v2 (
                run_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                path TEXT NOT NULL,
                role TEXT NOT NULL CHECK (
                    role IN (
                        'protocol', 'amendments', 'run', 'source', 'metric',
                        'query', 'finding', 'estimate', 'decision', 'report', 'schema'
                    )
                ),
                schema_id TEXT,
                artifact_digest TEXT NOT NULL,
                PRIMARY KEY (run_id, path),
                UNIQUE (run_id, ordinal),
                FOREIGN KEY (run_id) REFERENCES evidence_runs (run_id),
                FOREIGN KEY (artifact_digest) REFERENCES evidence_artifacts (digest)
            );
            INSERT INTO run_artifacts_v2
                (run_id, ordinal, path, role, schema_id, artifact_digest)
            SELECT run_id, ordinal, path, role, schema_id, artifact_digest
            FROM run_artifacts;
            DROP TABLE run_artifacts;
            ALTER TABLE run_artifacts_v2 RENAME TO run_artifacts;
            DELETE FROM evidence_schema_migrations WHERE version > 2;
            """
        )


def test_sql_run_store_is_append_only_explicit_and_survives_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "evidence-runs.sqlite3"
    run = completed_asos_run()
    first_repository = _repository(database_path)
    artifact_root = tmp_path / "artifacts"
    first_store = first_repository.create_evidence_run_store(artifact_root)
    _prepare_running_origin(first_repository)

    assert isinstance(first_store, SqlEvidenceRunStore)
    assert first_store.create(run) is True
    assert first_store.create(run) is False
    first_repository.close()

    restarted_repository = _repository(database_path)
    restarted_store = restarted_repository.create_evidence_run_store(artifact_root)
    assert restarted_store.get(run.run_id) == run

    with sqlite3.connect(database_path) as connection:
        run_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(evidence_runs)")
        }
        artifact_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(evidence_artifacts)")
        }
        mapping_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(run_artifacts)")
        }
        versions = connection.execute(
            "SELECT version FROM evidence_schema_migrations ORDER BY version"
        ).fetchall()

    assert "payload_json" not in run_columns | artifact_columns | mapping_columns
    assert {
        "run_id",
        "origin_job_id",
        "protocol_revision_id",
        "runner_digest",
        "record_digest",
        "artifact_count",
    } <= run_columns
    assert {"digest", "media_type", "size", "storage_key"} <= artifact_columns
    assert {"run_id", "path", "role", "schema_id", "artifact_digest"} <= mapping_columns
    assert versions == [(1,), (2,), (EVIDENCE_SCHEMA_VERSION,)]
    restarted_repository.close()


def test_evidence_schema_v3_migrates_existing_runs_and_allows_method_role(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "evidence-v2.sqlite3"
    artifact_root = tmp_path / "artifacts"
    run = completed_asos_run()
    repository = _repository(database_path)
    _prepare_running_origin(repository)
    assert repository.create_evidence_run_store(artifact_root).create(run) is True
    repository.close()
    _downgrade_run_artifacts_to_v2(database_path)

    restarted_repository = _repository(database_path)
    restarted_store = restarted_repository.create_evidence_run_store(artifact_root)
    assert restarted_store.get(run.run_id) == run

    with sqlite3.connect(database_path) as connection:
        versions = connection.execute(
            "SELECT version FROM evidence_schema_migrations ORDER BY version"
        ).fetchall()
        artifact_digest = connection.execute(
            "SELECT artifact_digest FROM run_artifacts WHERE run_id = ? LIMIT 1",
            (run.run_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO run_artifacts
                (run_id, ordinal, path, role, schema_id, artifact_digest)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                len(run.artifacts),
                "methods/profile.json",
                "method",
                "urn:evidenceos:abx:schema:0.1:method-profile",
                artifact_digest,
            ),
        )
        connection.rollback()

    assert versions == [(1,), (2,), (3,)]
    restarted_repository.close()


def test_hydrated_sql_run_publishes_as_verified_abx_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "published-run.sqlite3"
    artifact_root = tmp_path / "artifacts"
    run = completed_asos_run()
    first_repository = _repository(database_path)
    _prepare_running_origin(first_repository)
    assert first_repository.create_evidence_run_store(artifact_root).create(run) is True
    first_repository.close()

    restarted_repository = _repository(database_path)
    restarted_store = restarted_repository.create_evidence_run_store(artifact_root)
    destination = tmp_path / "hydrated.tmk"

    result = publish_completed_run_abx(
        restarted_store,
        run_id=run.run_id,
        destination=destination,
    )

    assert result == verify_bundle(destination)
    assert result["valid"] is True
    assert result["run_id"] == run.run_id
    restarted_repository.close()


def test_sql_run_store_allows_exactly_one_concurrent_create(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent-runs.sqlite3"
    first_repository = _repository(database_path)
    second_repository = _repository(database_path)
    artifact_root = tmp_path / "artifacts"
    first_store = first_repository.create_evidence_run_store(artifact_root)
    second_store = second_repository.create_evidence_run_store(artifact_root)
    _prepare_running_origin(first_repository)
    run = completed_asos_run()
    barrier = Barrier(2)

    def create(store: SqlEvidenceRunStore) -> bool:
        barrier.wait(timeout=5)
        return store.create(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, (first_store, second_store)))

    assert sorted(outcomes) == [False, True]
    assert first_store.get(run.run_id) == run
    first_repository.close()
    second_repository.close()


def test_sql_run_store_rolls_back_the_whole_record_on_artifact_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atomic-runs.sqlite3"
    repository = _repository(database_path)
    store = repository.create_evidence_run_store(tmp_path / "artifacts")
    _prepare_running_origin(repository)
    run = completed_asos_run()
    with sqlite3.connect(database_path) as connection, connection:
        connection.execute(
            """
            CREATE TRIGGER reject_evidence_estimate
            BEFORE INSERT ON run_artifacts
            WHEN NEW.role = 'estimate'
            BEGIN
                SELECT RAISE(ABORT, 'forced artifact failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced artifact failure"):
        store.create(run)

    assert store.get(run.run_id) is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence_runs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM run_artifacts").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM evidence_artifacts").fetchone() == (0,)
    repository.close()


def test_sql_run_store_rejects_corrupt_artifact_payloads(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt-run.sqlite3"
    repository = _repository(database_path)
    artifact_root = tmp_path / "artifacts"
    store = repository.create_evidence_run_store(artifact_root)
    _prepare_running_origin(repository)
    run = completed_asos_run()
    assert store.create(run) is True
    with sqlite3.connect(database_path) as connection, connection:
        storage_key = connection.execute(
            """
            SELECT evidence_artifacts.storage_key
            FROM run_artifacts
            JOIN evidence_artifacts
              ON evidence_artifacts.digest = run_artifacts.artifact_digest
            WHERE run_artifacts.run_id = ? AND run_artifacts.path = ?
            """,
            (run.run_id, "run/run.json"),
        ).fetchone()[0]
    (artifact_root / Path(str(storage_key))).write_bytes(b"tampered")

    with pytest.raises(EvidenceRunStoreCorruptionError, match=run.run_id):
        store.get(run.run_id)
    repository.close()


def test_sql_run_store_rejects_current_ledger_with_partial_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "partial-run-schema.sqlite3"
    repository = _repository(database_path)
    artifact_root = tmp_path / "artifacts"
    repository.create_evidence_run_store(artifact_root)
    repository.close()
    with sqlite3.connect(database_path) as connection, connection:
        connection.execute("DROP TABLE run_artifacts")
        connection.execute(
            "CREATE TABLE run_artifacts (run_id TEXT NOT NULL, path TEXT NOT NULL)"
        )

    restarted_repository = _repository(database_path)
    with pytest.raises(EvidenceRunSchemaError, match="column shape"):
        restarted_repository.create_evidence_run_store(artifact_root)
    restarted_repository.close()


def test_sql_run_store_rejects_a_noncanonical_migration_ledger(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "corrupt-run-ledger.sqlite3"
    repository = _repository(database_path)
    artifact_root = tmp_path / "artifacts"
    repository.create_evidence_run_store(artifact_root)
    repository.close()
    with sqlite3.connect(database_path) as connection, connection:
        connection.execute(
            "UPDATE evidence_schema_migrations SET name = 'unexpected' WHERE version = 2"
        )

    restarted_repository = _repository(database_path)
    with pytest.raises(EvidenceRunSchemaError, match="ordered prefix"):
        restarted_repository.create_evidence_run_store(artifact_root)
    restarted_repository.close()


def test_sql_run_store_requires_the_exact_running_origin_revision(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "missing-origin.sqlite3")
    store = repository.create_evidence_run_store(tmp_path / "artifacts")

    with pytest.raises(EvidenceRunOriginError, match="running origin job revision"):
        store.create(completed_asos_run())
    repository.close()
