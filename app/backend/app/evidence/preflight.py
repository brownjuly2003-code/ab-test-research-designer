from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path
from statistics import NormalDist
from typing import Any, Literal, Self, cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.evidence._common import (
    SHA256_PATTERN as _SHA256_PATTERN,
)
from app.backend.app.evidence._common import (
    canonical_digest,
)
from app.backend.app.evidence.abx import (
    PROTOCOL_SCHEMA_ID,
    schema_violations,
)
from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    DuckDbFileAdapter,
    QueryBudget,
    QueryProvenance,
    QueryValue,
)
from app.backend.app.execution.bucketer import preview_assignment_distribution
from app.backend.app.stats.binary import standard_normal_sf
from app.backend.app.stats.srm import chi_square_srm

FindingCategory = Literal[
    "protocol",
    "statistics",
    "telemetry",
]
FindingCode = Literal[
    "PROTOCOL_SCHEMA_INVALID",
    "INTERVENTION_ID_DUPLICATE",
    "CONTROL_COUNT_INVALID",
    "INTERVENTION_ALLOCATION_NONPOSITIVE",
    "ALLOCATION_TOTAL_INVALID",
    "ESTIMAND_BASELINE_UNKNOWN",
    "ESTIMAND_BASELINE_NOT_CONTROL",
    "ESTIMAND_COMPARISON_UNKNOWN",
    "ESTIMAND_COMPARISON_NOT_TREATMENT",
    "ESTIMAND_POPULATION_MISMATCH",
    "METRIC_REFERENCE_DUPLICATE",
    "METRIC_ROLE_CONFLICT",
    "METRIC_REFERENCE_CONFLICT",
    "MULTIPLICITY_METRIC_UNKNOWN",
    "MULTIPLICITY_POLICY_INCONSISTENT",
    "COVARIATE_METRIC_UNKNOWN",
    "VARIANCE_REDUCTION_POLICY_INCONSISTENT",
    "HARM_RULE_METRIC_UNKNOWN",
    "HARM_RULE_METRIC_NOT_GUARDRAIL",
    "GUARDRAIL_POLICY_MISSING",
    "ALERT_THRESHOLD_METRIC_UNKNOWN",
    "APPROVAL_POLICY_UNSATISFIABLE",
    "TELEMETRY_EVENT_ROLE_CONFLICT",
    "TELEMETRY_DEDUP_EVENT_KEY_MISSING",
    "TELEMETRY_EVENT_SCHEMA_MISSING",
    "TELEMETRY_SCHEMA_VERSION_DUPLICATE",
    "TELEMETRY_SCHEMA_VERSION_CONFLICT",
    "TELEMETRY_OUTCOME_BEFORE_EXPOSURE",
    "TELEMETRY_DUPLICATE_EVENTS",
    "TELEMETRY_UNLINKED_SUBJECTS",
    "TELEMETRY_SCHEMA_VERSION_UNKNOWN",
    "TELEMETRY_MAX_LATENESS_EXCEEDED",
    "AA_CALIBRATION_FAILED",
    "AA_CALIBRATION_ASSERTED_FAILED",
    "EMPIRICAL_POWER_BELOW_TARGET",
    "ASSIGNMENT_SYNTHETIC_BALANCE_FAILED",
    "ASSIGNMENT_SAMPLE_RATIO_MISMATCH",
]

_JSON_POINTER_PATTERN = r"^(?:/(?:[^~/]|~0|~1)*)*$"
_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_METHOD_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_PROBABILITY_PATTERN = r"^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$"
_DECIMAL_NUMBER_PATTERN = (
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)
_MAX_PROBABILITY_STRING_LENGTH = 128
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_SYNTHETIC_SAMPLE_SIZE = 100_000
_MIN_AA_SIMULATION_COUNT = 200
_DEFAULT_AA_SIMULATION_COUNT = 1_000
_AA_CALIBRATION_THRESHOLD = Decimal("0.01")
_MIN_POWER_SIMULATION_COUNT = 500
_DEFAULT_POWER_SIMULATION_COUNT = 1_000
_MAX_INTERNAL_SIMULATION_COUNT = 100_000
_ASSIGNMENT_HASH_VERSIONS = {
    "assignment_v1": 1,
    "assignment_v2": 2,
}


class ProtocolPreflightFinding(BaseModel):
    """One deterministic blocking defect in a frozen protocol."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FindingCode
    category: FindingCategory
    blocking: Literal[True] = True
    json_pointer: str = Field(max_length=512, pattern=_JSON_POINTER_PATTERN)
    message: str = Field(min_length=1, max_length=4096)


class ProtocolPreflightReport(BaseModel):
    """Immutable offline result with no clock or random inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_digest: str = Field(pattern=_SHA256_PATTERN)
    findings: tuple[ProtocolPreflightFinding, ...]

    @property
    def ready(self) -> bool:
        return not self.findings


class ObservedTelemetrySchemaVersion(BaseModel):
    """One aggregate declaration observed in telemetry, without event rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    version: str = Field(min_length=1, max_length=64)


class ObservedTelemetryProfile(BaseModel):
    """Immutable aggregate telemetry quality counters and schema declarations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome_before_exposure_count: int = Field(strict=True, ge=0)
    duplicate_event_count: int = Field(strict=True, ge=0)
    unlinked_subject_count: int = Field(strict=True, ge=0)
    events_beyond_max_lateness_count: int = Field(strict=True, ge=0)
    schema_versions: tuple[ObservedTelemetrySchemaVersion, ...]


class SimulatedAaAnalysisMethod(BaseModel):
    """Frozen analysis method used to produce simulated null p-values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_id: str = Field(min_length=1, max_length=64, pattern=_METHOD_ID_PATTERN)
    method_version: str = Field(min_length=1, max_length=64)


class SimulatedAaAllocation(BaseModel):
    """One frozen allocation declaration used by the simulated A/A runner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intervention_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_OPAQUE_ID_PATTERN,
    )
    allocation: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_PROBABILITY_PATTERN,
    )
    namespace: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    hash_version: str = Field(min_length=1, max_length=64)


class SimulatedAaMetricCalibration(BaseModel):
    """Aggregate p-value uniformity result for one frozen metric declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    metric_version: str = Field(min_length=1, max_length=64)
    definition_digest: str = Field(pattern=_SHA256_PATTERN)
    calibration_source: Literal["internal_permutation", "upstream_asserted"]
    simulated_p_value_count: int = Field(
        strict=True,
        ge=_MIN_AA_SIMULATION_COUNT,
        le=_MAX_SAFE_INTEGER,
    )
    simulated_p_values_digest: str | None = Field(
        default=None,
        pattern=_SHA256_PATTERN,
    )
    uniformity_p_value: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_PROBABILITY_PATTERN,
    )

    @model_validator(mode="after")
    def validate_internal_evidence(self) -> Self:
        if (
            self.calibration_source == "internal_permutation"
            and self.simulated_p_values_digest is None
        ):
            raise ValueError(
                "internal permutation calibration requires a p-value vector digest"
            )
        return self


class SimulatedAaProfile(BaseModel):
    """Aggregate-only simulated A/A inputs and metric calibration results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    random_seed: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)
    analysis_method: SimulatedAaAnalysisMethod
    allocations: tuple[SimulatedAaAllocation, ...] = Field(min_length=2)
    metric_calibrations: tuple[SimulatedAaMetricCalibration, ...] = Field(
        min_length=1
    )


