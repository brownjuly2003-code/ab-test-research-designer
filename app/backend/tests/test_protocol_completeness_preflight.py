from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence import abx
from app.backend.app.evidence.preflight import preflight_protocol

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "evidence" / "healthy_protocol.json"
Mutation = Callable[[dict[str, Any]], None]


def _healthy_protocol() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _set(path: tuple[str | int, ...], value: Any) -> Mutation:
    def mutate(protocol: dict[str, Any]) -> None:
        target: Any = protocol
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

    return mutate


def _append(path: tuple[str | int, ...], value: Any) -> Mutation:
    def mutate(protocol: dict[str, Any]) -> None:
        target: Any = protocol
        for part in path:
            target = target[part]
        target.append(deepcopy(value))

    return mutate


def _clear(path: tuple[str | int, ...]) -> Mutation:
    def mutate(protocol: dict[str, Any]) -> None:
        target: Any = protocol
        for part in path:
            target = target[part]
        target.clear()

    return mutate


def _remove_schema(event_type: str) -> Mutation:
    def mutate(protocol: dict[str, Any]) -> None:
        schemas = protocol["telemetry"]["schema_versions"]
        protocol["telemetry"]["schema_versions"] = [
            schema for schema in schemas if schema["event_type"] != event_type
        ]

    return mutate


def _assert_finding(protocol: dict[str, Any], code: str, pointer: str) -> None:
    report = preflight_protocol(protocol)
    matches = [
        finding
        for finding in report.findings
        if finding.code == code and finding.json_pointer == pointer
    ]
    assert matches, [(finding.code, finding.json_pointer) for finding in report.findings]
    assert all(finding.blocking for finding in matches)
    expected_category = "telemetry" if code.startswith("TELEMETRY_") else "protocol"
    assert {finding.category for finding in matches} == {expected_category}
    assert not report.ready


def test_healthy_protocol_has_stable_digest_no_findings_and_immutable_report() -> None:
    protocol = _healthy_protocol()
    original = deepcopy(protocol)
    reordered = {key: protocol[key] for key in reversed(protocol)}

    report = preflight_protocol(protocol)
    repeated = preflight_protocol(reordered)

    assert report == repeated
    assert report.protocol_digest.startswith("sha256:")
    assert len(report.protocol_digest) == 71
    assert report.findings == ()
    assert report.ready
    assert protocol == original
    with pytest.raises(ValidationError, match="frozen"):
        report.protocol_digest = "sha256:" + "0" * 64


def test_schema_invalid_protocol_returns_a_blocking_pointer() -> None:
    protocol = _healthy_protocol()
    protocol["interventions"][0]["allocation"] = "1.5"

    _assert_finding(
        protocol,
        "PROTOCOL_SCHEMA_INVALID",
        "/interventions/0/allocation",
    )


def test_missing_required_protocol_field_returns_a_blocking_parent_pointer() -> None:
    protocol = _healthy_protocol()
    del protocol["protocol"]["hypothesis"]

    _assert_finding(
        protocol,
        "PROTOCOL_SCHEMA_INVALID",
        "/protocol",
    )


def test_schema_violations_api_is_public_immutable_and_deterministic() -> None:
    protocol = _healthy_protocol()
    del protocol["protocol"]["hypothesis"]

    schema_violations = abx.schema_violations
    first = schema_violations(protocol, abx.PROTOCOL_SCHEMA_ID)
    repeated = schema_violations(protocol, abx.PROTOCOL_SCHEMA_ID)

    assert isinstance(first, tuple)
    assert first == repeated
    assert first
    assert first[0][0] == "/protocol"


