from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.evidence._common import canonical_digest
from app.backend.app.evidence.abx import (
    ABX_VERSION,
    PROTOCOL_SCHEMA_ID,
    AbxError,
    canonical_json_bytes,
    validate_abx_document,
)
from app.backend.app.schemas.api._experiment import ExperimentInput, MetricsConfig

MetricRole = Literal["primary", "secondary", "guardrail", "covariate"]
ThresholdOperator = Literal["lt", "lte", "gt", "gte"]


class LegacyConversionError(ValueError):
    """Raised when a legacy project has no unambiguous ABX representation."""


class LegacyEventSchemaContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1)
    version: str = Field(min_length=1)
    schema_digest: str = Field(min_length=1)


class LegacyTelemetryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_key: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    occurred_at_key: str = Field(min_length=1)
    exposure_event: str = Field(min_length=1)
    outcome_events: list[str] = Field(min_length=1)
    ordering: Literal["event_time", "ingest_time"]
    deduplication_keys: list[str] = Field(min_length=1)
    deduplication_window: str = Field(min_length=1)
    max_lateness: str = Field(min_length=1)
    schema_versions: list[LegacyEventSchemaContext] = Field(min_length=1)


class LegacyThresholdContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    operator: ThresholdOperator
    threshold: float


class LegacyProtocolContext(BaseModel):
    """Caller-owned semantics that do not exist in ``ExperimentInput``."""

    model_config = ConfigDict(extra="forbid")

    source_project_id: str = Field(min_length=1)
    owners: list[str] = Field(min_length=1)
    created_at: str = Field(min_length=1)
    frozen_by: str = Field(min_length=1)
    frozen_at: str = Field(min_length=1)
    intervention_labels: list[str] = Field(min_length=2)
    assignment_namespace: str | None = Field(default=None, min_length=1)
    assignment_hash_version: str = Field(min_length=1)
    trigger_expression: str = Field(min_length=1)
    analysis_population: Literal["intention_to_treat", "per_protocol", "exposed"]
    horizon: str = Field(min_length=1)
    missing_data_rule: Literal["exclude", "zero", "censor", "model"]
    exposure_semantics: str = Field(min_length=1)
    analysis_method_version: str = Field(min_length=1)
    multiplicity_method: Literal["none", "holm", "benjamini_hochberg", "dunnett"]
    multiplicity_family_metric_names: list[str]
    cuped_covariate_metric_name: str | None = Field(default=None, min_length=1)
    telemetry: LegacyTelemetryContext
    decision_owners: list[str] = Field(min_length=1)
    approval_roles: list[str] = Field(min_length=1)
    minimum_approvals: int = Field(ge=1, le=32)
    rollback_owner: str = Field(min_length=1)
    lag_budget_seconds: int = Field(ge=0, le=31_536_000)
    alert_thresholds: list[LegacyThresholdContext]

    @model_validator(mode="after")
    def validate_explicit_policies(self) -> LegacyProtocolContext:
        if self.multiplicity_method == "none" and self.multiplicity_family_metric_names:
            raise ValueError("multiplicity family must be empty when the method is none")
        if self.multiplicity_method != "none" and not self.multiplicity_family_metric_names:
            raise ValueError("multiplicity family is required when a correction method is selected")
        if self.minimum_approvals > len(self.approval_roles):
            raise ValueError("minimum approvals cannot exceed the number of approval roles")
        return self


@dataclass(frozen=True)
class _MetricRecord:
    name: str
    role: MetricRole
    metric_id: str
    definition_digest: str
    definition: dict[str, Any]

    def reference(self) -> dict[str, str]:
        return {
            "metric_id": self.metric_id,
            "metric_version": "legacy-v1",
            "definition_digest": self.definition_digest,
        }

    def extension_entry(self) -> dict[str, Any]:
        return {**self.reference(), "definition": self.definition}


def _digest(value: Any) -> str:
    return canonical_digest(value)


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{_digest(value)[7:31]}"


def _metric_record(name: str, kind: str, role: MetricRole, **details: Any) -> _MetricRecord:
    clean_name = name.strip()
    if not clean_name:
        raise LegacyConversionError(f"{role} metric name must not be empty")
    definition: dict[str, Any] = {"kind": kind, "name": clean_name, "role": role}
    definition.update(details)
    definition_digest = _digest(definition)
    return _MetricRecord(
        name=clean_name,
        role=role,
        metric_id=f"metric_{definition_digest[7:31]}",
        definition_digest=definition_digest,
        definition=definition,
    )


