from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence.abx import (
    _stored_offsets_match_physical_layout,
    verify_bundle,
)
from app.backend.tests.test_evidence_abx_t09_deferred import _SFX_PREFIX
from app.backend.tests.test_evidence_abx_zip_transport import (
    _NO_END_RECORD,
    _central_directory_offsets,
    _copy_bundle,
    _eocd_offset,
    _inject_zip64_trailer,
    _stdlib_reads_archive,
    _verification_codes,
)


def _trailing_messages(result: dict[str, Any]) -> list[str]:
    return [
        cast(str, error["message"])
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["code"] == "archive_trailing_bytes"
    ]


def _layout_trusted(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        source = archive.fp
        assert source is not None
        position = source.tell()
        source.seek(0, 2)
        size = source.tell()
        source.seek(position)
        return _stored_offsets_match_physical_layout(archive, source, size)


def _forge_zip64_locator_eocd_offset(path: Path, delta: int = 99) -> None:
    payload = bytearray(path.read_bytes())
    locator = _eocd_offset(payload) - 20
    assert payload[locator : locator + 4] == b"PK\x06\x07"
    stored = int.from_bytes(payload[locator + 8 : locator + 16], "little")
    payload[locator + 8 : locator + 16] = (stored + delta).to_bytes(8, "little")
    path.write_bytes(payload)


def _forge_classic_eocd_cd_offset(path: Path, delta: int = 1) -> None:
    payload = bytearray(path.read_bytes())
    eocd = _eocd_offset(payload)
    stored = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    payload[eocd + 16 : eocd + 20] = (stored + delta).to_bytes(4, "little")
    path.write_bytes(payload)


def _forge_zip64_eocd_cd_offset(path: Path, delta: int = 7) -> None:
    """Bump Zip64 EOCD CD offset at file bytes zip64+48:56 (zip64_record[36:44])."""
    payload = bytearray(path.read_bytes())
    locator = _eocd_offset(payload) - 20
    zip64 = locator - 56
    assert payload[zip64 : zip64 + 4] == b"PK\x06\x06"
    stored = int.from_bytes(payload[zip64 + 48 : zip64 + 56], "little")
    payload[zip64 + 48 : zip64 + 56] = (stored + delta).to_bytes(8, "little")
    path.write_bytes(payload)


def _prepend_sfx_updating_zip64_offsets(path: Path, prefix: bytes) -> None:
    """Shift CD, Zip64 CD, Zip64 locator, and classic EOCD offsets by len(prefix)."""
    payload = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
        first_header = archive.infolist()[0].header_offset
    shift = len(prefix)
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        stored = int.from_bytes(payload[central_offset + 42 : central_offset + 46], "little")
        payload[central_offset + 42 : central_offset + 46] = (stored + shift).to_bytes(
            4, "little"
        )
    eocd = _eocd_offset(payload)
    locator = eocd - 20
    zip64 = locator - 56
    assert payload[locator : locator + 4] == b"PK\x06\x07"
    assert payload[zip64 : zip64 + 4] == b"PK\x06\x06"
    zip64_cd = int.from_bytes(payload[zip64 + 48 : zip64 + 56], "little")
    payload[zip64 + 48 : zip64 + 56] = (zip64_cd + shift).to_bytes(8, "little")
    locator_eocd = int.from_bytes(payload[locator + 8 : locator + 16], "little")
    payload[locator + 8 : locator + 16] = (locator_eocd + shift).to_bytes(8, "little")
    classic_cd = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    payload[eocd + 16 : eocd + 20] = (classic_cd + shift).to_bytes(4, "little")
    path.write_bytes(prefix + bytes(payload))
    with zipfile.ZipFile(path) as archive:
        assert archive.infolist()[0].header_offset == first_header + shift
        assert archive.start_dir == start_dir + shift


def _prepend_sfx_rebasing_zip64_locator_only(path: Path, prefix: bytes) -> None:
    """Prepend a stub and rebase only the Zip64 locator EOCD offset.

    zip64_record[36:44] (the stored CD offset) stays relative, so
    `_layout_trusted()` remains False. The locator then agrees with the
    physical Zip64 EOCD offset; a later locator forgery is the only way to
    trip the un-gated locator comparison.
    """
    payload = bytearray(path.read_bytes())
    shift = len(prefix)
    eocd = _eocd_offset(payload)
    locator = eocd - 20
    zip64 = locator - 56
    assert payload[locator : locator + 4] == b"PK\x06\x07"
    assert payload[zip64 : zip64 + 4] == b"PK\x06\x06"
    locator_eocd = int.from_bytes(payload[locator + 8 : locator + 16], "little")
    payload[locator + 8 : locator + 16] = (locator_eocd + shift).to_bytes(8, "little")
    path.write_bytes(prefix + bytes(payload))


def test_injected_zip64_trailer_keeps_the_layout_scan_trusted(tmp_path: Path) -> None:
    """Layout-scan control for an injected Zip64 trailer.

    This test does not call verify_bundle. Validity of the same fixture shape
    is pinned by test_verify_bundle_accepts_zip64_end_records in
    test_evidence_abx_zip_transport.py, which asserts result["valid"] is True.
    """
    archive_path = _copy_bundle(tmp_path, "zip64-control.tmk")
    _inject_zip64_trailer(archive_path)

    assert _layout_trusted(archive_path) is True


def test_sfx_zip64_with_updated_absolute_offsets_does_not_fail_locator(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "zip64-sfx-absolute.tmk")
    _inject_zip64_trailer(archive_path)
    _prepend_sfx_updating_zip64_offsets(archive_path, _SFX_PREFIX)

    result = verify_bundle(archive_path)

    assert _layout_trusted(archive_path) is True
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _trailing_messages(result) == [
        "archive contains bytes before the first member record"
    ]
    assert _NO_END_RECORD not in _trailing_messages(result)


def test_forged_zip64_locator_rejected_when_stored_cd_offset_matches(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "zip64-forged-locator-trusted.tmk")
    _inject_zip64_trailer(archive_path)
    _forge_zip64_locator_eocd_offset(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    if not _stdlib_reads_archive(archive_path):
        assert "invalid_archive" in _verification_codes(result)
        return
    assert _layout_trusted(archive_path) is True
    assert _NO_END_RECORD in _trailing_messages(result)


def test_unforged_prefixed_zip64_relative_offsets_collect_no_end_record(
    tmp_path: Path,
) -> None:
    """Accepted diagnostic cost of the un-gated Zip64 locator comparison.

    A Zip64 archive whose offsets stay relative to a prefix is already rejected
    by the layout scan. The locator comparison still adds `_NO_END_RECORD`
    because the stored locator EOCD offset is relative while `eocd_offset` is
    physical. Pin the exact trailing-message list so that set cannot drift.
    """
    archive_path = _copy_bundle(tmp_path, "zip64-prefix-relative-unforged.tmk")
    _inject_zip64_trailer(archive_path)
    archive_path.write_bytes(_SFX_PREFIX + archive_path.read_bytes())

    result = verify_bundle(archive_path)

    assert _layout_trusted(archive_path) is False
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _trailing_messages(result) == [
        "stored offsets do not match the physical layout",
        "archive contains bytes before the first member record",
        _NO_END_RECORD,
    ]


def test_forged_zip64_locator_rejected_when_stored_cd_offset_is_shifted(
    tmp_path: Path,
) -> None:
    unforged = _copy_bundle(tmp_path, "zip64-prefix-unforged-locator.tmk")
    _inject_zip64_trailer(unforged)
    _prepend_sfx_rebasing_zip64_locator_only(unforged, _SFX_PREFIX)

    unforged_result = verify_bundle(unforged)
    archive_path = tmp_path / "zip64-prefix-forged-locator.tmk"
    archive_path.write_bytes(unforged.read_bytes())
    _forge_zip64_locator_eocd_offset(archive_path)

    result = verify_bundle(archive_path)

    assert unforged_result["valid"] is False
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    if not _stdlib_reads_archive(unforged):
        assert "invalid_archive" in _verification_codes(unforged_result)
        assert "invalid_archive" in _verification_codes(result)
        return
    assert _layout_trusted(unforged) is False
    assert _trailing_messages(unforged_result) == [
        "stored offsets do not match the physical layout",
        "archive contains bytes before the first member record",
    ]
    assert _NO_END_RECORD not in _trailing_messages(unforged_result)
    assert "stored offsets do not match the physical layout" in _trailing_messages(result)
    assert _NO_END_RECORD in _trailing_messages(result)


def test_forged_classic_eocd_cd_offset_on_zip64_archive_is_rejected(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "zip64-forged-classic-cd.tmk")
    _inject_zip64_trailer(archive_path)
    _forge_classic_eocd_cd_offset(archive_path)

    result = verify_bundle(archive_path)

    assert _layout_trusted(archive_path) is True
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _NO_END_RECORD in _trailing_messages(result)


def test_forged_zip64_eocd_cd_offset_is_rejected_by_the_layout_scan(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "zip64-forged-eocd-cd.tmk")
    _inject_zip64_trailer(archive_path)
    _forge_zip64_eocd_cd_offset(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    if not _stdlib_reads_archive(archive_path):
        assert "invalid_archive" in _verification_codes(result)
        return
    assert _layout_trusted(archive_path) is False
    assert "stored offsets do not match the physical layout" in _trailing_messages(result)
