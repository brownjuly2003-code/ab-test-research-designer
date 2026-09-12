from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.backend.app.evidence._common import (
    SHA256_PATTERN as _SHA256_PATTERN,
)
from app.backend.app.evidence._common import (
    sha256_hex,
)
from app.backend.app.evidence.abx import (
    ABX_VERSION,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    AbxError,
    canonical_json_bytes,
    load_abx_document,
    manifest_bundle_id,
    pack_bundle,
    verify_logical_bundle,
)
from app.backend.app.evidence.decision_statement import parse_decision_artifact
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    EvidenceRunStore,
)

_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_UTC_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
    r"[0-9]{2}(?:\.[0-9]+)?Z$"
)


class EvidenceRunBundleError(ValueError):
    """Raised when a completed run cannot form a valid logical ABX bundle."""


class EvidenceRunNotFoundError(LookupError):
    """Raised when a requested completed run is absent from its store."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )


class LogicalAbxMember(_FrozenModel):
    """Immutable exact byte view of one ordered logical ABX member."""

    path: str = Field(min_length=1, max_length=240)
    payload: bytes = Field(max_length=MAX_MEMBER_BYTES)


class LogicalAbxBundle(_FrozenModel):
    """Deterministic logical ABX value before transport serialization."""

    bundle_id: str = Field(pattern=_SHA256_PATTERN)
    manifest_digest: str = Field(pattern=_SHA256_PATTERN)
    run_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    protocol_revision_id: str = Field(pattern=_SHA256_PATTERN)
    created_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    artifact_count: int = Field(strict=True, ge=1, le=MAX_MEMBERS - 1)
    manifest_payload: bytes = Field(max_length=MAX_MEMBER_BYTES)
    members: tuple[LogicalAbxMember, ...] = Field(
        min_length=2,
        max_length=MAX_MEMBERS,
    )

    @model_validator(mode="after")
    def validate_logical_bundle(self) -> Self:
        if len(self.members) != self.artifact_count + 1:
            raise ValueError("artifact count does not match logical members")
        manifest_member = self.members[0]
        if manifest_member.path != "manifest.json":
            raise ValueError("manifest.json must be the first logical member")
        if manifest_member.payload != self.manifest_payload:
            raise ValueError("manifest member does not match manifest payload")
        if self.manifest_digest != sha256_hex(self.manifest_payload):
            raise ValueError("manifest digest does not match manifest payload")

        manifest = load_abx_document(self.manifest_payload, label="manifest.json")
        expected = {
            "bundle_id": self.bundle_id,
            "run_id": self.run_id,
            "protocol_revision_id": self.protocol_revision_id,
            "created_at": self.created_at,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(f"{key} does not match the logical manifest")

        verification = verify_logical_bundle(
            self.manifest_payload,
            tuple((member.path, member.payload) for member in self.members[1:]),
        )
        if not verification["valid"]:
            raise ValueError(_verification_failure(verification))
        return self


def _manifest_entry(artifact: EvidenceRunArtifact) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": artifact.path,
        "role": artifact.role,
        "media_type": artifact.media_type,
        "size": artifact.size,
        "digest": artifact.digest,
    }
    if artifact.schema_id is not None:
        entry["schema_id"] = artifact.schema_id
    return entry


def _verification_failure(verification: dict[str, Any]) -> str:
    errors = cast(list[dict[str, Any]], verification["errors"])
    codes = sorted({cast(str, error["code"]) for error in errors})
    details = "; ".join(
        f"{error['code']}: {error['message']}" for error in errors
    )
    return f"logical ABX verification failed [{', '.join(codes)}]: {details}"


def _superseded_bundle_id(run: CompletedEvidenceRun) -> str | None:
    run_artifact = next(artifact for artifact in run.artifacts if artifact.role == "run")
    run_document = load_abx_document(run_artifact.payload, label=run_artifact.path)
    if "parent_run_id" not in run_document:
        return None
    decision_artifact = next(
        (artifact for artifact in run.artifacts if artifact.role == "decision"),
        None,
    )
    if decision_artifact is not None:
        decision_document = load_abx_document(
            decision_artifact.payload,
            label=decision_artifact.path,
        )
        decision, _, _ = parse_decision_artifact(
            decision_document,
            schema_id=decision_artifact.schema_id,
        )
        return cast(str, decision["cites_bundle_id"])
    extensions = cast(dict[str, Any], run_document["extensions"])
    transition = cast(dict[str, Any], extensions["trialmark.finding-state"])
    return cast(str, transition["cites_bundle_id"])


def materialize_completed_run_logical_abx(
    run: CompletedEvidenceRun,
) -> LogicalAbxBundle:
    """Materialize a completed run as deterministic verified logical ABX bytes."""
    try:
        validated = CompletedEvidenceRun.model_validate(
            run.model_dump(mode="python", round_trip=True)
        )
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        raise EvidenceRunBundleError(
            f"completed run revalidation failed: {exc}"
        ) from exc

    manifest: dict[str, Any] = {
        "abx_version": ABX_VERSION,
        "created_at": validated.sealed_at,
        "protocol_revision_id": validated.protocol_revision_id,
        "run_id": validated.run_id,
        "hash_algorithm": "sha256",
        "required_capabilities": list(validated.required_capabilities),
        "entries": [_manifest_entry(artifact) for artifact in validated.artifacts],
    }
    supersedes = _superseded_bundle_id(validated)
    if supersedes is not None:
        manifest["supersedes"] = supersedes
    try:
        manifest["bundle_id"] = manifest_bundle_id(manifest)
        manifest_payload = canonical_json_bytes(manifest)
    except AbxError as exc:
        raise EvidenceRunBundleError(
            f"logical ABX manifest materialization failed: {exc}"
        ) from exc

    exact_members = tuple(
        (artifact.path, artifact.payload) for artifact in validated.artifacts
    )
    verification = verify_logical_bundle(manifest_payload, exact_members)
    if not verification["valid"]:
        raise EvidenceRunBundleError(_verification_failure(verification))

    members = (
        LogicalAbxMember(path="manifest.json", payload=manifest_payload),
        *(
            LogicalAbxMember(path=artifact.path, payload=artifact.payload)
            for artifact in validated.artifacts
        ),
    )
    return LogicalAbxBundle(
        bundle_id=cast(str, manifest["bundle_id"]),
        manifest_digest=sha256_hex(manifest_payload),
        run_id=validated.run_id,
        protocol_revision_id=validated.protocol_revision_id,
        created_at=validated.sealed_at,
        artifact_count=len(validated.artifacts),
        manifest_payload=manifest_payload,
        members=members,
    )


def publish_completed_run_abx(
    store: EvidenceRunStore,
    *,
    run_id: str,
    destination: str | Path,
) -> dict[str, Any]:
    """Resolve one completed run and atomically publish its verified ABX archive."""
    output = Path(destination)
    if os.path.lexists(output):
        raise AbxError(f"destination already exists: {output}")

    run = store.get(run_id)
    if run is None:
        raise EvidenceRunNotFoundError(f"completed evidence run not found: {run_id}")
    if run.run_id != run_id:
        raise EvidenceRunBundleError(
            f"completed run lookup returned {run.run_id!r} for {run_id!r}"
        )

    bundle = materialize_completed_run_logical_abx(run)
    with tempfile.TemporaryDirectory(prefix="trialmark-run-abx-") as temporary_name:
        logical_root = Path(temporary_name) / "logical"
        logical_root.mkdir()
        for member in bundle.members:
            target = logical_root / member.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(member.payload)
        return pack_bundle(logical_root, output)


__all__ = [
    "EvidenceRunBundleError",
    "EvidenceRunNotFoundError",
    "LogicalAbxBundle",
    "LogicalAbxMember",
    "materialize_completed_run_logical_abx",
    "publish_completed_run_abx",
]
