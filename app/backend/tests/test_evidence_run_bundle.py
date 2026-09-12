from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.abx import (
    AbxError,
    canonical_json_bytes,
    manifest_bundle_id,
    pack_bundle,
    verify_bundle,
    verify_logical_bundle,
)
from app.backend.app.evidence.run_abx import (
    EvidenceRunBundleError,
    EvidenceRunNotFoundError,
    LogicalAbxBundle,
    materialize_completed_run_logical_abx,
    publish_completed_run_abx,
)
from app.backend.app.evidence.runs import (
    CompletedEvidenceRun,
    EvidenceRunArtifact,
    create_completed_evidence_run,
    create_evidence_run_artifact,
)
from app.backend.tests.evidence_run_fixtures import completed_asos_run


class _StubRunStore:
    def __init__(
        self,
        run: CompletedEvidenceRun | None,
        *,
        failure: RuntimeError | None = None,
    ) -> None:
        self._run = run
        self._failure = failure
        self.lookups: list[str] = []

    def create(self, run: CompletedEvidenceRun) -> bool:
        del run
        raise AssertionError("publication must not create runs")

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        self.lookups.append(run_id)
        if self._failure is not None:
            raise self._failure
        return self._run


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _manifest_entry(artifact: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": artifact.path,
        "role": artifact.role,
        "media_type": artifact.media_type,
        "size": artifact.size,
        "digest": artifact.digest,
    }
    if artifact.schema_id is not None:
        entry["schema_id"] = artifact.schema_id
    return entry


def _rebuild_run(
    original: CompletedEvidenceRun,
    artifacts: tuple[EvidenceRunArtifact, ...],
) -> CompletedEvidenceRun:
    return create_completed_evidence_run(
        origin_job_id=original.origin_job_id,
        origin_job_revision=original.origin_job_revision,
        sealed_at=original.sealed_at,
        artifacts=artifacts,
    )


def _run_with_query_payload(payload: bytes) -> CompletedEvidenceRun:
    original = completed_asos_run()
    query = next(artifact for artifact in original.artifacts if artifact.role == "query")
    run_artifact = next(
        artifact for artifact in original.artifacts if artifact.role == "run"
    )
    query_digest = _sha256(payload)
    query_path = f"queries/{query_digest.removeprefix('sha256:')}.sql"
    run_document = cast(dict[str, Any], json.loads(run_artifact.payload))
    run_document["queries"][0]["statement_path"] = query_path
    run_document["queries"][0]["statement_digest"] = query_digest
    run_payload = canonical_json_bytes(run_document)

    artifacts = tuple(
        create_evidence_run_artifact(
            path=(
                query_path
                if artifact is query
                else artifact.path
            ),
            role=artifact.role,
            media_type=artifact.media_type,
            schema_id=artifact.schema_id,
            payload=(
                payload
                if artifact is query
                else run_payload
                if artifact is run_artifact
                else artifact.payload
            ),
        )
        for artifact in original.artifacts
    )
    return _rebuild_run(original, artifacts)


def _run_with_protocol_metric_version(version: str) -> CompletedEvidenceRun:
    original = completed_asos_run()
    protocol = next(
        artifact for artifact in original.artifacts if artifact.role == "protocol"
    )
    document = cast(dict[str, Any], json.loads(protocol.payload))
    document["metrics"]["primary"][0]["metric_version"] = version
    payload = canonical_json_bytes(document)
    artifacts = tuple(
        create_evidence_run_artifact(
            path=artifact.path,
            role=artifact.role,
            media_type=artifact.media_type,
            schema_id=artifact.schema_id,
            payload=payload if artifact is protocol else artifact.payload,
        )
        for artifact in original.artifacts
    )
    return _rebuild_run(original, artifacts)


def _write_and_pack(
    bundle: LogicalAbxBundle,
    logical_root: Path,
    destination: Path,
) -> dict[str, Any]:
    logical_root.mkdir()
    for member in bundle.members:
        target = logical_root / member.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(member.payload)
    return pack_bundle(logical_root, destination)


