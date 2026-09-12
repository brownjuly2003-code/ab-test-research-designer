from __future__ import annotations

import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.backend.app.evidence.abx import (
    canonical_json_bytes,
    inspect_bundle,
    verify_bundle,
)
from app.backend.app.evidence.public_pilot_abx import (
    AsosPublicPilotAbxContext,
    load_asos_public_pilot_abx_context,
    pack_asos_public_pilot_abx,
)
from app.backend.app.evidence.public_pilots import load_asos_public_pilot

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence" / "asos"
CONTEXT_PATH = FIXTURE_DIR / "benchmark-context.json"
BUNDLE_DIR = FIXTURE_DIR / "bundles"
BACKEND_DIR = Path(__file__).parents[1]
EXPERIMENT_IDS = ("d53f0e", "26bd38", "834947")
EXPECTED_ARCHIVES = {
    "d53f0e": (
        "sha256:5fb64dd809aba8e701314874679d7d56794a411e1b177ab3265f2de5b54ce1f0",
        "sha256:60fee3fae970b607fec89bec8d6e8fc423d55a42f6d3f02b679436c281b694b3",
    ),
    "26bd38": (
        "sha256:76a9e2411ec8254d77b0ec7200b3bde2adec0cd061481949a029be92d7395536",
        "sha256:de3b8372fc60bfb8049455d738febde068a062386de8f9253d32177c0025c942",
    ),
    "834947": (
        "sha256:4b747b3f81c2862e8c374089c1b627d5bde0bc7639084d6a6f7c0d230e3148ec",
        "sha256:0f6654308d5e89ceb89a780498c79079049b5c087fcb444e444d9a722266602a",
    ),
}


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _archive_members(path: Path) -> dict[str, bytes]:
    """The uncompressed member bytes, which are what the format pins.

    ADR 0004 keeps bundle identity in the manifest digest and explicitly rejects
    hashing the ZIP byte stream, "because compression metadata can" differ. The
    deflate output is one such difference: CPython 3.14 links a different zlib
    from 3.13, so the same members compress to a different number of bytes. The
    members themselves stay byte-for-byte stable, so that is what a freshly
    packed archive is compared against.
    """
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _read_json(archive: zipfile.ZipFile, path: str) -> dict[str, Any]:
    value = json.loads(archive.read(path))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _expected_runner_build_digest() -> str:
    sources = [
        {
            "path": relative_path,
            "digest": _sha256((BACKEND_DIR / relative_path).read_bytes()),
        }
        for relative_path in (
            "app/evidence/public_pilot_abx.py",
            "app/evidence/public_pilots.py",
        )
    ]
    return _sha256(canonical_json_bytes({"sources": sources}))


def test_public_pilot_json_artifact_is_rfc8785_canonical(tmp_path: Path) -> None:
    context = load_asos_public_pilot_abx_context(CONTEXT_PATH)
    destination = tmp_path / "d53f0e.tmk"
    pack_asos_public_pilot_abx(
        FIXTURE_DIR / "d53f0e.parquet",
        context=context,
        destination=destination,
        expected_experiment_id="d53f0e",
    )
    with zipfile.ZipFile(destination) as archive:
        payload = archive.read("protocol/protocol.json")
    parsed = json.loads(payload)
    assert isinstance(parsed, dict)
    assert payload == canonical_json_bytes(parsed)


def test_benchmark_context_is_explicit_and_immutable() -> None:
    context = load_asos_public_pilot_abx_context(CONTEXT_PATH)

    assert context.evidence_type == "public_benchmark"
    assert context.partner_approved is False
    assert context.original_protocol_available is False
    assert context.original_metric_semantics_available is False
    assert context.timing_is_partner_evidence is False
    assert context.retrospective_protocol_harness is True
    assert context.horizon_rule == "terminal_checkpoint_from_time_since_start"
    assert context.artifact_created_at >= context.run_completed_at
    with pytest.raises(ValidationError, match="frozen"):
        context.partner_approved = True  # type: ignore[assignment]


def test_benchmark_context_rejects_artifact_before_run_completion() -> None:
    payload = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    payload["artifact_created_at"] = payload["run_started_at"]

    with pytest.raises(ValidationError, match="artifact_created_at"):
        AsosPublicPilotAbxContext.model_validate(payload)


