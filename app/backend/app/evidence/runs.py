from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Final, Literal, Protocol, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.backend.app.evidence._common import (
    SHA256_PATTERN as _SHA256_PATTERN,
)
from app.backend.app.evidence._common import (
    sha256_hex,
)
from app.backend.app.evidence.abx import (
    ABX_VERSION,
    KNOWN_CAPABILITIES,
    MANIFEST_SCHEMA_ID,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_BYTES,
    STRUCTURED_ROLES,
    AbxError,
    canonical_json_bytes,
    load_abx_document,
    validate_abx_document,
)
from app.backend.app.evidence.decision_statement import (
    DECISION_RECORD_SCHEMA_ID,
    DECISION_STATEMENT_SCHEMA_ID,
    DecisionStatementError,
    parse_decision_artifact,
)

RUN_SCHEMA_ID: Final = "urn:evidenceos:abx:schema:0.1:run"
_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_CAPABILITY_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
_UTC_TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
    r"[0-9]{2}(?:\.[0-9]+)?Z$"
)

OpaqueId = Annotated[str, StringConstraints(pattern=_OPAQUE_ID_PATTERN)]
Sha256Digest = Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
Capability = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=_CAPABILITY_PATTERN),
]
CanonicalUtcTimestamp = Annotated[
    str,
    StringConstraints(pattern=_UTC_TIMESTAMP_PATTERN),
]
EvidenceRunKind = Literal["preflight", "analysis"]
EvidenceArtifactRole = Literal[
    "protocol",
    "amendments",
    "run",
    "source",
    "metric",
    "method",
    "query",
    "finding",
    "estimate",
    "decision",
    "report",
    "schema",
]


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


def _entry(artifact: EvidenceRunArtifact) -> dict[str, Any]:
    value: dict[str, Any] = {
        "path": artifact.path,
        "role": artifact.role,
        "media_type": artifact.media_type,
        "size": artifact.size,
        "digest": artifact.digest,
    }
    if artifact.schema_id is not None:
        value["schema_id"] = artifact.schema_id
    return value


def _validate_manifest_entry(entry: dict[str, Any]) -> None:
    manifest = {
        "abx_version": ABX_VERSION,
        "bundle_id": "sha256:" + "0" * 64,
        "created_at": "2000-01-01T00:00:00Z",
        "protocol_revision_id": "sha256:" + "0" * 64,
        "run_id": "run_validation",
        "hash_algorithm": "sha256",
        "required_capabilities": ["lineage-v1", "protocol-core"],
        "entries": [entry],
    }
    validate_abx_document(manifest, MANIFEST_SCHEMA_ID)


class EvidenceRunArtifact(_FrozenModel):
    """Exact immutable bytes and manifest metadata for one logical ABX member."""

    path: str = Field(min_length=1, max_length=240)
    role: EvidenceArtifactRole
    media_type: str = Field(min_length=1, max_length=128)
    schema_id: str | None = Field(default=None, min_length=1, max_length=256)
    size: int = Field(strict=True, ge=0, le=MAX_MEMBER_BYTES)
    digest: Sha256Digest
    payload: bytes = Field(max_length=MAX_MEMBER_BYTES)

    @model_validator(mode="after")
    def validate_exact_artifact(self) -> Self:
        if self.size != len(self.payload):
            raise ValueError("artifact size does not match its exact payload")
        if self.digest != sha256_hex(self.payload):
            raise ValueError("artifact digest does not match its exact payload")
        try:
            _validate_manifest_entry(_entry(self))
        except AbxError as error:
            raise ValueError("artifact manifest metadata is invalid") from error

        if self.role in STRUCTURED_ROLES:
            if self.schema_id is None:
                raise ValueError("structured artifacts require a schema ID")
            try:
                document = load_abx_document(self.payload, label=self.path)
                validate_abx_document(document, self.schema_id)
                if (
                    self.role == "decision"
                    and self.schema_id == DECISION_STATEMENT_SCHEMA_ID
                ):
                    decision, _, _ = parse_decision_artifact(
                        document,
                        schema_id=self.schema_id,
                    )
                    validate_abx_document(decision, DECISION_RECORD_SCHEMA_ID)
            except (AbxError, DecisionStatementError) as error:
                raise ValueError("artifact ABX document is invalid") from error
        elif self.role == "schema":
            try:
                load_abx_document(self.payload, label=self.path)
            except AbxError as error:
                raise ValueError("schema artifact is not strict I-JSON") from error
        return self


