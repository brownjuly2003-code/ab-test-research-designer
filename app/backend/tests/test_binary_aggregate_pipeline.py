from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from app.backend.app.evidence._common import (
    canonical_json_bytes,
    load_ijson_object,
    sha256_hex,
)
from app.backend.app.evidence.abx import verify_bundle
from app.backend.app.evidence.pilot_records import inspect_external_pilot_bundle
from app.backend.app.evidence.pipeline import run_protocol
from app.backend.app.evidence.protocol_io import freeze
from app.backend.app.evidence.run_abx import publish_completed_run_abx
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.evidence.stats_kernel import StatsKernelBuild

REPO_ROOT = Path(__file__).resolve().parents[3]
ASOS_BUNDLE = (
    REPO_ROOT
    / "app"
    / "backend"
    / "tests"
    / "fixtures"
    / "evidence"
    / "asos"
    / "bundles"
    / "d53f0e.tmk"
)
TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:" + hashlib.sha256(b"aggregate-pipeline-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"aggregate-pipeline-test-lock").hexdigest(),
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


def _protocol() -> dict[str, Any]:
    with zipfile.ZipFile(ASOS_BUNDLE) as archive:
        protocol = cast(
            dict[str, Any],
            json.loads(archive.read("protocol/protocol.json")),
        )
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    protocol["analysis"]["random_seed"] = 20260901
    protocol["estimand"]["effect_measure"] = "risk_difference"
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = "assignment_v1"
        intervention["allocation"] = (
            "0.45" if intervention["kind"] == "control" else "0.55"
        )
    definition = {
        "aggregation": "binary_rate",
        "denominator": "assigned_subjects",
        "numerator": "converted_subjects",
    }
    metric = protocol["metrics"]["primary"][0]
    metric.update(
        {
            "metric_id": "metric_checkout_conversion",
            "metric_version": "pilot-v1",
            "definition_digest": sha256_hex(canonical_json_bytes(definition)),
        }
    )
    protocol["metrics"]["secondary"] = []
    protocol["metrics"]["guardrails"] = []
    protocol["protocol"].update(
        {
            "protocol_id": "external-pilot-checkout",
            "title": "External pilot checkout conversion",
        }
    )
    protocol["estimand"]["estimand_id"] = "estimand_checkout_conversion"
    protocol["extensions"] = {
        "trialmark.aggregate-binary": {
            "schema_version": "1",
            "source_ref": "pilot_source_alpha",
            "evidence_type": "external_pilot",
            "partner_approved": True,
            "metric": {
                "name": "Checkout conversion rate",
                "direction": "increase",
                "unit": "proportion",
                "owner_ref": "pilot_growth_team",
                "definition": definition,
            },
            "observed_telemetry": {
                "outcome_before_exposure_count": 0,
                "duplicate_event_count": 0,
                "unlinked_subject_count": 0,
                "events_beyond_max_lateness_count": 0,
                "schema_versions": protocol["telemetry"]["schema_versions"],
            },
        }
    }
    return protocol


def _write_aggregate(path: Path) -> Path:
    path.write_text(
        "control_users,control_conversions,treatment_users,treatment_conversions\n"
        "1000,100,1200,144\n",
        encoding="utf-8",
    )
    return path


def test_run_protocol_publishes_external_binary_aggregate_csv(tmp_path: Path) -> None:
    store = MemoryEvidenceRunStore()
    source = _write_aggregate(tmp_path / "aggregate.csv")

    with patch(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        return_value=TEST_BUILD,
    ):
        run = run_protocol(
            freeze(_protocol()),
            source,
            principal="pilot-operator",
            out_store=store,
        )

    destination = tmp_path / "pilot.tmk"
    publish_completed_run_abx(store, run_id=run.run_id, destination=destination)
    report = verify_bundle(destination)
    assert report["valid"] is True
    assert report["verdicts"]["lineage"] == "pass"
    assert report["verdicts"]["privacy_policy"] == "pass"
    census = inspect_external_pilot_bundle(destination)
    assert census.bundle_id == report["bundle_id"]
    assert census.run_id == run.run_id
    assert census.aggregate_only is True
    assert census.evidence_type == "external_pilot"
    assert census.partner_approved is True
    assert census.estimate_count == 1
    assert census.row_level_artifact_count == 0

    documents = {
        artifact.role: load_ijson_object(artifact.payload)
        for artifact in run.artifacts
        if artifact.role in {"source", "metric", "run", "estimate"}
    }
    source_document = documents["source"]
    assert source_document["source_ref"] == "pilot_source_alpha"
    assert source_document["extensions"]["trialmark.aggregate-binary"] == {
        "aggregate_only": True,
        "evidence_type": "external_pilot",
        "partner_approved": True,
        "telemetry_profile_source": "upstream_asserted",
    }
    assert documents["metric"]["extensions"]["trialmark.aggregate-binary"][
        "definition"
    ] == _protocol()["extensions"]["trialmark.aggregate-binary"]["metric"]["definition"]
    assert documents["run"]["extensions"]["trialmark.aggregate-binary"] == {
        "aggregate_only": True,
        "evidence_type": "external_pilot",
    }
    assert documents["estimate"]["sample_size"] == {
        "total": 2200,
        "groups": {"control": 1000, "treatment": 1200},
    }


def test_run_protocol_rejects_non_aggregate_csv_shape(tmp_path: Path) -> None:
    source = tmp_path / "row-level.csv"
    source.write_text(
        "unit_id,variant,converted\nuser-1,control,1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="aggregate-binary source schema mismatch"):
        run_protocol(
            freeze(_protocol()),
            source,
            principal="pilot-operator",
            out_store=MemoryEvidenceRunStore(),
        )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (
            "1000,100,1200,144\n1000,100,1200,144\n",
            "aggregate-binary source must contain exactly one aggregate row",
        ),
        (
            "1000,1001,1200,144\n",
            "control conversions cannot exceed users",
        ),
    ],
)
def test_run_protocol_rejects_invalid_aggregate_values(
    tmp_path: Path,
    rows: str,
    message: str,
) -> None:
    source = tmp_path / "invalid.csv"
    source.write_text(
        "control_users,control_conversions,treatment_users,treatment_conversions\n"
        + rows,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        run_protocol(
            freeze(_protocol()),
            source,
            principal="pilot-operator",
            out_store=MemoryEvidenceRunStore(),
        )


def test_run_protocol_requires_partner_approval(tmp_path: Path) -> None:
    protocol = _protocol()
    protocol["extensions"]["trialmark.aggregate-binary"][
        "partner_approved"
    ] = False

    with pytest.raises(
        ValueError,
        match="protocol trialmark.aggregate-binary extension is invalid",
    ):
        run_protocol(
            freeze(protocol),
            _write_aggregate(tmp_path / "aggregate.csv"),
            principal="pilot-operator",
            out_store=MemoryEvidenceRunStore(),
        )


def test_run_protocol_binds_metric_definition_digest(tmp_path: Path) -> None:
    protocol = _protocol()
    protocol["metrics"]["primary"][0]["definition_digest"] = "sha256:" + "0" * 64

    with pytest.raises(
        ValueError,
        match="aggregate-binary metric definition digest does not match the protocol",
    ):
        run_protocol(
            freeze(protocol),
            _write_aggregate(tmp_path / "aggregate.csv"),
            principal="pilot-operator",
            out_store=MemoryEvidenceRunStore(),
        )
