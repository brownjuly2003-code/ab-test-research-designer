from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.evidence._common import SHA256_PATTERN as _SHA256_PATTERN

JobKind = Literal["preflight", "analysis"]
JobStatus = Literal[
    "queued",
    "running",
    "cancel_requested",
    "succeeded",
    "failed",
    "cancelled",
]
_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"


class JobStateError(ValueError):
    """Raised when a requested job transition is not valid for its state."""


class JobPublication(BaseModel):
    """The single discoverable result attached by a successful transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    bundle_id: str = Field(pattern=_SHA256_PATTERN)
    artifact_ref: str = Field(min_length=1, max_length=512)


class JobFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    message: str = Field(min_length=1, max_length=4096)
    retryable: bool


class EvidenceJob(BaseModel):
    """Serializable control-plane state; publication is terminal and atomic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    kind: JobKind
    protocol_revision_id: str = Field(pattern=_SHA256_PATTERN)
    request_digest: str = Field(pattern=_SHA256_PATTERN)
    status: JobStatus
    revision: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    lease_token: str | None = Field(default=None, min_length=1, max_length=256)
    lease_expires_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    publication: JobPublication | None = None
    failure: JobFailure | None = None

    @model_validator(mode="after")
    def validate_persisted_state(self) -> EvidenceJob:
        timestamps = {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "lease_expires_at": self.lease_expires_at,
            "cancel_requested_at": self.cancel_requested_at,
        }
        for name, value in timestamps.items():
            if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
                raise ValueError(f"{name} must be timezone-aware UTC")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        for name in ("started_at", "finished_at", "cancel_requested_at"):
            value = timestamps[name]
            if value is not None and value < self.created_at:
                raise ValueError(f"{name} must not precede created_at")
            if value is not None and value > self.updated_at:
                raise ValueError(f"{name} must not follow updated_at")
        if (self.started_at is None) != (self.attempt_count == 0):
            raise ValueError("started_at and a positive attempt count must appear together")

        active_lease = self.status in {"running", "cancel_requested"}
        has_lease_token = self.lease_token is not None
        has_lease_expiry = self.lease_expires_at is not None
        if active_lease and not (has_lease_token and has_lease_expiry):
            raise ValueError("running and cancel_requested jobs require exactly one active lease")
        if not active_lease and (has_lease_token or has_lease_expiry):
            raise ValueError("jobs without an active lease forbid lease fields")
        if active_lease:
            if self.started_at is None or self.attempt_count < 1:
                raise ValueError("leased jobs require a start time and positive attempt count")
            if self.lease_expires_at is not None and self.lease_expires_at <= self.updated_at:
                raise ValueError("active lease must expire after updated_at")

        terminal = self.status in {"succeeded", "failed", "cancelled"}
        if terminal != (self.finished_at is not None):
            raise ValueError("terminal jobs require finished_at and unfinished jobs forbid it")
        if self.status in {"succeeded", "failed"} and self.started_at is None:
            raise ValueError("succeeded and failed jobs require started_at")
        if (self.publication is not None) != (self.status == "succeeded"):
            raise ValueError("publication is allowed only on a succeeded job")
        if (self.failure is not None) != (self.status == "failed"):
            raise ValueError("failure details are allowed only on a failed job")
        cancelled_state = self.status in {"cancel_requested", "cancelled"}
        if cancelled_state != (self.cancel_requested_at is not None):
            raise ValueError("cancel_requested_at must match a cancellation state")
        return self


def _evolve(job: EvidenceJob, **changes: Any) -> EvidenceJob:
    value = job.model_dump(mode="python")
    value.update(changes)
    return EvidenceJob.model_validate(value)


