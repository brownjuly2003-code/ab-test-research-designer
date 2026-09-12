from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from app.backend.app.evidence import data_sources, query_identity
from app.backend.app.evidence.abx import (
    AbxError,
    _query_identity_digest,
    canonical_json_bytes,
    inspect_bundle,
    manifest_bundle_id,
    pack_bundle,
    verify_bundle,
)
from app.backend.app.evidence.data_sources import (
    AggregateQuery,
    DuckDbFileAdapter,
    QueryBudget,
)
from app.backend.tests.test_abx_cli import _make_bundle_directory

_BUNDLE_DIR = (
    Path(__file__).parent / "fixtures" / "evidence" / "asos" / "bundles"
)
_ASOS_BUNDLES = tuple(sorted(_BUNDLE_DIR.glob("*.tmk")))
_PLACEHOLDER_PROTOCOL = "sha256:" + "b" * 64
_PLACEHOLDER_BUILD = "sha256:" + "f" * 64
_PLACEHOLDER_LOCK = "sha256:" + "a" * 64


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _codes(result: dict[str, Any]) -> set[str]:
    return {
        cast(str, error["code"])
        for error in cast(list[dict[str, Any]], result["errors"])
    }


def _load_members(archive_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive_path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _materialize_members(members: dict[str, bytes], logical_root: Path) -> None:
    logical_root.mkdir()
    for name, payload in members.items():
        target = logical_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _write_members(destination: Path, members: dict[str, bytes], tmp_path: Path) -> None:
    logical_root = tmp_path / f"{destination.stem}-logical"
    _materialize_members(members, logical_root)
    pack_bundle(logical_root, destination, require_valid=False)


def _write_clean_archive(destination: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(destination, "w", allowZip64=False) as archive:
        names = ["manifest.json", *sorted(name for name in members if name != "manifest.json")]
        for name in names:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with archive.open(info, "w") as target:
                target.write(members[name])


def _load_json_member(members: dict[str, bytes], path: str) -> dict[str, Any]:
    document = json.loads(members[path])
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


def _dump_json_member(members: dict[str, bytes], path: str, document: dict[str, Any]) -> None:
    members[path] = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode()


def _rebind_manifest(members: dict[str, bytes]) -> None:
    manifest = _load_json_member(members, "manifest.json")
    for entry in cast(list[dict[str, Any]], manifest["entries"]):
        payload = members[cast(str, entry["path"])]
        entry["size"] = len(payload)
        entry["digest"] = _sha256(payload)
    manifest["bundle_id"] = manifest_bundle_id(manifest)
    _dump_json_member(members, "manifest.json", manifest)


def _asos_control_bundle() -> Path:
    assert _ASOS_BUNDLES, "ASOS public benchmark bundles are missing"
    return _BUNDLE_DIR / "d53f0e.tmk"


def test_unchanged_asos_bundles_pass_content_bound_lineage() -> None:
    assert [path.name for path in _ASOS_BUNDLES] == [
        "26bd38.tmk",
        "834947.tmk",
        "d53f0e.tmk",
    ]
    for archive_path in _ASOS_BUNDLES:
        result = verify_bundle(archive_path)
        inspection = inspect_bundle(archive_path)

        assert result["valid"] is True, archive_path.name
        assert result["verdicts"]["lineage"] == "pass", archive_path.name
        assert "lineage/unbound_reference" not in _codes(result), archive_path.name
        assert inspection["valid"] is True, archive_path.name
        assert inspection["verdicts"]["lineage"] == "pass", archive_path.name


def test_placeholder_protocol_revision_id_fails_lineage_even_when_strings_match(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    manifest = _load_json_member(members, "manifest.json")
    run = _load_json_member(members, "run/run.json")
    manifest["protocol_revision_id"] = _PLACEHOLDER_PROTOCOL
    run["protocol_revision_id"] = _PLACEHOLDER_PROTOCOL
    _dump_json_member(members, "manifest.json", manifest)
    _dump_json_member(members, "run/run.json", run)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["protocol_revision_id"] = _PLACEHOLDER_PROTOCOL
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    archive_path = tmp_path / "placeholder-protocol.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_manifest = _load_json_member(packed, "manifest.json")
    packed_run = _load_json_member(packed, "run/run.json")
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert (
        packed_manifest["protocol_revision_id"]
        == packed_run["protocol_revision_id"]
        == _PLACEHOLDER_PROTOCOL
    )
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "protocol_revision_id" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_workbench_placeholder_runner_digests_fail_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    run = _load_json_member(members, "run/run.json")
    run["runner"]["build_digest"] = _PLACEHOLDER_BUILD
    run["runner"]["dependency_lock_digest"] = _PLACEHOLDER_LOCK
    _dump_json_member(members, "run/run.json", run)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["runner"]["build_digest"] = _PLACEHOLDER_BUILD
            estimate["lineage"]["runner"]["dependency_lock_digest"] = _PLACEHOLDER_LOCK
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    archive_path = tmp_path / "placeholder-runner.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    inspection = inspect_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert inspection["valid"] is False
    assert inspection["verdicts"]["lineage"] == "fail"


def test_one_byte_protocol_json_change_fails_lineage_after_integrity_rebind(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    protocol_path = "protocol/protocol.json"
    original = members[protocol_path]
    marker = b"ASOS public benchmark d53f0e"
    replacement = b"ASOS public benchmark d53f0E"
    assert marker in original
    assert len(marker) == len(replacement)
    members[protocol_path] = original.replace(marker, replacement, 1)
    assert members[protocol_path] != original
    _rebind_manifest(members)

    protocol = json.loads(members[protocol_path])
    content_digest = _sha256(canonical_json_bytes(protocol))
    manifest = _load_json_member(members, "manifest.json")
    run = _load_json_member(members, "run/run.json")
    assert manifest["protocol_revision_id"] == run["protocol_revision_id"]
    assert manifest["protocol_revision_id"] != content_digest

    archive_path = tmp_path / "protocol-one-byte.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)


def _rewrite_run_query_id(members: dict[str, bytes], query_id: str | None) -> None:
    run = _load_json_member(members, "run/run.json")
    original = run["queries"][0]["query_id"]
    if query_id is None:
        del run["queries"][0]["query_id"]
    else:
        run["queries"][0]["query_id"] = query_id
    _dump_json_member(members, "run/run.json", run)
    if not isinstance(query_id, str):
        return
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["query_ids"] = [
                query_id if item == original else item
                for item in estimate["lineage"]["query_ids"]
            ]
            _dump_json_member(members, path, estimate)


def test_query_id_degenerate_fails_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    _rewrite_run_query_id(members, "sha256:" + "c" * 64)
    _rebind_manifest(members)

    archive_path = tmp_path / "degenerate-query-id.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "query_id" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


@pytest.mark.parametrize(
    "query_id",
    [
        pytest.param("not-a-digest", id="malformed"),
        pytest.param(None, id="missing"),
    ],
)
def test_malformed_or_missing_query_id_fails_schema_before_lineage(
    tmp_path: Path,
    query_id: str | None,
) -> None:
    members = _load_members(_asos_control_bundle())
    _rewrite_run_query_id(members, query_id)
    _rebind_manifest(members)

    archive_path = tmp_path / "schema-query-id.tmk"
    _write_clean_archive(archive_path, members)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["schema_conformance"] == "fail"
    assert result["verdicts"]["lineage"] == "not_checked"
    assert "lineage/unbound_reference" not in _codes(result)


def test_statement_digest_not_bound_to_query_bytes_fails_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    run = _load_json_member(members, "run/run.json")
    statement_path = cast(str, run["queries"][0]["statement_path"])
    original_digest = run["queries"][0]["statement_digest"]
    members[statement_path] = members[statement_path] + b"\n-- mutated-byte\n"
    assert original_digest != _sha256(members[statement_path])
    _rebind_manifest(members)

    archive_path = tmp_path / "unbound-sql.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "statement_digest" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_estimate_metric_digest_not_bound_to_metric_content_fails_lineage(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    wrong_digest = "sha256:" + "ab" * 32
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["metric"]["metric_digest"] = wrong_digest
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    archive_path = tmp_path / "unbound-metric.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)


def _rebind_estimate_metric_digests(members: dict[str, bytes]) -> None:
    metric_digests: dict[str, str] = {}
    for path, payload in members.items():
        if path.startswith("metrics/") and path.endswith(".json"):
            metric = _load_json_member(members, path)
            metric_digests[cast(str, metric["metric_id"])] = _sha256(payload)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            metric_id = cast(str, estimate["lineage"]["metric"]["metric_id"])
            estimate["lineage"]["metric"]["metric_digest"] = metric_digests[metric_id]
            _dump_json_member(members, path, estimate)


def _rebind_protocol_revision_ids(members: dict[str, bytes]) -> None:
    protocol = json.loads(members["protocol/protocol.json"])
    digest = _sha256(canonical_json_bytes(protocol))
    manifest = _load_json_member(members, "manifest.json")
    manifest["protocol_revision_id"] = digest
    _dump_json_member(members, "manifest.json", manifest)
    run = _load_json_member(members, "run/run.json")
    run["protocol_revision_id"] = digest
    _dump_json_member(members, "run/run.json", run)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["protocol_revision_id"] = digest
            _dump_json_member(members, path, estimate)
        if path.startswith("decision/") and path.endswith(".json"):
            decision = _load_json_member(members, path)
            decision["protocol_revision_id"] = digest
            _dump_json_member(members, path, decision)


def _iter_metric_paths(members: dict[str, bytes]) -> list[str]:
    return [
        path
        for path in members
        if path.startswith("metrics/") and path.endswith(".json")
    ]


def _set_protocol_definition_digests(
    members: dict[str, bytes],
    digests: dict[str, str],
) -> None:
    protocol = _load_json_member(members, "protocol/protocol.json")
    for group in ("primary", "secondary", "guardrails"):
        for metric_ref in cast(list[dict[str, Any]], protocol.get("metrics", {}).get(group, [])):
            metric_id = cast(str, metric_ref["metric_id"])
            if metric_id in digests:
                metric_ref["definition_digest"] = digests[metric_id]
    _dump_json_member(members, "protocol/protocol.json", protocol)


def test_second_embedded_definition_does_not_silently_match_digest_strings(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    claimed: dict[str, str] = {}
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        definition = cast(dict[str, Any], metric["extensions"]["trialmark.asos"]["definition"])
        claimed[cast(str, metric["metric_id"])] = cast(str, metric["definition_digest"])
        definition["original_semantics_available"] = not bool(
            definition["original_semantics_available"]
        )
        metric["extensions"]["trialmark.decoy"] = {"definition": {"note": "decoy"}}
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "multiple-definitions.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_protocol = _load_json_member(packed, "protocol/protocol.json")
    packed_metric = _load_json_member(packed, _iter_metric_paths(packed)[0])
    result = verify_bundle(archive_path)

    assert packed_metric["definition_digest"] == claimed[cast(str, packed_metric["metric_id"])]
    assert (
        packed_protocol["metrics"]["primary"][0]["definition_digest"]
        == packed_metric["definition_digest"]
    )
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    test_unchanged_asos_bundles_pass_content_bound_lineage()


def test_absent_embedded_definition_compares_declared_digest_strings(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        metric["extensions"] = {}
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "definition-absent.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"
    assert "lineage/unbound_reference" not in _codes(result)
    assert "metric_definition_mismatch" not in _codes(result)


def test_absent_embedded_definition_mismatch_fails_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        metric["extensions"] = {}
        metric["definition_digest"] = "sha256:" + "ab" * 32
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "definition-absent-mismatch.tmk"
    _write_clean_archive(archive_path, members)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "metric_definition_mismatch" in _codes(result)
    assert "lineage/unbound_reference" not in _codes(result)


def test_extension_payload_without_definition_key_is_bound_not_downgraded(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    claimed: dict[str, str] = {}
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        claimed[cast(str, metric["metric_id"])] = cast(str, metric["definition_digest"])
        asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
        asos_extension["spec"] = asos_extension.pop("definition")
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "definition-other-key.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_metric = _load_json_member(packed, _iter_metric_paths(packed)[0])
    packed_protocol = _load_json_member(packed, "protocol/protocol.json")
    result = verify_bundle(archive_path)

    assert packed_metric["definition_digest"] == claimed[cast(str, packed_metric["metric_id"])]
    assert (
        packed_protocol["metrics"]["primary"][0]["definition_digest"]
        == packed_metric["definition_digest"]
    )
    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert "metric_definition_mismatch" not in _codes(result)


def test_nested_definition_is_bound_to_stored_extensions_form(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
        asos_extension["wrapper"] = {"definition": asos_extension.pop("definition")}
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "nested-definition.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_metric = _load_json_member(packed, _iter_metric_paths(packed)[0])
    packed_protocol = _load_json_member(packed, "protocol/protocol.json")
    result = verify_bundle(archive_path)

    assert (
        packed_metric["definition_digest"]
        == packed_protocol["metrics"]["primary"][0]["definition_digest"]
    )
    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)


def test_extension_form_without_definition_key_is_rejected_even_when_digest_matches_extensions(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    metric_paths = _iter_metric_paths(members)
    digests: dict[str, str] = {}
    for path in metric_paths:
        metric = _load_json_member(members, path)
        asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
        asos_extension.pop("definition")
        digest = _sha256(canonical_json_bytes(metric["extensions"]))
        metric["definition_digest"] = digest
        digests[cast(str, metric["metric_id"])] = digest
        _dump_json_member(members, path, metric)
    _set_protocol_definition_digests(members, digests)
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "extensions-form-bound.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert result["unbound_bindings"] == sorted(metric_paths)
    test_unchanged_asos_bundles_pass_content_bound_lineage()


def test_definition_payload_may_contain_nested_definition_key(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    digests: dict[str, str] = {}
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        definition = cast(dict[str, Any], metric["extensions"]["trialmark.asos"]["definition"])
        definition["definition"] = "inner-label"
        digest = _sha256(canonical_json_bytes(definition))
        metric["definition_digest"] = digest
        digests[cast(str, metric["metric_id"])] = digest
        _dump_json_member(members, path, metric)
    _set_protocol_definition_digests(members, digests)
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "nested-key-in-definition.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"


def test_query_identity_binding_uses_the_producer_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert data_sources.query_identity_digest is query_identity.query_identity_digest
    monkeypatch.setattr(
        "app.backend.app.evidence.query_identity.query_identity_digest",
        lambda **_: "sha256:" + "ab" * 32,
        raising=False,
    )

    result = verify_bundle(_asos_control_bundle())

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)


def test_pack_bundle_require_valid_false_allows_only_unbound_reference(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    run = _load_json_member(members, "run/run.json")
    run["runner"]["build_digest"] = _PLACEHOLDER_BUILD
    run["runner"]["dependency_lock_digest"] = _PLACEHOLDER_LOCK
    _dump_json_member(members, "run/run.json", run)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["runner"]["build_digest"] = _PLACEHOLDER_BUILD
            estimate["lineage"]["runner"]["dependency_lock_digest"] = _PLACEHOLDER_LOCK
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    logical_root = tmp_path / "unbound-logical"
    _materialize_members(members, logical_root)
    packed = pack_bundle(logical_root, tmp_path / "unbound.tmk", require_valid=False)

    assert packed["valid"] is False
    assert packed["verdicts"]["lineage"] == "fail"
    assert _codes(packed) == {"lineage/unbound_reference"}


def test_pack_bundle_require_valid_false_still_blocks_other_lineage_errors(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["estimand_id"] = "estimand_other"
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    logical_root = tmp_path / "estimand-logical"
    _materialize_members(members, logical_root)
    with pytest.raises(AbxError, match="estimate_estimand"):
        pack_bundle(logical_root, tmp_path / "blocked.tmk", require_valid=False)


def test_decision_context_message_names_only_the_run_id_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    packed = tmp_path / "cli.tmk"
    pack_bundle(source, packed)
    members = _load_members(packed)
    decision = _load_json_member(members, "decision/decision.json")
    decision["run_id"] = "run_other_01"
    _dump_json_member(members, "decision/decision.json", decision)
    _rebind_manifest(members)

    archive_path = tmp_path / "decision-run.tmk"
    _write_clean_archive(archive_path, members)
    result = verify_bundle(archive_path)

    messages = [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "decision_context"
    ]
    assert messages
    assert messages == ["decision references a different run"]
    assert all("protocol" not in message for message in messages)


def test_decision_protocol_mismatch_is_unbound_reference_not_decision_context(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logical"
    _make_bundle_directory(source)
    packed = tmp_path / "cli.tmk"
    pack_bundle(source, packed)
    members = _load_members(packed)
    decision = _load_json_member(members, "decision/decision.json")
    decision["protocol_revision_id"] = "sha256:" + "ab" * 32
    _dump_json_member(members, "decision/decision.json", decision)
    _rebind_manifest(members)

    archive_path = tmp_path / "decision-protocol.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert "decision_context" not in _codes(result)
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert any(
        "protocol_revision_id" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference"
    )


def test_query_id_not_bound_to_identity_document_fails_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    run = _load_json_member(members, "run/run.json")
    original_query_id = run["queries"][0]["query_id"]
    run["queries"][0]["parameters_digest"] = "sha256:" + "ab" * 32
    _dump_json_member(members, "run/run.json", run)
    _rebind_manifest(members)

    archive_path = tmp_path / "unbound-query-identity.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    packed_run = _load_json_member(_load_members(archive_path), "run/run.json")
    assert packed_run["queries"][0]["query_id"] == original_query_id
    assert packed_run["queries"][0]["parameters_digest"] == "sha256:" + "ab" * 32
    assert result["valid"] is False
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "query_id" in cast(str, error["message"])
        and "identity" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )
    test_unchanged_asos_bundles_pass_content_bound_lineage()


def test_well_formed_unrelated_query_id_fails_lineage(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    unrelated = _sha256(b"totally unrelated query identity")
    run = _load_json_member(members, "run/run.json")
    original = run["queries"][0]["query_id"]
    run["queries"][0]["query_id"] = unrelated
    _dump_json_member(members, "run/run.json", run)
    for path in list(members):
        if path.startswith("estimates/") and path.endswith(".json"):
            estimate = _load_json_member(members, path)
            estimate["lineage"]["query_ids"] = [
                unrelated if item == original else item
                for item in estimate["lineage"]["query_ids"]
            ]
            _dump_json_member(members, path, estimate)
    _rebind_manifest(members)

    archive_path = tmp_path / "unrelated-query-id.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert unrelated != original
    assert result["valid"] is False
    assert result["verdicts"]["schema_conformance"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "query_id" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_matching_placeholder_definition_digests_fail_when_definition_content_exists(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    wrong = "sha256:" + "ab" * 32
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        metric["definition_digest"] = wrong
        _dump_json_member(members, path, metric)
    protocol = _load_json_member(members, "protocol/protocol.json")
    for group in ("primary", "secondary", "guardrails"):
        for metric_ref in cast(list[dict[str, Any]], protocol.get("metrics", {}).get(group, [])):
            metric_ref["definition_digest"] = wrong
    _dump_json_member(members, "protocol/protocol.json", protocol)
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "unbound-definition-digest.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_protocol = _load_json_member(packed, "protocol/protocol.json")
    packed_metric = _load_json_member(packed, _iter_metric_paths(packed)[0])
    result = verify_bundle(archive_path)

    assert packed_metric["definition_digest"] == wrong
    assert packed_protocol["metrics"]["primary"][0]["definition_digest"] == wrong
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "pass"
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "definition_digest" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )
    test_unchanged_asos_bundles_pass_content_bound_lineage()


def test_embedded_definition_mutation_fails_lineage_while_digest_strings_still_match(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    protocol = _load_json_member(members, "protocol/protocol.json")
    original_refs = {
        cast(str, metric_ref["metric_id"]): cast(str, metric_ref["definition_digest"])
        for group in ("primary", "secondary", "guardrails")
        for metric_ref in cast(list[dict[str, Any]], protocol.get("metrics", {}).get(group, []))
    }
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        definition = cast(dict[str, Any], metric["extensions"]["trialmark.asos"]["definition"])
        assert metric["definition_digest"] == original_refs[cast(str, metric["metric_id"])]
        definition["original_semantics_available"] = not bool(
            definition["original_semantics_available"]
        )
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "mutated-definition.tmk"
    _write_members(archive_path, members, tmp_path)
    packed = _load_members(archive_path)
    packed_protocol = _load_json_member(packed, "protocol/protocol.json")
    packed_metric = _load_json_member(packed, _iter_metric_paths(packed)[0])
    result = verify_bundle(archive_path)

    assert (
        packed_metric["definition_digest"]
        == packed_protocol["metrics"]["primary"][0]["definition_digest"]
    )
    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "definition_digest" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_canonical_digest_does_not_swallow_oserror_from_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `_core` is where `_canonical_digest` resolves the name, so that is
    # the module the substitute has to land in.
    from app.backend.app.evidence.abx import _core as abx_module

    real = abx_module.canonical_json_bytes

    def selective(value: object) -> bytes:
        if isinstance(value, dict) and "spec_version" in value:
            raise OSError("disk vanished")
        return real(value)

    monkeypatch.setattr(abx_module, "canonical_json_bytes", selective)
    result = verify_bundle(_asos_control_bundle())
    messages = [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    ]
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any("disk vanished" in message for message in messages)
    assert all("RFC 8785 canonicalizable" not in message for message in messages)


def test_canonical_digest_maps_recursion_error_to_unbound_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `_core` is where `_canonical_digest` resolves the name, so that is
    # the module the substitute has to land in.
    from app.backend.app.evidence.abx import _core as abx_module

    real = abx_module.canonical_json_bytes

    def selective(value: object) -> bytes:
        if isinstance(value, dict) and "spec_version" in value:
            raise RecursionError("too deep")
        return real(value)

    monkeypatch.setattr(abx_module, "canonical_json_bytes", selective)
    result = verify_bundle(_asos_control_bundle())
    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert any(
        error["code"] == "lineage/unbound_reference"
        and "RFC 8785 canonicalizable" in cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_query_identity_digest_matches_live_producer_provenance() -> None:
    adapter = DuckDbFileAdapter(
        path=Path(__file__).parent / "fixtures" / "evidence" / "cross_engine.csv",
        relation="evidence_fixture",
        source_ref="cross_engine_fixture",
    )
    result = adapter.execute(
        AggregateQuery(
            statement=(
                "SELECT variant, COUNT(*)::BIGINT AS units "
                "FROM evidence_fixture GROUP BY variant ORDER BY variant"
            ),
            budget=QueryBudget(max_scan_rows=100, timeout_ms=500, max_result_rows=10),
        )
    )
    provenance = result.provenance
    query_doc = {
        "dialect": provenance.dialect,
        "parameters_digest": provenance.parameters_digest,
        "statement_digest": provenance.statement_digest,
    }
    source_doc = {"fingerprint": provenance.source_fingerprint.model_dump(mode="json")}

    assert _query_identity_digest(query_doc, source_doc) == provenance.query_id
    assert provenance.query_id == data_sources.query_identity_digest(
        dialect=provenance.dialect,
        parameters_digest=provenance.parameters_digest,
        source_fingerprint=provenance.source_fingerprint.model_dump(mode="json"),
        statement_digest=provenance.statement_digest,
    )
