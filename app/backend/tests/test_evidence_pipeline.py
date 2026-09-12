"""Contract tests for the evidence pipeline orchestrator."""

from __future__ import annotations

import hashlib
import inspect
import json
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.abx import manifest_bundle_id, verify_logical_bundle
from app.backend.app.evidence.protocol_io import FrozenProtocol, freeze
from app.backend.app.evidence.run_abx import materialize_completed_run_logical_abx
from app.backend.app.evidence.runs import CompletedEvidenceRun, EvidenceRunStore
from app.backend.app.evidence.stats_kernel import (
    LegacyStatsKernelAdapter,
    StatsKernelBuild,
)

ASOS_PARQUET = (
    Path(__file__).parent / "fixtures" / "evidence" / "asos" / "d53f0e.parquet"
)
_ASOS_BUNDLE = (
    Path(__file__).parent
    / "fixtures"
    / "evidence"
    / "asos"
    / "bundles"
    / "d53f0e.tmk"
)

_TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:" + hashlib.sha256(b"pipeline-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"pipeline-test-lock").hexdigest(),
)


@pytest.fixture(autouse=True)
def _stable_stats_kernel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        lambda: _TEST_BUILD,
    )


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


def test_run_protocol_import_contract() -> None:
    from app.backend.app.evidence.pipeline import run_protocol

    assert callable(run_protocol)
    signature = inspect.signature(run_protocol)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == [
        "frozen",
        "source",
        "principal",
        "out_store",
    ]
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[3].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.return_annotation != inspect.Signature.empty
    annotation = signature.return_annotation
    if isinstance(annotation, str):
        assert annotation.endswith("CompletedEvidenceRun")
    else:
        assert annotation is CompletedEvidenceRun


def _protocol(*, complete_telemetry: bool = True) -> dict[str, Any]:
    with zipfile.ZipFile(_ASOS_BUNDLE) as archive:
        protocol = json.loads(archive.read("protocol/protocol.json"))
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    protocol["analysis"]["random_seed"] = 20260901
    protocol["estimand"]["effect_measure"] = "risk_difference"
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = "assignment_v1"
    if not complete_telemetry:
        protocol["telemetry"]["schema_versions"] = [
            schema
            for schema in protocol["telemetry"]["schema_versions"]
            if schema["event_type"] != "aggregate_metric_checkpoint"
        ]
    return protocol


def _frozen_protocol(*, complete_telemetry: bool = True) -> FrozenProtocol:
    return freeze(_protocol(complete_telemetry=complete_telemetry))


def _role_paths(run: CompletedEvidenceRun) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for artifact in run.artifacts:
        grouped.setdefault(artifact.role, []).append(artifact.path)
    return grouped


def _publish_and_verify(run: CompletedEvidenceRun, store: EvidenceRunStore, packed: Path) -> dict[str, Any]:
    from app.backend.app.evidence.abx import verify_bundle
    from app.backend.app.evidence.run_abx import publish_completed_run_abx

    result = publish_completed_run_abx(
        store,
        run_id=run.run_id,
        destination=packed,
    )
    report = verify_bundle(packed)
    assert result == report
    assert report["valid"] is True
    assert report["verdicts"]["lineage"] == "pass"
    assert packed.is_file()
    return report


def test_run_protocol_persists_asos_via_duckdb_and_stats(tmp_path: Path) -> None:
    from app.backend.app.evidence.pipeline import run_protocol

    store: EvidenceRunStore = MemoryEvidenceRunStore()
    analyze_implementation = LegacyStatsKernelAdapter.analyze
    with patch.object(
        LegacyStatsKernelAdapter,
        "analyze",
        autospec=True,
        side_effect=analyze_implementation,
    ) as analyze:
        run = run_protocol(
            _frozen_protocol(),
            ASOS_PARQUET,
            principal="qa-operator",
            out_store=store,
        )
    assert analyze.called
    assert isinstance(run, CompletedEvidenceRun)
    assert store.get(run.run_id) is run
    assert run.kind == "analysis"
    assert run.status == "succeeded"
    roles = _role_paths(run)
    assert roles["protocol"]
    assert roles["source"]
    assert roles["query"]
    assert roles["metric"]
    assert roles["method"] == ["methods/profile.json"]
    assert roles["estimate"]
    assert roles["decision"]
    assert roles["report"] == ["rendered/report.html"]
    query = next(artifact for artifact in run.artifacts if artifact.role == "query")
    assert b"SELECT" in query.payload.upper()
    decision = next(artifact for artifact in run.artifacts if artifact.role == "decision")
    assert b"proposed" in decision.payload
    report = next(artifact for artifact in run.artifacts if artifact.role == "report")
    assert report.media_type == "text/html"
    report_text = report.payload.decode("utf-8")
    assert run.run_id in report_text
    assert query.payload.decode("utf-8") in report_text
    assert "ASOS decision metric 1" in report_text
    assert "human_verdict=inconclusive" in report_text
    assert "run_checkout_workbench_001" not in report_text
    method = load_ijson_object(
        next(artifact for artifact in run.artifacts if artifact.role == "method").payload
    )
    run_document = load_ijson_object(
        next(artifact for artifact in run.artifacts if artifact.role == "run").payload
    )
    assert method["method_id"] == "binary_pooled_z_newcombe"
    assert method["method_version"] == "binary_pooled_z_newcombe_v1"
    assert method["error_control"]["nominal_alpha"] == 0.05
    assert method["implementation_digest"] == run_document["runner"]["build_digest"]
    _publish_and_verify(run, store, tmp_path / "d53f0e.tmk")