def _validate_transition_time(job: EvidenceJob, now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise JobStateError("transition time must be timezone-aware UTC")
    if now < job.updated_at:
        raise JobStateError("transition time must not precede the current revision")


def _validate_lease(job: EvidenceJob, lease_token: str, now: datetime) -> None:
    if job.lease_token != lease_token:
        raise JobStateError("lease token does not own the current job revision")
    if job.lease_expires_at is None or now >= job.lease_expires_at:
        raise JobStateError("job lease has expired")


def create_evidence_job(
    *,
    job_id: str,
    kind: JobKind,
    protocol_revision_id: str,
    request_digest: str,
    created_at: datetime,
) -> EvidenceJob:
    return EvidenceJob(
        job_id=job_id,
        kind=kind,
        protocol_revision_id=protocol_revision_id,
        request_digest=request_digest,
        status="queued",
        revision=0,
        attempt_count=0,
        created_at=created_at,
        updated_at=created_at,
    )


def claim_evidence_job(
    job: EvidenceJob,
    *,
    lease_token: str,
    now: datetime,
    lease_expires_at: datetime,
) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status != "queued":
        raise JobStateError(f"cannot claim job from {job.status}")
    if not lease_token.strip():
        raise JobStateError("lease token must not be blank")
    if lease_expires_at.tzinfo is None or lease_expires_at.utcoffset() != timedelta(0):
        raise JobStateError("lease expiry must be timezone-aware UTC")
    if lease_expires_at <= now:
        raise JobStateError("lease expiry must be after claim time")
    return _evolve(
        job,
        status="running",
        revision=job.revision + 1,
        attempt_count=job.attempt_count + 1,
        updated_at=now,
        started_at=job.started_at or now,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
    )


def request_evidence_job_cancel(job: EvidenceJob, *, now: datetime) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status in {"succeeded", "failed", "cancelled", "cancel_requested"}:
        return job
    if job.status == "queued":
        return _evolve(
            job,
            status="cancelled",
            revision=job.revision + 1,
            updated_at=now,
            finished_at=now,
            cancel_requested_at=now,
        )
    return _evolve(
        job,
        status="cancel_requested",
        revision=job.revision + 1,
        updated_at=now,
        cancel_requested_at=now,
    )


def recover_evidence_job(job: EvidenceJob, *, now: datetime) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status not in {"running", "cancel_requested"}:
        return job
    if job.lease_expires_at is not None and now < job.lease_expires_at:
        return job
    if job.status == "cancel_requested":
        return _evolve(
            job,
            status="cancelled",
            revision=job.revision + 1,
            updated_at=now,
            finished_at=now,
            lease_token=None,
            lease_expires_at=None,
        )
    return _evolve(
        job,
        status="queued",
        revision=job.revision + 1,
        updated_at=now,
        lease_token=None,
        lease_expires_at=None,
    )


def succeed_evidence_job(
    job: EvidenceJob,
    *,
    publication: JobPublication,
    lease_token: str,
    now: datetime,
) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status != "running":
        raise JobStateError(f"cannot succeed job from {job.status}")
    _validate_lease(job, lease_token, now)
    return _evolve(
        job,
        status="succeeded",
        revision=job.revision + 1,
        updated_at=now,
        finished_at=now,
        lease_token=None,
        lease_expires_at=None,
        publication=publication,
    )


def fail_evidence_job(
    job: EvidenceJob,
    *,
    failure: JobFailure,
    lease_token: str,
    now: datetime,
) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status != "running":
        raise JobStateError(f"cannot fail job from {job.status}")
    _validate_lease(job, lease_token, now)
    return _evolve(
        job,
        status="failed",
        revision=job.revision + 1,
        updated_at=now,
        finished_at=now,
        lease_token=None,
        lease_expires_at=None,
        failure=failure,
    )


def acknowledge_evidence_job_cancel(
    job: EvidenceJob,
    *,
    lease_token: str,
    now: datetime,
) -> EvidenceJob:
    _validate_transition_time(job, now)
    if job.status != "cancel_requested":
        raise JobStateError(f"cannot acknowledge cancellation from {job.status}")
    _validate_lease(job, lease_token, now)
    return _evolve(
        job,
        status="cancelled",
        revision=job.revision + 1,
        updated_at=now,
        finished_at=now,
        lease_token=None,
        lease_expires_at=None,
    )
