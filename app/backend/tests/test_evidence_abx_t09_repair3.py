from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence.abx import verify_bundle
from app.backend.tests.test_evidence_abx_content_binding import (
    _asos_control_bundle,
    _dump_json_member,
    _iter_metric_paths,
    _load_json_member,
    _load_members,
    _rebind_estimate_metric_digests,
    _rebind_manifest,
    _write_members,
)
from app.backend.tests.test_evidence_abx_t09_deferred import (
    _SFX_PREFIX,
    _inflate_cd_and_eocd_offsets,
    _prepend_sfx_with_absolute_offsets,
)
from app.backend.tests.test_evidence_abx_zip_transport import (
    _central_directory_offsets,
    _copy_bundle,
    _eocd_offset,
    _verification_codes,
)


def _append_local_record_copy_and_repoint_cd(path: Path) -> str:
    """Point one CD relative-offset at a trailing copy of that member's local record.

    zipfile derives ``ZipInfo.header_offset`` from the CD field, so a +1 forgery
    seeks into the original header and fails the physical walk. A full copy keeps
    the walk successful; only the sequential CD-offset check can then name the
    member. The last physical member is copied so the dominant layout shift still
    names the forged member rather than an honest neighbour.
    """
    with zipfile.ZipFile(path) as archive:
        last = max(archive.infolist(), key=lambda info: info.header_offset)
        start_dir = archive.start_dir
        count = len(archive.infolist())
        member_name = last.orig_filename
        last_offset = last.header_offset
    payload = bytearray(path.read_bytes())
    copy_bytes = bytes(payload[last_offset:start_dir])
    assert copy_bytes[:4] == b"PK\x03\x04"
    new_payload = bytearray(payload[:start_dir] + copy_bytes + payload[start_dir:])
    copy_size = len(copy_bytes)
    new_start_dir = start_dir + copy_size
    eocd = _eocd_offset(new_payload)
    stored_cd = int.from_bytes(new_payload[eocd + 16 : eocd + 20], "little")
    needle = member_name.encode("utf-8")
    target_cd: int | None = None
    for central_offset in _central_directory_offsets(new_payload, new_start_dir, count):
        name_size = int.from_bytes(
            new_payload[central_offset + 28 : central_offset + 30], "little"
        )
        name = bytes(new_payload[central_offset + 46 : central_offset + 46 + name_size])
        if name == needle:
            target_cd = central_offset
            break
    assert target_cd is not None
    new_payload[target_cd + 42 : target_cd + 46] = stored_cd.to_bytes(4, "little")
    new_payload[eocd + 16 : eocd + 20] = (stored_cd + copy_size).to_bytes(4, "little")
    path.write_bytes(new_payload)
    return member_name


def _mismatch_paths(result: dict[str, Any]) -> set[str]:
    return {
        cast(str, error["path"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "central_directory_mismatch" and error.get("path")
    }


def _local_header_mismatch_paths(result: dict[str, Any]) -> set[str]:
    return {
        cast(str, error["path"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "local_header_mismatch" and error.get("path")
    }


def _protocol_unbound_messages(result: dict[str, Any]) -> list[str]:
    return [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference"
        and error.get("path") == "protocol/protocol.json"
    ]


def test_uniform_offset_inflation_plus_one_forged_member_names_only_that_member(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "inflated-then-forged-offset.tmk")
    _inflate_cd_and_eocd_offsets(archive_path, 4096)
    member_name = _append_local_record_copy_and_repoint_cd(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "archive_trailing_bytes" in _verification_codes(result)
    assert _mismatch_paths(result) == {member_name}
    assert member_name not in _local_header_mismatch_paths(result)


def test_sfx_absolute_offsets_plus_one_forged_member_names_only_that_member(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "sfx-then-forged-offset.tmk")
    _prepend_sfx_with_absolute_offsets(archive_path, _SFX_PREFIX)
    member_name = _append_local_record_copy_and_repoint_cd(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "archive_trailing_bytes" in _verification_codes(result)
    assert _mismatch_paths(result) == {member_name}
    assert member_name not in _local_header_mismatch_paths(result)


def test_protocol_unlocated_binding_error_names_each_metric(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    metric_ids: list[str] = []
    for path in _iter_metric_paths(members):
        metric = _load_json_member(members, path)
        asos_extension = cast(dict[str, Any], metric["extensions"]["trialmark.asos"])
        asos_extension["spec"] = asos_extension.pop("definition")
        metric_ids.append(cast(str, metric["metric_id"]))
        _dump_json_member(members, path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "all-metrics-unlocated.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    protocol_messages = _protocol_unbound_messages(result)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert len(protocol_messages) == len(metric_ids)
    assert len(set(protocol_messages)) == len(metric_ids)
    assert {
        f"protocol metric {metric_id!r} definition payload could not be located for binding"
        for metric_id in metric_ids
    } == set(protocol_messages)


def test_protocol_ambiguous_binding_error_names_the_metric(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    metric_path = "metrics/metric_asos_1.json"
    metric = _load_json_member(members, metric_path)
    metric_id = cast(str, metric["metric_id"])
    metric["extensions"]["trialmark.decoy"] = {"definition": {"note": "decoy"}}
    _dump_json_member(members, metric_path, metric)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "ambiguous-protocol-unbound.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    protocol_messages = _protocol_unbound_messages(result)

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert (
        f"protocol metric {metric_id!r} definition_digest cannot be bound to "
        "multiple embedded definition payloads"
        in protocol_messages
    )
    assert not any("could not be located for binding" in message for message in protocol_messages)
