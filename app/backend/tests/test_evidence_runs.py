from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    create_evidence_run_artifact,
)
from app.backend.tests.evidence_run_fixtures import completed_asos_run


def test_completed_run_is_canonical_deeply_immutable_and_json_round_trips() -> None:
    run = completed_asos_run()

    assert run.run_id == "run_asos_d53f0e_terminal"
    assert run.origin_job_id == "job_asos_d53f0e"
    assert run.origin_job_revision == 1
    assert run.status == "succeeded"
    assert run.kind == "analysis"
    assert run.required_capabilities == ("lineage-v1", "protocol-core")
    assert len(run.artifacts) == 12
    assert tuple(artifact.path for artifact in run.artifacts) == tuple(
        sorted(artifact.path for artifact in run.artifacts)
    )
    assert CompletedEvidenceRun.model_validate_json(run.model_dump_json()) == run

    with pytest.raises(ValidationError, match="frozen"):
        run.run_id = "run_changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        run.artifacts[0].payload = b"changed"  # type: ignore[misc]


def test_artifact_revalidates_exact_payload_size_digest_and_manifest_metadata() -> None:
    artifact = completed_asos_run().artifacts[0]
    tampered = artifact.model_dump(mode="python")
    tampered["payload"] = artifact.payload + b"\n"

    with pytest.raises(ValidationError, match="size|digest"):
        EvidenceRunArtifact.model_validate(tampered)

    with pytest.raises(ValidationError, match="manifest metadata"):
        create_evidence_run_artifact(
            path=artifact.path,
            role="report",
            media_type=artifact.media_type,
            schema_id=artifact.schema_id,
            payload=artifact.payload,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("run_id", "run_other", "run_id"),
        ("protocol_revision_id", "sha256:" + "0" * 64, "protocol_revision_id"),
        ("kind", "preflight", "kind"),
        ("completed_at", "2026-08-20T00:00:00Z", "completed_at"),
        ("runner_digest", "sha256:" + "0" * 64, "runner_digest"),
        ("sealed_at", "2026-08-20T00:00:00Z", "sealed_at"),
    ],
)
def test_completed_run_header_must_match_the_embedded_run_document(
    field: str,
    value: object,
    message: str,
) -> None:
    invalid = completed_asos_run().model_dump(mode="python")
    invalid[field] = value

    with pytest.raises(ValidationError, match=message):
        CompletedEvidenceRun.model_validate(invalid)


def test_completed_run_requires_a_closed_canonical_artifact_set() -> None:
    run = completed_asos_run()
    missing_source = run.model_dump(mode="python")
    missing_source["artifacts"] = tuple(
        artifact for artifact in run.artifacts if artifact.role != "source"
    )
    reversed_artifacts = run.model_dump(mode="python")
    reversed_artifacts["artifacts"] = tuple(reversed(run.artifacts))
    duplicate_path = run.model_dump(mode="python")
    duplicate_path["artifacts"] = (*run.artifacts, run.artifacts[0])

    with pytest.raises(ValidationError, match="source_snapshot_ids"):
        CompletedEvidenceRun.model_validate(missing_source)
    with pytest.raises(ValidationError, match="canonical path order"):
        CompletedEvidenceRun.model_validate(reversed_artifacts)
    with pytest.raises(ValidationError, match="duplicate artifact path"):
        CompletedEvidenceRun.model_validate(duplicate_path)

    unsupported_capability = run.model_dump(mode="python")
    unsupported_capability["required_capabilities"] = (
        "future-capability",
        "lineage-v1",
        "protocol-core",
    )
    with pytest.raises(ValidationError, match="unsupported capability"):
        CompletedEvidenceRun.model_validate(unsupported_capability)


def test_completed_run_rejects_a_non_succeeded_run_document() -> None:
    run = completed_asos_run()
    run_artifact = next(artifact for artifact in run.artifacts if artifact.role == "run")
    document: dict[str, Any] = json.loads(run_artifact.payload)
    document["status"] = "failed"
    payload = (json.dumps(document, sort_keys=True) + "\n").encode()

    with pytest.raises(ValidationError, match="ABX document"):
        create_evidence_run_artifact(
            path=run_artifact.path,
            role=run_artifact.role,
            media_type=run_artifact.media_type,
            schema_id=run_artifact.schema_id,
            payload=payload,
        )