class SimulatedAaBinaryAggregate(BaseModel):
    """Binary sufficient statistics used for conditional arm permutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    metric_version: str = Field(min_length=1, max_length=64)
    definition_digest: str = Field(pattern=_SHA256_PATTERN)
    control_users: int = Field(strict=True, ge=2, le=_MAX_SAFE_INTEGER)
    control_conversions: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)
    treatment_users: int = Field(strict=True, ge=2, le=_MAX_SAFE_INTEGER)
    treatment_conversions: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)

    @model_validator(mode="after")
    def validate_conversion_counts(self) -> Self:
        if self.control_conversions > self.control_users:
            raise ValueError("control conversions cannot exceed control users")
        if self.treatment_conversions > self.treatment_users:
            raise ValueError("treatment conversions cannot exceed treatment users")
        return self


class EmpiricalPowerMetricResult(BaseModel):
    """Aggregate simulated power result for one frozen metric declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    metric_version: str = Field(min_length=1, max_length=64)
    definition_digest: str = Field(pattern=_SHA256_PATTERN)
    power_source: Literal["internal_bootstrap", "upstream_asserted"]
    historical_distribution_digest: str = Field(pattern=_SHA256_PATTERN)
    simulation_count: int = Field(
        strict=True,
        ge=_MIN_POWER_SIMULATION_COUNT,
        le=_MAX_SAFE_INTEGER,
    )
    evaluated_total_sample_size: int = Field(
        strict=True,
        ge=2,
        le=_MAX_SAFE_INTEGER,
    )
    achieved_power: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_PROBABILITY_PATTERN,
    )
    detectable_effect_at_evaluated_total_sample_size: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_DECIMAL_NUMBER_PATTERN,
    )
    recommended_total_sample_size: int = Field(
        strict=True,
        ge=2,
        le=_MAX_SAFE_INTEGER,
    )


class EmpiricalPowerBinaryMetricSource(BaseModel):
    """One binary historical column and its frozen evaluation volume."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_id: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    metric_version: str = Field(min_length=1, max_length=64)
    definition_digest: str = Field(pattern=_SHA256_PATTERN)
    outcome_column: str = Field(
        min_length=1,
        max_length=128,
        pattern=_OPAQUE_ID_PATTERN,
    )
    evaluated_total_sample_size: int = Field(
        strict=True,
        ge=4,
        le=_MAX_SAFE_INTEGER,
    )


class EmpiricalPowerProfile(BaseModel):
    """Immutable aggregate-only empirical power simulation results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_digest: str = Field(pattern=_SHA256_PATTERN)
    random_seed: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)
    analysis_method: SimulatedAaAnalysisMethod
    target_power: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_PROBABILITY_PATTERN,
    )
    minimum_worthwhile_effect: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_DECIMAL_NUMBER_PATTERN,
    )
    allocations: tuple[SimulatedAaAllocation, ...] = Field(min_length=2)
    metric_results: tuple[EmpiricalPowerMetricResult, ...] = Field(min_length=1)


class AssignmentHealthIntervention(BaseModel):
    """One ordered aggregate assignment binding and observed count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intervention_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=_OPAQUE_ID_PATTERN,
    )
    allocation: str = Field(
        max_length=_MAX_PROBABILITY_STRING_LENGTH,
        pattern=_PROBABILITY_PATTERN,
    )
    namespace: str = Field(min_length=1, max_length=128, pattern=_OPAQUE_ID_PATTERN)
    hash_version: str = Field(min_length=1, max_length=64)
    observed_count: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)


class AssignmentHealthProfile(BaseModel):
    """Immutable aggregate-only evidence for frozen assignment declarations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_digest: str = Field(pattern=_SHA256_PATTERN)
    random_seed: int = Field(strict=True, ge=0, le=_MAX_SAFE_INTEGER)
    synthetic_sample_size: int = Field(
        strict=True,
        ge=2,
        le=_MAX_SYNTHETIC_SAMPLE_SIZE,
    )
    interventions: tuple[AssignmentHealthIntervention, ...] = Field(
        min_length=2,
        max_length=MAX_SUPPORTED_VARIANTS,
    )

    @model_validator(mode="after")
    def validate_observed_total(self) -> AssignmentHealthProfile:
        if sum(
            intervention.observed_count for intervention in self.interventions
        ) == 0:
            raise ValueError(
                "assignment health observed counts must have a positive total"
            )
        return self


def _finding(
    code: FindingCode,
    category: FindingCategory,
    pointer: str,
    message: str,
) -> ProtocolPreflightFinding:
    return ProtocolPreflightFinding(
        code=code,
        category=category,
        json_pointer=pointer,
        message=message,
    )


def _protocol_digest(protocol: dict[str, Any]) -> str:
    return canonical_digest(protocol)


def _check_interventions_and_estimand(
    protocol: dict[str, Any],
    findings: list[ProtocolPreflightFinding],
) -> None:
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    interventions_by_id: dict[str, dict[str, Any]] = {}
    control_count = 0
    allocation_total = Decimal(0)

    for index, intervention in enumerate(interventions):
        intervention_id = cast(str, intervention["intervention_id"])
        if intervention_id in interventions_by_id:
            findings.append(
                _finding(
                    "INTERVENTION_ID_DUPLICATE",
                    "protocol",
                    f"/interventions/{index}/intervention_id",
                    f"intervention_id {intervention_id!r} is declared more than once",
                )
            )
        else:
            interventions_by_id[intervention_id] = intervention

        if intervention["kind"] == "control":
            control_count += 1
        allocation = Decimal(cast(str, intervention["allocation"]))
        allocation_total += allocation
        if allocation <= 0:
            findings.append(
                _finding(
                    "INTERVENTION_ALLOCATION_NONPOSITIVE",
                    "protocol",
                    f"/interventions/{index}/allocation",
                    "each intervention must receive a positive allocation",
                )
            )

    if control_count != 1:
        findings.append(
            _finding(
                "CONTROL_COUNT_INVALID",
                "protocol",
                "/interventions",
                f"exactly one control intervention is required; found {control_count}",
            )
        )
    if allocation_total != Decimal(1):
        findings.append(
            _finding(
                "ALLOCATION_TOTAL_INVALID",
                "protocol",
                "/interventions",
                f"intervention allocations must sum to 1; found {allocation_total}",
            )
        )

    estimand = cast(dict[str, Any], protocol["estimand"])
    baseline_id = cast(str, estimand["baseline_intervention_id"])
    baseline = interventions_by_id.get(baseline_id)
    if baseline is None:
        findings.append(
            _finding(
                "ESTIMAND_BASELINE_UNKNOWN",
                "protocol",
                "/estimand/baseline_intervention_id",
                f"baseline intervention {baseline_id!r} is not declared",
            )
        )
    elif baseline["kind"] != "control":
        findings.append(
            _finding(
                "ESTIMAND_BASELINE_NOT_CONTROL",
                "protocol",
                "/estimand/baseline_intervention_id",
                "the estimand baseline must reference the control intervention",
            )
        )

    comparison_ids = cast(list[str], estimand["comparison_intervention_ids"])
    for index, comparison_id in enumerate(comparison_ids):
        comparison = interventions_by_id.get(comparison_id)
        pointer = f"/estimand/comparison_intervention_ids/{index}"
        if comparison is None:
            findings.append(
                _finding(
                    "ESTIMAND_COMPARISON_UNKNOWN",
                    "protocol",
                    pointer,
                    f"comparison intervention {comparison_id!r} is not declared",
                )
            )
        elif comparison["kind"] != "treatment":
            findings.append(
                _finding(
                    "ESTIMAND_COMPARISON_NOT_TREATMENT",
                    "protocol",
                    pointer,
                    "each estimand comparison must reference a treatment intervention",
                )
            )

    population = cast(dict[str, Any], protocol["population"])
    if estimand["population"] != population["analysis_population"]:
        findings.append(
            _finding(
                "ESTIMAND_POPULATION_MISMATCH",
                "protocol",
                "/estimand/population",
                "estimand population must match population.analysis_population",
            )
        )


