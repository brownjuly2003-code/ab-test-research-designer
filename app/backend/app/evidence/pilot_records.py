"""Privacy-bounded records for externally observed Trialmark pilot sessions."""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.abx import load_abx_document, verify_bundle

PilotOutcome = Literal["completed", "incomplete"]
PilotReuseKind = Literal["second_run", "evidence_reopen"]

_ANONYMOUS_REF_PATTERN = r"^anon_[0-9a-f]{16}$"
_OPAQUE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
_UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_MAX_RECORD_BYTES = 64 * 1024
_REQUIRED_VERDICTS = (
    "integrity",
    "schema_conformance",
    "reference_integrity",
    "lineage",
    "privacy_policy",
)


class PilotRecordValidationError(ValueError):
    """Raised when a pilot record or cited bundle violates the pilot contract."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PilotRatio(_FrozenModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_ratio(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("measurement numerator cannot exceed its denominator")
        return self


class PilotMeasurements(_FrozenModel):
    completed_cycles: PilotRatio
    bundle_privacy: PilotRatio
    estimate_lineage: PilotRatio


class PilotReuse(_FrozenModel):
    observed: bool
    kind: PilotReuseKind | None = None
    observed_at: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.observed != (self.kind is not None and self.observed_at is not None):
            raise ValueError("reuse evidence must provide both kind and observed_at")
        if self.observed_at is not None:
            _parse_timestamp(self.observed_at)
        return self


class PilotBundleCensus(_FrozenModel):
    bundle_id: str = Field(pattern=_SHA256_PATTERN)
    run_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    artifact_count: int = Field(ge=1)
    source_artifact_count: Literal[1]
    estimate_count: Literal[1]
    row_level_artifact_count: Literal[0]
    aggregate_only: Literal[True]
    evidence_type: Literal["external_pilot"]
    partner_approved: Literal[True]
    lineage_verdict: Literal["pass"]
    privacy_verdict: Literal["pass"]


class PilotSessionRecord(_FrozenModel):
    schema_version: Literal["1"]
    participant_ref: str = Field(pattern=_ANONYMOUS_REF_PATTERN)
    session_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    outcome: PilotOutcome
    external_practitioner: Literal[True]
    practitioner_owned_source: Literal[True]
    source_kind: Literal["aggregate_csv"]
    source_rows_copied: Literal[0]
    source_ready_at: str
    bundle_ready_at: str | None
    time_to_bundle_seconds: int | None = Field(ge=0)
    bundle: PilotBundleCensus | None
    reuse: PilotReuse
    measurements: PilotMeasurements
    record_digest: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        source_ready = _parse_timestamp(self.source_ready_at)
        if self.session_date != source_ready.date().isoformat():
            raise ValueError("session_date must match source_ready_at")
        if self.reuse.observed_at is not None:
            if _parse_timestamp(self.reuse.observed_at) < source_ready:
                raise ValueError("reuse evidence cannot predate source readiness")

        if self.outcome == "completed":
            if self.bundle_ready_at is None or self.bundle is None:
                raise ValueError("completed pilot requires a bundle and ready timestamp")
            bundle_ready = _parse_timestamp(self.bundle_ready_at)
            elapsed = int((bundle_ready - source_ready).total_seconds())
            if elapsed < 0 or self.time_to_bundle_seconds != elapsed:
                raise ValueError("time_to_bundle_seconds is inconsistent")
            expected_measurements = PilotMeasurements(
                completed_cycles=PilotRatio(numerator=1, denominator=1),
                bundle_privacy=PilotRatio(numerator=1, denominator=1),
                estimate_lineage=PilotRatio(
                    numerator=self.bundle.estimate_count,
                    denominator=self.bundle.estimate_count,
                ),
            )
        else:
            if any(
                value is not None
                for value in (
                    self.bundle_ready_at,
                    self.time_to_bundle_seconds,
                    self.bundle,
                )
            ):
                raise ValueError("incomplete pilot cannot claim a completed bundle")
            expected_measurements = PilotMeasurements(
                completed_cycles=PilotRatio(numerator=0, denominator=1),
                bundle_privacy=PilotRatio(numerator=0, denominator=0),
                estimate_lineage=PilotRatio(numerator=0, denominator=0),
            )
        if self.measurements != expected_measurements:
            raise ValueError("pilot measurements are inconsistent")

        content = self.model_dump(mode="json", exclude={"record_digest"})
        if self.record_digest != sha256_hex(canonical_json_bytes(content)):
            raise ValueError("pilot record digest is inconsistent")
        return self


def _parse_timestamp(value: str) -> datetime:
    if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("pilot timestamps must use second-precision UTC RFC 3339")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("pilot timestamp is not a real UTC date-time") from None


def _validated_record(value: object) -> PilotSessionRecord:
    try:
        return PilotSessionRecord.model_validate(value)
    except (TypeError, ValueError, ValidationError):
        raise PilotRecordValidationError(
            "pilot record does not satisfy the privacy-safe schema"
        ) from None


def _bundle_documents(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest = load_abx_document(
                archive.read("manifest.json"),
                label="manifest.json",
            )
            entries = cast(list[dict[str, Any]], manifest["entries"])
            source_entries = [entry for entry in entries if entry["role"] == "source"]
            run_entries = [entry for entry in entries if entry["role"] == "run"]
            if len(source_entries) != 1 or len(run_entries) != 1:
                raise PilotRecordValidationError(
                    "pilot bundle must contain exactly one source and one run"
                )
            source_document = load_abx_document(
                archive.read(cast(str, source_entries[0]["path"])),
                label="pilot source artifact",
            )
            run_document = load_abx_document(
                archive.read(cast(str, run_entries[0]["path"])),
                label="pilot run artifact",
            )
    except PilotRecordValidationError:
        raise
    except (KeyError, OSError, ValueError, zipfile.BadZipFile):
        raise PilotRecordValidationError(
            "pilot bundle artifacts could not be inspected"
        ) from None
    return source_document, run_document, entries


def _extension(value: object, key: str) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    extension = value.get(key)
    return extension if isinstance(extension, Mapping) else None


def inspect_external_pilot_bundle(path: Path | str) -> PilotBundleCensus:
    """Verify and summarize one partner-approved aggregate-only pilot bundle."""

    bundle_path = Path(path)
    verification = verify_bundle(bundle_path)
    verdicts = verification.get("verdicts")
    if not verification.get("valid") or not isinstance(verdicts, Mapping):
        raise PilotRecordValidationError(
            "pilot bundle must pass offline ABX verification"
        )
    if any(verdicts.get(dimension) != "pass" for dimension in _REQUIRED_VERDICTS):
        raise PilotRecordValidationError(
            "pilot bundle must pass privacy and lineage verification"
        )

    source, run, entries = _bundle_documents(bundle_path)
    source_profile = _extension(
        source.get("extensions"),
        "trialmark.aggregate-binary",
    )
    run_profile = _extension(
        run.get("extensions"),
        "trialmark.aggregate-binary",
    )
    if source_profile is None or run_profile is None:
        raise PilotRecordValidationError(
            "pilot bundle is not an external aggregate pilot"
        )
    if not (
        source_profile.get("aggregate_only") is True
        and source_profile.get("evidence_type") == "external_pilot"
        and source_profile.get("partner_approved") is True
        and source_profile.get("telemetry_profile_source") == "upstream_asserted"
        and run_profile.get("aggregate_only") is True
        and run_profile.get("evidence_type") == "external_pilot"
    ):
        raise PilotRecordValidationError(
            "pilot bundle external aggregate claims are incomplete"
        )
    roles = Counter(cast(str, entry["role"]) for entry in entries)
    if (
        run.get("kind") != "analysis"
        or run.get("status") != "succeeded"
        or roles["estimate"] != 1
        or len(cast(list[object], run.get("estimate_ids", []))) != 1
    ):
        raise PilotRecordValidationError(
            "completed pilot bundle must contain one lineaged estimate"
        )
    if any(
        cast(str, entry["path"]).lower().endswith((".csv", ".parquet"))
        for entry in entries
    ):
        raise PilotRecordValidationError(
            "pilot bundle must not contain row-level source artifacts"
        )

    try:
        return PilotBundleCensus(
            bundle_id=cast(str, verification["bundle_id"]),
            run_id=cast(str, verification["run_id"]),
            artifact_count=len(entries),
            source_artifact_count=1,
            estimate_count=1,
            row_level_artifact_count=0,
            aggregate_only=True,
            evidence_type="external_pilot",
            partner_approved=True,
            lineage_verdict="pass",
            privacy_verdict="pass",
        )
    except ValidationError:
        raise PilotRecordValidationError(
            "pilot bundle identity does not satisfy the record schema"
        ) from None


def create_pilot_session_record(
    *,
    participant_ref: str,
    source_ready_at: str,
    outcome: PilotOutcome,
    bundle_path: Path | str | None = None,
    bundle_ready_at: str | None = None,
    reuse_kind: PilotReuseKind | None = None,
    reuse_observed_at: str | None = None,
) -> PilotSessionRecord:
    """Create one anonymous record without accepting source paths or rows."""

    try:
        source_ready = _parse_timestamp(source_ready_at)
    except ValueError:
        raise PilotRecordValidationError("source_ready_at is invalid") from None
    if outcome not in {"completed", "incomplete"}:
        raise PilotRecordValidationError("pilot outcome is unsupported")
    if (reuse_kind is None) != (reuse_observed_at is None):
        raise PilotRecordValidationError(
            "reuse evidence requires both kind and observed_at"
        )

    bundle: PilotBundleCensus | None
    time_to_bundle_seconds: int | None
    if outcome == "completed":
        if bundle_path is None or bundle_ready_at is None:
            raise PilotRecordValidationError(
                "completed pilot requires --bundle and --bundle-ready-at"
            )
        try:
            bundle_ready = _parse_timestamp(bundle_ready_at)
        except ValueError:
            raise PilotRecordValidationError("bundle_ready_at is invalid") from None
        elapsed = int((bundle_ready - source_ready).total_seconds())
        if elapsed < 0:
            raise PilotRecordValidationError(
                "bundle_ready_at cannot predate source_ready_at"
            )
        bundle = inspect_external_pilot_bundle(bundle_path)
        time_to_bundle_seconds = elapsed
        measurements = {
            "completed_cycles": {"numerator": 1, "denominator": 1},
            "bundle_privacy": {"numerator": 1, "denominator": 1},
            "estimate_lineage": {
                "numerator": bundle.estimate_count,
                "denominator": bundle.estimate_count,
            },
        }
    else:
        if bundle_path is not None or bundle_ready_at is not None:
            raise PilotRecordValidationError(
                "incomplete pilot cannot claim a completed bundle"
            )
        bundle = None
        time_to_bundle_seconds = None
        measurements = {
            "completed_cycles": {"numerator": 0, "denominator": 1},
            "bundle_privacy": {"numerator": 0, "denominator": 0},
            "estimate_lineage": {"numerator": 0, "denominator": 0},
        }

    content: dict[str, Any] = {
        "schema_version": "1",
        "participant_ref": participant_ref,
        "session_date": source_ready.date().isoformat(),
        "outcome": outcome,
        "external_practitioner": True,
        "practitioner_owned_source": True,
        "source_kind": "aggregate_csv",
        "source_rows_copied": 0,
        "source_ready_at": source_ready_at,
        "bundle_ready_at": bundle_ready_at,
        "time_to_bundle_seconds": time_to_bundle_seconds,
        "bundle": None if bundle is None else bundle.model_dump(mode="json"),
        "reuse": {
            "observed": reuse_kind is not None,
            "kind": reuse_kind,
            "observed_at": reuse_observed_at,
        },
        "measurements": measurements,
    }
    content["record_digest"] = sha256_hex(canonical_json_bytes(content))
    return _validated_record(content)


def render_pilot_record(record: PilotSessionRecord) -> bytes:
    """Render the only accepted Markdown representation of a pilot record."""

    document = record.model_dump(mode="json")
    body = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (
        f"# External pilot session `{record.participant_ref}`\n\n"
        "This record intentionally contains no participant identity, organization, "
        "source path, or source rows.\n\n"
        f"```json\n{body}\n```\n"
    ).encode()


def _expected_filename(record: PilotSessionRecord) -> str:
    return f"{record.session_date}-{record.participant_ref}.md"


def write_pilot_record(
    record: PilotSessionRecord,
    destination: Path | str,
) -> Path:
    """Write one canonical record without overwriting an existing observation."""

    path = Path(destination)
    if path.name != _expected_filename(record):
        raise PilotRecordValidationError(
            "pilot record filename must be <date>-<anon>.md"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = render_pilot_record(record)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise PilotRecordValidationError("pilot record already exists") from None
    return path


def load_pilot_record(path: Path | str) -> PilotSessionRecord:
    """Load, validate, and canonicalize one privacy-safe pilot Markdown file."""

    record_path = Path(path)
    if record_path.is_symlink() or not record_path.is_file():
        raise PilotRecordValidationError("pilot record must be a regular file")
    payload = record_path.read_bytes()
    if len(payload) > _MAX_RECORD_BYTES:
        raise PilotRecordValidationError("pilot record exceeds the size limit")
    marker = b"```json\n"
    if payload.count(marker) != 1 or payload.count(b"\n```\n") != 1:
        raise PilotRecordValidationError("pilot record Markdown framing is invalid")
    _, document_bytes = payload.split(marker, 1)
    document_bytes, _ = document_bytes.split(b"\n```\n", 1)
    try:
        document = load_ijson_object(document_bytes)
    except (TypeError, ValueError):
        raise PilotRecordValidationError("pilot record JSON is invalid") from None
    record = _validated_record(document)
    if record_path.name != _expected_filename(record):
        raise PilotRecordValidationError(
            "pilot record filename must be <date>-<anon>.md"
        )
    if payload != render_pilot_record(record):
        raise PilotRecordValidationError("pilot record Markdown is not canonical")
    return record


def summarize_pilot_record(
    record: PilotSessionRecord,
    path: Path | str,
) -> dict[str, Any]:
    """Return the bounded CLI result for a validated record."""

    return {
        "valid": True,
        "record": str(Path(path).resolve()),
        "record_digest": record.record_digest,
        "participant_ref": record.participant_ref,
        "outcome": record.outcome,
        "reuse_observed": record.reuse.observed,
    }


__all__ = [
    "PilotBundleCensus",
    "PilotMeasurements",
    "PilotOutcome",
    "PilotRatio",
    "PilotRecordValidationError",
    "PilotReuseKind",
    "PilotSessionRecord",
    "create_pilot_session_record",
    "inspect_external_pilot_bundle",
    "load_pilot_record",
    "render_pilot_record",
    "summarize_pilot_record",
    "write_pilot_record",
]