def create_evidence_run_artifact(
    *,
    path: str,
    role: EvidenceArtifactRole,
    media_type: str,
    payload: bytes,
    schema_id: str | None = None,
) -> EvidenceRunArtifact:
    """Bind exact bytes to their validated logical ABX manifest entry."""
    return EvidenceRunArtifact(
        path=path,
        role=role,
        media_type=media_type,
        schema_id=schema_id,
        size=len(payload),
        digest=sha256_hex(payload),
        payload=payload,
    )


def _artifact_documents(
    artifacts: tuple[EvidenceRunArtifact, ...],
) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if artifact.role in STRUCTURED_ROLES or artifact.role == "schema":
            document = load_abx_document(
                artifact.payload,
                label=artifact.path,
            )
            if artifact.role == "decision":
                document, _, _ = parse_decision_artifact(
                    document,
                    schema_id=artifact.schema_id,
                )
            documents[artifact.path] = document
    return documents


def _role_id_map(
    artifacts: tuple[EvidenceRunArtifact, ...],
    documents: dict[str, dict[str, Any]],
    *,
    role: EvidenceArtifactRole,
    id_key: str,
) -> dict[str, EvidenceRunArtifact]:
    output: dict[str, EvidenceRunArtifact] = {}
    for artifact in artifacts:
        if artifact.role != role:
            continue
        identifier = documents[artifact.path].get(id_key)
        if not isinstance(identifier, str):
            raise ValueError(f"{role} artifact has no {id_key}")
        if identifier in output:
            raise ValueError(f"duplicate {role} artifact ID: {identifier}")
        output[identifier] = artifact
    return output