def _append_logical_artifact(
    bundle: LogicalAbxBundle,
    *,
    path: str,
    role: str,
    media_type: str,
    payload: bytes,
    schema_id: str | None = None,
) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    manifest = cast(dict[str, Any], json.loads(bundle.manifest_payload))
    entry: dict[str, Any] = {
        "path": path,
        "role": role,
        "media_type": media_type,
        "size": len(payload),
        "digest": _sha256(payload),
    }
    if schema_id is not None:
        entry["schema_id"] = schema_id
    entries = cast(list[dict[str, Any]], manifest["entries"])
    entries.append(entry)
    entries.sort(key=lambda item: cast(str, item["path"]))
    manifest["bundle_id"] = manifest_bundle_id(manifest)
    payloads_by_path = {
        member.path: member.payload for member in bundle.members[1:]
    }
    payloads_by_path[path] = payload
    members = tuple(
        (cast(str, item["path"]), payloads_by_path[cast(str, item["path"])])
        for item in entries
    )
    return canonical_json_bytes(manifest), members


def _write_raw_bundle(
    destination: Path,
    manifest_payload: bytes,
    members: tuple[tuple[str, bytes], ...],
) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_payload)
        for path, payload in members:
            archive.writestr(path, payload)


def _verification_codes(result: dict[str, Any]) -> set[str]:
    return {
        cast(str, error["code"])
        for error in cast(list[dict[str, Any]], result["errors"])
    }


