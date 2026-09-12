from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.preflight import (
    ProtocolPreflightReport,
    SimulatedAaBinaryAggregate,
    SimulatedAaProfile,
    preflight_protocol,
    preflight_simulated_aa,
    simulate_aa_profile,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "evidence"
PROFILE_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_simulated_aa_profile.json"
PROTOCOL_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_protocol.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _healthy_profile_data() -> dict[str, Any]:
    return _load_json(PROFILE_FIXTURE_PATH)


def _healthy_protocol() -> dict[str, Any]:
    return _load_json(PROTOCOL_FIXTURE_PATH)


def _healthy_aggregates() -> tuple[SimulatedAaBinaryAggregate, ...]:
    return (
        SimulatedAaBinaryAggregate(
            metric_id="metric_conversion",
            metric_version="v1",
            definition_digest="sha256:" + "c" * 64,
            control_users=10_000,
            control_conversions=1_000,
            treatment_users=10_000,
            treatment_conversions=1_000,
        ),
        SimulatedAaBinaryAggregate(
            metric_id="metric_refund",
            metric_version="v1",
            definition_digest="sha256:" + "d" * 64,
            control_users=10_000,
            control_conversions=100,
            treatment_users=10_000,
            treatment_conversions=100,
        ),
    )


def _single_metric_protocol(*, random_seed: int) -> dict[str, Any]:
    protocol = _healthy_protocol()
    protocol["analysis"]["random_seed"] = random_seed
    protocol["metrics"]["guardrails"] = []
    protocol["decision"]["harm_rules"] = []
    return protocol


def test_healthy_simulated_aa_profile_is_deterministic_immutable_and_ready() -> None:
    profile = SimulatedAaProfile.model_validate(_healthy_profile_data())
    protocol = _healthy_protocol()
    original_protocol = deepcopy(protocol)

    report = preflight_simulated_aa(protocol, profile)
    repeated = preflight_simulated_aa(protocol, profile)

    assert isinstance(report, ProtocolPreflightReport)
    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert report.findings == ()
    assert report.ready
    assert protocol == original_protocol
    assert isinstance(profile.allocations, tuple)
    assert isinstance(profile.metric_calibrations, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        profile.random_seed = 7
    with pytest.raises(ValidationError, match="frozen"):
        profile.metric_calibrations[0].uniformity_p_value = "0.01"


def test_profile_rejects_nonaggregate_payloads_and_connection_details() -> None:
    raw = _healthy_profile_data()
    raw["raw_rows"] = [{"subject_id": "subject-123", "event_id": "event-456"}]
    raw["connection_details"] = {"dsn": "postgresql://private"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SimulatedAaProfile.model_validate(raw)

    nested_raw = _healthy_profile_data()
    nested_raw["metric_calibrations"][0]["subject_ids"] = ["subject-123"]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SimulatedAaProfile.model_validate(nested_raw)


def test_profile_rejects_invalid_aggregate_calibration_values() -> None:
    minimum_positive_count = _healthy_profile_data()
    minimum_positive_count["metric_calibrations"][0]["simulated_p_value_count"] = 200
    profile = SimulatedAaProfile.model_validate(minimum_positive_count)
    assert profile.metric_calibrations[0].simulated_p_value_count == 200

    no_simulations = _healthy_profile_data()
    no_simulations["metric_calibrations"][0]["simulated_p_value_count"] = 199
    with pytest.raises(ValidationError):
        SimulatedAaProfile.model_validate(no_simulations)

    invalid_p_value = _healthy_profile_data()
    invalid_p_value["metric_calibrations"][0]["uniformity_p_value"] = "1.01"
    with pytest.raises(ValidationError):
        SimulatedAaProfile.model_validate(invalid_p_value)

    oversized_p_value = _healthy_profile_data()
    oversized_p_value["metric_calibrations"][0]["uniformity_p_value"] = (
        "0." + "0" * 128 + "1"
    )
    with pytest.raises(ValidationError):
        SimulatedAaProfile.model_validate(oversized_p_value)

    oversized_allocation = _healthy_profile_data()
    oversized_allocation["allocations"][0]["allocation"] = (
        "0." + "0" * 128 + "1"
    )
    with pytest.raises(ValidationError):
        SimulatedAaProfile.model_validate(oversized_allocation)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.__setitem__("random_seed", 7),
        lambda profile: profile["analysis_method"].__setitem__(
            "method_version", "2"
        ),
        lambda profile: profile["allocations"][0].__setitem__(
            "allocation", "0.4"
        ),
        lambda profile: profile["metric_calibrations"][0].__setitem__(
            "definition_digest", "sha256:" + "9" * 64
        ),
    ],
    ids=["seed", "analysis-method", "allocation", "metric-definition"],
)
def test_profile_must_be_bound_to_frozen_protocol_declarations(mutate: Any) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    with pytest.raises(ValueError, match="not match frozen protocol"):
        preflight_simulated_aa(
            _healthy_protocol(),
            SimulatedAaProfile.model_validate(profile_data),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile["metric_calibrations"].pop(),
        lambda profile: profile["allocations"].reverse(),
        lambda profile: profile["metric_calibrations"].reverse(),
    ],
    ids=["missing-metric", "allocation-order", "metric-order"],
)
def test_missing_or_reordered_bindings_are_contract_errors(mutate: Any) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    with pytest.raises(ValueError, match="not match frozen protocol"):
        preflight_simulated_aa(
            _healthy_protocol(),
            SimulatedAaProfile.model_validate(profile_data),
        )


