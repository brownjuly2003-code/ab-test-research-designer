from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from statistics import NormalDist
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.preflight import (
    EmpiricalPowerBinaryMetricSource,
    EmpiricalPowerProfile,
    ProtocolPreflightReport,
    preflight_empirical_power,
    preflight_protocol,
    simulate_empirical_power_profile,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "evidence"
PROFILE_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_empirical_power_profile.json"
PROTOCOL_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_protocol.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _healthy_profile_data() -> dict[str, Any]:
    return _load_json(PROFILE_FIXTURE_PATH)


def _healthy_protocol() -> dict[str, Any]:
    return _load_json(PROTOCOL_FIXTURE_PATH)


def _single_metric_protocol() -> dict[str, Any]:
    protocol = _healthy_protocol()
    protocol["metrics"]["guardrails"] = []
    protocol["decision"]["harm_rules"] = []
    protocol["decision"]["minimum_worthwhile_effect"] = 0.05
    return protocol


def test_healthy_profile_is_aggregate_immutable_deterministic_and_ready() -> None:
    profile = EmpiricalPowerProfile.model_validate(_healthy_profile_data())
    protocol = _healthy_protocol()
    original_protocol = deepcopy(protocol)

    report = preflight_empirical_power(protocol, profile)
    repeated = preflight_empirical_power(protocol, profile)

    assert isinstance(report, ProtocolPreflightReport)
    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert profile.protocol_digest == report.protocol_digest
    assert report.findings == ()
    assert report.ready
    assert protocol == original_protocol
    assert isinstance(profile.allocations, tuple)
    assert isinstance(profile.metric_results, tuple)
    assert profile.metric_results[0].evaluated_total_sample_size == 24000
    assert (
        profile.metric_results[0].historical_distribution_digest
        == "sha256:" + "1" * 64
    )
    assert (
        profile.metric_results[0].detectable_effect_at_evaluated_total_sample_size
        == "0.0095"
    )
    assert profile.metric_results[0].recommended_total_sample_size == 22000
    with pytest.raises(ValidationError, match="frozen"):
        profile.random_seed = 7
    with pytest.raises(ValidationError, match="frozen"):
        profile.metric_results[0].achieved_power = "0.79"


def test_internal_bootstrap_computes_power_from_historical_duckdb_source(
    tmp_path: Path,
) -> None:
    protocol = _single_metric_protocol()
    source = tmp_path / "historical.csv"
    source.write_text(
        "conversion\n" + "\n".join(["1"] * 200 + ["0"] * 800) + "\n",
        encoding="utf-8",
    )
    metric = protocol["metrics"]["primary"][0]
    metric_source = EmpiricalPowerBinaryMetricSource(
        metric_id=metric["metric_id"],
        metric_version=metric["metric_version"],
        definition_digest=metric["definition_digest"],
        outcome_column="conversion",
        evaluated_total_sample_size=2_500,
    )

    profile = simulate_empirical_power_profile(
        protocol,
        source,
        relation="historical_power",
        source_ref="historical_power_fixture",
        metrics=(metric_source,),
    )
    repeated = simulate_empirical_power_profile(
        protocol,
        source,
        relation="historical_power",
        source_ref="historical_power_fixture",
        metrics=(metric_source,),
    )

    control_users = treatment_users = 1_250
    control_rate = 0.2
    treatment_rate = 0.25
    pooled_rate = (
        control_users * control_rate + treatment_users * treatment_rate
    ) / (control_users + treatment_users)
    null_standard_error = math.sqrt(
        pooled_rate
        * (1.0 - pooled_rate)
        * (1.0 / control_users + 1.0 / treatment_users)
    )
    alternative_standard_error = math.sqrt(
        control_rate * (1.0 - control_rate) / control_users
        + treatment_rate * (1.0 - treatment_rate) / treatment_users
    )
    mean_z = (treatment_rate - control_rate) / null_standard_error
    standard_deviation_z = alternative_standard_error / null_standard_error
    critical = NormalDist().inv_cdf(0.975)
    expected_power = NormalDist(mean_z, standard_deviation_z).cdf(-critical) + (
        1.0 - NormalDist(mean_z, standard_deviation_z).cdf(critical)
    )

    assert profile == repeated
    assert profile.metric_results[0].power_source == "internal_bootstrap"
    assert profile.metric_results[0].simulation_count == 1_000
    assert abs(float(profile.metric_results[0].achieved_power) - expected_power) <= 0.03
    assert profile.metric_results[0].historical_distribution_digest.startswith(
        "sha256:"
    )
    assert preflight_empirical_power(protocol, profile).ready
    assert "outcome_column" not in profile.model_dump_json()


@pytest.mark.parametrize(
    ("simulation_count", "message"),
    [
        (499, "requires between 500 and 100000"),
        (100_001, "requires between 500 and 100000"),
        (500.0, "must be an integer"),
        (True, "must be an integer"),
    ],
    ids=["below-minimum", "above-maximum", "float", "bool"],
)
def test_internal_bootstrap_rejects_invalid_simulation_count(
    simulation_count: Any,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        simulate_empirical_power_profile(
            _single_metric_protocol(),
            "unused.csv",
            relation="historical_power",
            source_ref="historical_power_fixture",
            metrics=(),
            simulation_count=simulation_count,
        )


def test_profile_rejects_raw_payloads_identifiers_and_connection_details() -> None:
    raw = _healthy_profile_data()
    raw["raw_rows"] = [{"subject_id": "subject-123", "event_id": "event-456"}]
    raw["connection_details"] = {"dsn": "postgresql://private"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EmpiricalPowerProfile.model_validate(raw)

    nested_raw = _healthy_profile_data()
    nested_raw["metric_results"][0]["bootstrap_samples"] = [0.1, 0.2]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EmpiricalPowerProfile.model_validate(nested_raw)

    nested_query = _healthy_profile_data()
    nested_query["metric_results"][0]["statement"] = "SELECT * FROM private"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EmpiricalPowerProfile.model_validate(nested_query)


def test_evaluated_volume_is_explicitly_total_under_unequal_allocations() -> None:
    protocol = _healthy_protocol()
    protocol["interventions"][0]["allocation"] = "0.25"
    protocol["interventions"][1]["allocation"] = "0.75"
    profile_data = _healthy_profile_data()
    profile_data["protocol_digest"] = preflight_protocol(protocol).protocol_digest
    profile_data["allocations"][0]["allocation"] = "0.25"
    profile_data["allocations"][1]["allocation"] = "0.75"

    profile = EmpiricalPowerProfile.model_validate(profile_data)
    report = preflight_empirical_power(protocol, profile)

    assert report.ready
    serialized_result = profile.metric_results[0].model_dump()
    assert serialized_result["evaluated_total_sample_size"] == 24000
    assert "evaluated_sample_size" not in serialized_result


def test_ambiguous_evaluated_sample_size_is_rejected() -> None:
    profile_data = _healthy_profile_data()
    metric_result = profile_data["metric_results"][0]
    metric_result["evaluated_sample_size"] = metric_result.pop(
        "evaluated_total_sample_size"
    )

    with pytest.raises(ValidationError):
        EmpiricalPowerProfile.model_validate(profile_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("simulation_count", 0),
        ("simulation_count", 9_007_199_254_740_992),
        ("evaluated_total_sample_size", 1),
        ("evaluated_total_sample_size", 9_007_199_254_740_992),
        ("achieved_power", "1.01"),
        ("achieved_power", "0." + "0" * 128 + "1"),
        ("detectable_effect_at_evaluated_total_sample_size", "not-a-number"),
        (
            "detectable_effect_at_evaluated_total_sample_size",
            "0." + "0" * 128 + "1",
        ),
        ("recommended_total_sample_size", 1),
        ("recommended_total_sample_size", 9_007_199_254_740_992),
        ("historical_distribution_digest", "sha256:" + "9" * 63),
    ],
    ids=[
        "zero-simulations",
        "oversized-simulations",
        "undersized-sample",
        "oversized-sample",
        "invalid-power",
        "oversized-power",
        "invalid-detectable-effect",
        "oversized-detectable-effect",
        "undersized-recommended-sample",
        "oversized-recommended-sample",
        "invalid-historical-distribution-digest",
    ],
)
def test_profile_rejects_invalid_bounded_aggregate_values(
    field: str,
    value: Any,
) -> None:
    profile_data = _healthy_profile_data()
    profile_data["metric_results"][0][field] = value

    with pytest.raises(ValidationError):
        EmpiricalPowerProfile.model_validate(profile_data)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.__setitem__(
            "protocol_digest", "sha256:" + "9" * 64
        ),
        lambda profile: profile.__setitem__("random_seed", 7),
        lambda profile: profile["analysis_method"].__setitem__(
            "method_version", "2"
        ),
        lambda profile: profile.__setitem__("target_power", "0.9"),
        lambda profile: profile.__setitem__(
            "minimum_worthwhile_effect", "0.02"
        ),
        lambda profile: profile["allocations"][0].__setitem__(
            "allocation", "0.4"
        ),
        lambda profile: profile["metric_results"][0].__setitem__(
            "definition_digest", "sha256:" + "9" * 64
        ),
    ],
    ids=[
        "protocol-digest",
        "seed",
        "analysis-method",
        "target-power",
        "minimum-worthwhile-effect",
        "allocation",
        "metric-definition",
    ],
)
def test_profile_must_match_all_frozen_protocol_bindings(mutate: Any) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    with pytest.raises(ValueError, match="does not match frozen protocol"):
        preflight_empirical_power(
            _healthy_protocol(),
            EmpiricalPowerProfile.model_validate(profile_data),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile["metric_results"].pop(),
        lambda profile: profile["allocations"].reverse(),
        lambda profile: profile["metric_results"].reverse(),
    ],
    ids=["missing-metric", "allocation-order", "metric-order"],
)
def test_missing_or_reordered_bindings_are_contract_errors(mutate: Any) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    with pytest.raises(ValueError, match="does not match frozen protocol"):
        preflight_empirical_power(
            _healthy_protocol(),
            EmpiricalPowerProfile.model_validate(profile_data),
        )