def test_pipeline_asos_d53f0e(tmp_path: Path) -> None:
    from app.backend.app.evidence.pipeline import run_protocol
    from app.backend.app.evidence.run_abx import materialize_completed_run_logical_abx

    store: EvidenceRunStore = MemoryEvidenceRunStore()
    run = run_protocol(
        _frozen_protocol(),
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=store,
    )
    assert store.get(run.run_id) is run
    logical = materialize_completed_run_logical_abx(run)
    assert logical is not None
    assert logical.run_id == run.run_id
    _publish_and_verify(run, store, tmp_path / "pipeline_d53f0e.tmk")


def test_run_protocol_is_deterministic() -> None:
    from app.backend.app.evidence.pipeline import run_protocol

    first_store = MemoryEvidenceRunStore()
    second_store = MemoryEvidenceRunStore()
    frozen = _frozen_protocol()
    first = run_protocol(
        frozen,
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=first_store,
    )
    second = run_protocol(
        frozen,
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=second_store,
    )
    assert first.run_id == second.run_id
    assert first.record_digest == second.record_digest
    assert first.protocol_revision_id == second.protocol_revision_id
    first_digests = tuple(artifact.digest for artifact in first.artifacts)
    second_digests = tuple(artifact.digest for artifact in second.artifacts)
    assert first_digests == second_digests
    assert tuple(artifact.payload for artifact in first.artifacts) == tuple(
        artifact.payload for artifact in second.artifacts
    )
    assert first.started_at == second.started_at
    assert first.completed_at == second.completed_at
    assert first.sealed_at == second.sealed_at


def test_run_protocol_store_idempotency() -> None:
    from app.backend.app.evidence.pipeline import run_protocol

    store = MemoryEvidenceRunStore()
    frozen = _frozen_protocol()
    first = run_protocol(
        frozen,
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=store,
    )
    second = run_protocol(
        frozen,
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=store,
    )
    assert second is first
    assert list(store.runs) == [first.run_id]


def test_run_protocol_blocked_skips_stats_and_omits_estimate() -> None:
    from app.backend.app.evidence._common import load_ijson_object
    from app.backend.app.evidence.pipeline import run_protocol

    store = MemoryEvidenceRunStore()
    with patch.object(
        LegacyStatsKernelAdapter,
        "analyze",
        side_effect=AssertionError("stats adapter must not run on blocking findings"),
    ) as analyze:
        run = run_protocol(
            _frozen_protocol(complete_telemetry=False),
            ASOS_PARQUET,
            principal="qa-operator",
            out_store=store,
        )
    analyze.assert_not_called()
    assert store.get(run.run_id) is run
    assert run.kind == "preflight"
    assert run.status == "succeeded"
    roles = {artifact.role for artifact in run.artifacts}
    assert "method" in roles
    assert "estimate" not in roles
    assert "decision" not in roles
    assert "finding" in roles
    assert "report" in roles
    report = next(artifact for artifact in run.artifacts if artifact.role == "report")
    report_text = report.payload.decode("utf-8")
    assert run.run_id in report_text
    assert "No estimate was produced for this run." in report_text
    assert "No decision was recorded for this run." in report_text
    findings = [
        load_ijson_object(artifact.payload)
        for artifact in run.artifacts
        if artifact.role == "finding"
    ]
    assert findings
    assert all(finding["blocking"] is True for finding in findings)
    run_document = load_ijson_object(
        next(artifact for artifact in run.artifacts if artifact.role == "run").payload
    )
    assert run_document["kind"] == "preflight"
    assert run_document["status"] == "succeeded"
    assert run_document["estimate_ids"] == []
    assert "decision_id" not in run_document
    method = load_ijson_object(
        next(artifact for artifact in run.artifacts if artifact.role == "method").payload
    )
    assert method["implementation_digest"] == run_document["runner"]["build_digest"]


def test_verifier_rejects_rebound_method_implementation_digest() -> None:
    from app.backend.app.evidence.pipeline import run_protocol

    store = MemoryEvidenceRunStore()
    run = run_protocol(
        _frozen_protocol(),
        ASOS_PARQUET,
        principal="qa-operator",
        out_store=store,
    )
    bundle = materialize_completed_run_logical_abx(run)
    assert bundle is not None
    manifest = load_ijson_object(bundle.manifest_payload)
    members = [(member.path, member.payload) for member in bundle.members[1:]]
    method_index = next(
        index for index, member in enumerate(members) if member[0] == "methods/profile.json"
    )
    method = load_ijson_object(members[method_index][1])
    method["implementation_digest"] = "sha256:" + "0" * 64
    method_payload = canonical_json_bytes(method)
    members[method_index] = ("methods/profile.json", method_payload)
    entry = next(
        item
        for item in manifest["entries"]
        if item["path"] == "methods/profile.json"
    )
    entry["size"] = len(method_payload)
    entry["digest"] = sha256_hex(method_payload)
    manifest["bundle_id"] = manifest_bundle_id(manifest)

    report = verify_logical_bundle(canonical_json_bytes(manifest), tuple(members))

    assert report["valid"] is False
    assert report["verdicts"]["schema_conformance"] == "pass"
    assert report["verdicts"]["lineage"] == "fail"
    assert "method_profile_mismatch" in {
        error["code"] for error in report["errors"]
    }