@pytest.mark.parametrize(
    ("mutate", "code", "pointer"),
    [
        (
            _set(("interventions", 1, "intervention_id"), "control"),
            "INTERVENTION_ID_DUPLICATE",
            "/interventions/1/intervention_id",
        ),
        (
            _set(("interventions", 1, "kind"), "control"),
            "CONTROL_COUNT_INVALID",
            "/interventions",
        ),
        (
            _set(("interventions", 1, "allocation"), "0"),
            "INTERVENTION_ALLOCATION_NONPOSITIVE",
            "/interventions/1/allocation",
        ),
        (
            _set(("interventions", 1, "allocation"), "0.4"),
            "ALLOCATION_TOTAL_INVALID",
            "/interventions",
        ),
        (
            _set(("estimand", "baseline_intervention_id"), "missing"),
            "ESTIMAND_BASELINE_UNKNOWN",
            "/estimand/baseline_intervention_id",
        ),
        (
            _set(("estimand", "baseline_intervention_id"), "treatment"),
            "ESTIMAND_BASELINE_NOT_CONTROL",
            "/estimand/baseline_intervention_id",
        ),
        (
            _set(("estimand", "comparison_intervention_ids", 0), "missing"),
            "ESTIMAND_COMPARISON_UNKNOWN",
            "/estimand/comparison_intervention_ids/0",
        ),
        (
            _set(("estimand", "comparison_intervention_ids", 0), "control"),
            "ESTIMAND_COMPARISON_NOT_TREATMENT",
            "/estimand/comparison_intervention_ids/0",
        ),
        (
            _set(("estimand", "population"), "per_protocol"),
            "ESTIMAND_POPULATION_MISMATCH",
            "/estimand/population",
        ),
    ],
    ids=[
        "duplicate-intervention-id",
        "control-cardinality",
        "nonpositive-allocation",
        "allocation-total",
        "baseline-reference",
        "baseline-role",
        "comparison-reference",
        "comparison-role",
        "estimand-population",
    ],
)
def test_intervention_allocation_and_estimand_faults(
    mutate: Mutation,
    code: str,
    pointer: str,
) -> None:
    protocol = _healthy_protocol()
    mutate(protocol)

    _assert_finding(protocol, code, pointer)


@pytest.mark.parametrize(
    ("mutate", "code", "pointer"),
    [
        (
            _append(
                ("metrics", "primary"),
                {
                    "metric_id": "metric_conversion",
                    "metric_version": "v1",
                    "definition_digest": "sha256:" + "c" * 64,
                },
            ),
            "METRIC_REFERENCE_DUPLICATE",
            "/metrics/primary/1/metric_id",
        ),
        (
            _append(
                ("metrics", "secondary"),
                {
                    "metric_id": "metric_conversion",
                    "metric_version": "v1",
                    "definition_digest": "sha256:" + "c" * 64,
                },
            ),
            "METRIC_ROLE_CONFLICT",
            "/metrics/secondary/0/metric_id",
        ),
        (
            _append(
                ("metrics", "primary"),
                {
                    "metric_id": "metric_conversion",
                    "metric_version": "v2",
                    "definition_digest": "sha256:" + "b" * 64,
                },
            ),
            "METRIC_REFERENCE_CONFLICT",
            "/metrics/primary/1/metric_id",
        ),
        (
            _append(("analysis", "multiplicity", "family_ids"), "metric_missing"),
            "MULTIPLICITY_METRIC_UNKNOWN",
            "/analysis/multiplicity/family_ids/0",
        ),
        (
            _append(("analysis", "variance_reduction", "covariate_metric_ids"), "metric_missing"),
            "COVARIATE_METRIC_UNKNOWN",
            "/analysis/variance_reduction/covariate_metric_ids/0",
        ),
        (
            _set(("decision", "harm_rules", 0, "metric_id"), "metric_missing"),
            "HARM_RULE_METRIC_UNKNOWN",
            "/decision/harm_rules/0/metric_id",
        ),
        (
            _set(("decision", "harm_rules", 0, "metric_id"), "metric_conversion"),
            "HARM_RULE_METRIC_NOT_GUARDRAIL",
            "/decision/harm_rules/0/metric_id",
        ),
        (
            _clear(("decision", "harm_rules")),
            "GUARDRAIL_POLICY_MISSING",
            "/metrics/guardrails/0/metric_id",
        ),
        (
            _set(("operations", "alert_thresholds", 0, "metric_id"), "metric_missing"),
            "ALERT_THRESHOLD_METRIC_UNKNOWN",
            "/operations/alert_thresholds/0/metric_id",
        ),
        (
            _set(("decision", "approval_policy", "minimum_approvals"), 2),
            "APPROVAL_POLICY_UNSATISFIABLE",
            "/decision/approval_policy/minimum_approvals",
        ),
    ],
    ids=[
        "duplicate-reference",
        "role-conflict",
        "definition-conflict",
        "multiplicity-reference",
        "covariate-reference",
        "harm-reference",
        "harm-role",
        "guardrail-policy",
        "alert-reference",
        "approval-policy",
    ],
)
def test_metric_role_reference_and_policy_faults(
    mutate: Mutation,
    code: str,
    pointer: str,
) -> None:
    protocol = _healthy_protocol()
    mutate(protocol)

    _assert_finding(protocol, code, pointer)