def _validate_reference_closure(
    artifacts: tuple[EvidenceRunArtifact, ...],
    documents: dict[str, dict[str, Any]],
    run: dict[str, Any],
    *,
    protocol_revision_id: str,
) -> None:
    protocol_artifacts = [
        artifact for artifact in artifacts if artifact.role == "protocol"
    ]
    if len(protocol_artifacts) != 1:
        raise ValueError("completed runs require exactly one protocol artifact")
    protocol = documents[protocol_artifacts[0].path]
    method_artifacts = [
        artifact for artifact in artifacts if artifact.role == "method"
    ]
    if len(method_artifacts) > 1:
        raise ValueError("completed runs allow at most one method profile artifact")
    sources = _role_id_map(
        artifacts,
        documents,
        role="source",
        id_key="source_snapshot_id",
    )
    metrics = _role_id_map(
        artifacts,
        documents,
        role="metric",
        id_key="metric_id",
    )
    findings = _role_id_map(
        artifacts,
        documents,
        role="finding",
        id_key="finding_id",
    )
    estimates = _role_id_map(
        artifacts,
        documents,
        role="estimate",
        id_key="estimate_id",
    )
    decisions = _role_id_map(
        artifacts,
        documents,
        role="decision",
        id_key="decision_id",
    )
    declared_sets = (
        ("source_snapshot_ids", set(sources)),
        ("metric_ids", set(metrics)),
        ("finding_ids", set(findings)),
        ("estimate_ids", set(estimates)),
    )
    for key, bundled in declared_sets:
        if set(cast(list[str], run[key])) != bundled:
            raise ValueError(f"run {key} do not match the persisted artifacts")

    decision_id = cast(str | None, run.get("decision_id"))
    expected_decisions = set() if decision_id is None else {decision_id}
    if set(decisions) != expected_decisions:
        raise ValueError("run decision_id does not match the persisted artifacts")
    parent_run_id = cast(str | None, run.get("parent_run_id"))
    decision_documents = [documents[artifact.path] for artifact in decisions.values()]
    for decision_artifact in decisions.values():
        raw_document = load_abx_document(
            decision_artifact.payload,
            label=decision_artifact.path,
        )
        _, statement, subject_bundle_id = parse_decision_artifact(
            raw_document,
            schema_id=decision_artifact.schema_id,
        )
        if (
            statement is not None
            and subject_bundle_id
            != documents[decision_artifact.path].get("cites_bundle_id")
        ):
            raise ValueError(
                "decision statement subject does not match its parent bundle citation"
            )
    cited_bundle_ids = {
        cast(str, document["cites_bundle_id"])
        for document in decision_documents
        if "cites_bundle_id" in document
    }
    run_extensions = cast(dict[str, Any], run["extensions"])
    finding_transition = run_extensions.get("trialmark.finding-state")
    if parent_run_id is not None:
        if parent_run_id == run.get("run_id"):
            raise ValueError("child run cannot name itself as its parent")
        if decision_documents:
            if finding_transition is not None:
                raise ValueError("decision child run cannot also change finding state")
            if len(decision_documents) != 1 or len(cited_bundle_ids) != 1:
                raise ValueError(
                    "decision child run requires one decision citing its parent bundle"
                )
        else:
            if not isinstance(finding_transition, dict):
                raise ValueError(
                    "finding-state child run requires a parent bundle transition"
                )
            required_transition_keys = {
                "action",
                "actor_ref",
                "cites_bundle_id",
                "finding_id",
                "recorded_at",
                "role",
            }
            if set(finding_transition) != required_transition_keys:
                raise ValueError("finding-state transition fields are invalid")
            finding_id = finding_transition["finding_id"]
            target_artifact = findings.get(finding_id)
            if target_artifact is None:
                raise ValueError("finding-state transition references an unknown finding")
            target = documents[target_artifact.path]
            target_extensions = cast(dict[str, Any], target["extensions"])
            if target_extensions.get("trialmark.finding-state") != finding_transition:
                raise ValueError("finding-state transition is not bound to its finding")
            if target.get("produced_at") != finding_transition["recorded_at"]:
                raise ValueError("finding-state transition time does not match its finding")
            if finding_transition["recorded_at"] != run["completed_at"]:
                raise ValueError("finding-state transition time does not match its run")
            cited_bundle_id = finding_transition["cites_bundle_id"]
            if not isinstance(cited_bundle_id, str) or re.fullmatch(
                _SHA256_PATTERN, cited_bundle_id
            ) is None:
                raise ValueError("finding-state transition has an invalid parent bundle")
            if not all(
                isinstance(finding_transition[key], str)
                and bool(finding_transition[key])
                for key in ("actor_ref", "role")
            ):
                raise ValueError("finding-state transition principal is invalid")
            action = finding_transition["action"]
            if action == "remediate":
                if target.get("state") != "resolved" or "override" in target:
                    raise ValueError("remediation must resolve the target finding")
            elif action == "override":
                override = target.get("override")
                if (
                    target.get("state") != "overridden"
                    or not isinstance(override, dict)
                    or override.get("actor_ref") != finding_transition["actor_ref"]
                    or override.get("recorded_at") != finding_transition["recorded_at"]
                ):
                    raise ValueError("override transition does not match its finding")
            else:
                raise ValueError("finding-state transition action is invalid")
    elif cited_bundle_ids or finding_transition is not None:
        raise ValueError("child-run state cites a parent without a parent run")

    query_artifacts = {
        artifact.path: artifact for artifact in artifacts if artifact.role == "query"
    }
    declared_query_paths: set[str] = set()
    query_ids: set[str] = set()
    for query in cast(list[dict[str, Any]], run["queries"]):
        query_id = cast(str, query["query_id"])
        if query_id in query_ids:
            raise ValueError(f"duplicate run query ID: {query_id}")
        query_ids.add(query_id)
        statement_path = cast(str, query["statement_path"])
        declared_query_paths.add(statement_path)
        artifact = query_artifacts.get(statement_path)
        if artifact is None:
            raise ValueError(f"run query artifact is missing: {statement_path}")
        if query["statement_digest"] != artifact.digest:
            raise ValueError("run query digest does not match its exact payload")
        if query["source_snapshot_id"] not in sources:
            raise ValueError("run query references an unknown source snapshot")
    if set(query_artifacts) != declared_query_paths:
        raise ValueError("persisted query artifacts do not match the run queries")

    run_id = cast(str, run["run_id"])
    run_runner = cast(dict[str, Any], run["runner"])
    if method_artifacts:
        method_profile = documents[method_artifacts[0].path]
        analysis = cast(dict[str, Any], protocol["analysis"])
        protocol_method = cast(dict[str, Any], analysis["method"])
        if (
            method_profile["method_id"] != protocol_method["method_id"]
            or method_profile["method_version"] != protocol_method["method_version"]
            or method_profile["implementation_digest"]
            != run_runner["build_digest"]
            or method_profile["error_control"]["nominal_alpha"]
            != float(cast(str, analysis["alpha"]))
        ):
            raise ValueError(
                "method profile does not match the frozen protocol and run build"
            )
    artifact_digests = {artifact.digest for artifact in artifacts}
    for artifact in artifacts:
        document = documents.get(artifact.path)
        if document is None:
            continue
        if artifact.role == "estimate":
            if document["run_id"] != run_id:
                raise ValueError("estimate references a different run")
            lineage = cast(dict[str, Any], document["lineage"])
            if lineage["protocol_revision_id"] != protocol_revision_id:
                raise ValueError("estimate references a different protocol revision")
            metric_lineage = cast(dict[str, Any], lineage["metric"])
            metric = metrics.get(cast(str, metric_lineage["metric_id"]))
            if metric is None or metric_lineage["metric_digest"] != metric.digest:
                raise ValueError("estimate metric lineage is not persisted")
            if not set(cast(list[str], lineage["query_ids"])) <= query_ids:
                raise ValueError("estimate query lineage is not persisted")
            if not set(cast(list[str], lineage["source_snapshot_ids"])) <= set(sources):
                raise ValueError("estimate source lineage is not persisted")
            estimate_runner = cast(dict[str, Any], lineage["runner"])
            if any(run_runner.get(key) != value for key, value in estimate_runner.items()):
                raise ValueError("estimate runner lineage does not match the run")
        elif artifact.role == "finding":
            if document["run_id"] != run_id:
                raise ValueError("finding references a different run")
            for evidence in cast(list[dict[str, Any]], document["evidence"]):
                if evidence["artifact_digest"] not in artifact_digests:
                    raise ValueError("finding evidence artifact is not persisted")
        elif artifact.role == "decision":
            if (
                document["run_id"] != run_id
                or document["protocol_revision_id"] != protocol_revision_id
            ):
                raise ValueError("decision references a different run or protocol")
            evidence = cast(dict[str, Any], document["evidence"])
            if not set(cast(list[str], evidence["estimate_ids"])) <= set(estimates):
                raise ValueError("decision estimate evidence is not persisted")
            if not set(cast(list[str], evidence["finding_ids"])) <= set(findings):
                raise ValueError("decision finding evidence is not persisted")