def _check_metric_references(
    protocol: dict[str, Any],
    findings: list[ProtocolPreflightFinding],
) -> None:
    metrics = cast(dict[str, list[dict[str, Any]]], protocol["metrics"])
    first_reference: dict[str, tuple[str, str, str]] = {}
    declared_metric_ids: set[str] = set()

    for role in ("primary", "secondary", "guardrails"):
        for index, reference in enumerate(metrics[role]):
            metric_id = cast(str, reference["metric_id"])
            metric_version = cast(str, reference["metric_version"])
            definition_digest = cast(str, reference["definition_digest"])
            pointer = f"/metrics/{role}/{index}/metric_id"
            declared_metric_ids.add(metric_id)
            previous = first_reference.get(metric_id)
            if previous is None:
                first_reference[metric_id] = (role, metric_version, definition_digest)
                continue
            previous_role, previous_version, previous_digest = previous
            if (metric_version, definition_digest) != (previous_version, previous_digest):
                findings.append(
                    _finding(
                        "METRIC_REFERENCE_CONFLICT",
                        "protocol",
                        pointer,
                        f"metric {metric_id!r} has conflicting version or definition digest",
                    )
                )
            elif role == previous_role:
                findings.append(
                    _finding(
                        "METRIC_REFERENCE_DUPLICATE",
                        "protocol",
                        pointer,
                        f"metric {metric_id!r} is repeated in the {role} role",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "METRIC_ROLE_CONFLICT",
                        "protocol",
                        pointer,
                        f"metric {metric_id!r} appears in both {previous_role} and {role}",
                    )
                )

    analysis = cast(dict[str, Any], protocol["analysis"])
    multiplicity = cast(dict[str, Any], analysis["multiplicity"])
    family_ids = cast(list[str], multiplicity["family_ids"])
    multiplicity_method = cast(str, multiplicity["method"])
    if (multiplicity_method == "none" and family_ids) or (
        multiplicity_method != "none" and not family_ids
    ):
        findings.append(
            _finding(
                "MULTIPLICITY_POLICY_INCONSISTENT",
                "protocol",
                "/analysis/multiplicity/family_ids",
                "multiplicity method 'none' requires no family ids, while active methods require at least one",
            )
        )
    for index, metric_id in enumerate(family_ids):
        if metric_id not in declared_metric_ids:
            findings.append(
                _finding(
                    "MULTIPLICITY_METRIC_UNKNOWN",
                    "protocol",
                    f"/analysis/multiplicity/family_ids/{index}",
                    f"multiplicity family references undeclared metric {metric_id!r}",
                )
            )

    variance_reduction = cast(dict[str, Any], analysis["variance_reduction"])
    covariate_ids = cast(list[str], variance_reduction["covariate_metric_ids"])
    variance_reduction_method = cast(str, variance_reduction["method"])
    if (variance_reduction_method == "none" and covariate_ids) or (
        variance_reduction_method != "none" and not covariate_ids
    ):
        findings.append(
            _finding(
                "VARIANCE_REDUCTION_POLICY_INCONSISTENT",
                "protocol",
                "/analysis/variance_reduction/covariate_metric_ids",
                "variance-reduction method 'none' requires no covariates, while active methods require at least one",
            )
        )
    for index, metric_id in enumerate(covariate_ids):
        if metric_id not in declared_metric_ids:
            findings.append(
                _finding(
                    "COVARIATE_METRIC_UNKNOWN",
                    "protocol",
                    f"/analysis/variance_reduction/covariate_metric_ids/{index}",
                    f"variance-reduction policy references undeclared metric {metric_id!r}",
                )
            )

    guardrail_ids = {cast(str, reference["metric_id"]) for reference in metrics["guardrails"]}
    decision = cast(dict[str, Any], protocol["decision"])
    harm_rules = cast(list[dict[str, Any]], decision["harm_rules"])
    covered_guardrails: set[str] = set()
    for index, rule in enumerate(harm_rules):
        metric_id = cast(str, rule["metric_id"])
        pointer = f"/decision/harm_rules/{index}/metric_id"
        if metric_id not in declared_metric_ids:
            findings.append(
                _finding(
                    "HARM_RULE_METRIC_UNKNOWN",
                    "protocol",
                    pointer,
                    f"harm rule references undeclared metric {metric_id!r}",
                )
            )
        elif metric_id not in guardrail_ids:
            findings.append(
                _finding(
                    "HARM_RULE_METRIC_NOT_GUARDRAIL",
                    "protocol",
                    pointer,
                    f"harm rule metric {metric_id!r} is not declared as a guardrail",
                )
            )
        else:
            covered_guardrails.add(metric_id)

    for index, reference in enumerate(metrics["guardrails"]):
        metric_id = cast(str, reference["metric_id"])
        if metric_id not in covered_guardrails:
            findings.append(
                _finding(
                    "GUARDRAIL_POLICY_MISSING",
                    "protocol",
                    f"/metrics/guardrails/{index}/metric_id",
                    f"guardrail metric {metric_id!r} has no harm rule",
                )
            )

    operations = cast(dict[str, Any], protocol["operations"])
    alert_thresholds = cast(list[dict[str, Any]], operations["alert_thresholds"])
    for index, rule in enumerate(alert_thresholds):
        metric_id = cast(str, rule["metric_id"])
        if metric_id not in declared_metric_ids:
            findings.append(
                _finding(
                    "ALERT_THRESHOLD_METRIC_UNKNOWN",
                    "protocol",
                    f"/operations/alert_thresholds/{index}/metric_id",
                    f"alert threshold references undeclared metric {metric_id!r}",
                )
            )

    approval_policy = cast(dict[str, Any], decision["approval_policy"])
    roles = cast(list[str], approval_policy["roles"])
    minimum_approvals = cast(int, approval_policy["minimum_approvals"])
    if minimum_approvals > len(roles):
        findings.append(
            _finding(
                "APPROVAL_POLICY_UNSATISFIABLE",
                "protocol",
                "/decision/approval_policy/minimum_approvals",
                "minimum approvals cannot exceed the number of eligible approval roles",
            )
        )


