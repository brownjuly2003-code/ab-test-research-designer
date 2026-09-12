from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from app.backend.app.evidence.jobs import (
    EvidenceJob,
    JobPublication,
    claim_evidence_job,
    create_evidence_job,
    succeed_evidence_job,
)
from app.backend.app.evidence.sql_job_store import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceJobSchemaError,
    EvidenceJobStoreCorruptionError,
    SqlEvidenceJobStore,
)
from app.backend.app.evidence.storage import EvidenceJobCoordinator
from app.backend.app.repository import ProjectRepository

T0 = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)
PROTOCOL_REVISION_ID = "sha256:" + "a" * 64
REQUEST_DIGEST = "sha256:" + "b" * 64
BUNDLE_ID = "sha256:" + "c" * 64


def _job(
    job_id: str = "job_sql_01",
    *,
    created_at: datetime = T0,
) -> EvidenceJob:
    return create_evidence_job(
        job_id=job_id,
        kind="preflight",
        protocol_revision_id=PROTOCOL_REVISION_ID,
        request_digest=REQUEST_DIGEST,
        created_at=created_at,
    )


def _publication() -> JobPublication:
    return JobPublication(
        run_id="run_sql_01",
        bundle_id=BUNDLE_ID,
        artifact_ref="bundles/run_sql_01.tmk",
    )


def _repository(path: Path) -> ProjectRepository:
    return ProjectRepository(str(path), busy_timeout_ms=5000)


def test_sql_store_factory_creates_explicit_schema_and_survives_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "evidence-jobs.sqlite3"
    first_repository = _repository(database_path)
    first_store = first_repository.create_evidence_job_store()

    assert isinstance(first_store, SqlEvidenceJobStore)
    assert first_store.create(_job()) is True
    assert first_store.create(_job()) is False
    first_repository.close()

    restarted_repository = _repository(database_path)
    restarted_store = restarted_repository.create_evidence_job_store()

    assert restarted_store.get("job_sql_01") == _job()
    with sqlite3.connect(database_path) as connection:
        column_rows = connection.execute(
            "PRAGMA table_info(evidence_jobs)"
        ).fetchall()
        columns = {str(row[1]) for row in column_rows}
        versions = connection.execute(
            "SELECT version FROM evidence_schema_migrations ORDER BY version"
        ).fetchall()

    assert "payload_json" not in columns
    assert {
        "job_id",
        "kind",
        "protocol_revision_id",
        "request_digest",
        "status",
        "revision",
        "publication_bundle_id",
        "failure_code",
    } <= columns
    job_id_column = next(row for row in column_rows if row[1] == "job_id")
    assert job_id_column[3] == 1
    assert versions == [(1,), (2,), (EVIDENCE_SCHEMA_VERSION,)]
    restarted_repository.close()


def test_sql_store_lists_only_unfinished_jobs_in_stable_order(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "ordered.sqlite3")
    store = repository.create_evidence_job_store()
    coordinator = EvidenceJobCoordinator(store)
    coordinator.create(_job("job_later", created_at=T0 + timedelta(seconds=1)))
    coordinator.create(_job("job_same_b"))
    coordinator.create(_job("job_same_a"))
    coordinator.create(_job("job_done", created_at=T0 - timedelta(seconds=1)))
    coordinator.claim(
        "job_done",
        lease_token="worker:done",
        now=T0,
        lease_expires_at=T0 + timedelta(seconds=30),
    )
    coordinator.complete(
        "job_done",
        publication=_publication(),
        lease_token="worker:done",
        now=T0 + timedelta(seconds=1),
    )

    assert [job.job_id for job in store.list_unfinished()] == [
        "job_same_a",
        "job_same_b",
        "job_later",
    ]
    repository.close()