def _record_core(
    *,
    run_id: str,
    origin_job_id: str,
    origin_job_revision: int,
    protocol_revision_id: str,
    kind: str,
    status: str,
    started_at: str,
    completed_at: str,
    sealed_at: str,
    runner_digest: str,
    required_capabilities: tuple[str, ...],
    artifacts: tuple[EvidenceRunArtifact, ...],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "origin_job_id": origin_job_id,
        "origin_job_revision": origin_job_revision,
        "protocol_revision_id": protocol_revision_id,
        "kind": kind,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "sealed_at": sealed_at,
        "runner_digest": runner_digest,
        "required_capabilities": list(required_capabilities),
        "artifacts": [_entry(artifact) for artifact in artifacts],
    }


def _record_digest(**values: Any) -> str:
    return sha256_hex(canonical_json_bytes(_record_core(**values)))


class CompletedEvidenceRun(_FrozenModel):
    """Append-only succeeded run plus its exact closed logical artifact set."""

    run_id: OpaqueId
    origin_job_id: OpaqueId
    origin_job_revision: int = Field(strict=True, ge=1)
    protocol_revision_id: Sha256Digest
    kind: EvidenceRunKind
    status: Literal["succeeded"] = "succeeded"
    started_at: CanonicalUtcTimestamp
    completed_at: CanonicalUtcTimestamp
    sealed_at: CanonicalUtcTimestamp
    runner_digest: Sha256Digest
    required_capabilities: tuple[Capability, ...] = Field(min_length=2)
    artifacts: tuple[EvidenceRunArtifact, ...] = Field(min_length=2, max_length=MAX_MEMBERS)
    record_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_completed_run(self) -> Self:
        started_at = datetime.fromisoformat(self.started_at[:-1] + "+00:00")
        completed_at = datetime.fromisoformat(self.completed_at[:-1] + "+00:00")
        sealed_at = datetime.fromisoformat(self.sealed_at[:-1] + "+00:00")
        if completed_at < started_at:
            raise ValueError("completed_at must not precede started_at")
        if sealed_at < completed_at:
            raise ValueError("sealed_at must not precede completed_at")
        if tuple(sorted(self.required_capabilities)) != self.required_capabilities:
            raise ValueError("required capabilities must use canonical sorted order")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("required capabilities must be unique")
        if not {"lineage-v1", "protocol-core"} <= set(self.required_capabilities):
            raise ValueError("completed runs require lineage-v1 and protocol-core")
        if not set(self.required_capabilities) <= KNOWN_CAPABILITIES:
            raise ValueError("completed run declares an unsupported capability")

        paths = tuple(artifact.path for artifact in self.artifacts)
        collision_keys = tuple(path.casefold() for path in paths)
        if len(set(collision_keys)) != len(collision_keys):
            raise ValueError("duplicate artifact path")
        if paths != tuple(sorted(paths)):
            raise ValueError("artifacts must use canonical path order")
        if sum(artifact.size for artifact in self.artifacts) > MAX_TOTAL_BYTES:
            raise ValueError("artifact set exceeds the ABX total-size limit")

        run_artifacts = [artifact for artifact in self.artifacts if artifact.role == "run"]
        protocol_artifacts = [
            artifact for artifact in self.artifacts if artifact.role == "protocol"
        ]
        amendment_artifacts = [
            artifact for artifact in self.artifacts if artifact.role == "amendments"
        ]
        if len(run_artifacts) != 1 or len(protocol_artifacts) != 1:
            raise ValueError("completed runs require exactly one run and protocol artifact")
        if len(amendment_artifacts) > 1:
            raise ValueError("completed runs allow at most one amendments artifact")

        documents = _artifact_documents(self.artifacts)
        run = documents[run_artifacts[0].path]
        expected_header = {
            "run_id": self.run_id,
            "protocol_revision_id": self.protocol_revision_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "required_capabilities": list(self.required_capabilities),
        }
        for key, expected in expected_header.items():
            if run[key] != expected:
                raise ValueError(f"{key} does not match the embedded run document")
        if run["status"] != "succeeded":
            raise ValueError("embedded run document must be succeeded")
        if self.runner_digest != sha256_hex(
            canonical_json_bytes(cast(dict[str, Any], run["runner"]))
        ):
            raise ValueError("runner_digest does not match the embedded run document")

        _validate_reference_closure(
            self.artifacts,
            documents,
            run,
            protocol_revision_id=self.protocol_revision_id,
        )
        expected_digest = _record_digest(
            run_id=self.run_id,
            origin_job_id=self.origin_job_id,
            origin_job_revision=self.origin_job_revision,
            protocol_revision_id=self.protocol_revision_id,
            kind=self.kind,
            status=self.status,
            started_at=self.started_at,
            completed_at=self.completed_at,
            sealed_at=self.sealed_at,
            runner_digest=self.runner_digest,
            required_capabilities=self.required_capabilities,
            artifacts=self.artifacts,
        )
        if self.record_digest != expected_digest:
            raise ValueError("completed run record digest mismatch")
        return self