def _check_telemetry(
    protocol: dict[str, Any],
    findings: list[ProtocolPreflightFinding],
) -> None:
    telemetry = cast(dict[str, Any], protocol["telemetry"])
    exposure_event = cast(str, telemetry["exposure_event"])
    outcome_events = cast(list[str], telemetry["outcome_events"])
    for index, event_type in enumerate(outcome_events):
        if event_type == exposure_event:
            findings.append(
                _finding(
                    "TELEMETRY_EVENT_ROLE_CONFLICT",
                    "telemetry",
                    f"/telemetry/outcome_events/{index}",
                    "the exposure event cannot also be an outcome event",
                )
            )

    event_key = cast(str, telemetry["event_key"])
    deduplication = cast(dict[str, Any], telemetry["deduplication"])
    deduplication_keys = cast(list[str], deduplication["keys"])
    if event_key not in deduplication_keys:
        findings.append(
            _finding(
                "TELEMETRY_DEDUP_EVENT_KEY_MISSING",
                "telemetry",
                "/telemetry/deduplication/keys",
                "deduplication keys must include telemetry.event_key",
            )
        )

    schema_versions = cast(list[dict[str, Any]], telemetry["schema_versions"])
    schema_event_types: set[str] = set()
    seen_versions: dict[tuple[str, str], str] = {}
    for index, schema in enumerate(schema_versions):
        event_type = cast(str, schema["event_type"])
        version = cast(str, schema["version"])
        schema_digest = cast(str, schema["schema_digest"])
        schema_event_types.add(event_type)
        key = (event_type, version)
        previous_digest = seen_versions.get(key)
        if previous_digest is None:
            seen_versions[key] = schema_digest
        elif previous_digest == schema_digest:
            findings.append(
                _finding(
                    "TELEMETRY_SCHEMA_VERSION_DUPLICATE",
                    "telemetry",
                    f"/telemetry/schema_versions/{index}",
                    f"schema version {event_type!r} {version!r} is declared more than once",
                )
            )
        else:
            findings.append(
                _finding(
                    "TELEMETRY_SCHEMA_VERSION_CONFLICT",
                    "telemetry",
                    f"/telemetry/schema_versions/{index}/schema_digest",
                    f"schema version {event_type!r} {version!r} has conflicting digests",
                )
            )

    if exposure_event not in schema_event_types:
        findings.append(
            _finding(
                "TELEMETRY_EVENT_SCHEMA_MISSING",
                "telemetry",
                "/telemetry/exposure_event",
                f"exposure event {exposure_event!r} has no declared schema version",
            )
        )
    for index, event_type in enumerate(outcome_events):
        if event_type not in schema_event_types:
            findings.append(
                _finding(
                    "TELEMETRY_EVENT_SCHEMA_MISSING",
                    "telemetry",
                    f"/telemetry/outcome_events/{index}",
                    f"outcome event {event_type!r} has no declared schema version",
                )
            )


def preflight_protocol(protocol: dict[str, Any]) -> ProtocolPreflightReport:
    """Run deterministic schema and completeness gates without reading events."""
    protocol_digest = _protocol_digest(protocol)
    schema_errors = schema_violations(protocol, PROTOCOL_SCHEMA_ID)
    if schema_errors:
        findings = tuple(
            _finding(
                "PROTOCOL_SCHEMA_INVALID",
                "protocol",
                pointer,
                message,
            )
            for pointer, message in schema_errors
        )
        return ProtocolPreflightReport(
            protocol_digest=protocol_digest,
            findings=findings,
        )

    findings_list: list[ProtocolPreflightFinding] = []
    _check_interventions_and_estimand(protocol, findings_list)
    _check_metric_references(protocol, findings_list)
    _check_telemetry(protocol, findings_list)
    findings_list.sort(key=lambda finding: (finding.json_pointer, finding.code))
    return ProtocolPreflightReport(
        protocol_digest=protocol_digest,
        findings=tuple(findings_list),
    )


def preflight_observed_telemetry(
    protocol: dict[str, Any],
    profile: ObservedTelemetryProfile,
) -> ProtocolPreflightReport:
    """Check aggregate observed telemetry against a complete frozen protocol."""
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        return protocol_report

    findings: list[ProtocolPreflightFinding] = []
    counters: tuple[tuple[int, FindingCode, str, str], ...] = (
        (
            profile.outcome_before_exposure_count,
            "TELEMETRY_OUTCOME_BEFORE_EXPOSURE",
            "/outcome_before_exposure_count",
            "outcome events were observed before exposure",
        ),
        (
            profile.duplicate_event_count,
            "TELEMETRY_DUPLICATE_EVENTS",
            "/duplicate_event_count",
            "duplicate events were observed after applying the protocol deduplication keys",
        ),
        (
            profile.unlinked_subject_count,
            "TELEMETRY_UNLINKED_SUBJECTS",
            "/unlinked_subject_count",
            "events were observed without a linkable subject",
        ),
    )
    for count, code, pointer, description in counters:
        if count > 0:
            findings.append(
                _finding(
                    code,
                    "telemetry",
                    pointer,
                    f"{description}; aggregate count is {count}",
                )
            )

    telemetry = cast(dict[str, Any], protocol["telemetry"])
    declared_versions = {
        (cast(str, schema["event_type"]), cast(str, schema["version"]))
        for schema in cast(list[dict[str, Any]], telemetry["schema_versions"])
    }
    for index, schema in enumerate(profile.schema_versions):
        if (schema.event_type, schema.version) not in declared_versions:
            findings.append(
                _finding(
                    "TELEMETRY_SCHEMA_VERSION_UNKNOWN",
                    "telemetry",
                    f"/schema_versions/{index}/version",
                    "observed event schema version is not declared by the protocol",
                )
            )

    if profile.events_beyond_max_lateness_count > 0:
        max_lateness = cast(str, telemetry["max_lateness"])
        findings.append(
            _finding(
                "TELEMETRY_MAX_LATENESS_EXCEEDED",
                "telemetry",
                "/events_beyond_max_lateness_count",
                "events exceeded protocol telemetry.max_lateness "
                f"{max_lateness!r}; aggregate count is "
                f"{profile.events_beyond_max_lateness_count}",
            )
        )

    findings.sort(key=lambda finding: (finding.json_pointer, finding.code))
    return ProtocolPreflightReport(
        protocol_digest=protocol_report.protocol_digest,
        findings=tuple(findings),
    )


def _probability_string(value: float) -> str:
    bounded = min(1.0, max(0.0, value))
    rendered = format(bounded, ".17f").rstrip("0").rstrip(".")
    return rendered or "0"


def _ks_uniformity_p_value(p_values: tuple[float, ...]) -> float:
    """Return the standard finite-sample-corrected KS survival approximation."""
    ordered = sorted(p_values)
    count = len(ordered)
    d_plus = max(
        (index + 1) / count - value for index, value in enumerate(ordered)
    )
    d_minus = max(
        value - index / count for index, value in enumerate(ordered)
    )
    statistic = max(d_plus, d_minus)
    root_count = math.sqrt(count)
    scaled = (root_count + 0.12 + 0.11 / root_count) * statistic
    survival = 0.0
    for term_index in range(1, 101):
        term = math.exp(-2.0 * term_index * term_index * scaled * scaled)
        survival += term if term_index % 2 else -term
        if term < 1e-15:
            break
    return min(1.0, max(0.0, 2.0 * survival))


def _permutation_p_values(
    aggregate: SimulatedAaBinaryAggregate,
    *,
    generator: np.random.Generator,
    simulation_count: int,
) -> tuple[float, ...]:
    total_users = aggregate.control_users + aggregate.treatment_users
    total_conversions = (
        aggregate.control_conversions + aggregate.treatment_conversions
    )
    pooled_rate = total_conversions / total_users
    standard_error = math.sqrt(
        pooled_rate
        * (1.0 - pooled_rate)
        * (1.0 / aggregate.control_users + 1.0 / aggregate.treatment_users)
    )
    if standard_error == 0.0:
        return (1.0,) * simulation_count

    treatment_draws = cast(
        list[int],
        generator.hypergeometric(
            total_conversions,
            total_users - total_conversions,
            aggregate.treatment_users,
            size=simulation_count,
        ).tolist(),
    )
    tie_breakers = cast(
        list[float],
        generator.uniform(-0.5, 0.5, size=simulation_count).tolist(),
    )
    p_values: list[float] = []
    for treatment_conversions, tie_breaker in zip(
        treatment_draws,
        tie_breakers,
        strict=True,
    ):
        randomized_treatment = treatment_conversions + tie_breaker
        randomized_control = total_conversions - randomized_treatment
        effect = (
            randomized_treatment / aggregate.treatment_users
            - randomized_control / aggregate.control_users
        )
        p_values.append(math.erfc(abs(effect / standard_error) / math.sqrt(2.0)))
    return tuple(p_values)


