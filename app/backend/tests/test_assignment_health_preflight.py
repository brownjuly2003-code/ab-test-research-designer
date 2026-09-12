from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.evidence.preflight import (
    AssignmentHealthProfile,
    ProtocolPreflightReport,
    preflight_assignment_health,
    preflight_protocol,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "evidence"
PROTOCOL_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_protocol.json"


def _healthy_protocol() -> dict[str, Any]:
    value = json.loads(PROTOCOL_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _healthy_profile_data(
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frozen_protocol = protocol if protocol is not None else _healthy_protocol()
    return {
        "protocol_digest": preflight_protocol(frozen_protocol).protocol_digest,
        "random_seed": frozen_protocol["analysis"]["random_seed"],
        "synthetic_sample_size": 10_000,
        "interventions": [
            {
                "intervention_id": intervention["intervention_id"],
                "allocation": intervention["allocation"],
                "namespace": intervention["namespace"],
                "hash_version": intervention["hash_version"],
                "observed_count": 5_000,
            }
            for intervention in frozen_protocol["interventions"]
        ],
    }


def test_healthy_profile_is_immutable_deterministic_and_ready() -> None:
    protocol = _healthy_protocol()
    original_protocol = deepcopy(protocol)
    profile = AssignmentHealthProfile.model_validate(
        _healthy_profile_data(protocol)
    )

    report = preflight_assignment_health(protocol, profile)
    repeated = preflight_assignment_health(protocol, profile)

    assert isinstance(report, ProtocolPreflightReport)
    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert profile.protocol_digest == report.protocol_digest
    assert report.findings == ()
    assert report.ready
    assert protocol == original_protocol
    assert isinstance(profile.interventions, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        profile.random_seed = 7
    with pytest.raises(ValidationError, match="frozen"):
        profile.interventions[0].observed_count = 7


def test_profile_and_report_preserve_aggregate_privacy_boundary() -> None:
    raw = _healthy_profile_data()
    raw["sample_assignments"] = [
        {"subject_id": "subject-123", "variation_index": 0}
    ]
    raw["connection_details"] = {"dsn": "postgresql://private"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AssignmentHealthProfile.model_validate(raw)

    nested_raw = _healthy_profile_data()
    nested_raw["interventions"][0]["user_ids"] = ["subject-123"]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AssignmentHealthProfile.model_validate(nested_raw)

    profile = AssignmentHealthProfile.model_validate(_healthy_profile_data())
    report = preflight_assignment_health(_healthy_protocol(), profile)
    serialized = (profile.model_dump_json() + report.model_dump_json()).lower()
    for forbidden in (
        "sample_assignments",
        "subject_id",
        "user_id",
        "event_id",
        "connection",
        "postgresql",
        "dsn",
        "raw_rows",
        "select ",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("synthetic_sample_size",), 1),
        (("synthetic_sample_size",), 100_001),
        (("random_seed",), -1),
        (("random_seed",), 9_007_199_254_740_992),
        (("interventions", 0, "observed_count"), -1),
        (
            ("interventions", 0, "observed_count"),
            9_007_199_254_740_992,
        ),
    ],
    ids=[
        "undersized-synthetic-sample",
        "oversized-synthetic-sample",
        "negative-seed",
        "oversized-seed",
        "negative-observed-count",
        "oversized-observed-count",
    ],
)
def test_profile_rejects_out_of_bounds_aggregate_values(
    path: tuple[str | int, ...],
    value: int,
) -> None:
    profile_data = _healthy_profile_data()
    target: Any = profile_data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        AssignmentHealthProfile.model_validate(profile_data)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.__setitem__(
            "protocol_digest", "sha256:" + "9" * 64
        ),
        lambda profile: profile.__setitem__("random_seed", 7),
        lambda profile: profile["interventions"][0].__setitem__(
            "intervention_id", "other-control"
        ),
        lambda profile: profile["interventions"][0].__setitem__(
            "allocation", "0.4"
        ),
        lambda profile: profile["interventions"][0].__setitem__(
            "namespace", "other-namespace"
        ),
        lambda profile: profile["interventions"][0].__setitem__(
            "hash_version", "assignment_v2"
        ),
        lambda profile: profile["interventions"].reverse(),
    ],
    ids=[
        "protocol-digest",
        "random-seed",
        "intervention-id",
        "allocation",
        "namespace",
        "hash-version",
        "intervention-order",
    ],
)
def test_profile_must_exactly_match_ordered_protocol_bindings(
    mutate: Any,
) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    with pytest.raises(ValueError, match="does not match frozen protocol"):
        preflight_assignment_health(
            _healthy_protocol(),
            AssignmentHealthProfile.model_validate(profile_data),
        )


def test_profile_rejects_missing_intervention_structurally() -> None:
    profile_data = _healthy_profile_data()
    profile_data["interventions"].pop()

    with pytest.raises(ValidationError, match="at least 2 items"):
        AssignmentHealthProfile.model_validate(profile_data)


def test_profile_rejects_more_than_supported_interventions() -> None:
    profile_data = _healthy_profile_data()
    profile_data["interventions"] *= MAX_SUPPORTED_VARIANTS

    with pytest.raises(ValidationError):
        AssignmentHealthProfile.model_validate(profile_data)


def test_profile_rejects_zero_observed_total() -> None:
    profile_data = _healthy_profile_data()
    for intervention in profile_data["interventions"]:
        intervention["observed_count"] = 0

    with pytest.raises(ValidationError, match="positive total"):
        AssignmentHealthProfile.model_validate(profile_data)


def test_protocol_without_random_seed_is_an_explicit_contract_error() -> None:
    protocol = _healthy_protocol()
    del protocol["analysis"]["random_seed"]
    profile_data = _healthy_profile_data()
    profile_data["protocol_digest"] = preflight_protocol(protocol).protocol_digest

    with pytest.raises(ValueError, match=r"analysis\.random_seed.*required"):
        preflight_assignment_health(
            protocol,
            AssignmentHealthProfile.model_validate(profile_data),
        )


@pytest.mark.parametrize(
    ("versions", "message"),
    [
        (("assignment_v3", "assignment_v3"), "unsupported.*assignment_v3"),
        (("assignment_v1", "assignment_v2"), "mixed assignment hash versions"),
    ],
    ids=["unknown", "mixed"],
)
def test_unknown_or_mixed_hash_versions_fail_explicitly(
    versions: tuple[str, str],
    message: str,
) -> None:
    protocol = _healthy_protocol()
    for intervention, version in zip(
        protocol["interventions"], versions, strict=True
    ):
        intervention["hash_version"] = version
    profile_data = _healthy_profile_data(protocol)

    with pytest.raises(ValueError, match=message):
        preflight_assignment_health(
            protocol,
            AssignmentHealthProfile.model_validate(profile_data),
        )


@pytest.mark.parametrize(
    ("hash_version", "expected_codes"),
    [
        ("assignment_v1", ["ASSIGNMENT_SYNTHETIC_BALANCE_FAILED"]),
        ("assignment_v2", []),
    ],
)
def test_hash_version_mapping_controls_deterministic_preview(
    hash_version: str,
    expected_codes: list[str],
) -> None:
    protocol = _healthy_protocol()
    protocol["analysis"]["random_seed"] = 860
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = hash_version
    profile_data = _healthy_profile_data(protocol)
    profile_data["synthetic_sample_size"] = 12
    profile_data["interventions"][0]["observed_count"] = 600
    profile_data["interventions"][1]["observed_count"] = 600
    profile = AssignmentHealthProfile.model_validate(profile_data)

    report = preflight_assignment_health(protocol, profile)

    assert [finding.code for finding in report.findings] == expected_codes
    if expected_codes:
        finding = report.findings[0]
        assert finding.category == "statistics"
        assert finding.json_pointer == "/synthetic_sample_size"
        assert finding.blocking


@pytest.mark.parametrize("observed_counts", [(9_000, 1_000), (0, 10_000)])
def test_skewed_observed_counts_yield_only_observed_srm_blocker(
    observed_counts: tuple[int, int],
) -> None:
    protocol = _healthy_protocol()
    profile_data = _healthy_profile_data(protocol)
    for intervention, observed_count in zip(
        profile_data["interventions"], observed_counts, strict=True
    ):
        intervention["observed_count"] = observed_count
    profile = AssignmentHealthProfile.model_validate(profile_data)

    report = preflight_assignment_health(protocol, profile)
    repeated = preflight_assignment_health(protocol, profile)

    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert [
        (finding.code, finding.category, finding.json_pointer, finding.blocking)
        for finding in report.findings
    ] == [
        (
            "ASSIGNMENT_SAMPLE_RATIO_MISMATCH",
            "statistics",
            "/interventions",
            True,
        )
    ]
    assert not report.ready
