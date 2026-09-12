from __future__ import annotations

import base64
import copy
import hashlib
import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from app.backend.app.config import get_settings
from app.backend.app.evidence.abx import (
    AbxError,
    canonical_json_bytes,
    inspect_bundle,
    pack_bundle,
    verify_bundle,
)
from app.backend.app.evidence.cli import main
from app.backend.app.evidence.data_sources import query_identity_digest
from app.backend.app.evidence.jobs import create_evidence_job
from app.backend.app.evidence.run_abx import (
    EvidenceRunBundleError,
    EvidenceRunNotFoundError,
)
from app.backend.app.evidence.sql_run_store import EvidenceRunStoreCorruptionError
from app.backend.app.evidence.stats_kernel import StatsKernelBuild
from app.backend.app.evidence.storage import EvidenceJobCoordinator
from app.backend.app.repository import ProjectRepository
from app.backend.tests.evidence_run_fixtures import completed_asos_run

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "app" / "backend" / "tests" / "fixtures" / "abx" / "0.1" / "valid"
ASOS_FIXTURE_ROOT = REPO_ROOT / "app" / "backend" / "tests" / "fixtures" / "evidence" / "asos"

_TEST_BUILD = StatsKernelBuild(
    git_commit="a" * 40,
    build_digest="sha256:" + hashlib.sha256(b"abx-cli-test-build").hexdigest(),
    dependency_lock_digest="sha256:"
    + hashlib.sha256(b"abx-cli-test-lock").hexdigest(),
)


@pytest.fixture(autouse=True)
def _stable_stats_kernel_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.backend.app.evidence.pipeline.load_stats_kernel_build",
        lambda: _TEST_BUILD,
    )


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