def _metric_records(metrics: MetricsConfig) -> tuple[list[_MetricRecord], dict[str, _MetricRecord]]:
    primary_details: dict[str, Any] = {}
    if metrics.metric_type == "ratio":
        primary_details["numerator_metric_name"] = metrics.numerator_metric_name
        primary_details["denominator_metric_name"] = metrics.denominator_metric_name
    if metrics.metric_type == "count" and metrics.exposure_per_user is not None:
        primary_details["exposure_per_user"] = metrics.exposure_per_user

    records = [
        _metric_record(
            metrics.primary_metric_name,
            metrics.metric_type,
            "primary",
            **primary_details,
        )
    ]
    records.extend(_metric_record(name, "unspecified", "secondary") for name in metrics.secondary_metrics)
    records.extend(
        _metric_record(guardrail.name, guardrail.metric_type, "guardrail")
        for guardrail in metrics.guardrail_metrics
    )

    by_name: dict[str, _MetricRecord] = {}
    for record in records:
        if record.name in by_name:
            raise LegacyConversionError(f"legacy metric names must be unique: {record.name}")
        by_name[record.name] = record
    return records, by_name


def _decimal_string(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _eligibility_expression(payload: ExperimentInput) -> str:
    parts = [
        payload.hypothesis.target_audience.strip(),
        payload.setup.inclusion_criteria.strip(),
    ]
    parts.extend(
        f"{rule.attribute} {rule.operator} {canonical_json_bytes(rule.value).decode('utf-8')}"
        for rule in payload.setup.targeting_rules
    )
    populated = [f"({part})" for part in parts if part]
    if not populated:
        raise LegacyConversionError("legacy population has no eligibility semantics")
    return " AND ".join(populated)


def _randomization_unit(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"user", "session", "account", "device", "cluster"}:
        raise LegacyConversionError(f"unsupported legacy randomization unit: {value}")
    return normalized


def _experiment_type(value: str, randomization_unit: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if randomization_unit == "cluster" and normalized in {
        "ab",
        "a/b",
        "cluster",
        "cluster_randomized",
        "randomized",
    }:
        return "cluster_randomized"
    mapping = {
        "ab": "randomized",
        "a/b": "randomized",
        "randomized": "randomized",
        "switchback": "switchback",
        "factorial": "factorial",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise LegacyConversionError(f"unsupported legacy experiment type: {value}") from exc


def _interference_assumption(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "none": "no_interference",
        "no": "no_interference",
        "low": "no_interference",
        "no_interference": "no_interference",
        "medium": "partial_interference",
        "partial": "partial_interference",
        "partial_interference": "partial_interference",
        "high": "interference_expected",
        "expected": "interference_expected",
        "interference_expected": "interference_expected",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise LegacyConversionError(f"unsupported legacy interference risk: {value}") from exc


def _namespace(payload: ExperimentInput, context: LegacyProtocolContext) -> str:
    if payload.setup.namespace is not None:
        return payload.setup.namespace.id
    if context.assignment_namespace is not None:
        return context.assignment_namespace
    raise LegacyConversionError("assignment namespace is required when the legacy payload has none")


def _metric_by_name(name: str, records: dict[str, _MetricRecord], purpose: str) -> _MetricRecord:
    try:
        return records[name.strip()]
    except KeyError as exc:
        raise LegacyConversionError(f"unknown metric in {purpose}: {name}") from exc


def _variance_reduction(
    metrics: MetricsConfig,
    context: LegacyProtocolContext,
    records: list[_MetricRecord],
    records_by_name: dict[str, _MetricRecord],
) -> dict[str, Any]:
    cuped_values = (metrics.cuped_pre_experiment_std, metrics.cuped_correlation)
    if all(value is None for value in cuped_values):
        if context.cuped_covariate_metric_name is not None:
            raise LegacyConversionError("CUPED covariate context was supplied without legacy CUPED parameters")
        return {"method": "none", "covariate_metric_ids": []}
    if any(value is None for value in cuped_values):
        raise LegacyConversionError("legacy CUPED conversion requires both standard deviation and correlation")
    if context.cuped_covariate_metric_name is None:
        raise LegacyConversionError("legacy CUPED conversion requires an explicit covariate metric name")
    covariate = _metric_record(context.cuped_covariate_metric_name, "unspecified", "covariate")
    if covariate.name in records_by_name:
        raise LegacyConversionError(f"legacy metric names must be unique: {covariate.name}")
    records.append(covariate)
    records_by_name[covariate.name] = covariate
    return {"method": "cuped", "covariate_metric_ids": [covariate.metric_id]}


def _harm_rules(metrics: MetricsConfig, records_by_name: dict[str, _MetricRecord]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    codes: set[str] = set()
    for guardrail in metrics.guardrail_metrics:
        margin = guardrail.non_inferiority_margin_pct
        if margin is None or margin == 0:
            continue
        baseline = guardrail.baseline_rate if guardrail.metric_type == "binary" else guardrail.baseline_mean
        if baseline is None:
            raise LegacyConversionError(f"guardrail baseline is missing: {guardrail.name}")
        direction_multiplier = Decimal(1) if guardrail.direction == "increase_is_bad" else Decimal(-1)
        threshold = Decimal(str(baseline)) * (
            Decimal(1) + direction_multiplier * Decimal(str(margin)) / Decimal(100)
        )
        code_root = re.sub(r"[^A-Z0-9]+", "_", guardrail.name.upper()).strip("_")
        code = f"{code_root}_HARM"[:64]
        if len(code) < 3 or code in codes:
            raise LegacyConversionError(f"guardrail name does not produce a unique rule code: {guardrail.name}")
        codes.add(code)
        rules.append(
                {
                    "code": code,
                    "metric_id": _metric_by_name(
                        guardrail.name,
                        records_by_name,
                        "guardrail harm rule",
                    ).metric_id,
                "operator": "gt" if guardrail.direction == "increase_is_bad" else "lt",
                "threshold": _json_number(threshold),
            }
        )
    return rules


def _alert_rules(
    context: LegacyProtocolContext,
    records_by_name: dict[str, _MetricRecord],
) -> list[dict[str, Any]]:
    return [
        {
            "code": rule.code,
            "metric_id": _metric_by_name(rule.metric_name, records_by_name, "alert threshold").metric_id,
            "operator": rule.operator,
            "threshold": rule.threshold,
        }
        for rule in context.alert_thresholds
    ]


def convert_legacy_project_to_protocol(
    payload: ExperimentInput,
    context: LegacyProtocolContext,
) -> dict[str, Any]:
    """Convert one validated legacy payload into a deterministic frozen protocol."""
    if len(context.intervention_labels) != payload.setup.variants_count:
        raise LegacyConversionError("intervention labels must match the legacy variant count")
    if len(set(context.intervention_labels)) != len(context.intervention_labels):
        raise LegacyConversionError("intervention labels must be unique")
    if sum(payload.setup.traffic_split) != 100:
        raise LegacyConversionError("legacy traffic split must sum to 100 for exact ABX allocation")

    randomization_unit = _randomization_unit(payload.setup.randomization_unit)
    namespace = _namespace(payload, context)
    protocol_id = _stable_id("protocol", {"source_project_id": context.source_project_id})
    interventions = [
        {
            "intervention_id": _stable_id(
                "intervention",
                {"index": index, "protocol_id": protocol_id},
            ),
            "label": label,
            "kind": "control" if index == 0 else "treatment",
            "allocation": _decimal_string(Decimal(weight) / Decimal(100)),
            "namespace": namespace,
            "hash_version": context.assignment_hash_version,
        }
        for index, (label, weight) in enumerate(
            zip(context.intervention_labels, payload.setup.traffic_split, strict=True)
        )
    ]

    metric_records, metrics_by_name = _metric_records(payload.metrics)
    variance_reduction = _variance_reduction(
        payload.metrics,
        context,
        metric_records,
        metrics_by_name,
    )
    primary_metric = metric_records[0]
    multiplicity_family_ids = [
        _metric_by_name(name, metrics_by_name, "multiplicity family").metric_id
        for name in context.multiplicity_family_metric_names
    ]
    effect_measure = {
        "binary": "risk_difference",
        "continuous": "mean_difference",
        "count": "rate_difference",
        "ratio": "ratio_difference",
    }[payload.metrics.metric_type]
    method_id = (
        "bayesian_precision"
        if payload.constraints.analysis_mode == "bayesian"
        else payload.metrics.planned_test or "z_test"
    )
    exclusions = [payload.setup.exclusion_criteria.strip()] if payload.setup.exclusion_criteria.strip() else []

    protocol: dict[str, Any] = {
        "spec_version": ABX_VERSION,
        "required_capabilities": ["protocol-core"],
        "protocol": {
            "protocol_id": protocol_id,
            "title": payload.project.project_name,
            "hypothesis": payload.hypothesis.hypothesis_statement,
            "owners": context.owners,
            "created_at": context.created_at,
        },
        "freeze": {
            "state": "frozen",
            "frozen_by": context.frozen_by,
            "frozen_at": context.frozen_at,
        },
        "population": {
            "eligibility_expression": _eligibility_expression(payload),
            "trigger_expression": context.trigger_expression,
            "randomization_unit": randomization_unit,
            "analysis_population": context.analysis_population,
            "exclusions": exclusions,
        },
        "interventions": interventions,
        "metrics": {
            "primary": [record.reference() for record in metric_records if record.role == "primary"],
            "secondary": [record.reference() for record in metric_records if record.role == "secondary"],
            "guardrails": [record.reference() for record in metric_records if record.role == "guardrail"],
        },
        "estimand": {
            "estimand_id": _stable_id(
                "estimand",
                {
                    "population": context.analysis_population,
                    "primary_metric_id": primary_metric.metric_id,
                    "protocol_id": protocol_id,
                },
            ),
            "population": context.analysis_population,
            "baseline_intervention_id": interventions[0]["intervention_id"],
            "comparison_intervention_ids": [item["intervention_id"] for item in interventions[1:]],
            "effect_measure": effect_measure,
            "horizon": context.horizon,
            "missing_data_rule": context.missing_data_rule,
        },
        "design": {
            "experiment_type": _experiment_type(payload.setup.experiment_type, randomization_unit),
            "interference_assumption": _interference_assumption(payload.constraints.interference_risk),
            "exposure_semantics": context.exposure_semantics,
        },
        "analysis": {
            "method": {"method_id": method_id, "method_version": context.analysis_method_version},
            "alpha": _decimal_string(Decimal(str(payload.metrics.alpha))),
            "power": _decimal_string(Decimal(str(payload.metrics.power))),
            "stopping": {
                "mode": "fixed_horizon" if payload.constraints.n_looks == 1 else "group_sequential",
                "look_count": payload.constraints.n_looks,
            },
            "multiplicity": {
                "method": context.multiplicity_method,
                "family_ids": multiplicity_family_ids,
            },
            "variance_reduction": variance_reduction,
        },
        "telemetry": {
            "subject_key": context.telemetry.subject_key,
            "event_key": context.telemetry.event_key,
            "occurred_at_key": context.telemetry.occurred_at_key,
            "exposure_event": context.telemetry.exposure_event,
            "outcome_events": context.telemetry.outcome_events,
            "ordering": context.telemetry.ordering,
            "deduplication": {
                "keys": context.telemetry.deduplication_keys,
                "window": context.telemetry.deduplication_window,
            },
            "max_lateness": context.telemetry.max_lateness,
            "schema_versions": [
                item.model_dump(mode="json") for item in context.telemetry.schema_versions
            ],
        },
        "decision": {
            "minimum_worthwhile_effect": _json_number(
                Decimal(str(payload.metrics.baseline_value))
                * Decimal(str(payload.metrics.mde_pct))
                / Decimal(100)
            ),
            "harm_rules": _harm_rules(payload.metrics, metrics_by_name),
            "owners": context.decision_owners,
            "approval_policy": {
                "roles": context.approval_roles,
                "minimum_approvals": context.minimum_approvals,
            },
        },
        "operations": {
            "rollback_owner": context.rollback_owner,
            "lag_budget_seconds": context.lag_budget_seconds,
            "alert_thresholds": _alert_rules(context, metrics_by_name),
        },
        "extensions": {
            "legacy.ab-test": {
                "source_project_id": context.source_project_id,
                "source_payload": payload.model_dump(
                    mode="json",
                    exclude={"additional_context"},
                    exclude_none=True,
                ),
                "metric_definitions": [record.extension_entry() for record in metric_records],
            }
        },
    }
    try:
        canonical_json_bytes(protocol)
        validate_abx_document(protocol, PROTOCOL_SCHEMA_ID)
    except AbxError as exc:
        raise LegacyConversionError(f"converted protocol is invalid: {exc}") from exc
    return protocol
