from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from app.backend.app.evidence import data_sources, query_identity
from app.backend.app.evidence.abx import (
    _canonical_digest,
    inspect_bundle,
    verify_bundle,
)
from app.backend.app.evidence.cli import main
from app.backend.tests.test_evidence_abx_content_binding import (
    _ASOS_BUNDLES,
    _PLACEHOLDER_BUILD,
    _PLACEHOLDER_LOCK,
    _asos_control_bundle,
    _codes,
    _dump_json_member,
    _iter_metric_paths,
    _load_json_member,
    _load_members,
    _rebind_estimate_metric_digests,
    _rebind_manifest,
    _rebind_protocol_revision_ids,
    _set_protocol_definition_digests,
    _write_clean_archive,
    _write_members,
)
from app.backend.tests.test_evidence_abx_zip_transport import (
    _NO_END_RECORD,
    _central_directory_offsets,
    _copy_bundle,
    _eocd_offset,
    _integrity_errors,
    _verification_codes,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SFX_PREFIX = b"MZ" + b"\x00" * 62


def _prepend_sfx_with_absolute_offsets(path: Path, prefix: bytes) -> None:
    payload = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
        first_header = archive.infolist()[0].header_offset
    shift = len(prefix)
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        stored = int.from_bytes(payload[central_offset + 42 : central_offset + 46], "little")
        payload[central_offset + 42 : central_offset + 46] = (stored + shift).to_bytes(4, "little")
    eocd = _eocd_offset(payload)
    stored_cd = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    payload[eocd + 16 : eocd + 20] = (stored_cd + shift).to_bytes(4, "little")
    path.write_bytes(prefix + bytes(payload))
    with zipfile.ZipFile(path) as archive:
        assert archive.infolist()[0].header_offset == first_header + shift
        assert archive.start_dir == start_dir + shift


def _inflate_cd_and_eocd_offsets(path: Path, shift: int) -> None:
    payload = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        stored = int.from_bytes(payload[central_offset + 42 : central_offset + 46], "little")
        payload[central_offset + 42 : central_offset + 46] = (stored + shift).to_bytes(4, "little")
    eocd = _eocd_offset(payload)
    stored_cd = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    payload[eocd + 16 : eocd + 20] = (stored_cd + shift).to_bytes(4, "little")
    path.write_bytes(payload)


def test_uniform_cd_and_eocd_offset_inflation_is_rejected(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "inflated-cd-eocd-offsets.tmk")
    _inflate_cd_and_eocd_offsets(archive_path, 4096)

    result = verify_bundle(archive_path)
    integrity = _integrity_errors(result)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    trailing = [error for error in integrity if error["code"] == "archive_trailing_bytes"]
    assert len(trailing) == 1
    assert "path" not in trailing[0]
    assert "central_directory_mismatch" not in _verification_codes(result)


def test_sfx_prefix_with_absolute_offsets_reports_prefix_without_member_mismatch(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "sfx-absolute-offsets.tmk")
    _prepend_sfx_with_absolute_offsets(archive_path, _SFX_PREFIX)

    result = verify_bundle(archive_path)
    integrity = _integrity_errors(result)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "archive contains bytes before the first member record"
        and "path" not in error
        for error in integrity
    )
    assert "central_directory_mismatch" not in _verification_codes(result)
    assert not any(error.get("path") for error in integrity)
    assert not any(error["message"] == _NO_END_RECORD for error in integrity)


def test_cd_only_external_attr_does_not_invalidate_bundle(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "cd-only-symlink-attr.tmk")
    with zipfile.ZipFile(archive_path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
    payload = bytearray(archive_path.read_bytes())
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        payload[central_offset + 38 : central_offset + 42] = ((0o120777) << 16).to_bytes(
            4, "little"
        )
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)
    assert "special_member" not in _verification_codes(result)