def simulate_aa_profile(
    protocol: dict[str, Any],
    aggregates: tuple[SimulatedAaBinaryAggregate, ...],
    *,
    simulation_count: int = _DEFAULT_AA_SIMULATION_COUNT,
) -> SimulatedAaProfile:
    """Generate content-bound null p-values by permuting binary arm aggregates."""
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        raise ValueError("simulated A/A requires a valid frozen protocol")
    if simulation_count < _MIN_AA_SIMULATION_COUNT:
        raise ValueError(
            "simulated A/A requires at least "
            f"{_MIN_AA_SIMULATION_COUNT} permutations"
        )
    if simulation_count > _MAX_SAFE_INTEGER:
        raise ValueError("simulated A/A permutation count exceeds the safe limit")

    analysis = cast(dict[str, Any], protocol["analysis"])
    if "random_seed" not in analysis:
        raise ValueError(
            "frozen protocol analysis.random_seed is required for simulated A/A"
        )
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    if len(interventions) != 2:
        raise ValueError("simulated A/A requires exactly two interventions")

    metrics = cast(dict[str, list[dict[str, Any]]], protocol["metrics"])
    expected_metrics = tuple(
        (
            cast(str, metric["metric_id"]),
            cast(str, metric["metric_version"]),
            cast(str, metric["definition_digest"]),
        )
        for role in ("primary", "secondary", "guardrails")
        for metric in metrics[role]
    )
    actual_metrics = tuple(
        (
            aggregate.metric_id,
            aggregate.metric_version,
            aggregate.definition_digest,
        )
        for aggregate in aggregates
    )
    if actual_metrics != expected_metrics:
        raise ValueError(
            "simulated A/A aggregate declarations do not match frozen protocol"
        )

    random_seed = cast(int, analysis["random_seed"])
    generator = np.random.Generator(np.random.PCG64(random_seed))
    calibrations: list[SimulatedAaMetricCalibration] = []
    for aggregate in aggregates:
        p_values = _permutation_p_values(
            aggregate,
            generator=generator,
            simulation_count=simulation_count,
        )
        serialized_p_values = tuple(
            _probability_string(value) for value in p_values
        )
        calibrations.append(
            SimulatedAaMetricCalibration(
                metric_id=aggregate.metric_id,
                metric_version=aggregate.metric_version,
                definition_digest=aggregate.definition_digest,
                calibration_source="internal_permutation",
                simulated_p_value_count=simulation_count,
                simulated_p_values_digest=canonical_digest(serialized_p_values),
                uniformity_p_value=_probability_string(
                    _ks_uniformity_p_value(p_values)
                ),
            )
        )

    method = cast(dict[str, Any], analysis["method"])
    profile = SimulatedAaProfile(
        random_seed=random_seed,
        analysis_method=SimulatedAaAnalysisMethod(
            method_id=cast(str, method["method_id"]),
            method_version=cast(str, method["method_version"]),
        ),
        allocations=tuple(
            SimulatedAaAllocation(
                intervention_id=cast(str, intervention["intervention_id"]),
                allocation=cast(str, intervention["allocation"]),
                namespace=cast(str, intervention["namespace"]),
                hash_version=cast(str, intervention["hash_version"]),
            )
            for intervention in interventions
        ),
        metric_calibrations=tuple(calibrations),
    )
    _validate_simulated_aa_bindings(protocol, profile)
    return profile


def _validate_simulated_aa_bindings(
    protocol: dict[str, Any],
    profile: SimulatedAaProfile,
) -> None:
    analysis = cast(dict[str, Any], protocol["analysis"])
    method = cast(dict[str, Any], analysis["method"])
    expected_method = (
        cast(str, method["method_id"]),
        cast(str, method["method_version"]),
    )
    actual_method = (
        profile.analysis_method.method_id,
        profile.analysis_method.method_version,
    )
    if actual_method != expected_method:
        raise ValueError(
            "simulated A/A analysis method does not match frozen protocol"
        )
    if "random_seed" not in analysis:
        raise ValueError(
            "frozen protocol analysis.random_seed is required for simulated A/A"
        )
    if profile.random_seed != analysis["random_seed"]:
        raise ValueError("simulated A/A random seed does not match frozen protocol")

    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    expected_allocations = tuple(
        (
            cast(str, intervention["intervention_id"]),
            cast(str, intervention["allocation"]),
            cast(str, intervention["namespace"]),
            cast(str, intervention["hash_version"]),
        )
        for intervention in interventions
    )
    actual_allocations = tuple(
        (
            allocation.intervention_id,
            allocation.allocation,
            allocation.namespace,
            allocation.hash_version,
        )
        for allocation in profile.allocations
    )
    if actual_allocations != expected_allocations:
        raise ValueError(
            "simulated A/A allocations do not match frozen protocol"
        )

    metrics = cast(dict[str, list[dict[str, Any]]], protocol["metrics"])
    expected_metrics = tuple(
        (
            cast(str, metric["metric_id"]),
            cast(str, metric["metric_version"]),
            cast(str, metric["definition_digest"]),
        )
        for role in ("primary", "secondary", "guardrails")
        for metric in metrics[role]
    )
    actual_metrics = tuple(
        (
            calibration.metric_id,
            calibration.metric_version,
            calibration.definition_digest,
        )
        for calibration in profile.metric_calibrations
    )
    if actual_metrics != expected_metrics:
        raise ValueError(
            "simulated A/A metric declarations do not match frozen protocol"
        )


def preflight_simulated_aa(
    protocol: dict[str, Any],
    profile: SimulatedAaProfile,
) -> ProtocolPreflightReport:
    """Check aggregate simulated-null p-value uniformity for frozen metrics."""
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        return protocol_report

    _validate_simulated_aa_bindings(protocol, profile)
    findings: list[ProtocolPreflightFinding] = []
    for index, calibration in enumerate(profile.metric_calibrations):
        if Decimal(calibration.uniformity_p_value) < _AA_CALIBRATION_THRESHOLD:
            code: FindingCode = (
                "AA_CALIBRATION_FAILED"
                if calibration.calibration_source == "internal_permutation"
                else "AA_CALIBRATION_ASSERTED_FAILED"
            )
            findings.append(
                _finding(
                    code,
                    "statistics",
                    f"/metric_calibrations/{index}/uniformity_p_value",
                    "simulated A/A p-values failed KS uniformity calibration at "
                    f"the protocol-independent threshold "
                    f"{str(_AA_CALIBRATION_THRESHOLD)!r}; "
                    f"{calibration.calibration_source} uniformity p-value is "
                    f"{calibration.uniformity_p_value!r} over "
                    f"{calibration.simulated_p_value_count} permutations",
                )
            )

    findings.sort(key=lambda finding: (finding.json_pointer, finding.code))
    return ProtocolPreflightReport(
        protocol_digest=protocol_report.protocol_digest,
        findings=tuple(findings),
    )


