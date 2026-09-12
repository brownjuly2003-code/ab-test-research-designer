"""Run one frozen aggregate protocol into a closed, persisted evidence record."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.binary_aggregate import (
    BinaryAggregateSource,
    BinaryAggregateValidationError,
    load_binary_aggregate,
    metric_definition_digest,
)
from app.backend.app.evidence.data_sources import QueryProvenance, SourceInspection
from app.backend.app.evidence.preflight import (
    AssignmentHealthIntervention,
    AssignmentHealthProfile,
    ObservedTelemetryProfile,
    ObservedTelemetrySchemaVersion,
    ProtocolPreflightFinding,
    preflight_assignment_health,
    preflight_observed_telemetry,
    preflight_protocol,
)
from app.backend.app.evidence.protocol_io import FrozenProtocol
from app.backend.app.evidence.public_pilots import (
    AsosMetricSnapshot,
    AsosPublicPilot,
    load_asos_public_pilot,
)
from app.backend.app.evidence.report import create_report_artifact
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    EvidenceRunStore,
    create_completed_evidence_run,
    create_evidence_run_artifact,
)
from app.backend.app.evidence.sql_run_store import EvidenceRunConflictError
from app.backend.app.evidence.stats_kernel import (
    AnalysisPlan,
    BinaryArmStatistics,
    BinarySufficientStatistics,
    LegacyStatsKernelAdapter,
    StatsKernelBuild,
    StatsKernelInputLineage,
    StatsKernelRequest,
    StatsKernelResult,
    load_stats_kernel_build,
)
from app.backend.app.evidence.stats_kernel_abx import (
    METHOD_PROFILE_SCHEMA_ID,
    StatsKernelAbxEstimateContext,
    materialize_method_guarantee_profile,
    materialize_stats_kernel_abx_estimate,
)

_PROTOCOL_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:protocol"
_RUN_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:run"
_SOURCE_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:source"
_METRIC_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:metric"
_FINDING_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:finding"
_ESTIMATE_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:estimate"
_DECISION_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:decision"
_JSON_MEDIA_TYPE = "application/json"
_SQL_MEDIA_TYPE = "application/sql"
_STARTED_AT = "2026-09-01T00:00:00Z"
_COMPLETED_AT = "2026-09-01T00:00:01Z"
_SEALED_AT = "2026-09-01T00:00:02Z"
_REQUIRED_CAPABILITIES = ("lineage-v1", "protocol-core")
_ASOS_OBSERVED_SCHEMAS = (
    ObservedTelemetrySchemaVersion(
        event_type="aggregate_assignment",
        version="benchmark-v1",
    ),
    ObservedTelemetrySchemaVersion(
        event_type="aggregate_metric_checkpoint",
        version="benchmark-v1",
    ),
)


@dataclass(frozen=True, slots=True)
class _BinarySnapshot:
    control_users: int
    control_conversions: int
    treatment_users: int
    treatment_conversions: int


@dataclass(frozen=True, slots=True)
class _MetricSource:
    metric_id: str
    name: str
    kind: str
    direction: str
    unit: str
    aggregation: str
    owner_ref: str
    extensions: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PipelineSource:
    inspection: SourceInspection
    provenance: QueryProvenance
    snapshot: _BinarySnapshot
    source_snapshot_id: str
    source_extensions: dict[str, Any]
    metrics: tuple[_MetricSource, ...]
    estimate_id: str
    run_extensions: dict[str, Any]
    observed_telemetry: ObservedTelemetryProfile


def run_protocol(
    frozen: FrozenProtocol,
    source: Path,
    *,
    principal: object,
    out_store: EvidenceRunStore,
) -> CompletedEvidenceRun:
    """Execute one supported aggregate binary path and persist it atomically."""

    protocol = load_ijson_object(frozen.canonical_bytes)
    pipeline_source = _load_pipeline_source(protocol, source)
    actor_ref = _principal_actor(principal)
    findings = _preflight_findings(protocol, frozen, pipeline_source)
    blocked = bool(findings)
    run_id, origin_job_id = _run_identities(
        frozen=frozen,
        source=pipeline_source,
        actor_ref=actor_ref,
        blocked=blocked,
    )

    protocol_artifact = create_evidence_run_artifact(
        path="protocol/protocol.json",
        role="protocol",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=_PROTOCOL_SCHEMA_ID,
        payload=frozen.canonical_bytes,
    )
    source_artifact = _source_artifact(pipeline_source)
    metric_artifacts = _metric_artifacts(
        protocol,
        source=pipeline_source,
    )
    primary_metric_id = cast(str, _primary_metric(protocol)["metric_id"])
    primary_metric_artifact = next(
        artifact
        for artifact in metric_artifacts
        if _artifact_id(artifact, "metric_id") == primary_metric_id
    )
    query_artifact = _query_artifact(pipeline_source)
    finding_artifacts = _finding_artifacts(
        findings,
        run_id=run_id,
        protocol_digest=protocol_artifact.digest,
    )

    build = load_stats_kernel_build()
    plan = _analysis_plan(protocol)
    method_artifact = _method_profile_artifact(build, plan)
    estimate_artifact: EvidenceRunArtifact | None = None
    decision_artifact: EvidenceRunArtifact | None = None
    if blocked:
        runner = _runner_from_build(build)
    else:
        result = LegacyStatsKernelAdapter(build).analyze(
            _stats_request(
                protocol=protocol,
                frozen=frozen,
                source=pipeline_source,
                metric_artifact=primary_metric_artifact,
                plan=plan,
            )
        )
        runner = _runner_from_result(result)
        estimate_artifact = _estimate_artifact(
            result,
            protocol=protocol,
            estimate_id=pipeline_source.estimate_id,
            run_id=run_id,
        )
        decision_artifact = _decision_artifact(
            protocol,
            run_id=run_id,
            protocol_revision_id=frozen.protocol_revision_id,
            actor_ref=actor_ref,
            estimate_id=_artifact_id(estimate_artifact, "estimate_id"),
            finding_ids=tuple(
                _artifact_id(artifact, "finding_id")
                for artifact in finding_artifacts
            ),
        )

    run_artifact = _run_artifact(
        run_id=run_id,
        protocol_revision_id=frozen.protocol_revision_id,
        kind="preflight" if blocked else "analysis",
        runner=runner,
        source=pipeline_source,
        metric_ids=tuple(
            _artifact_id(artifact, "metric_id") for artifact in metric_artifacts
        ),
        query_artifact=query_artifact,
        finding_ids=tuple(
            _artifact_id(artifact, "finding_id")
            for artifact in finding_artifacts
        ),
        estimate_id=(
            _artifact_id(estimate_artifact, "estimate_id")
            if estimate_artifact is not None
            else None
        ),
        decision_id=(
            _artifact_id(decision_artifact, "decision_id")
            if decision_artifact is not None
            else None
        ),
    )
    artifacts = [
        protocol_artifact,
        source_artifact,
        *metric_artifacts,
        method_artifact,
        query_artifact,
        *finding_artifacts,
    ]
    if estimate_artifact is not None:
        artifacts.append(estimate_artifact)
    if decision_artifact is not None:
        artifacts.append(decision_artifact)
    artifacts.append(run_artifact)
    completed_without_report = create_completed_evidence_run(
        origin_job_id=origin_job_id,
        origin_job_revision=1,
        sealed_at=_SEALED_AT,
        artifacts=tuple(artifacts),
    )
    completed = create_completed_evidence_run(
        origin_job_id=origin_job_id,
        origin_job_revision=1,
        sealed_at=_SEALED_AT,
        artifacts=(
            *completed_without_report.artifacts,
            create_report_artifact(completed_without_report),
        ),
    )
    return _persist(completed, out_store)


def _experiment_id(protocol: dict[str, Any]) -> str:
    extensions = protocol.get("extensions")
    if not isinstance(extensions, Mapping):
        raise ValueError("protocol does not declare an ASOS experiment")
    asos = extensions.get("trialmark.asos")
    if not isinstance(asos, Mapping):
        raise ValueError("protocol does not declare an ASOS experiment")
    experiment_id = asos.get("experiment_id")
    if not isinstance(experiment_id, str):
        raise ValueError("protocol ASOS experiment_id is invalid")
    return experiment_id


def _binary_snapshot(pilot: AsosPublicPilot) -> AsosMetricSnapshot:
    for snapshot in pilot.snapshots:
        if snapshot.metric_id == 1 and snapshot.metric_kind == "binary":
            return snapshot
    raise ValueError("ASOS public pilot has no binary metric 1 snapshot")


def _metric_references(protocol: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    metrics = cast(dict[str, list[dict[str, Any]]], protocol["metrics"])
    return tuple(
        reference
        for role in ("primary", "secondary", "guardrails")
        for reference in metrics[role]
    )


def _load_pipeline_source(
    protocol: dict[str, Any],
    source_path: Path,
) -> _PipelineSource:
    extensions = protocol.get("extensions")
    if not isinstance(extensions, Mapping):
        raise ValueError(
            "protocol must declare exactly one supported aggregate source extension"
        )
    supported = tuple(
        key
        for key in ("trialmark.asos", "trialmark.aggregate-binary")
        if key in extensions
    )
    if len(supported) != 1:
        raise ValueError(
            "protocol must declare exactly one supported aggregate source extension"
        )
    if supported[0] == "trialmark.asos":
        return _load_asos_pipeline_source(protocol, source_path)
    return _load_binary_pipeline_source(protocol, source_path)


def _load_asos_pipeline_source(
    protocol: dict[str, Any],
    source_path: Path,
) -> _PipelineSource:
    experiment_id = _experiment_id(protocol)
    pilot = load_asos_public_pilot(
        source_path,
        expected_experiment_id=experiment_id,
    )
    primary_snapshot = _binary_snapshot(pilot)
    snapshots = {
        f"metric_asos_{snapshot.metric_id}": snapshot
        for snapshot in pilot.snapshots
    }
    metrics: list[_MetricSource] = []
    for reference in _metric_references(protocol):
        metric_id = cast(str, reference["metric_id"])
        snapshot = snapshots.get(metric_id)
        if snapshot is None:
            raise ValueError(
                f"ASOS protocol metric has no terminal snapshot: {metric_id}"
            )
        metric_kind = (
            "continuous"
            if snapshot.metric_kind == "nonnegative_real"
            else snapshot.metric_kind
        )
        metrics.append(
            _MetricSource(
                metric_id=metric_id,
                name=f"ASOS decision metric {snapshot.metric_id}",
                kind=metric_kind,
                direction="neutral",
                unit="published_response_unit",
                aggregation="mean",
                owner_ref="trialmark_public_benchmark",
                extensions={
                    "trialmark.asos": {
                        "aggregate_only": True,
                        "definition": {
                            "aggregation": "terminal_sample_mean",
                            "dataset_doi": "10.17605/OSF.IO/64JSB",
                            "metric_id": snapshot.metric_id,
                            "original_semantics_available": False,
                            "reported_kind": snapshot.metric_kind,
                        },
                        "experiment_id": experiment_id,
                        "metric_id": snapshot.metric_id,
                    }
                },
            )
        )
    return _PipelineSource(
        inspection=pilot.inspection,
        provenance=pilot.provenance,
        snapshot=_BinarySnapshot(
            control_users=primary_snapshot.count_c,
            control_conversions=_exact_conversions(
                primary_snapshot.count_c,
                primary_snapshot.mean_c,
            ),
            treatment_users=primary_snapshot.count_t,
            treatment_conversions=_exact_conversions(
                primary_snapshot.count_t,
                primary_snapshot.mean_t,
            ),
        ),
        source_snapshot_id=f"source_asos_{experiment_id}_terminal",
        source_extensions={
            "trialmark.asos": pilot.metadata.model_dump(mode="json"),
        },
        metrics=tuple(metrics),
        estimate_id=f"estimate_asos_{experiment_id}_1",
        run_extensions={
            "trialmark.asos": {
                "aggregate_only": True,
                "experiment_id": experiment_id,
            }
        },
        observed_telemetry=ObservedTelemetryProfile(
            outcome_before_exposure_count=0,
            duplicate_event_count=0,
            unlinked_subject_count=0,
            events_beyond_max_lateness_count=0,
            schema_versions=_ASOS_OBSERVED_SCHEMAS,
        ),
    )


def validate_binary_source(
    protocol: dict[str, Any],
    source_path: Path,
) -> BinaryAggregateSource:
    """Check a practitioner's CSV against a frozen protocol and nothing else.

    No store, no run, no bundle: this is the half of ``run`` that can fail on
    the file itself, split out so a thirty-minute session can find out in one
    second rather than after a pipeline has already started writing.
    """

    extensions = protocol.get("extensions")
    if (
        not isinstance(extensions, Mapping)
        or "trialmark.aggregate-binary" not in extensions
    ):
        raise BinaryAggregateValidationError(
            "protocol does not declare a trialmark.aggregate-binary source"
        )
    aggregate = load_binary_aggregate(
        source_path,
        extensions["trialmark.aggregate-binary"],
    )
    if len(_metric_references(protocol)) != 1:
        raise BinaryAggregateValidationError(
            "aggregate-binary protocol requires exactly one metric"
        )
    reference = _primary_metric(protocol)
    definition_digest = metric_definition_digest(aggregate.config)
    if reference["definition_digest"] != definition_digest:
        raise BinaryAggregateValidationError(
            "aggregate-binary metric definition digest does not match the "
            f"protocol: the protocol declares {reference['definition_digest']}, "
            f"the source metric definition hashes to {definition_digest}"
        )
    return aggregate


def summarize_binary_source(
    protocol: dict[str, Any],
    aggregate: BinaryAggregateSource,
) -> dict[str, Any]:
    """The bounded CLI result for one accepted source. Counts, never rows."""

    return {
        "valid": True,
        "source_ref": aggregate.config.source_ref,
        "evidence_type": aggregate.config.evidence_type,
        "partner_approved": aggregate.config.partner_approved,
        "metric_id": _primary_metric(protocol)["metric_id"],
        "definition_digest": metric_definition_digest(aggregate.config),
        "columns": [column.name for column in aggregate.inspection.columns],
        "aggregate": aggregate.snapshot.model_dump(mode="json"),
    }


def validate_source_document(
    frozen: FrozenProtocol,
    source_path: Path,
) -> dict[str, Any]:
    """Pre-flight a source against a frozen protocol and summarize the result.

    The one entry point the CLI needs: it starts from the canonical bytes the
    protocol was frozen into, so the check runs against exactly the document a
    later ``run`` would use.
    """

    protocol = load_ijson_object(frozen.canonical_bytes)
    aggregate = validate_binary_source(protocol, source_path)
    return summarize_binary_source(protocol, aggregate)


def _load_binary_pipeline_source(
    protocol: dict[str, Any],
    source_path: Path,
) -> _PipelineSource:
    aggregate = validate_binary_source(protocol, source_path)
    reference = _primary_metric(protocol)
    definition = aggregate.config.metric.definition.model_dump(mode="json")
    fingerprint_digest = sha256_hex(
        canonical_json_bytes(aggregate.inspection.fingerprint.model_dump(mode="json"))
    ).removeprefix("sha256:")
    telemetry = aggregate.config.observed_telemetry
    snapshot = aggregate.snapshot
    return _PipelineSource(
        inspection=aggregate.inspection,
        provenance=aggregate.provenance,
        snapshot=_BinarySnapshot(
            control_users=snapshot.control_users,
            control_conversions=snapshot.control_conversions,
            treatment_users=snapshot.treatment_users,
            treatment_conversions=snapshot.treatment_conversions,
        ),
        source_snapshot_id=f"source_aggregate_binary_{fingerprint_digest[:24]}",
        source_extensions={
            "trialmark.aggregate-binary": {
                "aggregate_only": True,
                "evidence_type": aggregate.config.evidence_type,
                "partner_approved": aggregate.config.partner_approved,
                "telemetry_profile_source": "upstream_asserted",
            }
        },
        metrics=(
            _MetricSource(
                metric_id=cast(str, reference["metric_id"]),
                name=aggregate.config.metric.name,
                kind="binary",
                direction=aggregate.config.metric.direction,
                unit=aggregate.config.metric.unit,
                aggregation="rate",
                owner_ref=aggregate.config.metric.owner_ref,
                extensions={
                    "trialmark.aggregate-binary": {
                        "definition": definition,
                    }
                },
            ),
        ),
        estimate_id=f"estimate_aggregate_binary_{fingerprint_digest[:24]}",
        run_extensions={
            "trialmark.aggregate-binary": {
                "aggregate_only": True,
                "evidence_type": aggregate.config.evidence_type,
            }
        },
        observed_telemetry=ObservedTelemetryProfile(
            outcome_before_exposure_count=telemetry.outcome_before_exposure_count,
            duplicate_event_count=telemetry.duplicate_event_count,
            unlinked_subject_count=telemetry.unlinked_subject_count,
            events_beyond_max_lateness_count=(
                telemetry.events_beyond_max_lateness_count
            ),
            schema_versions=tuple(
                ObservedTelemetrySchemaVersion(
                    event_type=schema.event_type,
                    version=schema.version,
                )
                for schema in telemetry.schema_versions
            ),
        ),
    )


def _primary_metric(protocol: dict[str, Any]) -> dict[str, Any]:
    metrics = cast(dict[str, Any], protocol["metrics"])
    primary = cast(list[dict[str, Any]], metrics["primary"])
    if len(primary) != 1:
        raise ValueError("pipeline requires exactly one primary metric")
    return primary[0]


def _preflight_findings(
    protocol: dict[str, Any],
    frozen: FrozenProtocol,
    source: _PipelineSource,
) -> tuple[ProtocolPreflightFinding, ...]:
    protocol_report = preflight_protocol(protocol)
    if protocol_report.findings:
        return protocol_report.findings

    telemetry_report = preflight_observed_telemetry(
        protocol,
        source.observed_telemetry,
    )
    analysis = cast(dict[str, Any], protocol["analysis"])
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    if len(interventions) != 2:
        raise ValueError("binary pipeline requires exactly two interventions")
    assignment_report = preflight_assignment_health(
        protocol,
        AssignmentHealthProfile(
            protocol_digest=frozen.protocol_revision_id,
            random_seed=cast(int, analysis["random_seed"]),
            synthetic_sample_size=100_000,
            interventions=tuple(
                AssignmentHealthIntervention(
                    intervention_id=cast(str, intervention["intervention_id"]),
                    allocation=cast(str, intervention["allocation"]),
                    namespace=cast(str, intervention["namespace"]),
                    hash_version=cast(str, intervention["hash_version"]),
                    observed_count=(
                        source.snapshot.control_users
                        if intervention["kind"] == "control"
                        else source.snapshot.treatment_users
                    ),
                )
                for intervention in interventions
            ),
        ),
    )
    unique = {
        (finding.code, finding.json_pointer): finding
        for finding in (*telemetry_report.findings, *assignment_report.findings)
    }
    return tuple(unique[key] for key in sorted(unique))


def _run_identities(
    *,
    frozen: FrozenProtocol,
    source: _PipelineSource,
    actor_ref: str,
    blocked: bool,
) -> tuple[str, str]:
    digest = sha256_hex(
        canonical_json_bytes(
            {
                "actor_ref": actor_ref,
                "blocked": blocked,
                "protocol_revision_id": frozen.protocol_revision_id,
                "query_id": source.provenance.query_id,
                "source_fingerprint": source.inspection.fingerprint.model_dump(
                    mode="json"
                ),
            }
        )
    ).removeprefix("sha256:")
    return f"run_{digest[:24]}", f"job_{digest[24:48]}"


def _source_artifact(
    source: _PipelineSource,
) -> EvidenceRunArtifact:
    document = {
        "schema_version": "0.1.0",
        "source_snapshot_id": source.source_snapshot_id,
        "source_ref": source.inspection.source_ref,
        "kind": "duckdb_file",
        "captured_at": _STARTED_AT,
        "fingerprint": source.inspection.fingerprint.model_dump(mode="json"),
        "engine": source.inspection.engine.model_dump(mode="json"),
        "schema_digest": source.inspection.schema_digest,
        "extensions": source.source_extensions,
    }
    return create_evidence_run_artifact(
        path=f"sources/{source.source_snapshot_id}.json",
        role="source",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=_SOURCE_SCHEMA_ID,
        payload=canonical_json_bytes(document),
    )


def _metric_artifacts(
    protocol: dict[str, Any],
    *,
    source: _PipelineSource,
) -> tuple[EvidenceRunArtifact, ...]:
    references = {
        cast(str, reference["metric_id"]): reference
        for reference in _metric_references(protocol)
    }
    artifacts: list[EvidenceRunArtifact] = []
    for metric in source.metrics:
        reference = references.get(metric.metric_id)
        if reference is None:
            raise ValueError(
                f"source metric is not declared by the protocol: {metric.metric_id}"
            )
        document = {
            "schema_version": "0.1.0",
            "metric_id": metric.metric_id,
            "metric_version": cast(str, reference["metric_version"]),
            "definition_digest": cast(str, reference["definition_digest"]),
            "name": metric.name,
            "kind": metric.kind,
            "direction": metric.direction,
            "unit": metric.unit,
            "aggregation": metric.aggregation,
            "owner_ref": metric.owner_ref,
            "source_snapshot_id": source.source_snapshot_id,
            "extensions": metric.extensions,
        }
        artifacts.append(
            create_evidence_run_artifact(
                path=f"metrics/{metric.metric_id}.json",
                role="metric",
                media_type=_JSON_MEDIA_TYPE,
                schema_id=_METRIC_SCHEMA_ID,
                payload=canonical_json_bytes(document),
            )
        )
    return tuple(artifacts)


def _query_artifact(source: _PipelineSource) -> EvidenceRunArtifact:
    payload = source.provenance.statement.encode("utf-8")
    if sha256_hex(payload) != source.provenance.statement_digest:
        raise ValueError("query statement digest is inconsistent")
    digest = source.provenance.statement_digest.removeprefix("sha256:")
    return create_evidence_run_artifact(
        path=f"queries/{digest}.sql",
        role="query",
        media_type=_SQL_MEDIA_TYPE,
        payload=payload,
    )


def _finding_artifacts(
    findings: tuple[ProtocolPreflightFinding, ...],
    *,
    run_id: str,
    protocol_digest: str,
) -> tuple[EvidenceRunArtifact, ...]:
    artifacts: list[EvidenceRunArtifact] = []
    for finding in findings:
        identity_digest = sha256_hex(
            canonical_json_bytes(
                {
                    "code": finding.code,
                    "json_pointer": finding.json_pointer,
                    "run_id": run_id,
                }
            )
        ).removeprefix("sha256:")
        finding_id = f"finding_{identity_digest[:24]}"
        document: dict[str, Any] = {
            "schema_version": "0.1.0",
            "finding_id": finding_id,
            "run_id": run_id,
            "code": finding.code,
            "category": finding.category,
            "severity": "error",
            "state": "open",
            "blocking": True,
            "summary": finding.message,
            "evidence": [{"artifact_digest": protocol_digest}],
            "remediation": {
                "code": finding.code,
                "guidance": "Correct the frozen protocol declaration and rerun preflight.",
            },
            "produced_at": _COMPLETED_AT,
            "extensions": {
                "trialmark.preflight": {
                    "json_pointer": finding.json_pointer,
                }
            },
        }
        _add_content_digest(document)
        artifacts.append(
            create_evidence_run_artifact(
                path=f"diagnostics/{finding_id}.json",
                role="finding",
                media_type=_JSON_MEDIA_TYPE,
                schema_id=_FINDING_SCHEMA_ID,
                payload=canonical_json_bytes(document),
            )
        )
    return tuple(artifacts)


def _analysis_plan(protocol: dict[str, Any]) -> AnalysisPlan:
    analysis = cast(dict[str, Any], protocol["analysis"])
    return AnalysisPlan(alpha=float(analysis["alpha"]))


def _method_profile_artifact(
    build: StatsKernelBuild,
    plan: AnalysisPlan,
) -> EvidenceRunArtifact:
    profile = materialize_method_guarantee_profile(build, plan)
    return create_evidence_run_artifact(
        path="methods/profile.json",
        role="method",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=METHOD_PROFILE_SCHEMA_ID,
        payload=canonical_json_bytes(profile.model_dump(mode="json")),
    )


def _stats_request(
    *,
    protocol: dict[str, Any],
    frozen: FrozenProtocol,
    source: _PipelineSource,
    metric_artifact: EvidenceRunArtifact,
    plan: AnalysisPlan,
) -> StatsKernelRequest:
    baseline_id, comparison_id = _intervention_ids(protocol)
    metric = _primary_metric(protocol)
    return StatsKernelRequest(
        plan=plan,
        aggregates=BinarySufficientStatistics(
            control=BinaryArmStatistics(
                intervention_id=baseline_id,
                conversions=source.snapshot.control_conversions,
                users=source.snapshot.control_users,
            ),
            treatment=BinaryArmStatistics(
                intervention_id=comparison_id,
                conversions=source.snapshot.treatment_conversions,
                users=source.snapshot.treatment_users,
            ),
        ),
        lineage=StatsKernelInputLineage(
            protocol_revision_id=frozen.protocol_revision_id,
            metric_id=cast(str, metric["metric_id"]),
            metric_version=cast(str, metric["metric_version"]),
            metric_digest=metric_artifact.digest,
            query_ids=(source.provenance.query_id,),
            source_snapshot_ids=(source.source_snapshot_id,),
        ),
    )


def _exact_conversions(users: int, mean: float) -> int:
    value = users * mean
    rounded = round(value)
    if not math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("binary ASOS mean does not encode an exact conversion count")
    return rounded


def _intervention_ids(protocol: dict[str, Any]) -> tuple[str, str]:
    estimand = cast(dict[str, Any], protocol["estimand"])
    comparisons = cast(list[str], estimand["comparison_intervention_ids"])
    if len(comparisons) != 1:
        raise ValueError("binary pipeline requires exactly one comparison intervention")
    return cast(str, estimand["baseline_intervention_id"]), comparisons[0]


def _estimate_artifact(
    result: StatsKernelResult,
    *,
    protocol: dict[str, Any],
    estimate_id: str,
    run_id: str,
) -> EvidenceRunArtifact:
    baseline_id, comparison_id = _intervention_ids(protocol)
    estimand = cast(dict[str, Any], protocol["estimand"])
    estimate = materialize_stats_kernel_abx_estimate(
        result,
        StatsKernelAbxEstimateContext(
            estimate_id=estimate_id,
            run_id=run_id,
            estimand_id=cast(str, estimand["estimand_id"]),
            baseline_intervention_id=baseline_id,
            comparison_intervention_id=comparison_id,
            produced_at=_COMPLETED_AT,
        ),
    )
    return create_evidence_run_artifact(
        path=f"estimates/{estimate_id}.json",
        role="estimate",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=_ESTIMATE_SCHEMA_ID,
        payload=canonical_json_bytes(estimate.model_dump(mode="json")),
    )


def _runner_from_build(build: StatsKernelBuild) -> dict[str, str]:
    return {
        "name": "legacy_stats_kernel",
        "version": build.kernel_version,
        "build_digest": build.build_digest,
        "dependency_lock_digest": build.dependency_lock_digest,
        "analyzer_version": "binary_pooled_z_newcombe_v1",
        "policy_version": "fixed_horizon_two_sided_v1",
    }


def _runner_from_result(result: StatsKernelResult) -> dict[str, str]:
    lineage = result.lineage
    return {
        "name": lineage.kernel_name,
        "version": lineage.kernel_version,
        "build_digest": lineage.build_digest,
        "dependency_lock_digest": lineage.dependency_lock_digest,
        "analyzer_version": lineage.analyzer_version,
        "policy_version": lineage.policy_version,
    }


def _decision_artifact(
    protocol: dict[str, Any],
    *,
    run_id: str,
    protocol_revision_id: str,
    actor_ref: str,
    estimate_id: str,
    finding_ids: tuple[str, ...],
) -> EvidenceRunArtifact:
    decision_digest = sha256_hex(run_id.encode("utf-8")).removeprefix("sha256:")
    decision_id = f"decision_{decision_digest[:24]}"
    policy = cast(dict[str, Any], protocol["decision"])
    approval = cast(dict[str, Any], policy["approval_policy"])
    harm_rules = cast(list[dict[str, Any]], policy["harm_rules"])
    document: dict[str, Any] = {
        "schema_version": "0.1.0",
        "decision_id": decision_id,
        "run_id": run_id,
        "protocol_revision_id": protocol_revision_id,
        "policy": {
            "policy_id": "frozen_protocol_policy",
            "version": "1",
            "minimum_worthwhile_effect": float(
                policy["minimum_worthwhile_effect"]
            ),
            "harm_rule_codes": [
                cast(str, rule["code"])
                for rule in harm_rules
                if isinstance(rule.get("code"), str)
            ],
            "approval_roles": cast(list[str], approval["roles"]),
        },
        "evidence": {
            "estimate_ids": [estimate_id],
            "finding_ids": list(finding_ids),
        },
        "proposed_verdict": "inconclusive",
        "human_verdict": "inconclusive",
        "rationale": "Proposed for human review after independent ABX verification.",
        "state": "proposed",
        "decided_at": _COMPLETED_AT,
        "decided_by": {
            "actor_ref": actor_ref,
            "role": "evidence_system",
        },
        "approvals": [],
        "extensions": {},
    }
    _add_content_digest(document)
    return create_evidence_run_artifact(
        path="decision/decision.json",
        role="decision",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=_DECISION_SCHEMA_ID,
        payload=canonical_json_bytes(document),
    )


def _run_artifact(
    *,
    run_id: str,
    protocol_revision_id: str,
    kind: str,
    runner: dict[str, str],
    source: _PipelineSource,
    metric_ids: tuple[str, ...],
    query_artifact: EvidenceRunArtifact,
    finding_ids: tuple[str, ...],
    estimate_id: str | None,
    decision_id: str | None,
) -> EvidenceRunArtifact:
    document: dict[str, Any] = {
        "schema_version": "0.1.0",
        "required_capabilities": list(_REQUIRED_CAPABILITIES),
        "run_id": run_id,
        "protocol_revision_id": protocol_revision_id,
        "kind": kind,
        "status": "succeeded",
        "started_at": _STARTED_AT,
        "completed_at": _COMPLETED_AT,
        "runner": runner,
        "source_snapshot_ids": [source.source_snapshot_id],
        "metric_ids": list(metric_ids),
        "queries": [
            {
                "query_id": source.provenance.query_id,
                "source_snapshot_id": source.source_snapshot_id,
                "dialect": source.provenance.dialect,
                "statement_path": query_artifact.path,
                "statement_digest": query_artifact.digest,
                "parameters_digest": source.provenance.parameters_digest,
                "input_aggregate_digests": [source.inspection.fingerprint.value],
                "extensions": {
                    "trialmark.query-budget": {
                        "estimated_scan_rows": source.provenance.estimated_scan_rows,
                    }
                },
            }
        ],
        "finding_ids": list(finding_ids),
        "estimate_ids": [] if estimate_id is None else [estimate_id],
        "extensions": source.run_extensions,
    }
    if decision_id is not None:
        document["decision_id"] = decision_id
    return create_evidence_run_artifact(
        path="run/run.json",
        role="run",
        media_type=_JSON_MEDIA_TYPE,
        schema_id=_RUN_SCHEMA_ID,
        payload=canonical_json_bytes(document),
    )


def _add_content_digest(document: dict[str, Any]) -> None:
    document["content_digest"] = sha256_hex(canonical_json_bytes(document))


def _artifact_id(artifact: EvidenceRunArtifact, key: str) -> str:
    return cast(str, load_ijson_object(artifact.payload)[key])


def _principal_actor(principal: object) -> str:
    if isinstance(principal, str):
        actor_ref = principal
    else:
        actor_ref = next(
            (
                value
                for attribute in ("actor_ref", "actor", "name", "id")
                if isinstance((value := getattr(principal, attribute, None)), str)
            ),
            "local-operator",
        )
    if not actor_ref or len(actor_ref) > 128:
        raise ValueError("principal actor reference is invalid")
    if not actor_ref[0].isalpha() or any(
        not (character.isalnum() or character in "_.-")
        for character in actor_ref
    ):
        raise ValueError("principal actor reference is invalid")
    return actor_ref


def _persist(
    run: CompletedEvidenceRun,
    out_store: EvidenceRunStore,
) -> CompletedEvidenceRun:
    if out_store.create(run):
        return run
    existing = out_store.get(run.run_id)
    if existing is None:
        raise EvidenceRunConflictError(
            f"store rejected insert for {run.run_id} without an existing record"
        )
    if existing.record_digest != run.record_digest:
        raise EvidenceRunConflictError(f"conflicting completed run for {run.run_id}")
    return existing


__all__ = ["run_protocol"]