def test_directory_member_is_rejected_as_directory_not_symlink(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "directory-member-source.tmk")
    archive_path = tmp_path / "directory-member.tmk"
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(info, source.read(info))
            output.writestr("empty_dir/", b"")

    result = verify_bundle(archive_path)
    directory = [
        error
        for error in cast(list[dict[str, Any]], result["errors"])
        if error.get("path") == "empty_dir/"
    ]

    assert result["valid"] is False
    assert {error["code"] for error in directory} == {"unsafe_member_path"}
    assert "special_member" not in _verification_codes(result)
    assert not any(
        "symlink" in cast(str, error["message"]) or "special file" in cast(str, error["message"])
        for error in directory
    )


def test_offline_verifier_import_does_not_load_database_adapters() -> None:
    script = (
        "import sys\n"
        "import app.backend.app.evidence.abx  # noqa: F401\n"
        "loaded = set(sys.modules)\n"
        "assert 'duckdb' not in loaded, sorted(loaded)\n"
        "assert 'psycopg' not in loaded, sorted(loaded)\n"
        "assert not any(name == 'psycopg' or name.startswith('psycopg.') for name in loaded)\n"
    )
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_REPO_ROOT), pythonpath]))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_absent_embedded_definition_surfaces_unbound_bindings(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    metric_paths = _iter_metric_paths(members)
    for path in metric_paths:
        metric = _load_json_member(members, path)
        metric["extensions"] = {}
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "definition-absent-unbound.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    inspection = inspect_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"
    assert result["unbound_bindings"] == sorted(metric_paths)
    assert inspection["unbound_bindings"] == result["unbound_bindings"]
    assert "lineage/unbound_reference" not in _codes(result)


def _bundle_with_run_only_unbound_metric(tmp_path: Path) -> Path:
    members = _load_members(_asos_control_bundle())
    protocol = _load_json_member(members, "protocol/protocol.json")
    secondary = list(protocol["metrics"]["secondary"])
    protocol["metrics"]["secondary"] = [
        ref for ref in secondary if ref.get("metric_id") != "metric_asos_4"
    ]
    assert len(protocol["metrics"]["secondary"]) == len(secondary) - 1
    _dump_json_member(members, "protocol/protocol.json", protocol)
    metric = _load_json_member(members, "metrics/metric_asos_4.json")
    metric["extensions"] = {}
    _dump_json_member(members, "metrics/metric_asos_4.json", metric)
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)
    archive_path = tmp_path / "run-only-metric-unbound.tmk"
    _write_members(archive_path, members, tmp_path)
    return archive_path


def test_run_referenced_metric_absent_definition_is_in_unbound_bindings(
    tmp_path: Path,
) -> None:
    archive_path = _bundle_with_run_only_unbound_metric(tmp_path)
    result = verify_bundle(archive_path)
    inspection = inspect_bundle(archive_path)

    assert result["valid"] is True
    assert result["verdicts"]["lineage"] == "pass"
    assert result["errors"] == []
    assert result["unbound_bindings"] == ["metrics/metric_asos_4.json"]
    assert inspection["unbound_bindings"] == result["unbound_bindings"]
    assert "lineage/unbound_reference" not in _codes(result)