def _historical_binary_outcomes(
    adapter: DuckDbFileAdapter,
    *,
    relation: str,
    metric: EmpiricalPowerBinaryMetricSource,
    max_scan_rows: int,
) -> tuple[tuple[int, ...], QueryProvenance]:
    column = metric.outcome_column
    result = adapter.execute(
        AggregateQuery(
            statement=(
                f"SELECT {column} FROM {relation} "
                f"WHERE {column} IS NOT NULL ORDER BY {column}"
            ),
            budget=QueryBudget(
                max_scan_rows=max_scan_rows,
                timeout_ms=30_000,
                max_result_rows=max_scan_rows,
            ),
        )
    )
    outcomes: list[int] = []
    for row in result.rows:
        value: QueryValue = row[0]
        if isinstance(value, bool):
            outcomes.append(int(value))
        elif isinstance(value, (int, float)) and value in (0, 1):
            outcomes.append(int(value))
        else:
            raise ValueError(
                f"historical metric {metric.metric_id!r} must contain only 0/1 outcomes"
            )
    if len(outcomes) < 20:
        raise ValueError(
            f"historical metric {metric.metric_id!r} requires at least 20 outcomes"
        )
    if not 0 < sum(outcomes) < len(outcomes):
        raise ValueError(
            f"historical metric {metric.metric_id!r} requires both outcome classes"
        )
    return tuple(outcomes), result.provenance


def _binary_allocation_weights(protocol: dict[str, Any]) -> tuple[float, float]:
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    controls = [item for item in interventions if item["kind"] == "control"]
    treatments = [item for item in interventions if item["kind"] == "treatment"]
    if len(controls) != 1 or len(treatments) != 1:
        raise ValueError(
            "empirical binary power requires one control and one treatment"
        )
    return (
        float(Decimal(cast(str, controls[0]["allocation"]))),
        float(Decimal(cast(str, treatments[0]["allocation"]))),
    )


def _binary_arm_sizes(
    total_sample_size: int,
    allocation_weights: tuple[float, float],
) -> tuple[int, int]:
    control_weight, _ = allocation_weights
    control_users = min(
        total_sample_size - 2,
        max(2, round(total_sample_size * control_weight)),
    )
    return control_users, total_sample_size - control_users


def _approximate_binary_power(
    *,
    baseline_rate: float,
    effect: float,
    alpha: float,
    total_sample_size: int,
    allocation_weights: tuple[float, float],
) -> float:
    control_users, treatment_users = _binary_arm_sizes(
        total_sample_size,
        allocation_weights,
    )
    treatment_rate = baseline_rate + effect
    if not 0.0 <= treatment_rate <= 1.0:
        raise ValueError(
            "minimum worthwhile effect is outside the historical binary support"
        )
    pooled_rate = (
        control_users * baseline_rate + treatment_users * treatment_rate
    ) / total_sample_size
    null_standard_error = math.sqrt(
        pooled_rate
        * (1.0 - pooled_rate)
        * (1.0 / control_users + 1.0 / treatment_users)
    )
    if null_standard_error == 0.0:
        return 0.0
    alternative_standard_error = math.sqrt(
        baseline_rate * (1.0 - baseline_rate) / control_users
        + treatment_rate * (1.0 - treatment_rate) / treatment_users
    )
    mean_z = effect / null_standard_error
    critical = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    if alternative_standard_error == 0.0:
        return float(abs(mean_z) >= critical)
    distribution = NormalDist(
        mean_z,
        alternative_standard_error / null_standard_error,
    )
    # Both tails come from the CDF's stable direction: the lower one directly, the
    # upper one through the standardized complement, so neither subtracts a
    # probability that has already rounded to 1.0.
    standardized_upper = (critical - distribution.mean) / distribution.stdev
    return distribution.cdf(-critical) + standard_normal_sf(standardized_upper)


def _bootstrap_binary_power(
    outcomes: tuple[int, ...],
    *,
    effect: float,
    alpha: float,
    total_sample_size: int,
    allocation_weights: tuple[float, float],
    generator: np.random.Generator,
    simulation_count: int,
) -> float:
    control_users, treatment_users = _binary_arm_sizes(
        total_sample_size,
        allocation_weights,
    )
    historical_rate = sum(outcomes) / len(outcomes)
    bootstrap_rates = (
        generator.binomial(
            len(outcomes),
            historical_rate,
            size=simulation_count,
        )
        / len(outcomes)
    )
    treatment_rates = np.clip(bootstrap_rates + effect, 0.0, 1.0)
    control_conversions = generator.binomial(control_users, bootstrap_rates)
    treatment_conversions = generator.binomial(
        treatment_users,
        treatment_rates,
    )
    pooled_rates = (
        control_conversions + treatment_conversions
    ) / total_sample_size
    standard_errors = np.sqrt(
        pooled_rates
        * (1.0 - pooled_rates)
        * (1.0 / control_users + 1.0 / treatment_users)
    )
    effects = (
        treatment_conversions / treatment_users
        - control_conversions / control_users
    )
    test_statistics = np.divide(
        effects,
        standard_errors,
        out=np.zeros_like(effects, dtype=float),
        where=standard_errors > 0.0,
    )
    critical = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    return float(np.mean(np.abs(test_statistics) >= critical))


def _recommended_binary_total_sample_size(
    *,
    baseline_rate: float,
    effect: float,
    alpha: float,
    target_power: float,
    allocation_weights: tuple[float, float],
) -> int:
    control_weight, treatment_weight = allocation_weights
    low = max(
        4,
        math.ceil(2.0 / control_weight),
        math.ceil(2.0 / treatment_weight),
    )
    high = low
    while (
        _approximate_binary_power(
            baseline_rate=baseline_rate,
            effect=effect,
            alpha=alpha,
            total_sample_size=high,
            allocation_weights=allocation_weights,
        )
        < target_power
    ):
        if high >= 1_000_000_000:
            raise ValueError("empirical power recommendation exceeds the safe limit")
        high = min(1_000_000_000, high * 2)
    while low < high:
        middle = (low + high) // 2
        if (
            _approximate_binary_power(
                baseline_rate=baseline_rate,
                effect=effect,
                alpha=alpha,
                total_sample_size=middle,
                allocation_weights=allocation_weights,
            )
            >= target_power
        ):
            high = middle
        else:
            low = middle + 1
    return low


def _detectable_binary_effect(
    *,
    baseline_rate: float,
    effect_direction: float,
    alpha: float,
    target_power: float,
    total_sample_size: int,
    allocation_weights: tuple[float, float],
) -> float:
    direction = 1.0 if effect_direction > 0.0 else -1.0
    low = 0.0
    high = 1.0 - baseline_rate if direction > 0.0 else baseline_rate
    for _ in range(64):
        middle = (low + high) / 2.0
        if (
            _approximate_binary_power(
                baseline_rate=baseline_rate,
                effect=direction * middle,
                alpha=alpha,
                total_sample_size=total_sample_size,
                allocation_weights=allocation_weights,
            )
            >= target_power
        ):
            high = middle
        else:
            low = middle
    return direction * high


def _decimal_number_string(value: float) -> str:
    rendered = format(value, ".17f").rstrip("0").rstrip(".")
    return rendered if rendered not in {"", "-0"} else "0"