def _fixture_canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode()


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_json(root: Path, relative_path: str, value: Any) -> bytes:
    payload = _json_bytes(value)
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _make_bundle_directory(
    root: Path, *, query_payload: bytes = b"SELECT COUNT(*) FROM events;\n"
) -> dict[str, Any]:
    root.mkdir()

    query_digest = _digest(query_payload)
    query_path = f"queries/{query_digest.removeprefix('sha256:')}.sql"
    query_file = root / query_path
    query_file.parent.mkdir(parents=True)
    query_file.write_bytes(query_payload)

    protocol = _load_fixture("protocol.json")
    protocol_revision_id = _digest(canonical_json_bytes(protocol))
    amendments = _load_fixture("amendments.json")
    source = _load_fixture("source.json")
    conversion_metric = _load_fixture("metric.json")
    refund_metric = copy.deepcopy(conversion_metric)
    refund_metric.update(
        {
            "metric_id": "metric_refund",
            "definition_digest": "sha256:" + "d" * 64,
            "name": "Refund rate",
            "direction": "decrease",
        }
    )

    payloads: dict[str, bytes] = {
        "protocol/protocol.json": _write_json(root, "protocol/protocol.json", protocol),
        "protocol/amendments.json": _write_json(root, "protocol/amendments.json", amendments),
        "sources/source_fixture.json": _write_json(root, "sources/source_fixture.json", source),
        "metrics/metric_conversion.json": _write_json(
            root, "metrics/metric_conversion.json", conversion_metric
        ),
        "metrics/metric_refund.json": _write_json(root, "metrics/metric_refund.json", refund_metric),
        query_path: query_payload,
    }

    run = _load_fixture("run.json")
    run["protocol_revision_id"] = protocol_revision_id
    run["runner"]["build_digest"] = _digest(b"abx-cli-fixture-build")
    run["runner"]["dependency_lock_digest"] = _digest(b"abx-cli-fixture-lock")
    query_id = query_identity_digest(
        dialect=run["queries"][0]["dialect"],
        parameters_digest=run["queries"][0]["parameters_digest"],
        source_fingerprint=source["fingerprint"],
        statement_digest=query_digest,
    )
    run["queries"][0].update(
        {
            "query_id": query_id,
            "statement_path": query_path,
            "statement_digest": query_digest,
        }
    )
    payloads["run/run.json"] = _write_json(root, "run/run.json", run)

    finding = _load_fixture("finding.json")
    finding["evidence"][0]["artifact_digest"] = _digest(payloads["run/run.json"])
    payloads["diagnostics/finding_01.json"] = _write_json(
        root, "diagnostics/finding_01.json", finding
    )

    estimate = _load_fixture("estimate.json")
    estimate["lineage"]["protocol_revision_id"] = protocol_revision_id
    estimate["lineage"]["query_ids"] = [query_id]
    estimate["lineage"]["metric"]["metric_digest"] = _digest(
        payloads["metrics/metric_conversion.json"]
    )
    estimate["lineage"]["runner"]["build_digest"] = run["runner"]["build_digest"]
    estimate["lineage"]["runner"]["dependency_lock_digest"] = run["runner"]["dependency_lock_digest"]
    payloads["estimates/estimate_01.json"] = _write_json(
        root, "estimates/estimate_01.json", estimate
    )

    decision = _load_fixture("decision.json")
    decision["protocol_revision_id"] = protocol_revision_id
    payloads["decision/decision.json"] = _write_json(root, "decision/decision.json", decision)

    roles = {
        "protocol/protocol.json": "protocol",
        "protocol/amendments.json": "amendments",
        "run/run.json": "run",
        "sources/source_fixture.json": "source",
        "metrics/metric_conversion.json": "metric",
        "metrics/metric_refund.json": "metric",
        query_path: "query",
        "diagnostics/finding_01.json": "finding",
        "estimates/estimate_01.json": "estimate",
        "decision/decision.json": "decision",
    }
    media_types = {"query": "application/sql"}
    entries: list[dict[str, Any]] = []
    for path in sorted(payloads):
        role = roles[path]
        entry = {
            "path": path,
            "role": role,
            "media_type": media_types.get(role, "application/json"),
            "size": len(payloads[path]),
            "digest": _digest(payloads[path]),
        }
        if role != "query":
            entry["schema_id"] = f"urn:evidenceos:abx:schema:0.1:{role}"
        entries.append(entry)

    manifest: dict[str, Any] = {
        "abx_version": "0.1.0",
        "bundle_id": "sha256:" + "0" * 64,
        "created_at": "2026-08-21T21:00:00Z",
        "protocol_revision_id": protocol_revision_id,
        "run_id": "run_foundation_01",
        "hash_algorithm": "sha256",
        "required_capabilities": ["lineage-v1", "protocol-core"],
        "entries": entries,
    }
    manifest_core = {key: value for key, value in manifest.items() if key != "bundle_id"}
    manifest["bundle_id"] = _digest(_fixture_canonical_bytes(manifest_core))
    _write_json(root, "manifest.json", manifest)
    return manifest


def _rewrite_archive(
    source: Path,
    destination: Path,
    *,
    mutation: tuple[str, bytes, bytes] | None = None,
    reverse_order: bool = False,
) -> None:
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if reverse_order:
            members.reverse()
        with zipfile.ZipFile(destination, "w") as output:
            for member in members:
                payload = archive.read(member)
                if mutation is not None and member.filename == mutation[0]:
                    marker, replacement = mutation[1:]
                    assert marker in payload
                    assert len(marker) == len(replacement)
                    payload = payload.replace(marker, replacement, 1)
                copied = zipfile.ZipInfo(member.filename, date_time=(2025, 2, 3, 4, 5, 6))
                copied.compress_type = member.compress_type
                copied.create_system = member.create_system
                copied.external_attr = member.external_attr
                output.writestr(copied, payload)