def create_completed_evidence_run(
    *,
    origin_job_id: str,
    origin_job_revision: int,
    sealed_at: str,
    artifacts: tuple[EvidenceRunArtifact, ...],
) -> CompletedEvidenceRun:
    """Derive a canonical completed-run record from exact logical artifacts."""
    ordered = tuple(sorted(artifacts, key=lambda artifact: artifact.path))
    run_artifacts = [artifact for artifact in ordered if artifact.role == "run"]
    if len(run_artifacts) != 1:
        raise ValueError("completed runs require exactly one run artifact")
    run = load_abx_document(run_artifacts[0].payload, label=run_artifacts[0].path)
    run_id = cast(str, run["run_id"])
    protocol_revision_id = cast(str, run["protocol_revision_id"])
    kind = cast(EvidenceRunKind, run["kind"])
    status = cast(Literal["succeeded"], run["status"])
    started_at = cast(str, run["started_at"])
    completed_at = cast(str, run["completed_at"])
    runner_digest = sha256_hex(
        canonical_json_bytes(cast(dict[str, Any], run["runner"]))
    )
    required_capabilities = tuple(
        sorted(cast(list[str], run["required_capabilities"]))
    )
    return CompletedEvidenceRun(
        run_id=run_id,
        origin_job_id=origin_job_id,
        origin_job_revision=origin_job_revision,
        protocol_revision_id=protocol_revision_id,
        kind=kind,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        sealed_at=sealed_at,
        runner_digest=runner_digest,
        required_capabilities=required_capabilities,
        artifacts=ordered,
        record_digest=_record_digest(
            run_id=run_id,
            origin_job_id=origin_job_id,
            origin_job_revision=origin_job_revision,
            protocol_revision_id=protocol_revision_id,
            kind=kind,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            sealed_at=sealed_at,
            runner_digest=runner_digest,
            required_capabilities=required_capabilities,
            artifacts=ordered,
        ),
    )


class EvidenceRunStore(Protocol):
    """Atomic append-only persistence boundary for complete validated runs."""

    def create(self, run: CompletedEvidenceRun) -> bool:
        """Insert the whole record only when its run ID is absent."""
        ...

    def get(self, run_id: str) -> CompletedEvidenceRun | None: ...


__all__ = [
    "CompletedEvidenceRun",
    "EvidenceArtifactRole",
    "EvidenceRunArtifact",
    "EvidenceRunStore",
    "create_completed_evidence_run",
    "create_evidence_run_artifact",
]