def simulate_empirical_power_profile(
    protocol: dict[str, Any],
    source: Path | str,
    *,
    relation: str,
    source_ref: str,
    metrics: tuple[EmpiricalPowerBinaryMetricSource, ...],
    simulation_count: int = _DEFAULT_POWER_SIMULATION_COUNT,
) -> EmpiricalPowerProfile:
    """Bootstrap binary power from a bounded historical DuckDB file source."""
    if isinstance(simulation_count, bool) or not isinstance(simulation_count, int):
        raise ValueError("empirical power simulation count must be an integer")
    if not _MIN_POWER_SIMULATION_COUNT <= simulation_count <= _MAX_INTERNAL_SIMULATION_COUNT:
        raise ValueError(
            "empirical power requires between "
            f"{_MIN_POWER_SIMULATION_COUNT} and "
            f"{_MAX_INTERNAL_SIMULATION_COUNT} bootstrap simulations"
        )
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        raise ValueError("empirical power requires a valid frozen protocol")

    analysis = cast(dict[str, Any], protocol["analysis"])
    if "random_seed" not in analysis:
        raise ValueError(
            "frozen protocol analysis.random_seed is required for empirical power"
        )
    expected_metrics = tuple(
        (
            cast(str, metric["metric_id"]),
            cast(str, metric["metric_version"]),
            cast(str, metric["definition_digest"]),
        )
        for role in ("primary", "secondary", "guardrails")
        for metric in cast(dict[str, list[dict[str, Any]]], protocol["metrics"])[
            role
        ]
    )
    actual_metrics = tuple(
        (metric.metric_id, metric.metric_version, metric.definition_digest)
        for metric in metrics
    )
    if actual_metrics != expected_metrics:
        raise ValueError(
            "empirical power historical metrics do not match frozen protocol"
        )

    adapter = DuckDbFileAdapter(
        path=source,
        relation=relation,
        source_ref=source_ref,
    )
    inspection = adapter.introspect()
    if inspection.estimated_rows > 10_000:
        raise ValueError("empirical power historical source exceeds 10000 rows")
    available_columns = {column.name for column in inspection.columns}
    missing_columns = [
        metric.outcome_column
        for metric in metrics
        if metric.outcome_column not in available_columns
    ]
    if missing_columns:
        raise ValueError(
            f"empirical power historical column is missing: {missing_columns[0]!r}"
        )

    random_seed = cast(int, analysis["random_seed"])
    generator = np.random.Generator(np.random.PCG64(random_seed))
    alpha = float(cast(str, analysis["alpha"]))
    target_power = float(cast(str, analysis["power"]))
    decision = cast(dict[str, Any], protocol["decision"])
    minimum_effect = float(decision["minimum_worthwhile_effect"])
    if minimum_effect == 0.0:
        raise ValueError(
            "empirical power requires a non-zero minimum worthwhile effect"
        )
    allocation_weights = _binary_allocation_weights(protocol)
    results: list[EmpiricalPowerMetricResult] = []
    for metric in metrics:
        outcomes, provenance = _historical_binary_outcomes(
            adapter,
            relation=relation,
            metric=metric,
            max_scan_rows=inspection.estimated_rows,
        )
        if provenance.source_fingerprint != inspection.fingerprint:
            raise ValueError(
                "empirical power historical source changed after inspection"
            )
        baseline_rate = sum(outcomes) / len(outcomes)
        achieved_power = _bootstrap_binary_power(
            outcomes,
            effect=minimum_effect,
            alpha=alpha,
            total_sample_size=metric.evaluated_total_sample_size,
            allocation_weights=allocation_weights,
            generator=generator,
            simulation_count=simulation_count,
        )
        recommended_total = _recommended_binary_total_sample_size(
            baseline_rate=baseline_rate,
            effect=minimum_effect,
            alpha=alpha,
            target_power=target_power,
            allocation_weights=allocation_weights,
        )
        detectable_effect = _detectable_binary_effect(
            baseline_rate=baseline_rate,
            effect_direction=minimum_effect,
            alpha=alpha,
            target_power=target_power,
            total_sample_size=metric.evaluated_total_sample_size,
            allocation_weights=allocation_weights,
        )
        results.append(
            EmpiricalPowerMetricResult(
                metric_id=metric.metric_id,
                metric_version=metric.metric_version,
                definition_digest=metric.definition_digest,
                power_source="internal_bootstrap",
                historical_distribution_digest=canonical_digest(
                    {
                        "outcome_counts": {
                            "0": len(outcomes) - sum(outcomes),
                            "1": sum(outcomes),
                        },
                        "query_id": provenance.query_id,
                    }
                ),
                simulation_count=simulation_count,
                evaluated_total_sample_size=metric.evaluated_total_sample_size,
                achieved_power=_probability_string(achieved_power),
                detectable_effect_at_evaluated_total_sample_size=(
                    _decimal_number_string(detectable_effect)
                ),
                recommended_total_sample_size=recommended_total,
            )
        )

    method = cast(dict[str, Any], analysis["method"])
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    profile = EmpiricalPowerProfile(
        protocol_digest=protocol_report.protocol_digest,
        random_seed=random_seed,
        analysis_method=SimulatedAaAnalysisMethod(
            method_id=cast(str, method["method_id"]),
            method_version=cast(str, method["method_version"]),
        ),
        target_power=cast(str, analysis["power"]),
        minimum_worthwhile_effect=str(decision["minimum_worthwhile_effect"]),
        allocations=tuple(
            SimulatedAaAllocation(
                intervention_id=cast(str, intervention["intervention_id"]),
                allocation=cast(str, intervention["allocation"]),
                namespace=cast(str, intervention["namespace"]),
                hash_version=cast(str, intervention["hash_version"]),
            )
            for intervention in interventions
        ),
        metric_results=tuple(results),
    )
    _validate_empirical_power_bindings(
        protocol,
        profile,
        protocol_report.protocol_digest,
    )
    return profile


def _validate_empirical_power_bindings(
    protocol: dict[str, Any],
    profile: EmpiricalPowerProfile,
    protocol_digest: str,
) -> None:
    analysis = cast(dict[str, Any], protocol["analysis"])
    if "random_seed" not in analysis:
        raise ValueError(
            "frozen protocol analysis.random_seed is required for empirical power"
        )
    if profile.protocol_digest != protocol_digest:
        raise ValueError(
            "empirical power protocol digest does not match frozen protocol"
        )

    method = cast(dict[str, Any], analysis["method"])
    expected_method = (
        cast(str, method["method_id"]),
        cast(str, method["method_version"]),
    )
    actual_method = (
        profile.analysis_method.method_id,
        profile.analysis_method.method_version,
    )
    if actual_method != expected_method:
        raise ValueError(
            "empirical power analysis method does not match frozen protocol"
        )
    if profile.random_seed != analysis["random_seed"]:
        raise ValueError(
            "empirical power random seed does not match frozen protocol"
        )
    if profile.target_power != analysis["power"]:
        raise ValueError(
            "empirical power target does not match frozen protocol"
        )

    decision = cast(dict[str, Any], protocol["decision"])
    expected_effect = Decimal(str(decision["minimum_worthwhile_effect"]))
    if Decimal(profile.minimum_worthwhile_effect) != expected_effect:
        raise ValueError(
            "empirical power minimum worthwhile effect does not match frozen protocol"
        )

    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    expected_allocations = tuple(
        (
            cast(str, intervention["intervention_id"]),
            cast(str, intervention["allocation"]),
            cast(str, intervention["namespace"]),
            cast(str, intervention["hash_version"]),
        )
        for intervention in interventions
    )
    actual_allocations = tuple(
        (
            allocation.intervention_id,
            allocation.allocation,
            allocation.namespace,
            allocation.hash_version,
        )
        for allocation in profile.allocations
    )
    if actual_allocations != expected_allocations:
        raise ValueError(
            "empirical power allocation binding does not match frozen protocol"
        )

    metrics = cast(dict[str, list[dict[str, Any]]], protocol["metrics"])
    expected_metrics = tuple(
        (
            cast(str, metric["metric_id"]),
            cast(str, metric["metric_version"]),
            cast(str, metric["definition_digest"]),
        )
        for role in ("primary", "secondary", "guardrails")
        for metric in metrics[role]
    )
    actual_metrics = tuple(
        (
            result.metric_id,
            result.metric_version,
            result.definition_digest,
        )
        for result in profile.metric_results
    )
    if actual_metrics != expected_metrics:
        raise ValueError(
            "empirical power metric binding does not match frozen protocol"
        )

    target_power = Decimal(profile.target_power)
    minimum_effect = abs(Decimal(profile.minimum_worthwhile_effect))
    for result in profile.metric_results:
        if result.power_source == "internal_bootstrap":
            continue
        below_target = Decimal(result.achieved_power) < target_power
        recommends_more_units = (
            result.recommended_total_sample_size
            > result.evaluated_total_sample_size
        )
        detectable_effect_exceeds_minimum = (
            abs(
                Decimal(
                    result.detectable_effect_at_evaluated_total_sample_size
                )
            )
            > minimum_effect
        )
        if not (
            below_target
            == recommends_more_units
            == detectable_effect_exceeds_minimum
        ):
            raise ValueError(
                "empirical power remediation evidence is inconsistent with "
                "achieved power and the frozen target"
            )