def _persist_completed_run(database_path: Path, artifact_root: Path) -> str:
    repository = ProjectRepository(str(database_path), busy_timeout_ms=5000)
    run = completed_asos_run()
    started_at = datetime.fromisoformat(run.started_at[:-1] + "+00:00")
    sealed_at = datetime.fromisoformat(run.sealed_at[:-1] + "+00:00")
    coordinator = EvidenceJobCoordinator(repository.create_evidence_job_store())
    coordinator.create(
        create_evidence_job(
            job_id=run.origin_job_id,
            kind=run.kind,
            protocol_revision_id=run.protocol_revision_id,
            request_digest="sha256:" + "a" * 64,
            created_at=started_at - timedelta(seconds=1),
        )
    )
    coordinator.claim(
        run.origin_job_id,
        lease_token="worker:abx-cli",
        now=started_at,
        lease_expires_at=sealed_at + timedelta(days=1),
    )
    assert repository.create_evidence_run_store(artifact_root).create(run) is True
    repository.close()
    return run.run_id


def _repository_settings(database_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        database_url=database_url,
        sqlite_busy_timeout_ms=2750,
        sqlite_journal_mode="DELETE",
        sqlite_synchronous="FULL",
        workspace_signing_key="test-signing-key",
        db_pool_size=7,
    )


def _write_supported_asos_protocol(path: Path) -> Path:
    with zipfile.ZipFile(ASOS_FIXTURE_ROOT / "bundles" / "d53f0e.tmk") as archive:
        protocol = json.loads(archive.read("protocol/protocol.json"))
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    protocol["analysis"]["random_seed"] = 20260901
    protocol["estimand"]["effect_measure"] = "risk_difference"
    for intervention in protocol["interventions"]:
        intervention["hash_version"] = "assignment_v1"
    path.write_bytes(
        yaml.safe_dump(protocol, allow_unicode=True, sort_keys=True).encode("utf-8")
    )
    return path


