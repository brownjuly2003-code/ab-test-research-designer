from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.jobs import (
    EvidenceJob,
    JobPublication,
    JobStateError,
    create_evidence_job,
    succeed_evidence_job,
)
from app.backend.app.evidence.storage import (
    EvidenceJobCoordinator,
    EvidenceJobStore,
)

T0 = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
PROTOCOL_REVISION_ID = "sha256:" + "a" * 64
REQUEST_DIGEST = "sha256:" + "b" * 64
BUNDLE_ID = "sha256:" + "c" * 64


class SerializedJobStore:
    """Test port that persists JSON rather than retaining model instances."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    def create(self, job: EvidenceJob) -> bool:
        if job.job_id in self.rows:
            return False
        self.rows[job.job_id] = job.model_dump_json()
        return True

    def get(self, job_id: str) -> EvidenceJob | None:
        payload = self.rows.get(job_id)
        return EvidenceJob.model_validate_json(payload) if payload is not None else None

    def compare_and_swap(self, replacement: EvidenceJob, *, expected_revision: int) -> bool:
        current = self.get(replacement.job_id)
        if current is None or current.revision != expected_revision:
            return False
        assert replacement.revision == expected_revision + 1
        self.rows[replacement.job_id] = replacement.model_dump_json()
        return True

    def list_unfinished(self) -> list[EvidenceJob]:
        return [
            job
            for payload in self.rows.values()
            if (job := EvidenceJob.model_validate_json(payload)).status
            in {"queued", "running", "cancel_requested"}
        ]


def _store() -> tuple[SerializedJobStore, EvidenceJobStore]:
    concrete = SerializedJobStore()
    return concrete, concrete


def _job() -> EvidenceJob:
    return create_evidence_job(
        job_id="job_preflight_01",
        kind="preflight",
        protocol_revision_id=PROTOCOL_REVISION_ID,
        request_digest=REQUEST_DIGEST,
        created_at=T0,
    )


def _publication() -> JobPublication:
    return JobPublication(
        run_id="run_preflight_01",
        bundle_id=BUNDLE_ID,
        artifact_ref="bundles/run_preflight_01.tmk",
    )


def test_restart_recovers_expired_work_without_publishing_partial_run() -> None:
    concrete, port = _store()
    first_process = EvidenceJobCoordinator(port)
    first_process.create(_job())
    running = first_process.claim(
        "job_preflight_01",
        lease_token="worker-a:lease-1",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    assert running.status == "running"
    assert running.attempt_count == 1

    restarted_process = EvidenceJobCoordinator(port)
    recovered = restarted_process.recover_unfinished(now=T0 + timedelta(seconds=32))

    assert [job.status for job in recovered] == ["queued"]
    persisted = concrete.get("job_preflight_01")
    assert persisted is not None
    assert persisted.publication is None
    assert persisted.lease_token is None

    rerun = restarted_process.claim(
        persisted.job_id,
        lease_token="worker-b:lease-2",
        now=T0 + timedelta(seconds=33),
        lease_expires_at=T0 + timedelta(seconds=63),
    )
    completed = restarted_process.complete(
        rerun.job_id,
        publication=_publication(),
        lease_token="worker-b:lease-2",
        now=T0 + timedelta(seconds=40),
    )

    assert completed.status == "succeeded"
    assert completed.publication == _publication()
    assert concrete.list_unfinished() == []


def test_cancel_wins_over_stale_success_and_restart_finishes_cancellation() -> None:
    concrete, port = _store()
    worker_process = EvidenceJobCoordinator(port)
    worker_process.create(_job())
    running = worker_process.claim(
        "job_preflight_01",
        lease_token="worker-a:lease-1",
        now=T0 + timedelta(seconds=1),
        lease_expires_at=T0 + timedelta(seconds=31),
    )
    stale_success = succeed_evidence_job(
        running,
        publication=_publication(),
        lease_token="worker-a:lease-1",
        now=T0 + timedelta(seconds=10),
    )

    restarted_process = EvidenceJobCoordinator(port)
    cancel_requested = restarted_process.request_cancel(
        running.job_id,
        now=T0 + timedelta(seconds=5),
    )
    assert cancel_requested.status == "cancel_requested"
    assert concrete.compare_and_swap(stale_success, expected_revision=running.revision) is False

    with pytest.raises(JobStateError, match="cancel_requested"):
        worker_process.complete(
            running.job_id,
            publication=_publication(),
            lease_token="worker-a:lease-1",
            now=T0 + timedelta(seconds=10),
        )

    recovered = restarted_process.recover_unfinished(now=T0 + timedelta(seconds=32))
    assert [job.status for job in recovered] == ["cancelled"]
    persisted = concrete.get(running.job_id)
    assert persisted is not None
    assert persisted.status == "cancelled"
    assert persisted.publication is None


def test_job_model_rejects_publication_outside_succeeded_state() -> None:
    invalid = _job().model_dump(mode="python")
    invalid["publication"] = _publication().model_dump(mode="python")

    with pytest.raises(ValidationError, match="publication"):
        EvidenceJob.model_validate(invalid)


@pytest.mark.parametrize(
    "changes",
    [
        {"lease_token": "orphaned-token"},
        {"lease_expires_at": T0 + timedelta(seconds=30)},
        {"started_at": T0 + timedelta(seconds=1)},
    ],
)
def test_job_model_rejects_partial_or_chronologically_impossible_state(
    changes: dict[str, object],
) -> None:
    invalid = _job().model_dump(mode="python")
    invalid.update(changes)

    with pytest.raises(ValidationError):
        EvidenceJob.model_validate(invalid)