def preflight_empirical_power(
    protocol: dict[str, Any],
    profile: EmpiricalPowerProfile,
) -> ProtocolPreflightReport:
    """Evaluate content-bound bootstrap or asserted power for a frozen protocol."""
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        return protocol_report

    _validate_empirical_power_bindings(
        protocol,
        profile,
        protocol_report.protocol_digest,
    )
    target_power = Decimal(profile.target_power)
    findings: list[ProtocolPreflightFinding] = []
    for index, result in enumerate(profile.metric_results):
        if Decimal(result.achieved_power) < target_power:
            findings.append(
                _finding(
                    "EMPIRICAL_POWER_BELOW_TARGET",
                    "statistics",
                    f"/metric_results/{index}/achieved_power",
                    "empirical power at frozen minimum worthwhile effect "
                    f"{profile.minimum_worthwhile_effect!r} is below protocol "
                    f"target {profile.target_power!r}; {result.power_source} "
                    f"achieved power is {result.achieved_power!r} over "
                    f"{result.simulation_count} simulations at evaluated total "
                    f"sample size {result.evaluated_total_sample_size}; detectable "
                    "effect "
                    f"{result.detectable_effect_at_evaluated_total_sample_size} "
                    "at that total size and protocol target; recommended total "
                    f"sample size {result.recommended_total_sample_size}",
                )
            )

    findings.sort(key=lambda finding: (finding.json_pointer, finding.code))
    return ProtocolPreflightReport(
        protocol_digest=protocol_report.protocol_digest,
        findings=tuple(findings),
    )


def _resolve_assignment_hash_version(protocol: dict[str, Any]) -> int:
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    versions = tuple(
        cast(str, intervention["hash_version"])
        for intervention in interventions
    )
    unsupported = sorted(
        set(versions).difference(_ASSIGNMENT_HASH_VERSIONS)
    )
    if unsupported:
        raise ValueError(
            "frozen protocol uses unsupported assignment hash_version "
            f"{unsupported[0]!r}; expected 'assignment_v1' or 'assignment_v2'"
        )
    if len(set(versions)) != 1:
        raise ValueError(
            "frozen protocol uses mixed assignment hash versions; all ordered "
            "interventions must use the same version"
        )
    return _ASSIGNMENT_HASH_VERSIONS[versions[0]]


def _validate_assignment_health_bindings(
    protocol: dict[str, Any],
    profile: AssignmentHealthProfile,
    protocol_digest: str,
) -> int:
    if profile.protocol_digest != protocol_digest:
        raise ValueError(
            "assignment health protocol digest does not match frozen protocol"
        )

    analysis = cast(dict[str, Any], protocol["analysis"])
    if "random_seed" not in analysis:
        raise ValueError(
            "frozen protocol analysis.random_seed is required for assignment health"
        )
    if profile.random_seed != analysis["random_seed"]:
        raise ValueError(
            "assignment health random seed does not match frozen protocol"
        )

    hash_version = _resolve_assignment_hash_version(protocol)
    interventions = cast(list[dict[str, Any]], protocol["interventions"])
    expected_bindings = tuple(
        (
            cast(str, intervention["intervention_id"]),
            cast(str, intervention["allocation"]),
            cast(str, intervention["namespace"]),
            cast(str, intervention["hash_version"]),
        )
        for intervention in interventions
    )
    actual_bindings = tuple(
        (
            intervention.intervention_id,
            intervention.allocation,
            intervention.namespace,
            intervention.hash_version,
        )
        for intervention in profile.interventions
    )
    if actual_bindings != expected_bindings:
        raise ValueError(
            "assignment health intervention binding does not match frozen protocol"
        )
    return hash_version


def _preview_assignment_counts(
    profile: AssignmentHealthProfile,
    hash_version: int,
) -> list[int]:
    distribution = cast(
        list[dict[str, Any]],
        preview_assignment_distribution(
            seed=str(profile.random_seed),
            num_variations=len(profile.interventions),
            coverage=1.0,
            weights=[
                float(Decimal(intervention.allocation))
                for intervention in profile.interventions
            ],
            sample_size=profile.synthetic_sample_size,
            user_id_prefix="assignment-health-",
            hash_version=hash_version,
        )["distribution"],
    )
    counts = [0] * len(profile.interventions)
    for entry in distribution:
        counts[cast(int, entry["variation_index"])] = cast(
            int,
            entry["count"],
        )
    return counts


def preflight_assignment_health(
    protocol: dict[str, Any],
    profile: AssignmentHealthProfile,
) -> ProtocolPreflightReport:
    """Check deterministic synthetic balance and aggregate observed ratios."""
    protocol_report = preflight_protocol(protocol)
    if not protocol_report.ready:
        return protocol_report

    hash_version = _validate_assignment_health_bindings(
        protocol,
        profile,
        protocol_report.protocol_digest,
    )
    expected_fractions = [
        float(Decimal(intervention.allocation))
        for intervention in profile.interventions
    ]
    synthetic_counts = _preview_assignment_counts(profile, hash_version)
    _, synthetic_p_value, synthetic_failed = chi_square_srm(
        observed_counts=synthetic_counts,
        expected_fractions=expected_fractions,
    )
    observed_counts = [
        intervention.observed_count for intervention in profile.interventions
    ]
    _, observed_p_value, observed_failed = chi_square_srm(
        observed_counts=observed_counts,
        expected_fractions=expected_fractions,
    )

    findings: list[ProtocolPreflightFinding] = []
    if synthetic_failed:
        findings.append(
            _finding(
                "ASSIGNMENT_SYNTHETIC_BALANCE_FAILED",
                "statistics",
                "/synthetic_sample_size",
                "deterministic synthetic assignment balance failed the existing "
                "chi-square SRM threshold; aggregate synthetic sample size is "
                f"{profile.synthetic_sample_size} and p-value is "
                f"{synthetic_p_value:.12g}",
            )
        )
    if observed_failed:
        findings.append(
            _finding(
                "ASSIGNMENT_SAMPLE_RATIO_MISMATCH",
                "statistics",
                "/interventions",
                "observed aggregate intervention counts failed the existing "
                "chi-square SRM threshold; aggregate observed total is "
                f"{sum(observed_counts)} and p-value is {observed_p_value:.12g}",
            )
        )

    findings.sort(key=lambda finding: (finding.json_pointer, finding.code))
    return ProtocolPreflightReport(
        protocol_digest=protocol_report.protocol_digest,
        findings=tuple(findings),
    )
