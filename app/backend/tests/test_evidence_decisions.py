"""Append-only human-decision contracts for completed evidence runs."""

from __future__ import annotations

import base64
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.runs import CompletedEvidenceRun, EvidenceRunStore
from app.backend.tests.evidence_run_fixtures import completed_asos_run


class MemoryEvidenceRunStore:
    def __init__(self) -> None:
        self.runs: dict[str, CompletedEvidenceRun] = {}

    def create(self, run: CompletedEvidenceRun) -> bool:
        if run.run_id in self.runs:
            return False
        self.runs[run.run_id] = run
        return True

    def get(self, run_id: str) -> CompletedEvidenceRun | None:
        return self.runs.get(run_id)


def _document(run: CompletedEvidenceRun, role: str) -> dict[str, Any]:
    artifact = next(artifact for artifact in run.artifacts if artifact.role == role)
    return load_ijson_object(artifact.payload)


def _decision_statement(
    run: CompletedEvidenceRun,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    artifact = next(artifact for artifact in run.artifacts if artifact.role == "decision")
    envelope = load_ijson_object(artifact.payload)
    statement_payload = base64.b64decode(envelope["payload"], validate=True)
    statement = load_ijson_object(statement_payload)
    assert canonical_json_bytes(statement) == statement_payload
    return envelope, statement, statement["predicate"]


def test_human_decisions_create_verified_append_only_child_runs(
    tmp_path: Path,
) -> None:
    from app.backend.app.evidence.abx import (
        manifest_bundle_id,
        verify_bundle,
        verify_logical_bundle,
    )
    from app.backend.app.evidence.decisions import record_human_decision
    from app.backend.app.evidence.run_abx import (
        materialize_completed_run_logical_abx,
        publish_completed_run_abx,
    )

    store: EvidenceRunStore = MemoryEvidenceRunStore()
    parent = completed_asos_run()
    assert store.create(parent) is True
    parent_bundle = materialize_completed_run_logical_abx(parent)
    parent_snapshot = parent.model_dump(mode="python", round_trip=True)
    principal = SimpleNamespace(actor_ref="owner_01", role="benchmark_reviewer")
    first_time = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)
    second_time = datetime(2026, 9, 1, 15, 1, tzinfo=UTC)

    with patch(
        "app.backend.app.evidence.decisions.datetime"
    ) as datetime_class:
        datetime_class.now.side_effect = [first_time, second_time]
        approved = record_human_decision(
            parent.run_id,
            principal,
            "ship",
            "The verified effect meets the protocol threshold and is approved.",
            out_store=store,
        )
        rejected = record_human_decision(
            parent.run_id,
            principal,
            "hold",
            "The evidence remains useful, but rollout is held for review.",
            out_store=store,
        )

    assert approved.run_id != parent.run_id
    assert rejected.run_id not in {parent.run_id, approved.run_id}
    assert store.get(parent.run_id) is parent
    assert parent.model_dump(mode="python", round_trip=True) == parent_snapshot
    assert store.get(approved.run_id) is approved
    assert store.get(rejected.run_id) is rejected

    approved_run = _document(approved, "run")
    approved_envelope, approved_statement, approved_decision = _decision_statement(approved)
    rejected_envelope, rejected_statement, rejected_decision = _decision_statement(rejected)
    assert approved_run["parent_run_id"] == parent.run_id
    assert approved_envelope == {
        "payload": approved_envelope["payload"],
        "payloadType": "application/vnd.in-toto+json",
        "signatures": [],
    }
    assert approved_statement["_type"] == "https://in-toto.io/Statement/v1"
    assert approved_statement["predicateType"] == (
        "https://trialmark.dev/attestation/decision/v1"
    )
    assert approved_statement["subject"] == [
        {
            "name": "trialmark-bundle",
            "digest": {"sha256": parent_bundle.bundle_id.removeprefix("sha256:")},
        }
    ]
    assert rejected_envelope["payloadType"] == approved_envelope["payloadType"]
    assert rejected_statement["subject"] == approved_statement["subject"]
    assert approved_decision["cites_bundle_id"] == parent_bundle.bundle_id
    assert approved_decision["human_verdict"] == "ship"
    assert approved_decision["state"] == "approved"
    assert approved_decision["decided_at"] == "2026-09-01T15:00:00Z"
    # SimpleNamespace states a role without a credential behind it, which is
    # exactly what "asserted" means.
    assert approved_decision["decided_by"] == {
        "actor_ref": "owner_01",
        "role": "benchmark_reviewer",
        "role_source": "asserted",
    }
    assert rejected_decision["human_verdict"] == "hold"
    assert rejected_decision["state"] == "rejected"
    approved_report = next(
        artifact.payload.decode("utf-8")
        for artifact in approved.artifacts
        if artifact.role == "report"
    )
    rejected_report = next(
        artifact.payload.decode("utf-8")
        for artifact in rejected.artifacts
        if artifact.role == "report"
    )
    assert approved.run_id in approved_report
    assert "human_verdict=ship" in approved_report
    assert "The verified effect meets the protocol threshold and is approved." in approved_report
    assert rejected.run_id in rejected_report
    assert "human_verdict=hold" in rejected_report
    assert approved_report != rejected_report

    destination = tmp_path / "approved.tmk"
    published = publish_completed_run_abx(
        store,
        run_id=approved.run_id,
        destination=destination,
    )
    verified = verify_bundle(destination)
    assert published == verified
    assert verified["valid"] is True
    assert verified["verdicts"]["lineage"] == "pass"
    assert verified["verdicts"]["signature"] == "not_present"
    assert verified["statement"] == {
        "payload_type": "application/vnd.in-toto+json",
        "predicate_type": "https://trialmark.dev/attestation/decision/v1",
        "signature_count": 0,
        "subject": parent_bundle.bundle_id,
        "subject_matches_supersedes": True,
        "type": "https://in-toto.io/Statement/v1",
    }
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["supersedes"] == parent_bundle.bundle_id

    approved_bundle = materialize_completed_run_logical_abx(approved)
    statement_members = {
        member.path: member.payload for member in approved_bundle.members
    }
    statement_manifest = load_ijson_object(statement_members.pop("manifest.json"))
    statement_path = "decision/statement.dsse.json"
    foreign_envelope = load_ijson_object(statement_members[statement_path])
    foreign_statement = load_ijson_object(
        base64.b64decode(foreign_envelope["payload"], validate=True)
    )
    foreign_subject = "sha256:" + "34" * 32
    foreign_statement["subject"][0]["digest"]["sha256"] = (
        foreign_subject.removeprefix("sha256:")
    )
    foreign_envelope["payload"] = base64.b64encode(
        canonical_json_bytes(foreign_statement)
    ).decode("ascii")
    statement_members[statement_path] = canonical_json_bytes(foreign_envelope)
    statement_entry = next(
        entry
        for entry in statement_manifest["entries"]
        if entry["path"] == statement_path
    )
    statement_entry["size"] = len(statement_members[statement_path])
    statement_entry["digest"] = sha256_hex(statement_members[statement_path])
    statement_manifest["bundle_id"] = manifest_bundle_id(statement_manifest)
    foreign_subject_result = verify_logical_bundle(
        canonical_json_bytes(statement_manifest),
        tuple(statement_members.items()),
    )
    assert foreign_subject_result["valid"] is False
    assert foreign_subject_result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in {
        error["code"] for error in foreign_subject_result["errors"]
    }
    assert foreign_subject_result["statement"]["subject"] == foreign_subject
    assert foreign_subject_result["statement"]["subject_matches_supersedes"] is False

    manifest["supersedes"] = "sha256:" + "12" * 32
    manifest["bundle_id"] = manifest_bundle_id(manifest)
    tampered = verify_logical_bundle(
        canonical_json_bytes(manifest),
        tuple(
            (member.path, member.payload)
            for member in approved_bundle.members
            if member.path != "manifest.json"
        ),
    )
    assert tampered["valid"] is False
    assert tampered["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in {
        error["code"] for error in tampered["errors"]
    }
