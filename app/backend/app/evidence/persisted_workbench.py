from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.backend.app.evidence._common import load_ijson_object
from app.backend.app.evidence.abx import verify_logical_bundle
from app.backend.app.evidence.decision_statement import parse_decision_artifact
from app.backend.app.evidence.decisions import HumanVerdict
from app.backend.app.evidence.run_abx import materialize_completed_run_logical_abx
from app.backend.app.evidence.runs import CompletedEvidenceRun


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersistedBundleView(_Model):
    bundle_id: str
    verdicts: dict[str, str]


class PersistedRunSummary(_Model):
    run_id: str
    protocol_revision_id: str
    kind: str
    status: str
    started_at: str
    completed_at: str
    sealed_at: str
    bundle_id: str
    verdicts: dict[str, str]


class PersistedRunPortfolio(_Model):
    runs: list[PersistedRunSummary]


class PersistedRunView(_Model):
    run_id: str
    protocol_revision_id: str
    kind: str
    status: str
    started_at: str
    completed_at: str
    sealed_at: str
    protocol: dict[str, Any]
    run: dict[str, Any]
    sources: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    estimates: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    report_available: bool
    bundle: PersistedBundleView


class PersistedDecisionRequest(_Model):
    verdict: HumanVerdict
    rationale: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
    ]


class PersistedOverrideRequest(_Model):
    reason: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
    ]


def _bundle_view(run: CompletedEvidenceRun) -> PersistedBundleView:
    logical = materialize_completed_run_logical_abx(run)
    verification = verify_logical_bundle(
        logical.manifest_payload,
        tuple((member.path, member.payload) for member in logical.members[1:]),
    )
    return PersistedBundleView(
        bundle_id=logical.bundle_id,
        verdicts=cast(dict[str, str], verification["verdicts"]),
    )


def summarize_persisted_run(run: CompletedEvidenceRun) -> PersistedRunSummary:
    bundle = _bundle_view(run)
    return PersistedRunSummary(
        run_id=run.run_id,
        protocol_revision_id=run.protocol_revision_id,
        kind=run.kind,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        sealed_at=run.sealed_at,
        bundle_id=bundle.bundle_id,
        verdicts=bundle.verdicts,
    )


def _documents(run: CompletedEvidenceRun, role: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for artifact in run.artifacts:
        if artifact.role != role:
            continue
        document = load_ijson_object(artifact.payload)
        if role == "decision":
            document, _, _ = parse_decision_artifact(
                document,
                schema_id=artifact.schema_id,
            )
        documents.append(document)
    return documents


def _single_document(run: CompletedEvidenceRun, role: str) -> dict[str, Any]:
    documents = _documents(run, role)
    if len(documents) != 1:
        raise ValueError(f"completed run must contain exactly one {role} artifact")
    return documents[0]


def view_persisted_run(run: CompletedEvidenceRun) -> PersistedRunView:
    return PersistedRunView(
        run_id=run.run_id,
        protocol_revision_id=run.protocol_revision_id,
        kind=run.kind,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        sealed_at=run.sealed_at,
        protocol=_single_document(run, "protocol"),
        run=_single_document(run, "run"),
        sources=_documents(run, "source"),
        metrics=_documents(run, "metric"),
        findings=_documents(run, "finding"),
        estimates=_documents(run, "estimate"),
        decisions=_documents(run, "decision"),
        report_available=any(artifact.role == "report" for artifact in run.artifacts),
        bundle=_bundle_view(run),
    )


__all__ = [
    "PersistedDecisionRequest",
    "PersistedOverrideRequest",
    "PersistedRunPortfolio",
    "PersistedRunView",
    "summarize_persisted_run",
    "view_persisted_run",
]
