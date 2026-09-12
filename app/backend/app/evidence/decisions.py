"""Append-only human decisions derived from completed evidence runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.decision_statement import (
    DECISION_STATEMENT_MEDIA_TYPE,
    DECISION_STATEMENT_SCHEMA_ID,
    build_decision_statement_envelope,
    parse_decision_artifact,
)
from app.backend.app.evidence.report import create_report_artifact
from app.backend.app.evidence.run_abx import (
    EvidenceRunNotFoundError,
    materialize_completed_run_logical_abx,
)
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    EvidenceRunStore,
    create_completed_evidence_run,
    create_evidence_run_artifact,
)
from app.backend.app.evidence.sql_run_store import EvidenceRunConflictError

HumanVerdict = Literal["ship", "hold", "stop"]
FindingAction = Literal["remediate", "override"]
# Where the deciding role came from. "credential" is the only source this
# process verifies -- an issued API key that carries the role. "asserted" is a
# role the caller stated about itself (the CLI's --role). "policy_default" is
# no role at all: the frozen policy's first approval role stood in.
RoleSource = Literal["credential", "asserted", "policy_default"]

_RUN_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:run"
_JSON_MEDIA_TYPE = "application/json"


class EvidenceFindingNotFoundError(LookupError):
    """Raised when a persisted run does not contain the requested finding."""


@dataclass(frozen=True)
class AssertedPrincipal:
    """An actor whose role is stated by the caller, not carried by a credential.

    The CLI builds one of these for ``--role``. Nothing verifies the claim, so a
    decision recorded through it says ``role_source: asserted`` -- which is the
    point: a reader can tell it apart from a role an issued key carried.
    """

    actor_ref: str
    role: str | None = None


class ApprovalQuorumUnmetError(Exception):
    """Raised when the frozen policy wants more approvals than one call records.

    ``record_human_decision`` writes exactly one approval, the decider's own.
    A policy asking for two would otherwise get a decision that reads as
    approved on the strength of half the signatures it demands. Refusing is the
    honest answer until multi-party approval exists.
    """


class RoleNotPermittedError(Exception):
    """Raised when the principal's role is outside the frozen approval policy.

    Deliberately not a ``ValueError``: an unauthorized role is neither a
    malformed request nor a conflict with the run's state, and callers map it to
    its own HTTP status (403 ``role_not_permitted``) rather than to 400/409.
    """


def record_human_decision(
    run_id: str,
    principal: object,
    verdict: HumanVerdict,
    rationale: str,
    *,
    out_store: EvidenceRunStore,
) -> CompletedEvidenceRun:
    """Persist one human decision as a new child run of an analysis run."""

    if verdict not in {"ship", "hold", "stop"}:
        raise ValueError("human verdict must be ship, hold, or stop")
    parent = out_store.get(run_id)
    if parent is None:
        raise EvidenceRunNotFoundError(f"completed evidence run not found: {run_id}")
    if parent.run_id != run_id:
        raise EvidenceRunConflictError(
            f"completed run lookup returned {parent.run_id!r} for {run_id!r}"
        )
    if parent.kind != "analysis":
        raise ValueError("human decisions require a completed analysis run")

    parent_run = _single_document(parent, "run")
    estimate_ids = cast(list[str], parent_run["estimate_ids"])
    if not estimate_ids:
        raise ValueError("human decisions require at least one persisted estimate")
    protocol = _single_document(parent, "protocol")
    policy, approval_roles, minimum_approvals = _decision_policy(protocol)
    actor_ref, role, role_source = _principal_identity(principal, approval_roles)
    if minimum_approvals > 1:
        raise ApprovalQuorumUnmetError(
            f"frozen approval policy requires {minimum_approvals} approvals and "
            "this build records one; multi-party approval is not implemented"
        )
    decided_at = _utc_timestamp(datetime.now(UTC))
    parent_bundle_id = materialize_completed_run_logical_abx(parent).bundle_id
    identity = sha256_hex(
        canonical_json_bytes(
            {
                "actor_ref": actor_ref,
                "decided_at": decided_at,
                "parent_bundle_id": parent_bundle_id,
                "parent_run_id": parent.run_id,
                "rationale": rationale,
                "role": role,
                "role_source": role_source,
                "verdict": verdict,
            }
        )
    ).removeprefix("sha256:")
    child_run_id = f"run_decision_{identity[:24]}"
    decision_id = f"decision_{identity[24:48]}"

    artifacts = [
        _rebind_run_artifact(artifact, child_run_id)
        if artifact.role in {"estimate", "finding"}
        else artifact
        for artifact in parent.artifacts
        if artifact.role not in {"run", "decision", "report"}
    ]
    proposed_verdict = _proposed_verdict(parent)
    state = "approved" if verdict == "ship" else "rejected"
    decision: dict[str, Any] = {
        "schema_version": "0.1.0",
        "decision_id": decision_id,
        "run_id": child_run_id,
        "cites_bundle_id": parent_bundle_id,
        "protocol_revision_id": parent.protocol_revision_id,
        "policy": policy,
        "evidence": {
            "estimate_ids": estimate_ids,
            "finding_ids": cast(list[str], parent_run["finding_ids"]),
        },
        "proposed_verdict": proposed_verdict,
        "human_verdict": verdict,
        "rationale": rationale,
        "state": state,
        "decided_at": decided_at,
        "decided_by": {
            "actor_ref": actor_ref,
            "role": role,
            "role_source": role_source,
        },
        "approvals": [
            {
                "actor_ref": actor_ref,
                "role": role,
                "verdict": "approve" if state == "approved" else "reject",
                "approved_at": decided_at,
            }
        ],
        "extensions": {},
    }
    _add_content_digest(decision)
    statement_envelope = build_decision_statement_envelope(
        decision,
        subject_bundle_id=parent_bundle_id,
    )
    artifacts.append(
        create_evidence_run_artifact(
            path="decision/statement.dsse.json",
            role="decision",
            media_type=DECISION_STATEMENT_MEDIA_TYPE,
            schema_id=DECISION_STATEMENT_SCHEMA_ID,
            payload=canonical_json_bytes(statement_envelope),
        )
    )

    child_run = dict(parent_run)
    child_run.update(
        {
            "run_id": child_run_id,
            "parent_run_id": parent.run_id,
            "started_at": decided_at,
            "completed_at": decided_at,
            "decision_id": decision_id,
        }
    )
    artifacts.append(
        create_evidence_run_artifact(
            path="run/run.json",
            role="run",
            media_type=_JSON_MEDIA_TYPE,
            schema_id=_RUN_SCHEMA_ID,
            payload=canonical_json_bytes(child_run),
        )
    )
    completed_without_report = create_completed_evidence_run(
        origin_job_id=f"job_decision_{identity[48:]}",
        origin_job_revision=1,
        sealed_at=decided_at,
        artifacts=tuple(artifacts),
    )
    completed = create_completed_evidence_run(
        origin_job_id=completed_without_report.origin_job_id,
        origin_job_revision=completed_without_report.origin_job_revision,
        sealed_at=completed_without_report.sealed_at,
        artifacts=(
            *completed_without_report.artifacts,
            create_report_artifact(completed_without_report),
        ),
    )
    if not out_store.create(completed):
        raise EvidenceRunConflictError(
            f"decision child run already exists: {completed.run_id}"
        )
    return completed


def record_finding_state(
    run_id: str,
    finding_id: str,
    principal: object,
    action: FindingAction,
    *,
    reason: str | None = None,
    out_store: EvidenceRunStore,
) -> CompletedEvidenceRun:
    """Persist one resolved or overridden finding as a content-bound child run."""

    if action not in {"remediate", "override"}:
        raise ValueError("finding action must be remediate or override")
    parent = out_store.get(run_id)
    if parent is None:
        raise EvidenceRunNotFoundError(f"completed evidence run not found: {run_id}")
    if parent.run_id != run_id:
        raise EvidenceRunConflictError(
            f"completed run lookup returned {parent.run_id!r} for {run_id!r}"
        )
    target = next(
        (
            load_ijson_object(artifact.payload)
            for artifact in parent.artifacts
            if artifact.role == "finding"
            and load_ijson_object(artifact.payload).get("finding_id") == finding_id
        ),
        None,
    )
    if target is None:
        # Ahead of the state guards below: a finding the run never carried is
        # absent whatever that run has since decided, so the caller gets 404
        # instead of a 409 that reads as "it exists, but not right now".
        raise EvidenceFindingNotFoundError(
            f"completed run does not contain finding: {finding_id}"
        )
    if any(artifact.role == "decision" for artifact in parent.artifacts):
        raise ValueError("finding actions require a pre-decision run")

    parent_run = _single_document(parent, "run")
    protocol = _single_document(parent, "protocol")
    _, approval_roles, _ = _decision_policy(protocol)
    actor_ref, role, _ = _principal_identity(principal, approval_roles)
    if target.get("state") != "open":
        raise ValueError("finding actions require an open finding")
    reason_text = reason.strip() if reason is not None else None
    if action == "override" and not reason_text:
        raise ValueError("finding override requires a reason")

    recorded_at = _utc_timestamp(datetime.now(UTC))
    parent_bundle_id = materialize_completed_run_logical_abx(parent).bundle_id
    identity = sha256_hex(
        canonical_json_bytes(
            {
                "action": action,
                "actor_ref": actor_ref,
                "finding_id": finding_id,
                "parent_bundle_id": parent_bundle_id,
                "parent_run_id": parent.run_id,
                "reason": reason_text,
                "recorded_at": recorded_at,
                "role": role,
            }
        )
    ).removeprefix("sha256:")
    child_run_id = f"run_finding_{identity[:24]}"
    transition: dict[str, Any] = {
        "action": action,
        "actor_ref": actor_ref,
        "cites_bundle_id": parent_bundle_id,
        "finding_id": finding_id,
        "recorded_at": recorded_at,
        "role": role,
    }

    artifacts: list[EvidenceRunArtifact] = []
    for artifact in parent.artifacts:
        if artifact.role in {"run", "report"}:
            continue
        if artifact.role not in {"estimate", "finding"}:
            artifacts.append(artifact)
            continue
        document = load_ijson_object(artifact.payload)
        document["run_id"] = child_run_id
        if artifact.role == "finding" and document["finding_id"] == finding_id:
            document["state"] = "resolved" if action == "remediate" else "overridden"
            document["produced_at"] = recorded_at
            extensions = dict(cast(dict[str, Any], document["extensions"]))
            extensions["trialmark.finding-state"] = transition
            document["extensions"] = extensions
            if action == "override":
                document["override"] = {
                    "actor_ref": actor_ref,
                    "reason": reason_text,
                    "policy_version": "override_v1",
                    "recorded_at": recorded_at,
                }
        _add_content_digest(document)
        artifacts.append(
            create_evidence_run_artifact(
                path=artifact.path,
                role=artifact.role,
                media_type=artifact.media_type,
                schema_id=artifact.schema_id,
                payload=canonical_json_bytes(document),
            )
        )

    child_run = dict(parent_run)
    run_extensions = dict(cast(dict[str, Any], child_run["extensions"]))
    run_extensions["trialmark.finding-state"] = transition
    child_run.update(
        {
            "run_id": child_run_id,
            "parent_run_id": parent.run_id,
            "started_at": recorded_at,
            "completed_at": recorded_at,
            "extensions": run_extensions,
        }
    )
    artifacts.append(
        create_evidence_run_artifact(
            path="run/run.json",
            role="run",
            media_type=_JSON_MEDIA_TYPE,
            schema_id=_RUN_SCHEMA_ID,
            payload=canonical_json_bytes(child_run),
        )
    )
    completed_without_report = create_completed_evidence_run(
        origin_job_id=f"job_finding_{identity[48:]}",
        origin_job_revision=1,
        sealed_at=recorded_at,
        artifacts=tuple(artifacts),
    )
    completed = create_completed_evidence_run(
        origin_job_id=completed_without_report.origin_job_id,
        origin_job_revision=completed_without_report.origin_job_revision,
        sealed_at=completed_without_report.sealed_at,
        artifacts=(
            *completed_without_report.artifacts,
            create_report_artifact(completed_without_report),
        ),
    )
    if not out_store.create(completed):
        raise EvidenceRunConflictError(
            f"finding-state child run already exists: {completed.run_id}"
        )
    return completed


def _single_document(run: CompletedEvidenceRun, role: str) -> dict[str, Any]:
    artifacts = [artifact for artifact in run.artifacts if artifact.role == role]
    if len(artifacts) != 1:
        raise ValueError(f"completed run must contain exactly one {role} artifact")
    return load_ijson_object(artifacts[0].payload)


def _decision_policy(
    protocol: dict[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...], int]:
    declaration = cast(dict[str, Any], protocol["decision"])
    approval = cast(dict[str, Any], declaration["approval_policy"])
    roles = tuple(cast(list[str], approval["roles"]))
    minimum_approvals = int(cast(int, approval["minimum_approvals"]))
    harm_rules = cast(list[dict[str, Any]], declaration["harm_rules"])
    return (
        {
            "policy_id": "frozen_protocol_policy",
            "version": "1",
            "minimum_worthwhile_effect": float(
                declaration["minimum_worthwhile_effect"]
            ),
            "harm_rule_codes": [
                cast(str, rule["code"]) for rule in harm_rules if "code" in rule
            ],
            "approval_roles": list(roles),
        },
        roles,
        minimum_approvals,
    )


def _principal_identity(
    principal: object,
    allowed_roles: tuple[str, ...],
) -> tuple[str, str, RoleSource]:
    actor_ref: object
    role: object
    role_source: RoleSource
    if isinstance(principal, str):
        actor_ref = principal
        role = allowed_roles[0]
        role_source = "policy_default"
    else:
        actor_ref = getattr(principal, "actor_ref", None)
        role = getattr(principal, "role", None)
        # A principal that declares no role inherits the frozen policy's first
        # approval role: authentication grants the write scope, and nothing about
        # this caller says which role it acts in.
        if role is None:
            role = allowed_roles[0]
            role_source = "policy_default"
        else:
            declared = getattr(principal, "role_source", None)
            # Only a credential the process itself resolved may claim to be one.
            # Anything else a caller says about its own role is an assertion.
            role_source = "credential" if declared == "credential" else "asserted"
    if not isinstance(actor_ref, str) or not actor_ref:
        raise ValueError("principal must provide a non-empty actor_ref")
    if not isinstance(role, str) or role not in allowed_roles:
        raise RoleNotPermittedError(
            f"principal role {role!r} is not listed in the frozen approval policy"
        )
    return actor_ref, role, role_source


def _proposed_verdict(parent: CompletedEvidenceRun) -> str:
    decisions = [artifact for artifact in parent.artifacts if artifact.role == "decision"]
    if not decisions:
        return "inconclusive"
    document = load_ijson_object(decisions[0].payload)
    decision, _, _ = parse_decision_artifact(
        document,
        schema_id=decisions[0].schema_id,
    )
    return cast(str, decision["proposed_verdict"])


def _rebind_run_artifact(
    artifact: EvidenceRunArtifact,
    run_id: str,
) -> EvidenceRunArtifact:
    document = load_ijson_object(artifact.payload)
    document["run_id"] = run_id
    _add_content_digest(document)
    return create_evidence_run_artifact(
        path=artifact.path,
        role=artifact.role,
        media_type=artifact.media_type,
        schema_id=artifact.schema_id,
        payload=canonical_json_bytes(document),
    )


def _add_content_digest(document: dict[str, Any]) -> None:
    document.pop("content_digest", None)
    document["content_digest"] = sha256_hex(canonical_json_bytes(document))


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ApprovalQuorumUnmetError",
    "AssertedPrincipal",
    "EvidenceFindingNotFoundError",
    "FindingAction",
    "HumanVerdict",
    "RoleNotPermittedError",
    "RoleSource",
    "record_finding_state",
    "record_human_decision",
]
