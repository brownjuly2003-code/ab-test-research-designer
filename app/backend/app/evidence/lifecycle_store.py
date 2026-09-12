from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.backend.app.evidence.jobs import JobPublication, create_evidence_job
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.evidence.sql_run_store import SqlEvidenceRunStore
from app.backend.app.evidence.storage import EvidenceJobCoordinator
from app.backend.app.repository import ProjectRepository


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("completed run timestamp must be UTC")
    return parsed


class LifecycleEvidenceRunStore:
    """Attach completed runs to their persisted evidence-job lifecycle."""

    def __init__(self, repository: ProjectRepository, artifact_root: Path) -> None:
        self._store: SqlEvidenceRunStore = repository.create_evidence_run_store(
            artifact_root
        )
        self._coordinator = EvidenceJobCoordinator(
            repository.create_evidence_job_store()
        )
        self._leases: dict[str, tuple[str, str]] = {}

    def create(self, run: CompletedEvidenceRun) -> bool:
        if self._store.get(run.run_id) is not None:
            return self._store.create(run)

        started_at = _timestamp(run.started_at)
        lease_token = f"trialmark:{run.run_id}"
        lease_expires_at = max(
            _timestamp(run.sealed_at),
            datetime.now(UTC),
        ) + timedelta(days=1)
        self._coordinator.create(
            create_evidence_job(
                job_id=run.origin_job_id,
                kind=run.kind,
                protocol_revision_id=run.protocol_revision_id,
                request_digest=run.record_digest,
                created_at=started_at,
            )
        )
        self._coordinator.claim(
            run.origin_job_id,
            lease_token=lease_token,
            now=started_at,
            lease_expires_at=lease_expires_at,
        )
        inserted = self._store.create(run)
        if inserted:
            self._leases[run.run_id] = (run.origin_job_id, lease_token)
        return inserted

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        return self._store.get(run_id)

    def list_run_ids(self) -> list[str]:
        return self._store.list_run_ids()

    def complete(
        self,
        run: CompletedEvidenceRun,
        *,
        bundle_id: str,
        artifact_ref: str,
    ) -> None:
        lease = self._leases.pop(run.run_id, None)
        if lease is None:
            return
        job_id, lease_token = lease
        self._coordinator.complete(
            job_id,
            publication=JobPublication(
                run_id=run.run_id,
                bundle_id=bundle_id,
                artifact_ref=artifact_ref,
            ),
            lease_token=lease_token,
            now=datetime.now(UTC),
        )


__all__ = ["LifecycleEvidenceRunStore"]