@pytest.mark.parametrize(
    ("mutate", "code", "pointer"),
    [
        (
            _set(("analysis", "multiplicity", "family_ids"), ["metric_conversion"]),
            "MULTIPLICITY_POLICY_INCONSISTENT",
            "/analysis/multiplicity/family_ids",
        ),
        (
            _set(("analysis", "multiplicity", "method"), "holm"),
            "MULTIPLICITY_POLICY_INCONSISTENT",
            "/analysis/multiplicity/family_ids",
        ),
        (
            _set(
                ("analysis", "variance_reduction", "covariate_metric_ids"),
                ["metric_conversion"],
            ),
            "VARIANCE_REDUCTION_POLICY_INCONSISTENT",
            "/analysis/variance_reduction/covariate_metric_ids",
        ),
        (
            _set(("analysis", "variance_reduction", "method"), "cuped"),
            "VARIANCE_REDUCTION_POLICY_INCONSISTENT",
            "/analysis/variance_reduction/covariate_metric_ids",
        ),
    ],
    ids=[
        "multiplicity-none-with-family",
        "multiplicity-method-without-family",
        "variance-none-with-covariate",
        "variance-method-without-covariate",
    ],
)
def test_analysis_policy_method_and_references_are_consistent(
    mutate: Mutation,
    code: str,
    pointer: str,
) -> None:
    protocol = _healthy_protocol()
    mutate(protocol)

    _assert_finding(protocol, code, pointer)


@pytest.mark.parametrize(
    ("mutate", "code", "pointer"),
    [
        (
            _append(("telemetry", "outcome_events"), "checkout_exposure"),
            "TELEMETRY_EVENT_ROLE_CONFLICT",
            "/telemetry/outcome_events/2",
        ),
        (
            _set(("telemetry", "deduplication", "keys"), ["subject_key"]),
            "TELEMETRY_DEDUP_EVENT_KEY_MISSING",
            "/telemetry/deduplication/keys",
        ),
        (
            _remove_schema("checkout_exposure"),
            "TELEMETRY_EVENT_SCHEMA_MISSING",
            "/telemetry/exposure_event",
        ),
        (
            _remove_schema("refund_issued"),
            "TELEMETRY_EVENT_SCHEMA_MISSING",
            "/telemetry/outcome_events/1",
        ),
        (
            _append(
                ("telemetry", "schema_versions"),
                {
                    "event_type": "checkout_exposure",
                    "version": "v1",
                    "schema_digest": "sha256:" + "a" * 64,
                },
            ),
            "TELEMETRY_SCHEMA_VERSION_DUPLICATE",
            "/telemetry/schema_versions/3",
        ),
        (
            _append(
                ("telemetry", "schema_versions"),
                {
                    "event_type": "checkout_exposure",
                    "version": "v1",
                    "schema_digest": "sha256:" + "9" * 64,
                },
            ),
            "TELEMETRY_SCHEMA_VERSION_CONFLICT",
            "/telemetry/schema_versions/3/schema_digest",
        ),
    ],
    ids=[
        "exposure-outcome-conflict",
        "dedup-event-key",
        "exposure-schema",
        "outcome-schema",
        "duplicate-schema-version",
        "conflicting-schema-version",
    ],
)
def test_declared_telemetry_faults(
    mutate: Mutation,
    code: str,
    pointer: str,
) -> None:
    protocol = _healthy_protocol()
    mutate(protocol)

    _assert_finding(protocol, code, pointer)