@pytest.mark.parametrize("experiment_id", EXPERIMENT_IDS)
def test_packs_deterministic_offline_asos_public_benchmark(
    experiment_id: str,
    tmp_path: Path,
) -> None:
    context = load_asos_public_pilot_abx_context(CONTEXT_PATH)
    fixture_path = FIXTURE_DIR / f"{experiment_id}.parquet"
    committed_path = BUNDLE_DIR / f"{experiment_id}.tmk"
    generated_path = tmp_path / f"{experiment_id}.tmk"
    repeated_path = tmp_path / f"{experiment_id}-repeat.tmk"

    first = pack_asos_public_pilot_abx(
        fixture_path,
        context=context,
        destination=generated_path,
        expected_experiment_id=experiment_id,
    )
    second = pack_asos_public_pilot_abx(
        fixture_path,
        context=context,
        destination=repeated_path,
        expected_experiment_id=experiment_id,
    )

    expected_archive_sha256, expected_bundle_id = EXPECTED_ARCHIVES[experiment_id]
    generated_payload = generated_path.read_bytes()
    assert generated_payload == repeated_path.read_bytes()
    assert _archive_members(generated_path) == _archive_members(committed_path)
    assert _sha256(committed_path.read_bytes()) == expected_archive_sha256
    assert first["bundle_id"] == second["bundle_id"] == expected_bundle_id
    assert first == verify_bundle(generated_path)
    assert first["valid"] is True
    assert first["verdicts"]["statistical_validity"] == "not_asserted"
    assert inspect_bundle(generated_path) == {
        "abx_version": "0.1.0",
        "artifact_count": 12,
        "bundle_id": expected_bundle_id,
        "roles": {
            "estimate": 4,
            "metric": 4,
            "protocol": 1,
            "query": 1,
            "run": 1,
            "source": 1,
        },
        "run_id": f"run_asos_{experiment_id}_terminal",
        "unbound_bindings": [],
        "valid": True,
        "verdicts": first["verdicts"],
    }

    pilot = load_asos_public_pilot(
        fixture_path,
        expected_experiment_id=experiment_id,
    )
    with zipfile.ZipFile(generated_path) as archive:
        manifest = _read_json(archive, "manifest.json")
        protocol = _read_json(archive, "protocol/protocol.json")
        run = _read_json(archive, "run/run.json")
        source = _read_json(archive, f"sources/source_asos_{experiment_id}.json")
        entries = cast(list[dict[str, Any]], manifest["entries"])
        paths_by_role = {
            role: sorted(str(entry["path"]) for entry in entries if entry["role"] == role)
            for role in {str(entry["role"]) for entry in entries}
        }

        assert len(entries) == 12
        assert not ({"decision", "finding", "amendments", "report"} & set(paths_by_role))
        assert all(not path.endswith(".parquet") for path in archive.namelist())
        query_path = f"queries/{pilot.provenance.statement_digest.removeprefix('sha256:')}.sql"
        assert paths_by_role["query"] == [query_path]
        assert archive.read(query_path) == pilot.provenance.statement.encode("utf-8")
        assert run["queries"][0]["query_id"] == pilot.provenance.query_id
        assert run["queries"][0]["statement_digest"] == pilot.provenance.statement_digest
        assert run["queries"][0]["statement_path"] == query_path
        assert run["runner"]["build_digest"] == _expected_runner_build_digest()
        assert run["runner"]["dependency_lock_digest"] == _sha256(
            (BACKEND_DIR / "requirements.txt").read_bytes()
        )

        protocol_digest = _sha256(canonical_json_bytes(protocol))
        assert manifest["protocol_revision_id"] == run["protocol_revision_id"] == protocol_digest
        assert source["fingerprint"]["value"] == pilot.inspection.fingerprint.value
        assert source["extensions"]["trialmark.asos"]["upstream_source_sha256"] == (
            pilot.metadata.source_sha256
        )
        assert source["fingerprint"]["value"] != pilot.metadata.source_sha256

        metric_entries = {
            str(_read_json(archive, path)["metric_id"]): next(
                entry for entry in entries if entry["path"] == path
            )
            for path in paths_by_role["metric"]
        }
        assert protocol["metrics"]["primary"][0]["metric_id"] == "metric_asos_1"
        assert [item["metric_id"] for item in protocol["metrics"]["secondary"]] == [
            "metric_asos_2",
            "metric_asos_3",
            "metric_asos_4",
        ]
        for snapshot, estimate_path in zip(pilot.snapshots, paths_by_role["estimate"], strict=True):
            estimate = _read_json(archive, estimate_path)
            standard_error = math.sqrt(
                snapshot.variance_c / snapshot.count_c
                + snapshot.variance_t / snapshot.count_t
            )
            point_estimate = snapshot.mean_t - snapshot.mean_c
            aggregate_inputs = estimate["extensions"]["trialmark.aggregate-inputs"]

            assert estimate["effect_measure"] == "mean_difference"
            assert estimate["point_estimate"] == pytest.approx(point_estimate)
            assert estimate["uncertainty"]["standard_error"] == pytest.approx(standard_error)
            assert estimate["sample_size"] == {
                "total": snapshot.count_c + snapshot.count_t,
                "groups": {"control": snapshot.count_c, "treatment": snapshot.count_t},
            }
            assert aggregate_inputs == {
                "count_c": snapshot.count_c,
                "count_t": snapshot.count_t,
                "mean_c": snapshot.mean_c,
                "mean_t": snapshot.mean_t,
                "variance_c": snapshot.variance_c,
                "variance_t": snapshot.variance_t,
            }
            metric_id = str(estimate["lineage"]["metric"]["metric_id"])
            assert estimate["lineage"]["metric"]["metric_digest"] == metric_entries[metric_id][
                "digest"
            ]
            assert estimate["lineage"]["runner"] == run["runner"]

        for document in (manifest, protocol, run, source):
            benchmark = document["extensions"]["trialmark.asos"]
            assert benchmark["evidence_type"] == "public_benchmark"
            assert benchmark["partner_approved"] is False
            assert benchmark["original_protocol_available"] is False
            assert benchmark["original_metric_semantics_available"] is False
            assert benchmark["timing_is_partner_evidence"] is False
        json_documents = {
            path: _read_json(archive, path)
            for path in archive.namelist()
            if path.endswith(".json")
        }
        assert len(json_documents) == 12
        assert any("https://" in json.dumps(document) for document in json_documents.values())
        for path, document in json_documents.items():
            serialized = json.dumps(document, ensure_ascii=False, sort_keys=True)
            assert re.search(
                r"(?:\b[A-Za-z]:[\\/]|/(?:Users|home|var|tmp|etc)/)",
                serialized,
            ) is None, path
