from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.abx import PROTOCOL_SCHEMA_ID, validate_abx_document
from app.backend.app.evidence.reserved.legacy import (
    LegacyConversionError,
    LegacyProtocolContext,
    convert_legacy_project_to_protocol,
)
from app.backend.app.schemas.api._projects import ProjectRecord

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "abx" / "0.1" / "legacy"
)


def _load_json(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _context(
    *,
    primary_metric_name: str = "purchase_conversion",
    assignment_namespace: str | None = None,
) -> LegacyProtocolContext:
    value: dict[str, Any] = {
        "source_project_id": "project_checkout_2026",
        "owners": ["team_growth"],
        "created_at": "2026-08-21T18:00:00Z",
        "frozen_by": "team_growth",
        "frozen_at": "2026-08-21T20:00:00Z",
        "intervention_labels": ["Current checkout", "Two-step checkout", "Guest checkout"],
        "assignment_hash_version": "assignment_v1",
        "trigger_expression": "first checkout page view after a valid assignment",
        "analysis_population": "intention_to_treat",
        "horizon": "P14D",
        "missing_data_rule": "zero",
        "exposure_semantics": "A valid assignment followed by the first checkout page view is the exposure.",
        "analysis_method_version": "legacy-fisher-v1",
        "multiplicity_method": "holm",
        "multiplicity_family_metric_names": [primary_metric_name, "add_to_cart_rate"],
        "telemetry": {
            "subject_key": "subject_key",
            "event_key": "event_id",
            "occurred_at_key": "occurred_at",
            "exposure_event": "checkout_exposure",
            "outcome_events": [
                "purchase_completed",
                "add_to_cart",
                "payment_error",
                "refund_recorded",
            ],
            "ordering": "event_time",
            "deduplication_keys": ["event_id"],
            "deduplication_window": "P30D",
            "max_lateness": "P1D",
            "schema_versions": [
                {
                    "event_type": "purchase_completed",
                    "version": "v1",
                    "schema_digest": "sha256:" + "e" * 64,
                },
                {
                    "event_type": "add_to_cart",
                    "version": "v1",
                    "schema_digest": "sha256:" + "f" * 64,
                },
                {
                    "event_type": "payment_error",
                    "version": "v1",
                    "schema_digest": "sha256:" + "a" * 64,
                },
                {
                    "event_type": "refund_recorded",
                    "version": "v1",
                    "schema_digest": "sha256:" + "b" * 64,
                },
            ],
        },
        "decision_owners": ["team_growth"],
        "approval_roles": ["product_owner", "data_scientist"],
        "minimum_approvals": 2,
        "rollback_owner": "team_growth",
        "lag_budget_seconds": 3600,
        "alert_thresholds": [
            {
                "code": "INGEST_LAG",
                "metric_name": primary_metric_name,
                "operator": "gt",
                "threshold": 1800,
            }
        ],
    }
    if assignment_namespace is not None:
        value["assignment_namespace"] = assignment_namespace
    return LegacyProtocolContext.model_validate(value)


def _all_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def test_saved_project_converts_to_exact_schema_valid_protocol_without_lineage() -> None:
    project = ProjectRecord.model_validate(_load_json("project.json"))
    expected = _load_json("protocol.json")
    context = _context()

    first = convert_legacy_project_to_protocol(project.payload, context)
    second = convert_legacy_project_to_protocol(project.payload, context)

    assert first == expected
    assert second == first
    validate_abx_document(first, PROTOCOL_SCHEMA_ID)
    assert "lineage" not in set(_all_keys(first))
    assert "Previous tests showed mixed results" not in json.dumps(first)


@pytest.mark.parametrize(
    ("metric_type", "metric_fields", "planned_test", "effect_measure"),
    [
        ("continuous", {"baseline_value": 45.0, "std_dev": 12.0}, "mann_whitney", "mean_difference"),
        ("count", {"baseline_value": 3.0, "exposure_per_user": 2.0}, None, "rate_difference"),
        (
            "ratio",
            {
                "baseline_value": 0.2,
                "numerator_metric_name": "clicks",
                "denominator_metric_name": "impressions",
            },
            None,
            "ratio_difference",
        ),
    ],
)
def test_metric_families_and_planned_tests_map_explicitly(
    metric_type: str,
    metric_fields: dict[str, Any],
    planned_test: str | None,
    effect_measure: str,
) -> None:
    raw_project = _load_json("project.json")
    metrics: dict[str, Any] = {
        "primary_metric_name": f"primary_{metric_type}",
        "metric_type": metric_type,
        "baseline_value": 1.0,
        "mde_pct": 5.0,
        "planned_test": planned_test,
        "alpha": 0.05,
        "power": 0.8,
        "secondary_metrics": [],
        "guardrail_metrics": [],
    }
    metrics.update(metric_fields)
    raw_project["payload"]["metrics"] = metrics
    project = ProjectRecord.model_validate(raw_project)
    context_payload = _context(primary_metric_name=metrics["primary_metric_name"]).model_dump(mode="json")
    context_payload["multiplicity_method"] = "none"
    context_payload["multiplicity_family_metric_names"] = []
    context_payload["alert_thresholds"] = []
    context_payload["analysis_method_version"] = "legacy-method-v1"

    protocol = convert_legacy_project_to_protocol(
        project.payload,
        LegacyProtocolContext.model_validate(context_payload),
    )

    assert protocol["estimand"]["effect_measure"] == effect_measure
    assert protocol["analysis"]["method"]["method_id"] == (planned_test or "z_test")
    validate_abx_document(protocol, PROTOCOL_SCHEMA_ID)


def test_converter_rejects_ambiguous_namespace_and_non_percentage_split() -> None:
    raw_project = _load_json("project.json")
    raw_project["payload"]["setup"].pop("namespace")
    project_without_namespace = ProjectRecord.model_validate(raw_project)
    with pytest.raises(LegacyConversionError, match="assignment namespace"):
        convert_legacy_project_to_protocol(project_without_namespace.payload, _context())

    raw_project = _load_json("project.json")
    raw_project["payload"]["setup"]["traffic_split"] = [1, 1, 1]
    project_with_ambiguous_split = ProjectRecord.model_validate(raw_project)
    with pytest.raises(LegacyConversionError, match="sum to 100"):
        convert_legacy_project_to_protocol(project_with_ambiguous_split.payload, _context())


def test_guardrail_lookup_uses_the_normalized_legacy_metric_name() -> None:
    raw_project = _load_json("project.json")
    raw_project["payload"]["metrics"]["guardrail_metrics"][0]["name"] = " Payment error rate "
    project = ProjectRecord.model_validate(raw_project)

    protocol = convert_legacy_project_to_protocol(project.payload, _context())

    assert protocol["decision"]["harm_rules"][0]["metric_id"] == (
        protocol["metrics"]["guardrails"][0]["metric_id"]
    )


def test_caller_owned_context_has_no_implicit_telemetry_default() -> None:
    context_payload = copy.deepcopy(_context().model_dump(mode="json"))
    context_payload.pop("telemetry")

    with pytest.raises(ValidationError):
        LegacyProtocolContext.model_validate(context_payload)