def _archive_decision(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        if "decision/statement.dsse.json" not in archive.namelist():
            return json.loads(archive.read("decision/decision.json"))
        envelope = json.loads(archive.read("decision/statement.dsse.json"))
        statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
        return statement["predicate"]


def test_rfc8785_canonicalization_uses_ecmascript_number_serialization() -> None:
    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "literals": [None, True, False],
    }

    assert canonical_json_bytes(value) == (
        b'{"literals":[null,true,false],'
        b'"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    )


def test_pack_verify_inspect_round_trip_and_cli_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "logical"
    manifest = _make_bundle_directory(source)
    archive = tmp_path / "result.tmk"

    assert main(["pack", str(source), "--out", str(archive)]) == 0
    packed = json.loads(capsys.readouterr().out)
    verified = verify_bundle(archive)
    inspected = inspect_bundle(archive)

    assert packed["valid"] is True
    assert verified["valid"] is True
    assert verified["bundle_id"] == manifest["bundle_id"]
    assert set(verified["verdicts"].values()) == {
        "pass",
        "not_present",
        "not_asserted",
    }
    assert inspected == {
        "abx_version": "0.1.0",
        "artifact_count": len(manifest["entries"]),
        "bundle_id": manifest["bundle_id"],
        "roles": {
            "amendments": 1,
            "decision": 1,
            "estimate": 1,
            "finding": 1,
            "metric": 2,
            "protocol": 1,
            "query": 1,
            "run": 1,
            "source": 1,
        },
        "run_id": "run_foundation_01",
        "unbound_bindings": [
            "metrics/metric_conversion.json",
            "metrics/metric_refund.json",
        ],
        "valid": True,
        "verdicts": verified["verdicts"],
    }

    assert main(["inspect", str(archive)]) == 0
    assert json.loads(capsys.readouterr().out) == inspected
    assert main(["verify", str(archive), "--offline", "--policy", "strict"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["valid"] is True
    assert cli_payload["bundle_id"] == manifest["bundle_id"]


def test_pack_run_defaults_to_the_configured_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--run` used to be an argparse error without `--artifact-root`.

    There is now one configured root shared with the API, so requiring the flag
    was friction rather than safety: an operator who set AB_ARTIFACT_ROOT had to
    repeat it on every command. The flag still overrides it.
    """
    configured = tmp_path / "configured" / "artifacts"
    seen: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def create_evidence_run_store(self, artifact_root: Path) -> object:
            seen["artifact_root"] = artifact_root
            return object()

        def close(self) -> None:
            return None

    def missing_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise EvidenceRunNotFoundError("Evidence run 'run_missing' was not found")

    settings = _repository_settings("sqlite:///D:/evidence/missing.sqlite3")
    settings.artifact_root = configured
    monkeypatch.setattr("app.backend.app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", FakeRepository)
    monkeypatch.setattr("app.backend.app.evidence.run_abx.publish_completed_run_abx", missing_run)

    assert main(["pack", "--run", "run_missing", "--out", str(tmp_path / "result.tmk")]) == 1

    assert seen["artifact_root"] == configured
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "run_not_found"


def test_pack_run_rejects_artifact_root_for_a_logical_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "pack",
                str(tmp_path / "logical"),
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--out",
                str(tmp_path / "result.tmk"),
            ]
        )

    assert raised.value.code == 2
    assert "--artifact-root can only be used with --run" in capsys.readouterr().err


@pytest.mark.parametrize("selector_case", ["neither", "both"])
def test_pack_run_requires_exactly_one_source_selector(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selector_case: str,
) -> None:
    arguments = ["pack", "--out", str(tmp_path / "result.tmk")]
    if selector_case == "both":
        arguments[1:1] = [
            str(tmp_path / "logical"),
            "--run",
            "run_01",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ]

    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///D:/evidence/test.sqlite3",
        "postgresql://evidence:password@db.example/evidence",
    ],
)
def test_pack_run_uses_application_repository_settings_and_closes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_url: str,
) -> None:
    calls: dict[str, Any] = {}
    run_store = object()

    class FakeRepository:
        def __init__(self, configured_url: str, **kwargs: Any) -> None:
            calls["database_url"] = configured_url
            calls["repository_options"] = kwargs

        def create_evidence_run_store(self, artifact_root: Path) -> object:
            calls["artifact_root"] = artifact_root
            return run_store

        def close(self) -> None:
            calls["closed"] = True

    def fake_publish(
        store: object,
        *,
        run_id: str,
        destination: Path,
    ) -> dict[str, Any]:
        calls["publish"] = (store, run_id, destination)
        return {"valid": True, "run_id": run_id}

    settings = _repository_settings(database_url)
    monkeypatch.setattr("app.backend.app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", FakeRepository)
    monkeypatch.setattr("app.backend.app.evidence.run_abx.publish_completed_run_abx", fake_publish)
    artifact_root = tmp_path / "artifacts"
    destination = tmp_path / "result.tmk"

    assert (
        main(
            [
                "pack",
                "--run",
                "run_01",
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(destination),
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"run_id": "run_01", "valid": True}
    assert calls == {
        "artifact_root": artifact_root,
        "closed": True,
        "database_url": database_url,
        "publish": (run_store, "run_01", destination),
        "repository_options": {
            "busy_timeout_ms": 2750,
            "journal_mode": "DELETE",
            "pool_size": 7,
            "synchronous": "FULL",
            "workspace_signing_key": "test-signing-key",
        },
    }


def test_pack_run_closes_repository_when_the_run_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, bool] = {}

    class FakeRepository:
        def __init__(self, configured_url: str, **kwargs: Any) -> None:
            del configured_url, kwargs

        def create_evidence_run_store(self, artifact_root: Path) -> object:
            del artifact_root
            return object()

        def close(self) -> None:
            calls["closed"] = True

    def missing_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise EvidenceRunNotFoundError("Evidence run 'run_missing' was not found")

    monkeypatch.setattr(
        "app.backend.app.config.get_settings",
        lambda: _repository_settings("sqlite:///D:/evidence/missing.sqlite3"),
    )
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", FakeRepository)
    monkeypatch.setattr("app.backend.app.evidence.run_abx.publish_completed_run_abx", missing_run)
    destination = tmp_path / "missing.tmk"

    assert (
        main(
            [
                "pack",
                "--run",
                "run_missing",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--out",
                str(destination),
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "run_not_found"
    assert calls == {"closed": True}
    assert not destination.exists()


@pytest.mark.parametrize(
    ("failure_type", "expected_code"),
    [
        (EvidenceRunStoreCorruptionError, "run_store_error"),
        (EvidenceRunBundleError, "pack_failed"),
    ],
)
def test_pack_run_maps_domain_failures_and_closes_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_type: type[Exception],
    expected_code: str,
) -> None:
    calls: dict[str, bool] = {}

    class FakeRepository:
        def __init__(self, configured_url: str, **kwargs: Any) -> None:
            del configured_url, kwargs

        def create_evidence_run_store(self, artifact_root: Path) -> object:
            del artifact_root
            return object()

        def close(self) -> None:
            calls["closed"] = True

    def fail_publication(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise failure_type("simulated persisted-run failure")

    monkeypatch.setattr(
        "app.backend.app.config.get_settings",
        lambda: _repository_settings("sqlite:///D:/evidence/failure.sqlite3"),
    )
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", FakeRepository)
    monkeypatch.setattr(
        "app.backend.app.evidence.run_abx.publish_completed_run_abx",
        fail_publication,
    )

    assert (
        main(
            [
                "pack",
                "--run",
                "run_01",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--out",
                str(tmp_path / "result.tmk"),
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == expected_code
    assert calls == {"closed": True}


def test_pack_run_preserves_existing_destination_before_repository_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "existing.tmk"
    destination.write_bytes(b"existing archive bytes")

    def unexpected_call(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("repository construction must not be attempted")

    # The CLI imports these inside the handler that needs them, so the
    # patch has to land on the module that defines them.
    monkeypatch.setattr("app.backend.app.config.get_settings", unexpected_call)
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", unexpected_call)

    assert (
        main(
            [
                "pack",
                "--run",
                "run_01",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--out",
                str(destination),
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "pack_failed"
    assert destination.read_bytes() == b"existing archive bytes"


@pytest.mark.parametrize(
    ("database_url", "sensitive_fragment"),
    [
        ("postgresql://reader:super-secret@db.example/evidence", "super-secret"),
        ("postgresql://db.example/evidence?sslpassword=super-secret", "super-secret"),
        ("postgresql://reader:p@password-tail@db.example/evidence", "password-tail"),
    ],
)
def test_pack_run_masks_credentials_in_repository_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    database_url: str,
    sensitive_fragment: str,
) -> None:
    class FailingRepository:
        def __init__(self, configured_url: str, **kwargs: Any) -> None:
            del kwargs
            raise RuntimeError(f"could not connect to {configured_url}")

    monkeypatch.setattr(
        "app.backend.app.config.get_settings",
        lambda: _repository_settings(database_url),
    )
    monkeypatch.setattr("app.backend.app.repository.ProjectRepository", FailingRepository)

    assert (
        main(
            [
                "pack",
                "--run",
                "run_01",
                "--artifact-root",
                str(tmp_path / "artifacts"),
                "--out",
                str(tmp_path / "result.tmk"),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["error"]["code"] == "repository_error"
    assert sensitive_fragment not in captured.out
    assert sensitive_fragment not in captured.err


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("pack", "pack_bundle"),
        ("verify", "verify_bundle"),
        ("inspect", "inspect_bundle"),
    ],
)
def test_existing_cli_command_value_errors_are_not_configuration_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    target: str,
) -> None:
    def unexpected_value_error(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise ValueError("simulated archive implementation failure")

    monkeypatch.setattr(f"app.backend.app.evidence.cli.{target}", unexpected_value_error)
    if command == "pack":
        arguments = ["pack", str(tmp_path / "logical"), "--out", str(tmp_path / "result.tmk")]
    else:
        arguments = [command, str(tmp_path / "result.tmk")]

    with pytest.raises(ValueError, match="simulated archive implementation failure"):
        main(arguments)


def test_pack_run_publishes_a_persisted_sqlite_run_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "evidence-runs.sqlite3"
    artifact_root = tmp_path / "artifacts"
    run_id = _persist_completed_run(database_path, artifact_root)
    destination = tmp_path / "persisted-run.tmk"
    monkeypatch.delenv("AB_DATABASE_URL", raising=False)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    get_settings.cache_clear()

    try:
        exit_code = main(
            [
                "pack",
                "--run",
                run_id,
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(destination),
            ]
        )
    finally:
        get_settings.cache_clear()

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == verify_bundle(destination)
    assert payload["valid"] is True
    assert payload["run_id"] == run_id


def test_persisted_run_decide_verify_and_list_cli_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = tmp_path / "trialmark.sqlite3"
    artifact_root = tmp_path / "artifacts"
    protocol_path = _write_supported_asos_protocol(tmp_path / "protocol.yaml")
    source_path = ASOS_FIXTURE_ROOT / "d53f0e.parquet"
    analysis_archive = tmp_path / "analysis.tmk"
    env_decision_archive = tmp_path / "env-decision.tmk"
    actor_decision_archive = tmp_path / "actor-decision.tmk"
    monkeypatch.delenv("AB_DATABASE_URL", raising=False)
    monkeypatch.setenv("AB_DB_PATH", str(database_path))
    monkeypatch.delenv("USER", raising=False)
    get_settings.cache_clear()

    try:
        assert main(
            [
                "run",
                "--protocol",
                str(protocol_path),
                "--source",
                str(source_path),
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(analysis_archive),
            ]
        ) == 0
        analysis_result = json.loads(capsys.readouterr().out)
        assert analysis_result == verify_bundle(analysis_archive)
        assert analysis_result["valid"] is True
        assert analysis_result["run_id"]
        assert analysis_result["bundle_id"]
        assert analysis_result["verdicts"]["lineage"] == "pass"
        assert _archive_decision(analysis_archive)["decided_by"]["actor_ref"] == "local-operator"

        assert main(["verify", str(analysis_archive)]) == 0
        assert json.loads(capsys.readouterr().out) == analysis_result

        monkeypatch.setenv("USER", "environment-operator")
        assert main(
            [
                "decide",
                "--run",
                analysis_result["run_id"],
                "--verdict",
                "hold",
                "--rationale",
                "Hold the rollout while the review is completed.",
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(env_decision_archive),
            ]
        ) == 0
        env_decision_result = json.loads(capsys.readouterr().out)
        env_decision = _archive_decision(env_decision_archive)
        assert env_decision_result == verify_bundle(env_decision_archive)
        assert env_decision_result["valid"] is True
        assert env_decision["human_verdict"] == "hold"
        assert env_decision["rationale"] == "Hold the rollout while the review is completed."
        assert env_decision["decided_by"]["actor_ref"] == "environment-operator"

        assert main(
            [
                "decide",
                "--run",
                analysis_result["run_id"],
                "--verdict",
                "ship",
                "--rationale",
                "The verified evidence is approved for rollout.",
                "--actor",
                "explicit-operator",
                "--artifact-root",
                str(artifact_root),
                "--out",
                str(actor_decision_archive),
            ]
        ) == 0
        actor_decision_result = json.loads(capsys.readouterr().out)
        actor_decision = _archive_decision(actor_decision_archive)
        assert actor_decision_result == verify_bundle(actor_decision_archive)
        assert actor_decision_result["valid"] is True
        assert actor_decision["human_verdict"] == "ship"
        assert actor_decision["decided_by"]["actor_ref"] == "explicit-operator"

        assert main(["verify", str(actor_decision_archive)]) == 0
        assert json.loads(capsys.readouterr().out) == actor_decision_result

        assert main(
            [
                "runs",
                "list",
                "--artifact-root",
                str(artifact_root),
            ]
        ) == 0
        listed = json.loads(capsys.readouterr().out)["runs"]
        expected = {
            result["run_id"]: {
                "bundle_id": result["bundle_id"],
                "verdicts": result["verdicts"],
            }
            for result in (
                analysis_result,
                env_decision_result,
                actor_decision_result,
            )
        }
        assert {
            item["run_id"]: {
                "bundle_id": item["bundle_id"],
                "verdicts": item["verdicts"],
            }
            for item in listed
        } == expected
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            ("metrics/metric_conversion.json", b"Checkout conversion", b"checkout conversion"),
            "digest_mismatch",
        ),
        (
            ("manifest.json", b"run_foundation_01", b"run_foundation_02"),
            "bundle_id_mismatch",
        ),
    ],
)
def test_one_byte_protected_payload_mutation_breaks_verification(
    tmp_path: Path, mutation: tuple[str, bytes, bytes], expected_code: str
) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    archive = tmp_path / "result.tmk"
    mutated = tmp_path / "mutated.tmk"
    pack_bundle(source, archive)

    _rewrite_archive(archive, mutated, mutation=mutation)
    result = verify_bundle(mutated)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(error["code"] == expected_code for error in result["errors"])


def test_zip_metadata_and_member_order_do_not_change_logical_identity(tmp_path: Path) -> None:
    source = tmp_path / "logical"
    manifest = _make_bundle_directory(source)
    archive = tmp_path / "result.tmk"
    repacked = tmp_path / "repacked.tmk"
    pack_bundle(source, archive)

    _rewrite_archive(archive, repacked, reverse_order=True)

    assert archive.read_bytes() != repacked.read_bytes()
    first = verify_bundle(archive)
    second = verify_bundle(repacked)
    assert first["valid"] is second["valid"] is True
    assert first["bundle_id"] == second["bundle_id"] == manifest["bundle_id"]


@pytest.mark.parametrize(
    ("extra_name", "expected_code"),
    [("../escape.txt", "unsafe_member_path"), ("extra.txt", "unlisted_member")],
)
def test_verifier_rejects_unsafe_and_unlisted_members(
    tmp_path: Path, extra_name: str, expected_code: str
) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    archive = tmp_path / "result.tmk"
    pack_bundle(source, archive)
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(extra_name, b"not protected")

    result = verify_bundle(archive)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(error["code"] == expected_code for error in result["errors"])


def test_packer_refuses_unlisted_source_file(tmp_path: Path) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    (source / "accidental-secret.txt").write_text("token=do-not-pack", encoding="utf-8")

    with pytest.raises(AbxError, match="unlisted"):
        pack_bundle(source, tmp_path / "result.tmk")


def test_packer_preserves_an_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    destination = tmp_path / "result.tmk"
    destination.write_bytes(b"existing archive bytes")

    with pytest.raises(AbxError, match="already exists"):
        pack_bundle(source, destination)

    assert destination.read_bytes() == b"existing archive bytes"
    assert list(tmp_path.glob(".result.tmk.*.tmp")) == []


def test_packer_preserves_a_destination_that_wins_the_publish_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    destination = tmp_path / "result.tmk"

    def racing_link(source_path: str | Path, destination_path: str | Path) -> None:
        del source_path
        Path(destination_path).write_bytes(b"concurrent publisher bytes")
        raise FileExistsError(destination_path)

    monkeypatch.setattr("app.backend.app.evidence.abx.pack.os.link", racing_link)

    with pytest.raises(AbxError, match="appeared during packing"):
        pack_bundle(source, destination)

    assert destination.read_bytes() == b"concurrent publisher bytes"
    assert list(tmp_path.glob(".result.tmk.*.tmp")) == []


def test_privacy_policy_rejects_connection_string_in_query(tmp_path: Path) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(
        source,
        query_payload=b"SELECT 'postgresql://reader:secret@db.example/evidence';\n",
    )
    archive = tmp_path / "with-dsn.tmk"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(candidate for candidate in source.rglob("*") if candidate.is_file()):
            output.write(path, path.relative_to(source).as_posix())

    result = verify_bundle(archive)

    assert result["valid"] is False
    assert result["verdicts"]["privacy_policy"] == "fail"
    assert any(error["code"] == "sensitive_value" for error in result["errors"])