def test_materializes_deterministic_verified_logical_members_from_exact_artifacts(
    tmp_path: Path,
) -> None:
    run = completed_asos_run()
    first_path = tmp_path / "first.tmk"
    second_path = tmp_path / "second.tmk"

    first = materialize_completed_run_logical_abx(run)
    second = materialize_completed_run_logical_abx(run)

    assert first == second
    assert first.run_id == run.run_id
    assert first.protocol_revision_id == run.protocol_revision_id
    assert first.created_at == run.sealed_at
    assert first.artifact_count == len(run.artifacts)
    assert tuple(member.path for member in first.members) == (
        "manifest.json",
        *(artifact.path for artifact in run.artifacts),
    )
    manifest = cast(dict[str, Any], json.loads(first.manifest_payload))
    assert first.manifest_payload == canonical_json_bytes(manifest)
    assert first.manifest_digest == _sha256(first.manifest_payload)
    assert manifest_bundle_id(manifest) == first.bundle_id
    assert manifest["created_at"] == run.sealed_at
    assert manifest["entries"] == [_manifest_entry(artifact) for artifact in run.artifacts]
    assert not (
        {"origin_job_id", "origin_job_revision", "record_digest", "extensions"}
        & set(manifest)
    )

    first_result = _write_and_pack(first, tmp_path / "logical-first", first_path)
    second_result = _write_and_pack(second, tmp_path / "logical-second", second_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_result == verify_bundle(first_path)
    assert second_result == verify_bundle(second_path)
    assert first_result["archive"] == str(first_path)
    assert second_result["archive"] == str(second_path)
    assert {
        key: value for key, value in first_result.items() if key != "archive"
    } == {key: value for key, value in second_result.items() if key != "archive"}
    assert first_result["valid"] is True
    assert first_result["bundle_id"] == first.bundle_id
    with zipfile.ZipFile(first_path) as archive:
        for artifact in run.artifacts:
            assert archive.read(artifact.path) == artifact.payload

    assert LogicalAbxBundle.model_validate_json(first.model_dump_json()) == first
    with pytest.raises(ValidationError, match="frozen"):
        first.bundle_id = "sha256:" + "0" * 64  # type: ignore[misc]


def test_publishes_one_persisted_run_as_deterministic_exact_archives(
    tmp_path: Path,
) -> None:
    run = completed_asos_run()
    store = _StubRunStore(run)
    first_path = tmp_path / "first.tmk"
    second_path = tmp_path / "second.tmk"

    first_result = publish_completed_run_abx(
        store,
        run_id=run.run_id,
        destination=first_path,
    )
    second_result = publish_completed_run_abx(
        store,
        run_id=run.run_id,
        destination=second_path,
    )

    assert store.lookups == [run.run_id, run.run_id]
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_result == verify_bundle(first_path)
    assert second_result == verify_bundle(second_path)
    assert first_result["valid"] is second_result["valid"] is True
    assert first_result["bundle_id"] == second_result["bundle_id"]
    with zipfile.ZipFile(first_path) as archive:
        assert archive.namelist() == [
            "manifest.json",
            *(artifact.path for artifact in run.artifacts),
        ]
        for artifact in run.artifacts:
            assert archive.read(artifact.path) == artifact.payload


def test_publisher_distinguishes_a_missing_run_without_creating_output(
    tmp_path: Path,
) -> None:
    store = _StubRunStore(None)
    destination = tmp_path / "missing.tmk"

    with pytest.raises(EvidenceRunNotFoundError, match="run_missing"):
        publish_completed_run_abx(
            store,
            run_id="run_missing",
            destination=destination,
        )

    assert store.lookups == ["run_missing"]
    assert not destination.exists()


def test_publisher_fails_before_lookup_when_destination_already_exists(
    tmp_path: Path,
) -> None:
    run = completed_asos_run()
    store = _StubRunStore(run)
    destination = tmp_path / "existing.tmk"
    destination.write_bytes(b"keep me")

    with pytest.raises(AbxError, match="already exists"):
        publish_completed_run_abx(
            store,
            run_id=run.run_id,
            destination=destination,
        )

    assert store.lookups == []
    assert destination.read_bytes() == b"keep me"


def test_publisher_does_not_mask_store_failures(tmp_path: Path) -> None:
    failure = RuntimeError("hydration failed")
    store = _StubRunStore(None, failure=failure)

    with pytest.raises(RuntimeError) as captured:
        publish_completed_run_abx(
            store,
            run_id="run_corrupt",
            destination=tmp_path / "corrupt.tmk",
        )

    assert captured.value is failure


def test_materializer_revalidates_the_completed_run() -> None:
    invalid = completed_asos_run().model_copy(
        update={"record_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(EvidenceRunBundleError, match="completed run revalidation"):
        materialize_completed_run_logical_abx(invalid)


def test_materializer_applies_privacy_policy_to_exact_members() -> None:
    run = _run_with_query_payload(
        b"SELECT 'postgresql://reader:secret@db.example/evidence';\n"
    )
    with pytest.raises(EvidenceRunBundleError, match="sensitive_value"):
        materialize_completed_run_logical_abx(run)


def test_materializer_applies_full_protocol_metric_reference_checks() -> None:
    run = _run_with_protocol_metric_version("9.9.9")

    with pytest.raises(EvidenceRunBundleError, match="metric_definition_mismatch"):
        materialize_completed_run_logical_abx(run)


def test_materializer_rejects_untrusted_embedded_schema_payload() -> None:
    original = completed_asos_run()
    schema = create_evidence_run_artifact(
        path="schemas/common.schema.json",
        role="schema",
        media_type="application/schema+json",
        schema_id="urn:evidenceos:abx:schema:0.1:common",
        payload=b"{}",
    )
    run = _rebuild_run(original, (*original.artifacts, schema))

    with pytest.raises(EvidenceRunBundleError, match="embedded_schema_mismatch"):
        materialize_completed_run_logical_abx(run)


def test_materializer_counts_manifest_against_member_limit() -> None:
    original = completed_asos_run()
    schemas = tuple(
        create_evidence_run_artifact(
            path=f"schemas/a{index:03d}.schema.json",
            role="schema",
            media_type="application/schema+json",
            schema_id="urn:evidenceos:abx:schema:0.1:common",
            payload=b"{}",
        )
        for index in range(500)
    )
    run = _rebuild_run(original, (*original.artifacts, *schemas))

    with pytest.raises(EvidenceRunBundleError, match="member count"):
        materialize_completed_run_logical_abx(run)


@pytest.mark.parametrize(
    ("extra_role", "expected_code"),
    [
        ("decision", "decision_reference"),
        ("metric", "run_reference_set"),
        ("query", "run_reference_set"),
    ],
)
def test_logical_and_archive_verifiers_reject_unreferenced_artifacts(
    tmp_path: Path,
    extra_role: str,
    expected_code: str,
) -> None:
    run = completed_asos_run()
    bundle = materialize_completed_run_logical_abx(run)
    run_document = cast(
        dict[str, Any],
        json.loads(next(item.payload for item in run.artifacts if item.role == "run")),
    )

    if extra_role == "decision":
        document = {
            "schema_version": "0.1.0",
            "decision_id": "decision_unreferenced",
            "content_digest": "sha256:" + "0" * 64,
            "run_id": run.run_id,
            "protocol_revision_id": run.protocol_revision_id,
            "policy": {
                "policy_id": "test_policy",
                "version": "1",
                "minimum_worthwhile_effect": 0.0,
                "harm_rule_codes": [],
                "approval_roles": ["product_owner"],
            },
            "evidence": {
                "estimate_ids": [run_document["estimate_ids"][0]],
                "finding_ids": [],
            },
            "proposed_verdict": "inconclusive",
            "human_verdict": "inconclusive",
            "rationale": "Verifier closure regression fixture.",
            "state": "proposed",
            "decided_at": run.completed_at,
            "decided_by": {"actor_ref": "owner_test", "role": "product_owner"},
            "approvals": [],
            "extensions": {},
        }
        manifest_payload, members = _append_logical_artifact(
            bundle,
            path="decision/decision.json",
            role="decision",
            media_type="application/json",
            schema_id="urn:evidenceos:abx:schema:0.1:decision",
            payload=canonical_json_bytes(document),
        )
    elif extra_role == "metric":
        metric = next(item for item in run.artifacts if item.role == "metric")
        document = cast(dict[str, Any], json.loads(metric.payload))
        document["metric_id"] = "metric_unreferenced"
        document["name"] = "Unreferenced verifier fixture"
        manifest_payload, members = _append_logical_artifact(
            bundle,
            path="metrics/metric_unreferenced.json",
            role="metric",
            media_type="application/json",
            schema_id="urn:evidenceos:abx:schema:0.1:metric",
            payload=canonical_json_bytes(document),
        )
    else:
        payload = b"SELECT 1;\n"
        digest = _sha256(payload).removeprefix("sha256:")
        manifest_payload, members = _append_logical_artifact(
            bundle,
            path=f"queries/{digest}.sql",
            role="query",
            media_type="application/sql",
            payload=payload,
        )

    logical_result = verify_logical_bundle(manifest_payload, members)
    archive_path = tmp_path / f"extra-{extra_role}.tmk"
    _write_raw_bundle(archive_path, manifest_payload, members)
    archive_result = verify_bundle(archive_path)

    assert logical_result["valid"] is False
    assert archive_result["valid"] is False
    assert expected_code in _verification_codes(logical_result)
    assert expected_code in _verification_codes(archive_result)
    assert logical_result["verdicts"] == archive_result["verdicts"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("order", "member_order_mismatch"),
        ("missing", "missing_member"),
        ("unlisted", "unlisted_member"),
        ("size", "size_mismatch"),
        ("digest", "digest_mismatch"),
        ("duplicate", "duplicate_member"),
        ("normalized", "normalized_name_collision"),
    ],
)
def test_logical_verifier_rejects_exact_member_correspondence_tampering(
    mutation: str,
    expected_code: str,
) -> None:
    bundle = materialize_completed_run_logical_abx(completed_asos_run())
    manifest = cast(dict[str, Any], json.loads(bundle.manifest_payload))
    manifest_payload = bundle.manifest_payload
    members = tuple((member.path, member.payload) for member in bundle.members[1:])

    if mutation == "order":
        members = (members[1], members[0], *members[2:])
    elif mutation == "missing":
        members = members[:-1]
    elif mutation == "unlisted":
        members = (*members, ("rendered/unlisted.txt", b"unlisted\n"))
    elif mutation in {"size", "digest"}:
        entry = cast(list[dict[str, Any]], manifest["entries"])[0]
        if mutation == "size":
            entry["size"] = cast(int, entry["size"]) + 1
        else:
            entry["digest"] = "sha256:" + "0" * 64
        manifest["bundle_id"] = manifest_bundle_id(manifest)
        manifest_payload = canonical_json_bytes(manifest)
    elif mutation == "duplicate":
        members = (*members, members[0])
    else:
        path, payload = members[0]
        colliding_path = path[0].swapcase() + path[1:]
        members = (*members, (colliding_path, payload))

    result = verify_logical_bundle(manifest_payload, members)

    assert result["valid"] is False
    assert expected_code in _verification_codes(result)
