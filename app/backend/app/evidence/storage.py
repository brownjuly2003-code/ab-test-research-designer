from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.backend.app.evidence.jobs import (
    EvidenceJob,
    JobFailure,
    JobPublication,
    acknowledge_evidence_job_cancel,
    claim_evidence_job,
    fail_evidence_job,
    recover_evidence_job,
    request_evidence_job_cancel,
    succeed_evidence_job,
)


class JobNotFoundError(LookupError):
    """Raised when a job identifier is not present in the store."""


class JobConflictError(RuntimeError):
    """Raised when another process committed the expected job revision first."""


class EvidenceJobStore(Protocol):
    """Atomic persistence boundary for whole validated job records."""

    def create(self, job: EvidenceJob) -> bool:
        """Insert only when the job id is absent; return whether it was inserted."""
        ...

    def get(self, job_id: str) -> EvidenceJob | None: ...

    def compare_and_swap(self, replacement: EvidenceJob, *, expected_revision: int) -> bool:
        """Atomically replace one record only when its revision still matches."""
        ...

    def list_unfinished(self) -> list[EvidenceJob]:
        """Return queued, running, and cancel-requested records."""
        ...


class EvidenceJobCoordinator:
    """Applies state transitions and commits each as one revision-checked write."""

    def __init__(self, store: EvidenceJobStore) -> None:
        self._store = store

    def create(self, job: EvidenceJob) -> EvidenceJob:
        if not self._store.create(job):
            raise JobConflictError(f"job already exists: {job.job_id}")
        return job

    def _load(self, job_id: str) -> EvidenceJob:
        job = self._store.get(job_id)
        if job is None:
            raise JobNotFoundError(f"job not found: {job_id}")
        return job

    def _commit(self, current: EvidenceJob, replacement: EvidenceJob) -> EvidenceJob:
        if replacement.revision == current.revision:
            return current
        if replacement.job_id != current.job_id or replacement.revision != current.revision + 1:
            raise JobConflictError("replacement is not the next revision of the current job")
        if not self._store.compare_and_swap(replacement, expected_revision=current.revision):
            raise JobConflictError(f"job revision changed concurrently: {current.job_id}")
        return replacement

    def claim(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> EvidenceJob:
        current = self._load(job_id)
        return self._commit(
            current,
            claim_evidence_job(
                current,
                lease_token=lease_token,
                now=now,
                lease_expires_at=lease_expires_at,
            ),
        )

    def request_cancel(self, job_id: str, *, now: datetime) -> EvidenceJob:
        current = self._load(job_id)
        return self._commit(current, request_evidence_job_cancel(current, now=now))

    def complete(
        self,
        job_id: str,
        *,
        publication: JobPublication,
        lease_token: str,
        now: datetime,
    ) -> EvidenceJob:
        current = self._load(job_id)
        return self._commit(
            current,
            succeed_evidence_job(
                current,
                publication=publication,
                lease_token=lease_token,
                now=now,
            ),
        )

    def fail(
        self,
        job_id: str,
        *,
        failure: JobFailure,
        lease_token: str,
        now: datetime,
    ) -> EvidenceJob:
        current = self._load(job_id)
        return self._commit(
            current,
            fail_evidence_job(
                current,
                failure=failure,
                lease_token=lease_token,
                now=now,
            ),
        )

    def acknowledge_cancel(
        self,
        job_id: str,
        *,
        lease_token: str,
        now: datetime,
    ) -> EvidenceJob:
        current = self._load(job_id)
        return self._commit(
            current,
            acknowledge_evidence_job_cancel(
                current,
                lease_token=lease_token,
                now=now,
            ),
        )

    def recover_unfinished(self, *, now: datetime) -> list[EvidenceJob]:
        recovered: list[EvidenceJob] = []
        for current in self._store.list_unfinished():
            replacement = recover_evidence_job(current, now=now)
            if replacement.revision == current.revision:
                continue
            if self._store.compare_and_swap(replacement, expected_revision=current.revision):
                recovered.append(replacement)
        return recovered