def test_ambiguous_and_unlocated_definitions_are_in_unbound_bindings(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    ambiguous_path = "metrics/metric_asos_1.json"
    unlocated_path = "metrics/metric_asos_2.json"
    ambiguous = _load_json_member(members, ambiguous_path)
    ambiguous["extensions"]["trialmark.decoy"] = {"definition": {"note": "decoy"}}
    _dump_json_member(members, ambiguous_path, ambiguous)
    unlocated = _load_json_member(members, unlocated_path)
    asos_extension = cast(dict[str, Any], unlocated["extensions"]["trialmark.asos"])
    asos_extension["spec"] = asos_extension.pop("definition")
    _dump_json_member(members, unlocated_path, unlocated)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "ambiguous-unlocated-unbound.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert "lineage/unbound_reference" in _codes(result)
    assert ambiguous_path in result["unbound_bindings"]
    assert unlocated_path in result["unbound_bindings"]


def test_unlocated_metric_matching_extensions_digest_is_rejected(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    metric_path = "metrics/metric_asos_2.json"
    metric = _load_json_member(members, metric_path)
    asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
    asos_extension.pop("definition")
    asos_extension["note"] = "definition payload not embedded"
    extensions = cast(dict[str, Any], metric["extensions"])
    digest = _canonical_digest(extensions)
    assert digest is not None
    metric["definition_digest"] = digest
    _dump_json_member(members, metric_path, metric)
    _set_protocol_definition_digests(members, {"metric_asos_2": digest})
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "unlocated-extensions-digest.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert metric_path in result["unbound_bindings"]
    assert any(
        error["code"] == "lineage/unbound_reference" and error.get("path") == metric_path
        for error in cast(list[dict[str, Any]], result["errors"])
    )


def test_asos_control_bundles_have_empty_unbound_bindings() -> None:
    for archive_path in _ASOS_BUNDLES:
        result = verify_bundle(archive_path)
        inspection = inspect_bundle(archive_path)

        assert result["valid"] is True, archive_path.name
        assert result["verdicts"]["lineage"] == "pass", archive_path.name
        assert result["unbound_bindings"] == [], archive_path.name
        assert inspection["unbound_bindings"] == [], archive_path.name


def test_inspect_summary_reports_unbound_bindings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    control = _asos_control_bundle()
    assert main(["inspect", str(control), "--format", "summary"]) == 0
    control_out = capsys.readouterr().out.splitlines()
    assert "unbound_bindings: 0" in control_out

    archive_path = _bundle_with_run_only_unbound_metric(tmp_path)
    assert main(["inspect", str(archive_path), "--format", "summary"]) == 0
    mutated_out = capsys.readouterr().out.splitlines()
    assert "unbound_bindings: 1 (metrics/metric_asos_4.json)" in mutated_out


def test_run_only_metric_tampered_embedded_definition_fails_lineage(
    tmp_path: Path,
) -> None:
    members = _load_members(_asos_control_bundle())
    protocol = _load_json_member(members, "protocol/protocol.json")
    secondary = list(protocol["metrics"]["secondary"])
    protocol["metrics"]["secondary"] = [
        ref for ref in secondary if ref.get("metric_id") != "metric_asos_4"
    ]
    assert len(protocol["metrics"]["secondary"]) == len(secondary) - 1
    _dump_json_member(members, "protocol/protocol.json", protocol)
    metric_path = "metrics/metric_asos_4.json"
    metric = _load_json_member(members, metric_path)
    declared = metric["definition_digest"]
    metric["extensions"]["trialmark.asos"]["definition"]["reported_kind"] = "TAMPERED"
    _dump_json_member(members, metric_path, metric)
    _rebind_protocol_revision_ids(members)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "run-only-metric-tampered-definition.tmk"
    _write_members(archive_path, members, tmp_path)
    packed_metric = _load_json_member(_load_members(archive_path), metric_path)
    result = verify_bundle(archive_path)
    lineage_errors = [
        error
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference" and error.get("path") == metric_path
    ]

    assert packed_metric["definition_digest"] == declared
    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert len(lineage_errors) == 1


def test_integrity_failure_reports_unbound_bindings_not_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive_path = _copy_bundle(tmp_path, "integrity-fail-unbound.tmk")
    payload = bytearray(archive_path.read_bytes())
    payload[0] ^= 0xFF
    archive_path.write_bytes(bytes(payload))

    result = verify_bundle(archive_path)
    inspection = inspect_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert result["verdicts"]["lineage"] == "not_checked"
    assert result["unbound_bindings"] is None
    assert inspection["unbound_bindings"] is None

    assert main(["inspect", str(archive_path), "--format", "summary"]) == 1
    summary = capsys.readouterr().out.splitlines()
    assert "unbound_bindings: not_checked" in summary
    assert "unbound_bindings: 0" not in summary


def test_query_identity_helpers_are_exported_under_public_names() -> None:
    assert data_sources.query_identity_digest is query_identity.query_identity_digest
    assert data_sources.digest_json is query_identity.digest_json
    assert data_sources.sha256_prefixed is query_identity.sha256_prefixed


def test_degenerate_runner_digest_message_names_placeholder(tmp_path: Path) -> None:
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

    archive_path = tmp_path / "degenerate-runner-message.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    messages = [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference"
    ]

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert any(
        "is a degenerate placeholder digest, not a content digest" in message
        for message in messages
    )
    assert not any("missing, malformed, or degenerate" in message for message in messages)


def test_missing_protocol_member_reports_unbound_bindings_not_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    members = _load_members(_asos_control_bundle())
    metric = _load_json_member(members, "metrics/metric_asos_4.json")
    metric["extensions"] = {}
    _dump_json_member(members, "metrics/metric_asos_4.json", metric)
    _rebind_manifest(members)
    del members["protocol/protocol.json"]
    archive_path = tmp_path / "missing-protocol-unbound.tmk"
    _write_clean_archive(archive_path, members)

    result = verify_bundle(archive_path)
    inspection = inspect_bundle(archive_path)
    codes = _codes(result)

    assert result["valid"] is False
    assert "missing_member" in codes
    assert "role_cardinality" in codes
    assert result["unbound_bindings"] is None
    assert inspection["unbound_bindings"] is None
    assert result["verdicts"]["lineage"] == "not_checked"

    assert main(["inspect", str(archive_path), "--format", "summary"]) == 1
    summary = capsys.readouterr().out.splitlines()
    assert "unbound_bindings: not_checked" in summary
    assert "unbound_bindings: 0" not in summary


def test_sfx_prefix_without_rebasing_offsets_reports_only_archive_trailing_bytes(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "sfx-relative-offsets.tmk")
    archive_path.write_bytes(_SFX_PREFIX + archive_path.read_bytes())

    result = verify_bundle(archive_path)
    integrity = _integrity_errors(result)
    trailing = [error for error in integrity if error["code"] == "archive_trailing_bytes"]

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert len(trailing) == 2
    assert all("path" not in error for error in trailing)
    assert not any(error.get("path") for error in integrity)
    assert "central_directory_mismatch" not in _verification_codes(result)


def test_tampered_cd_local_header_offset_is_reported_on_that_member(tmp_path: Path) -> None:
    member_name = "metrics/metric_asos_2.json"
    archive_path = _copy_bundle(tmp_path, "tampered-cd-local-offset.tmk")
    with zipfile.ZipFile(archive_path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
    payload = bytearray(archive_path.read_bytes())
    needle = member_name.encode("utf-8")
    target_cd: int | None = None
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        name_size = int.from_bytes(payload[central_offset + 28 : central_offset + 30], "little")
        name = bytes(payload[central_offset + 46 : central_offset + 46 + name_size])
        if name == needle:
            target_cd = central_offset
            break
    assert target_cd is not None
    stored = int.from_bytes(payload[target_cd + 42 : target_cd + 46], "little")
    payload[target_cd + 42 : target_cd + 46] = (stored + 1).to_bytes(4, "little")
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)
    named = [
        error
        for error in cast(list[dict[str, Any]], result["errors"])
        if error.get("path") == member_name
    ]

    assert result["valid"] is False
    assert named
    assert any(error["code"] == "central_directory_mismatch" for error in named)


def test_trailing_backslash_member_error_codes_are_platform_independent(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "backslash-member-source.tmk")
    archive_path = tmp_path / "backslash-member.tmk"
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(info, source.read(info))
            output.writestr("dirmember/", b"")
    payload = bytearray(archive_path.read_bytes())
    slash_name = b"dirmember/"
    backslash_name = b"dirmember" + b"\\"
    assert payload.count(slash_name) == 2
    archive_path.write_bytes(payload.replace(slash_name, backslash_name))

    result = verify_bundle(archive_path)
    member_codes = {
        cast(str, error["code"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error.get("path") in {"dirmember\\", "dirmember/"}
    }

    assert result["valid"] is False
    assert member_codes == {"unsafe_member_path"}


def test_stored_offsets_match_physical_layout_is_boolean_not_unshift(
    tmp_path: Path,
) -> None:
    from app.backend.app.evidence.abx import _stored_offsets_match_physical_layout

    def layout_matches(path: Path) -> bool:
        with zipfile.ZipFile(path) as archive:
            source = archive.fp
            assert source is not None
            position = source.tell()
            source.seek(0, os.SEEK_END)
            size = source.tell()
            source.seek(position)
            matched = _stored_offsets_match_physical_layout(archive, source, size)
        assert matched is True or matched is False
        return matched

    control = _copy_bundle(tmp_path, "layout-match.tmk")
    assert layout_matches(control) is True

    inflated = _copy_bundle(tmp_path, "layout-mismatch.tmk")
    _inflate_cd_and_eocd_offsets(inflated, 4096)
    assert layout_matches(inflated) is False

    sfx = _copy_bundle(tmp_path, "layout-sfx-absolute.tmk")
    _prepend_sfx_with_absolute_offsets(sfx, _SFX_PREFIX)
    with zipfile.ZipFile(sfx) as archive:
        assert archive.infolist()[0].header_offset > 0
    assert layout_matches(sfx) is True


def _markdown_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("- "):
            if current:
                bullets.append(" ".join(current))
            current = [stripped[2:].strip()]
        elif current:
            if stripped:
                current.append(stripped)
            else:
                bullets.append(" ".join(current))
                current = []
    if current:
        bullets.append(" ".join(current))
    return bullets


def _clause_for(bullets: list[str], *, label: str, predicate: Any) -> str:
    matches = [item for item in bullets if predicate(item)]
    assert len(matches) == 1, f"{label}: expected 1 clause, got {matches!r}"
    return matches[0]


def _binding_state_clauses(text: str) -> dict[str, str]:
    bullets = _markdown_bullets(text)
    return {
        "absent": _clause_for(
            bullets, label="absent", predicate=lambda item: item.startswith("`absent`")
        ),
        "ambiguous": _clause_for(
            bullets,
            label="ambiguous",
            predicate=lambda item: "`ambiguous`" in item and "`unlocated`" in item,
        ),
        "present_mismatch": _clause_for(
            bullets,
            label="present_mismatch",
            predicate=lambda item: "`present`" in item and "does not match" in item,
        ),
        "present_match": _clause_for(
            bullets,
            label="present_match",
            predicate=lambda item: "`present`" in item and "matching digest" in item,
        ),
        "null": _clause_for(
            bullets,
            label="null",
            predicate=lambda item: "`null`" in item and "`not_checked`" in item,
        ),
    }


_OVERBROAD_UNBOUND_BINDINGS_INTRO = (
    "That key lists metric artifact paths whose definition identifiers "
    "could not be bound to content in the bundle (absent, ambiguous, or "
    "unlocated definition payload)."
)


def _assert_section_73_intro(text: str) -> None:
    folded = " ".join(text.split())
    assert "in binding states `absent`, `ambiguous`, and `unlocated`" in folded
    assert "could not be bound to content" not in folded


def _assert_binding_state_contract(text: str) -> None:
    clauses = _binding_state_clauses(text)
    absent = clauses["absent"]
    assert "listed and accepted" in absent
    assert "rejected" not in absent
    ambiguous = clauses["ambiguous"]
    assert "listed and rejected" in ambiguous
    assert "listed and accepted" not in ambiguous
    mismatch = clauses["present_mismatch"]
    assert "rejected as" in mismatch
    assert "not rejected" not in mismatch
    assert "listed and accepted" not in mismatch
    assert "not listed" in mismatch or "omitted" in mismatch
    match = clauses["present_match"]
    assert "the definition is bound" in match
    assert "accepted" in match
    assert "not listed" in match
    assert "rejected" not in match
    null = clauses["null"]
    assert "was not evaluated" in null or "were not evaluated" in null
    assert "was evaluated" not in null


def _section(text: str, start: str, end: str, label: str) -> str:
    assert start in text, f"{label}: missing section marker {start!r}"
    assert end in text, f"{label}: missing section marker {end!r}"
    after_start = text.split(start, 1)[1]
    assert end in after_start, f"{label}: missing section marker {end!r}"
    return after_start.split(end, 1)[0]


_BINDING_STATE_CANONICAL = (
    "`absent`: the path is listed and accepted.",
    "`ambiguous` and `unlocated`: the path is listed and rejected as `lineage/unbound_reference`.",
    "`present` with a digest that does not match: rejected as `lineage/unbound_reference` and not listed.",
    "`present` with a matching digest: the definition is bound; the path is accepted and not listed.",
    "`null` / `not_checked`: lineage was not evaluated.",
)

_BINDING_STATE_INVERSIONS = {
    "absent": "`absent`: the path is listed and rejected as `lineage/unbound_reference`.",
    "ambiguous_unlocated": "`ambiguous` and `unlocated`: the path is listed and accepted.",
    "present_mismatch": (
        "`present` with a digest that does not match: the bundle is not rejected; "
        "the path is omitted from `unbound_bindings`."
    ),
    "present_match": "`present` with a matching digest: rejected as `lineage/unbound_reference`.",
    "null": "`null` / `not_checked`: lineage was fully evaluated and every binding was checked.",
}

_BINDING_STATE_INDEX = {
    "absent": 0,
    "ambiguous_unlocated": 1,
    "present_mismatch": 2,
    "present_match": 3,
    "null": 4,
}


def _inverted_binding_states(state: str) -> str:
    bullets = list(_BINDING_STATE_CANONICAL)
    bullets[_BINDING_STATE_INDEX[state]] = _BINDING_STATE_INVERSIONS[state]
    return "\n".join(f"- {item}" for item in bullets) + "\n"


def test_docs_document_unbound_bindings_key() -> None:
    adr = (_REPO_ROOT / "docs" / "adr" / "0004-abx-container-and-integrity.md").read_text(
        encoding="utf-8"
    )
    architecture = (
        _REPO_ROOT / "docs" / "architecture" / "TRIALMARK_ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    section_73 = _section(
        architecture,
        "### 7.3 Verifier result",
        "### 7.4",
        "architecture §7.3",
    )
    adr_step_7 = _section(
        adr,
        "7. applies privacy/secret policy",
        "Embedded schema snapshots",
        "ADR 0004 verifier step 7",
    )
    adr_trust = _section(
        adr,
        "## Trust statement",
        "## Rejected alternatives",
        "ADR 0004 Trust statement",
    )

    for text in (section_73, adr_step_7):
        folded = " ".join(text.split())
        assert "`unbound_bindings`" in folded
        assert "does not mean every definition is bound" in folded
        _assert_binding_state_contract(text)

    _assert_section_73_intro(section_73)

    assert "verifier step 7" in adr_trust
    assert "ambiguous or unlocatable" not in adr_trust
    assert "`absent`" not in adr_trust


@pytest.mark.parametrize("state", list(_BINDING_STATE_INVERSIONS))
def test_docs_guard_rejects_inverted_binding_contract(state: str) -> None:
    with pytest.raises(AssertionError):
        _assert_binding_state_contract(_inverted_binding_states(state))


def test_docs_guard_rejects_overbroad_unbound_bindings_intro() -> None:
    overbroad = (
        _OVERBROAD_UNBOUND_BINDINGS_INTRO
        + "\n"
        + "\n".join(f"- {item}" for item in _BINDING_STATE_CANONICAL)
        + "\n\nAn empty `unbound_bindings` list therefore does not mean every "
        "definition is bound.\n"
    )
    with pytest.raises(AssertionError):
        _assert_section_73_intro(overbroad)


def test_docs_guard_section_names_missing_markers() -> None:
    with pytest.raises(AssertionError) as missing_start:
        _section("no headings", "### 7.3 Verifier result", "### 7.4", "architecture §7.3")
    start_message = str(missing_start.value)
    assert "architecture §7.3" in start_message
    assert "missing section marker" in start_message
    assert "### 7.3 Verifier result" in start_message

    with pytest.raises(AssertionError) as missing_end:
        _section(
            "### 7.3 Verifier result\nbody only",
            "### 7.3 Verifier result",
            "### 7.4",
            "architecture §7.3",
        )
    end_message = str(missing_end.value)
    assert "architecture §7.3" in end_message
    assert "missing section marker" in end_message
    assert "### 7.4" in end_message

    with pytest.raises(AssertionError) as end_before_start:
        _section(
            "### 7.4\n### 7.3 Verifier result\nbody",
            "### 7.3 Verifier result",
            "### 7.4",
            "architecture §7.3",
        )
    order_message = str(end_before_start.value)
    assert "architecture §7.3" in order_message
    assert "missing section marker" in order_message
    assert "### 7.4" in order_message
