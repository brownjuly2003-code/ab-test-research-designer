from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.preflight import (
    ObservedTelemetryProfile,
    ProtocolPreflightReport,
    preflight_observed_telemetry,
    preflight_protocol,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "evidence"
PROFILE_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_observed_telemetry_profile.json"
PROTOCOL_FIXTURE_PATH = FIXTURE_DIRECTORY / "healthy_protocol.json"
ProfileMutation = Callable[[dict[str, Any]], None]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _healthy_profile_data() -> dict[str, Any]:
    return _load_json(PROFILE_FIXTURE_PATH)


def _healthy_protocol() -> dict[str, Any]:
    return _load_json(PROTOCOL_FIXTURE_PATH)


def _set_profile_count(field: str, value: int) -> ProfileMutation:
    def mutate(profile: dict[str, Any]) -> None:
        profile[field] = value

    return mutate


def _append_unknown_schema_version(profile: dict[str, Any]) -> None:
    profile["schema_versions"].append(
        {"event_type": "checkout_completed", "version": "v2"}
    )


def test_healthy_aggregate_profile_is_immutable_deterministic_and_ready() -> None:
    profile_data = _healthy_profile_data()
    profile = ObservedTelemetryProfile.model_validate(profile_data)
    protocol = _healthy_protocol()
    original_protocol = deepcopy(protocol)

    report = preflight_observed_telemetry(protocol, profile)
    repeated = preflight_observed_telemetry(protocol, profile)

    assert isinstance(report, ProtocolPreflightReport)
    assert report == repeated
    assert report.protocol_digest == preflight_protocol(protocol).protocol_digest
    assert report.findings == ()
    assert report.ready
    assert protocol == original_protocol
    assert isinstance(profile.schema_versions, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        profile.duplicate_event_count = 1
    with pytest.raises(ValidationError, match="frozen"):
        profile.schema_versions[0].version = "v2"


def test_profile_rejects_negative_counts_extra_raw_data_and_connection_details() -> None:
    negative = _healthy_profile_data()
    negative["duplicate_event_count"] = -1
    with pytest.raises(ValidationError):
        ObservedTelemetryProfile.model_validate(negative)

    raw = _healthy_profile_data()
    raw["raw_rows"] = [{"subject_id": "subject-123", "event_id": "event-456"}]
    raw["connection_details"] = {"dsn": "postgresql://private"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ObservedTelemetryProfile.model_validate(raw)

    nested_extra = _healthy_profile_data()
    nested_extra["schema_versions"][0]["event_ids"] = ["event-456"]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ObservedTelemetryProfile.model_validate(nested_extra)


def test_observed_schema_declarations_match_protocol_identifier_limits() -> None:
    invalid_event_type = _healthy_profile_data()
    invalid_event_type["schema_versions"][0]["event_type"] = "postgresql://private"
    with pytest.raises(ValidationError):
        ObservedTelemetryProfile.model_validate(invalid_event_type)

    oversized_version = _healthy_profile_data()
    oversized_version["schema_versions"][0]["version"] = "v" * 65
    with pytest.raises(ValidationError):
        ObservedTelemetryProfile.model_validate(oversized_version)


@pytest.mark.parametrize(
    ("mutate", "code", "pointer"),
    [
        (
            _set_profile_count("outcome_before_exposure_count", 1),
            "TELEMETRY_OUTCOME_BEFORE_EXPOSURE",
            "/outcome_before_exposure_count",
        ),
        (
            _set_profile_count("duplicate_event_count", 1),
            "TELEMETRY_DUPLICATE_EVENTS",
            "/duplicate_event_count",
        ),
        (
            _set_profile_count("unlinked_subject_count", 1),
            "TELEMETRY_UNLINKED_SUBJECTS",
            "/unlinked_subject_count",
        ),
        (
            _append_unknown_schema_version,
            "TELEMETRY_SCHEMA_VERSION_UNKNOWN",
            "/schema_versions/3/version",
        ),
        (
            _set_profile_count("events_beyond_max_lateness_count", 1),
            "TELEMETRY_MAX_LATENESS_EXCEEDED",
            "/events_beyond_max_lateness_count",
        ),
    ],
    ids=[
        "outcome-before-exposure",
        "duplicate-events",
        "unlinked-subjects",
        "unknown-schema-version",
        "beyond-max-lateness",
    ],
)
def test_each_observed_data_quality_fault_is_detected_in_isolation(
    mutate: ProfileMutation,
    code: str,
    pointer: str,
) -> None:
    profile_data = _healthy_profile_data()
    mutate(profile_data)

    report = preflight_observed_telemetry(
        _healthy_protocol(),
        ObservedTelemetryProfile.model_validate(profile_data),
    )

    assert [(finding.code, finding.json_pointer) for finding in report.findings] == [
        (code, pointer)
    ]
    assert not report.ready


def test_all_observed_data_quality_failures_are_blocking_sorted_and_stable() -> None:
    profile_data = _healthy_profile_data()
    profile_data.update(
        {
            "outcome_before_exposure_count": 7,
            "duplicate_event_count": 5,
            "unlinked_subject_count": 3,
            "events_beyond_max_lateness_count": 2,
        }
    )
    profile_data["schema_versions"].append(
        {"event_type": "checkout_completed", "version": "v2"}
    )
    profile = ObservedTelemetryProfile.model_validate(profile_data)
    protocol = _healthy_protocol()

    report = preflight_observed_telemetry(protocol, profile)
    repeated = preflight_observed_telemetry(protocol, profile)

    expected = [
        ("TELEMETRY_DUPLICATE_EVENTS", "/duplicate_event_count"),
        (
            "TELEMETRY_MAX_LATENESS_EXCEEDED",
            "/events_beyond_max_lateness_count",
        ),
        (
            "TELEMETRY_OUTCOME_BEFORE_EXPOSURE",
            "/outcome_before_exposure_count",
        ),
        ("TELEMETRY_SCHEMA_VERSION_UNKNOWN", "/schema_versions/3/version"),
        ("TELEMETRY_UNLINKED_SUBJECTS", "/unlinked_subject_count"),
    ]
    assert [(finding.code, finding.json_pointer) for finding in report.findings] == expected
    assert report == repeated
    assert not report.ready
    assert all(finding.category == "telemetry" for finding in report.findings)
    assert all(finding.blocking for finding in report.findings)


def test_serialized_profile_and_report_contain_no_raw_identifiers_or_connections() -> None:
    profile = ObservedTelemetryProfile.model_validate(_healthy_profile_data())
    report = preflight_observed_telemetry(_healthy_protocol(), profile)

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