def test_protocol_without_random_seed_is_an_explicit_contract_error() -> None:
    protocol = _healthy_protocol()
    del protocol["analysis"]["random_seed"]
    assert preflight_protocol(protocol).ready

    with pytest.raises(ValueError, match=r"analysis\.random_seed.*required"):
        preflight_empirical_power(
            protocol,
            EmpiricalPowerProfile.model_validate(_healthy_profile_data()),
        )


@pytest.mark.parametrize(
    ("achieved_power", "detectable_effect", "recommended_total_sample_size"),
    [
        ("0.79", "0.011", 22000),
        ("0.79", "0.0095", 26000),
        ("0.84", "0.0095", 26000),
        ("0.84", "0.011", 22000),
    ],
    ids=[
        "underpowered-smaller-recommendation",
        "underpowered-smaller-detectable-effect",
        "powered-larger-recommendation",
        "powered-larger-detectable-effect",
    ],
)
def test_remediation_evidence_must_agree_with_power_verdict(
    achieved_power: str,
    detectable_effect: str,
    recommended_total_sample_size: int,
) -> None:
    profile_data = _healthy_profile_data()
    result = profile_data["metric_results"][0]
    result["achieved_power"] = achieved_power
    result["detectable_effect_at_evaluated_total_sample_size"] = detectable_effect
    result["recommended_total_sample_size"] = recommended_total_sample_size

    with pytest.raises(ValueError, match="remediation evidence is inconsistent"):
        preflight_empirical_power(
            _healthy_protocol(),
            EmpiricalPowerProfile.model_validate(profile_data),
        )