def test_protocol_without_a_random_seed_is_an_explicit_contract_error() -> None:
    protocol = _healthy_protocol()
    del protocol["analysis"]["random_seed"]
    assert preflight_protocol(protocol).ready

    with pytest.raises(ValueError, match=r"analysis\.random_seed.*required"):
        preflight_simulated_aa(
            protocol,
            SimulatedAaProfile.model_validate(_healthy_profile_data()),
        )


def test_failed_uniformity_calibration_has_stable_blocker_and_pointer() -> None:
    profile_data = _healthy_profile_data()
    profile_data["metric_calibrations"][0]["uniformity_p_value"] = "0.001"
    profile = SimulatedAaProfile.model_validate(profile_data)
    protocol = _healthy_protocol()

    report = preflight_simulated_aa(protocol, profile)
    repeated = preflight_simulated_aa(protocol, profile)

    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert [
        (finding.code, finding.category, finding.json_pointer, finding.blocking)
        for finding in report.findings
    ] == [
        (
            "AA_CALIBRATION_ASSERTED_FAILED",
            "statistics",
            "/metric_calibrations/0/uniformity_p_value",
            True,
        )
    ]
    assert not report.ready


def test_protocol_alpha_is_exclusive_and_multiple_failures_are_sorted() -> None:
    profile_data = _healthy_profile_data()
    profile_data["metric_calibrations"][0]["uniformity_p_value"] = "0.05"
    profile_data["metric_calibrations"][1]["uniformity_p_value"] = "0.001"
    profile = SimulatedAaProfile.model_validate(profile_data)
    protocol = _healthy_protocol()

    report = preflight_simulated_aa(protocol, profile)
    repeated = preflight_simulated_aa(protocol, profile)

    assert [(finding.code, finding.json_pointer) for finding in report.findings] == [
        (
            "AA_CALIBRATION_ASSERTED_FAILED",
            "/metric_calibrations/1/uniformity_p_value",
        ),
    ]
    assert report == repeated
    assert all(finding.category == "statistics" for finding in report.findings)
    assert all(finding.blocking for finding in report.findings)


def test_calibration_threshold_is_independent_of_protocol_alpha() -> None:
    profile_data = _healthy_profile_data()
    profile_data["metric_calibrations"][0]["uniformity_p_value"] = "0.02"

    report = preflight_simulated_aa(
        _healthy_protocol(),
        SimulatedAaProfile.model_validate(profile_data),
    )

    assert report.ready


def test_internal_permutation_profile_is_deterministic_and_content_bound() -> None:
    protocol = _healthy_protocol()

    profile = simulate_aa_profile(protocol, _healthy_aggregates())
    repeated = simulate_aa_profile(protocol, _healthy_aggregates())

    assert profile == repeated
    assert profile.random_seed == protocol["analysis"]["random_seed"]
    assert all(
        calibration.calibration_source == "internal_permutation"
        for calibration in profile.metric_calibrations
    )
    assert all(
        calibration.simulated_p_value_count == 1_000
        for calibration in profile.metric_calibrations
    )
    assert all(
        calibration.simulated_p_values_digest is not None
        and calibration.simulated_p_values_digest.startswith("sha256:")
        for calibration in profile.metric_calibrations
    )
    assert preflight_simulated_aa(protocol, profile).ready


def test_internal_calibration_uses_distinct_failure_code() -> None:
    profile_data = _healthy_profile_data()
    calibration = profile_data["metric_calibrations"][0]
    calibration["calibration_source"] = "internal_permutation"
    calibration["simulated_p_values_digest"] = "sha256:" + "1" * 64
    calibration["uniformity_p_value"] = "0.001"

    report = preflight_simulated_aa(
        _healthy_protocol(),
        SimulatedAaProfile.model_validate(profile_data),
    )

    assert [finding.code for finding in report.findings] == [
        "AA_CALIBRATION_FAILED"
    ]


def test_internal_healthy_metric_false_alarm_rate_is_at_most_one_percent() -> None:
    false_alarms = 0
    aggregate = (_healthy_aggregates()[0],)
    for random_seed in range(100):
        protocol = _single_metric_protocol(random_seed=random_seed)
        profile = simulate_aa_profile(protocol, aggregate)
        false_alarms += not preflight_simulated_aa(protocol, profile).ready

    assert false_alarms <= 1


def test_serialized_profile_and_report_retain_the_privacy_boundary() -> None:
    profile = SimulatedAaProfile.model_validate(_healthy_profile_data())
    report = preflight_simulated_aa(_healthy_protocol(), profile)

    serialized = (profile.model_dump_json() + report.model_dump_json()).lower()
    for forbidden in (
        "subject_id",
        "event_id",
        "connection",
        "postgresql",
        "dsn",
        "raw_rows",
    ):
        assert forbidden not in serialized