def test_sql_store_allows_exactly_one_concurrent_cas_winner(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent.sqlite3"
    first_repository = _repository(database_path)
    second_repository = _repository(database_path)
    first_store = first_repository.create_evidence_job_store()
    second_store = second_repository.create_evidence_job_store()
    assert first_store.create(_job()) is True
    current = first_store.get("job_sql_01")
    assert current is not None
    first_claim = claim_evidence_job(
        current,
        lease_token="worker:first",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    second_claim = claim_evidence_job(
        current,
        lease_token="worker:second",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    barrier = Barrier(2)

    def commit(store: SqlEvidenceJobStore, replacement: EvidenceJob) -> bool:
        barrier.wait(timeout=5)
        return store.compare_and_swap(replacement, expected_revision=current.revision)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda pair: commit(*pair),
                ((first_store, first_claim), (second_store, second_claim)),
            )
        )

    assert sorted(outcomes) == [False, True]
    persisted = first_store.get("job_sql_01")
    assert persisted is not None
    assert persisted.revision == 1
    assert persisted.lease_token in {"worker:first", "worker:second"}
    first_repository.close()
    second_repository.close()


def test_restart_recovers_expired_sql_job_without_partial_publication(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.sqlite3"
    first_repository = _repository(database_path)
    first_coordinator = EvidenceJobCoordinator(
        first_repository.create_evidence_job_store()
    )
    first_coordinator.create(_job())
    first_coordinator.claim(
        "job_sql_01",
        lease_token="worker:first",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    first_repository.close()

    restarted_repository = _repository(database_path)
    restarted_store = restarted_repository.create_evidence_job_store()
    recovered = EvidenceJobCoordinator(restarted_store).recover_unfinished(
        now=T0 + timedelta(seconds=32)
    )

    assert [job.status for job in recovered] == ["queued"]
    persisted = restarted_store.get("job_sql_01")
    assert persisted is not None
    assert persisted.publication is None
    assert persisted.lease_token is None
    restarted_repository.close()


def test_sql_cancel_wins_over_stale_success(tmp_path: Path) -> None:
    database_path = tmp_path / "cancel.sqlite3"
    worker_repository = _repository(database_path)
    cancelling_repository = _repository(database_path)
    worker_store = worker_repository.create_evidence_job_store()
    cancelling_store = cancelling_repository.create_evidence_job_store()
    worker = EvidenceJobCoordinator(worker_store)
    canceller = EvidenceJobCoordinator(cancelling_store)
    worker.create(_job())
    running = worker.claim(
        "job_sql_01",
        lease_token="worker:lease",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    stale_success = succeed_evidence_job(
        running,
        publication=_publication(),
        lease_token="worker:lease",
        now=T0 + timedelta(seconds=3),
    )

    assert canceller.request_cancel(
        "job_sql_01", now=T0 + timedelta(seconds=2)
    ).status == "cancel_requested"
    assert (
        worker_store.compare_and_swap(
            stale_success, expected_revision=running.revision
        )
        is False
    )
    canceller.recover_unfinished(now=T0 + timedelta(seconds=32))

    persisted = cancelling_store.get("job_sql_01")
    assert persisted is not None
    assert persisted.status == "cancelled"
    assert persisted.publication is None
    worker_repository.close()
    cancelling_repository.close()


def test_sql_store_rejects_invalid_revision_and_corrupt_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt.sqlite3"
    repository = _repository(database_path)
    store = repository.create_evidence_job_store()
    assert store.create(_job()) is True

    with pytest.raises(ValueError, match="next revision"):
        store.compare_and_swap(_job(), expected_revision=0)

    with sqlite3.connect(database_path) as connection, connection:
        connection.execute(
            "UPDATE evidence_jobs SET lease_token = ? WHERE job_id = ?",
            ("orphaned-lease", "job_sql_01"),
        )

    with pytest.raises(EvidenceJobStoreCorruptionError, match="job_sql_01"):
        store.get("job_sql_01")
    repository.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "analysis"),
        ("protocol_revision_id", "sha256:" + "d" * 64),
        ("request_digest", "sha256:" + "e" * 64),
        ("created_at", T0 - timedelta(seconds=1)),
    ],
)
def test_sql_cas_cannot_change_immutable_job_identity(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    repository = _repository(tmp_path / f"immutable-{field}.sqlite3")
    store = repository.create_evidence_job_store()
    original = _job()
    assert store.create(original) is True
    claimed = claim_evidence_job(
        original,
        lease_token="worker:identity",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    replacement = claimed.model_dump(mode="python")
    replacement[field] = value

    assert store.compare_and_swap(
        EvidenceJob.model_validate(replacement), expected_revision=0
    ) is False
    assert store.get(original.job_id) == original
    repository.close()


def test_sql_store_rejects_a_partial_schema_with_a_current_ledger(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "partial-schema.sqlite3"
    repository = _repository(database_path)
    repository.create_evidence_job_store()
    repository.close()
    with sqlite3.connect(database_path) as connection, connection:
        connection.execute("DROP TABLE evidence_jobs")
        connection.execute(
            "CREATE TABLE evidence_jobs (job_id TEXT NOT NULL PRIMARY KEY)"
        )

    restarted_repository = _repository(database_path)
    with pytest.raises(EvidenceJobSchemaError, match="column shape"):
        restarted_repository.create_evidence_job_store()
    restarted_repository.close()


def test_sql_store_rejects_a_noncanonical_migration_ledger(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt-ledger.sqlite3"
    repository = _repository(database_path)
    repository.create_evidence_job_store()
    repository.close()
    with sqlite3.connect(database_path) as connection, connection:
        connection.execute(
            "UPDATE evidence_schema_migrations SET name = 'unexpected' WHERE version = 1"
        )

    restarted_repository = _repository(database_path)
    with pytest.raises(EvidenceJobSchemaError, match="ordered prefix"):
        restarted_repository.create_evidence_job_store()
    restarted_repository.close()
