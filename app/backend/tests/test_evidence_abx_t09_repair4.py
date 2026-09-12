from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from app.backend.app.evidence.abx import verify_bundle, zip_safety
from app.backend.tests.test_evidence_abx_content_binding import (
    _asos_control_bundle,
    _dump_json_member,
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
from app.backend.tests.test_evidence_abx_t09_repair3 import (
    _append_local_record_copy_and_repoint_cd,
    _local_header_mismatch_paths,
    _mismatch_paths,
    _protocol_unbound_messages,
)
from app.backend.tests.test_evidence_abx_zip_transport import (
    _copy_bundle,
    _verification_codes,
)


def _physical_header_offsets(
    infos: list[zipfile.ZipInfo], spans: dict[int, int]
) -> dict[int, int]:
    return {id(info): info.header_offset for info in infos}


def test_appended_local_record_copy_cd_repoint_names_member_without_local_mismatch(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "copied-local-record-cd-repoint.tmk")
    member_name = _append_local_record_copy_and_repoint_cd(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _mismatch_paths(result) == {member_name}
    assert member_name not in _local_header_mismatch_paths(result)
    assert "local_header_mismatch" not in _verification_codes(result)


@pytest.mark.parametrize("layout", ["inflate", "sfx"])
def test_sequential_layout_mutant_does_not_name_forged_cd_offset_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    layout: str,
) -> None:
    archive_path = _copy_bundle(tmp_path, f"mutant-{layout}-cd-offset.tmk")
    if layout == "inflate":
        _inflate_cd_and_eocd_offsets(archive_path, 4096)
    else:
        _prepend_sfx_with_absolute_offsets(archive_path, _SFX_PREFIX)
    member_name = _append_local_record_copy_and_repoint_cd(archive_path)
    monkeypatch.setattr(
        zip_safety, "_sequential_local_header_offsets", _physical_header_offsets
    )

    result = verify_bundle(archive_path)

    assert member_name not in _mismatch_paths(result)
    assert member_name not in _local_header_mismatch_paths(result)


def test_protocol_ambiguous_and_unlocated_messages_are_distinct(tmp_path: Path) -> None:
    members = _load_members(_asos_control_bundle())
    ambiguous_path = "metrics/metric_asos_1.json"
    unlocated_path = "metrics/metric_asos_2.json"
    ambiguous = _load_json_member(members, ambiguous_path)
    unlocated = _load_json_member(members, unlocated_path)
    ambiguous_id = cast(str, ambiguous["metric_id"])
    unlocated_id = cast(str, unlocated["metric_id"])
    ambiguous["extensions"]["trialmark.decoy"] = {"definition": {"note": "decoy"}}
    _dump_json_member(members, ambiguous_path, ambiguous)
    asos_extension = cast(dict[str, Any], unlocated["extensions"]["trialmark.asos"])
    asos_extension["spec"] = asos_extension.pop("definition")
    _dump_json_member(members, unlocated_path, unlocated)
    _rebind_estimate_metric_digests(members)
    _rebind_manifest(members)

    archive_path = tmp_path / "ambiguous-and-unlocated-protocol.tmk"
    _write_members(archive_path, members, tmp_path)
    result = verify_bundle(archive_path)
    protocol_messages = _protocol_unbound_messages(result)
    ambiguous_protocol = (
        f"protocol metric {ambiguous_id!r} definition_digest cannot be bound to "
        "multiple embedded definition payloads"
    )
    unlocated_protocol = (
        f"protocol metric {unlocated_id!r} definition payload could not be located for binding"
    )
    path_messages = {
        cast(str, error["path"]): cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "lineage/unbound_reference" and error.get("path") != "protocol/protocol.json"
    }

    assert result["valid"] is False
    assert result["verdicts"]["lineage"] == "fail"
    assert ambiguous_protocol in protocol_messages
    assert unlocated_protocol in protocol_messages
    assert ambiguous_protocol != unlocated_protocol
    assert path_messages[ambiguous_path] == (
        "metric definition_digest cannot be bound to multiple embedded definition payloads"
    )
    assert path_messages[unlocated_path] == (
        "metric definition payload could not be located for binding"
    )