def test_below_target_power_has_one_stable_blocker_and_pointer() -> None:
    profile_data = _healthy_profile_data()
    profile_data["metric_results"][0].update(
        {
            "achieved_power": "0.79",
            "detectable_effect_at_evaluated_total_sample_size": "0.011",
            "recommended_total_sample_size": 26000,
        }
    )
    profile = EmpiricalPowerProfile.model_validate(profile_data)
    protocol = _healthy_protocol()

    report = preflight_empirical_power(protocol, profile)
    repeated = preflight_empirical_power(protocol, profile)

    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert [
        (finding.code, finding.category, finding.json_pointer, finding.blocking)
        for finding in report.findings
    ] == [
        (
            "EMPIRICAL_POWER_BELOW_TARGET",
            "statistics",
            "/metric_results/0/achieved_power",
            True,
        )
    ]
    assert not report.ready
    assert "evaluated total sample size 24000" in report.findings[0].message
    assert "detectable effect 0.011" in report.findings[0].message
    assert "recommended total sample size 26000" in report.findings[0].message


def test_target_boundary_passes_and_multiple_failures_are_sorted() -> None:
    boundary_data = _healthy_profile_data()
    boundary_data["metric_results"][0]["achieved_power"] = "0.8"
    boundary = preflight_empirical_power(
        _healthy_protocol(),
        EmpiricalPowerProfile.model_validate(boundary_data),
    )
    assert boundary.ready

    failing_data = _healthy_profile_data()
    failing_data["metric_results"][0].update(
        {
            "achieved_power": "0.79",
            "detectable_effect_at_evaluated_total_sample_size": "0.011",
            "recommended_total_sample_size": 26000,
        }
    )
    failing_data["metric_results"][1].update(
        {
            "achieved_power": "0.75",
            "detectable_effect_at_evaluated_total_sample_size": "0.012",
            "recommended_total_sample_size": 28000,
        }
    )
    profile = EmpiricalPowerProfile.model_validate(failing_data)

    report = preflight_empirical_power(_healthy_protocol(), profile)
    repeated = preflight_empirical_power(_healthy_protocol(), profile)

    assert [(finding.code, finding.json_pointer) for finding in report.findings] == [
        ("EMPIRICAL_POWER_BELOW_TARGET", "/metric_results/0/achieved_power"),
        ("EMPIRICAL_POWER_BELOW_TARGET", "/metric_results/1/achieved_power"),
    ]
    assert report == repeated
    assert all(finding.category == "statistics" for finding in report.findings)
    assert all(finding.blocking for finding in report.findings)


def test_serialized_profile_and_report_retain_aggregate_privacy_boundary() -> None:
    profile = EmpiricalPowerProfile.model_validate(_healthy_profile_data())
    report = preflight_empirical_power(_healthy_protocol(), profile)

    serialized = (profile.model_dump_json() + report.model_dump_json()).lower()
    for forbidden in (
        "subject_id",
        "event_id",
        "connection",
        "postgresql",
        "dsn",
        "raw_rows",
        "bootstrap_samples",
    ):
        assert forbidden not in serialized
