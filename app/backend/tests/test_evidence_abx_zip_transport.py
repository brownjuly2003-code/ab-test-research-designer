from __future__ import annotations

import io
import shutil
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence.abx import inspect_bundle, verify_bundle

_BUNDLE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "evidence" / "asos" / "bundles" / "d53f0e.tmk"
)
_EXTRA_FIELD = b"\xfe\xca\x01\x00x"
_DATA_DESCRIPTOR_SIGNATURE = b"PK\x07\x08"
# The CRC-32 an unsigned data descriptor must carry for its first four bytes to read as
# the optional descriptor signature.
_SIGNATURE_VALUED_CRC = int.from_bytes(_DATA_DESCRIPTOR_SIGNATURE, "little")
_NO_END_RECORD = "archive central directory has no end record"
_PREFLIGHT_CODES = frozenset(
    {"archive_trailing_bytes", "central_directory_mismatch", "local_header_mismatch"}
)


def _copy_bundle(tmp_path: Path, filename: str) -> Path:
    destination = tmp_path / filename
    shutil.copyfile(_BUNDLE_FIXTURE, destination)
    return destination


def _stdlib_reads_archive(path: Path) -> bool:
    """Whether this interpreter's zipfile opens the archive at all.

    CPython 3.14.7 hardened `zipfile._EndRecData64`: a Zip64 locator or end
    record whose stored offsets disagree with the physical layout now raises
    BadZipFile instead of silently falling back to the classic end record.
    Trialmark rejects those archives either way -- on the older interpreters
    through its own layout scan (`archive_trailing_bytes`), on the hardened
    ones because the archive never opens (`invalid_archive`). Tests that forge
    Zip64 offsets branch on this so the strict diagnostics stay pinned wherever
    the standard library still hands us the archive.
    """
    try:
        with zipfile.ZipFile(path):
            return True
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def _verification_codes(result: dict[str, Any]) -> set[str]:
    return {
        cast(str, error["code"])
        for error in cast(list[dict[str, Any]], result["errors"])
    }


def _integrity_errors(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        error
        for error in cast(list[dict[str, Any]], result["errors"])
        if error["dimension"] == "integrity"
    ]


def _eocd_offset(payload: bytes | bytearray) -> int:
    offset = bytes(payload).rfind(b"PK\x05\x06")
    assert offset >= 0
    return offset


def _central_directory_offsets(
    payload: bytearray, start_dir: int, count: int
) -> list[int]:
    offsets: list[int] = []
    offset = start_dir
    for _ in range(count):
        assert payload[offset : offset + 4] == b"PK\x01\x02"
        offsets.append(offset)
        offset += (
            46
            + int.from_bytes(payload[offset + 28 : offset + 30], "little")
            + int.from_bytes(payload[offset + 30 : offset + 32], "little")
            + int.from_bytes(payload[offset + 32 : offset + 34], "little")
        )
    return offsets


def _inject_central_only_extra(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
    payload = bytearray(path.read_bytes())
    name_size = int.from_bytes(payload[start_dir + 28 : start_dir + 30], "little")
    assert int.from_bytes(payload[start_dir + 30 : start_dir + 32], "little") == 0
    payload[start_dir + 30 : start_dir + 32] = len(_EXTRA_FIELD).to_bytes(2, "little")
    eocd_offset = _eocd_offset(payload)
    central_size = int.from_bytes(payload[eocd_offset + 12 : eocd_offset + 16], "little")
    payload[eocd_offset + 12 : eocd_offset + 16] = (
        central_size + len(_EXTRA_FIELD)
    ).to_bytes(4, "little")
    payload[start_dir + 46 + name_size : start_dir + 46 + name_size] = _EXTRA_FIELD
    path.write_bytes(payload)


def _inject_local_only_extra(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
        infos = archive.infolist()
    first = infos[0]
    payload = bytearray(path.read_bytes())
    local_offset = first.header_offset
    assert payload[local_offset : local_offset + 4] == b"PK\x03\x04"
    name_size = int.from_bytes(payload[local_offset + 26 : local_offset + 28], "little")
    local_extra_size = int.from_bytes(payload[local_offset + 28 : local_offset + 30], "little")
    assert local_extra_size == 0
    for central_offset in _central_directory_offsets(payload, start_dir, len(infos)):
        header_offset = int.from_bytes(payload[central_offset + 42 : central_offset + 46], "little")
        if header_offset > local_offset:
            payload[central_offset + 42 : central_offset + 46] = (
                header_offset + len(_EXTRA_FIELD)
            ).to_bytes(4, "little")
    payload[local_offset + 28 : local_offset + 30] = len(_EXTRA_FIELD).to_bytes(2, "little")
    eocd_offset = _eocd_offset(payload)
    payload[eocd_offset + 16 : eocd_offset + 20] = (
        start_dir + len(_EXTRA_FIELD)
    ).to_bytes(4, "little")
    payload[
        local_offset + 30 + name_size : local_offset + 30 + name_size
    ] = _EXTRA_FIELD
    path.write_bytes(payload)


def _inject_zip64_trailer(
    path: Path,
    record_size: int = 44,
    *,
    create_version: int = 45,
    read_version: int = 45,
) -> None:
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
    payload = path.read_bytes()
    eocd_offset = _eocd_offset(payload)
    central_size = eocd_offset - start_dir
    zip64_eocd = struct.pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06",
        record_size,
        create_version,
        read_version,
        0,
        0,
        count,
        count,
        central_size,
        start_dir,
    )
    zip64_locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, eocd_offset, 1)
    path.write_bytes(payload[:eocd_offset] + zip64_eocd + zip64_locator + payload[eocd_offset:])


def _inject_invalid_utf8_member_name(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        info = archive.infolist()[0]
        start_dir = archive.start_dir
    payload = bytearray(path.read_bytes())
    local_name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    central_name_size = int.from_bytes(payload[start_dir + 28 : start_dir + 30], "little")
    assert local_name_size == central_name_size
    invalid_name = b"\xff" * local_name_size
    payload[info.header_offset + 6 : info.header_offset + 8] = (
        int.from_bytes(payload[info.header_offset + 6 : info.header_offset + 8], "little") | 0x800
    ).to_bytes(2, "little")
    payload[info.header_offset + 30 : info.header_offset + 30 + local_name_size] = invalid_name
    payload[start_dir + 8 : start_dir + 10] = (
        int.from_bytes(payload[start_dir + 8 : start_dir + 10], "little") | 0x800
    ).to_bytes(2, "little")
    payload[start_dir + 46 : start_dir + 46 + central_name_size] = invalid_name
    path.write_bytes(payload)


def _set_first_member_flag_bits(path: Path, mask: int) -> None:
    """Set general-purpose flag bits in the first local header and its central entry."""
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        start_dir = archive.start_dir
    header_offset = infos[0].header_offset
    payload = bytearray(path.read_bytes())
    central_offset = next(
        offset
        for offset in _central_directory_offsets(payload, start_dir, len(infos))
        if int.from_bytes(payload[offset + 42 : offset + 46], "little") == header_offset
    )
    for offset in (header_offset + 6, central_offset + 8):
        payload[offset : offset + 2] = (
            int.from_bytes(payload[offset : offset + 2], "little") | mask
        ).to_bytes(2, "little")
    path.write_bytes(payload)


def _corrupt_compressed_payload(path: Path, member: str) -> None:
    """Flip bytes strictly inside a member's deflate stream, leaving every header intact."""
    with zipfile.ZipFile(path) as archive:
        info = next(item for item in archive.infolist() if item.filename == member)
    assert info.compress_type == zipfile.ZIP_DEFLATED
    payload = bytearray(path.read_bytes())
    name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_size = int.from_bytes(payload[info.header_offset + 28 : info.header_offset + 30], "little")
    data_start = info.header_offset + 30 + name_size + extra_size
    assert info.compress_size > 24
    for index in range(data_start + 4, data_start + 24):
        payload[index] ^= 0xFF
    path.write_bytes(payload)


def _inject_gap_before_central_directory(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        start_dir = archive.start_dir
    payload = bytearray(path.read_bytes())
    eocd_offset = _eocd_offset(payload)
    gap = b"unauthenticated-central-gap"
    payload[start_dir:start_dir] = gap
    eocd_offset += len(gap)
    payload[eocd_offset + 16 : eocd_offset + 20] = (start_dir + len(gap)).to_bytes(4, "little")
    path.write_bytes(payload)


class _UnseekableBuffer:
    def __init__(self) -> None:
        self._buffer = io.BytesIO()

    def flush(self) -> None:
        pass

    def tell(self) -> int:
        return self._buffer.tell()

    def write(self, payload: bytes) -> int:
        return self._buffer.write(payload)

    def getvalue(self) -> bytes:
        return self._buffer.getvalue()


def _write_data_descriptor_archive(
    source_path: Path, archive_path: Path, *, force_zip64: bool = False
) -> None:
    buffer = _UnseekableBuffer()
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(buffer, "w") as destination:
            for info in source.infolist():
                payload = source.read(info)
                if force_zip64:
                    with destination.open(info, "w", force_zip64=True) as target:
                        target.write(payload)
                else:
                    destination.writestr(info, payload)
    archive_path.write_bytes(buffer.getvalue())


def _whitespace_padded_to_crc(payload: bytes, target: int) -> bytes:
    """Pad a JSON member with insignificant whitespace until its CRC-32 is `target`.

    Trailing whitespace changes neither the parsed manifest nor its bundle_id, so the
    padded member stays a legitimate manifest that happens to carry a chosen CRC-32.
    """
    width = 64
    base_padding = b" " * width
    base = zlib.crc32(payload + base_padding)
    # CRC-32 is linear over equal-length messages, so every position that may hold "\n"
    # instead of " " contributes one fixed 32-bit vector over GF(2).
    pivots: dict[int, tuple[int, int]] = {}
    for index in range(width):
        candidate = bytearray(base_padding)
        candidate[index] = ord("\n")
        vector = zlib.crc32(payload + bytes(candidate)) ^ base
        combination = 1 << index
        while vector:
            bit = vector.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (vector, combination)
                break
            pivot_vector, pivot_combination = pivots[bit]
            vector ^= pivot_vector
            combination ^= pivot_combination
    goal = base ^ target
    chosen = 0
    while goal:
        bit = goal.bit_length() - 1
        assert bit in pivots, "whitespace padding cannot reach the requested CRC-32"
        pivot_vector, pivot_combination = pivots[bit]
        goal ^= pivot_vector
        chosen ^= pivot_combination
    padding = bytearray(base_padding)
    for index in range(width):
        if chosen >> index & 1:
            padding[index] = ord("\n")
    padded = payload + bytes(padding)
    assert zlib.crc32(padded) == target
    return padded


def _write_unsigned_data_descriptor_archive(source_path: Path, archive_path: Path) -> None:
    """Write a bundle whose manifest ends in an unsigned 12-byte data descriptor.

    The manifest is padded until its CRC-32 equals the descriptor signature, so the
    descriptor's first four bytes read as "PK\\x07\\x08" without being a signature. This
    is the ZIP form every reader accepts by taking the descriptor length from the flag,
    not from a guess at those four bytes.
    """
    buffer = _UnseekableBuffer()
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(buffer, "w") as destination:
            for info in source.infolist():
                member = source.read(info)
                if info.filename == "manifest.json":
                    member = _whitespace_padded_to_crc(member, _SIGNATURE_VALUED_CRC)
                destination.writestr(info, member)
    archive_path.write_bytes(buffer.getvalue())

    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        start_dir = archive.start_dir
    manifest = next(info for info in infos if info.filename == "manifest.json")
    payload = bytearray(archive_path.read_bytes())
    descriptor_offset = _descriptor_offset(payload, manifest)
    assert payload[descriptor_offset : descriptor_offset + 8] == _DATA_DESCRIPTOR_SIGNATURE * 2
    shift = len(_DATA_DESCRIPTOR_SIGNATURE)
    central_offsets = _central_directory_offsets(payload, start_dir, len(infos))
    eocd_offset = _eocd_offset(payload) - shift
    del payload[descriptor_offset : descriptor_offset + shift]
    for central_offset in central_offsets:
        shifted = central_offset - shift
        header_offset = int.from_bytes(payload[shifted + 42 : shifted + 46], "little")
        if header_offset > manifest.header_offset:
            payload[shifted + 42 : shifted + 46] = (header_offset - shift).to_bytes(4, "little")
    payload[eocd_offset + 16 : eocd_offset + 20] = (start_dir - shift).to_bytes(4, "little")
    archive_path.write_bytes(payload)


def _descriptor_offset(payload: bytearray, info: zipfile.ZipInfo) -> int:
    name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_size = int.from_bytes(payload[info.header_offset + 28 : info.header_offset + 30], "little")
    return info.header_offset + 30 + name_size + extra_size + info.compress_size


def _assert_unchanged_bundle_is_valid(tmp_path: Path, filename: str) -> None:
    assert verify_bundle(_copy_bundle(tmp_path, filename))["valid"] is True


def test_verify_bundle_accepts_unchanged_bundle_with_arbitrary_filename(
    tmp_path: Path,
) -> None:
    archive_path = _copy_bundle(tmp_path, "not-the-bundle-identity.data")

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_accepts_all_unchanged_asos_bundles(tmp_path: Path) -> None:
    for fixture in sorted(_BUNDLE_FIXTURE.parent.glob("*.tmk")):
        archive_path = tmp_path / f"arbitrary-{fixture.stem}.container"
        shutil.copyfile(fixture, archive_path)

        result = verify_bundle(archive_path)

        assert result["valid"] is True, fixture.name


def test_verify_bundle_rejects_archive_comment(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-comment-name.bin")
    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.comment = b"unauthenticated archive comment"

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _verification_codes(result) == {"entry_extra_field"}


def test_verify_bundle_rejects_central_only_entry_extra_field(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-central-extra-name.bundle")
    _inject_central_only_extra(archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.infolist()[0].extra == _EXTRA_FIELD

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "entry_extra_field" in _verification_codes(result)


def test_verify_bundle_rejects_local_only_entry_extra_field(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-local-extra-name.bundle")
    _inject_local_only_extra(archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.infolist()[0].extra == b""

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "entry_extra_field" in _verification_codes(result)


def test_verify_bundle_rejects_local_header_mismatch(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "local-header-control.tmk")
    with zipfile.ZipFile(_BUNDLE_FIXTURE) as archive:
        info = archive.infolist()[0]
    for field_name, field_offset, value in (
        ("version", 4, (info.extract_version + 1).to_bytes(2, "little")),
        ("flags", 6, b"\x02\x00"),
        ("method", 8, b"\x63\x00"),
        ("timestamp", 10, b"\xff\xff\xff\xff"),
        ("crc", 14, b"\xef\xbe\xad\xde"),
        ("sizes", 18, b"COVERT!!"),
    ):
        archive_path = _copy_bundle(tmp_path, f"local-header-{field_name}.tmk")
        payload = bytearray(archive_path.read_bytes())
        payload[info.header_offset + field_offset : info.header_offset + field_offset + len(value)] = value
        archive_path.write_bytes(payload)

        result = verify_bundle(archive_path)

        assert result["valid"] is False, field_name
        assert result["verdicts"]["integrity"] == "fail", field_name
        assert "local_header_mismatch" in _verification_codes(result), field_name


def test_verify_bundle_rejects_entry_comment(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-entry-comment-source.payload")
    archive_path = tmp_path / "unrelated-entry-comment-result.bundle"
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w") as destination:
            for index, info in enumerate(source.infolist()):
                if index == 0:
                    info.comment = b"unauthenticated entry comment"
                destination.writestr(info, source.read(info))

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _verification_codes(result) == {"entry_extra_field"}


def test_verify_bundle_rejects_prefix_bytes(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-prefix-name.zip")
    archive_path.write_bytes(b"x" * 4096 + archive_path.read_bytes())

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "archive contains bytes before the first member record"
        and "path" not in error
        for error in _integrity_errors(result)
    )
    # A prefix shifts every physical offset at once; it must not be re-reported as a
    # corrupt central directory entry per member, nor as a missing end record.
    assert "central_directory_mismatch" not in _verification_codes(result)
    assert not any(
        error["message"] == _NO_END_RECORD for error in _integrity_errors(result)
    )


def test_verify_bundle_rejects_gap_between_member_records(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-gap-source.bundle")
    archive_path = tmp_path / "unrelated-gap-result.zip"
    gap_member: str | None = None
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w") as destination:
            for index, info in enumerate(source.infolist()):
                if index == 1:
                    stream = destination.fp
                    assert stream is not None
                    stream.seek(destination.start_dir)
                    stream.write(b"G" * 32)
                    destination.start_dir = stream.tell()
                    gap_member = info.filename
                destination.writestr(info, source.read(info))

    result = verify_bundle(archive_path)

    assert gap_member is not None
    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "archive contains bytes outside member records"
        and error.get("path") == gap_member
        for error in _integrity_errors(result)
    )


def test_verify_bundle_rejects_bytes_after_eocd(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-tail-name.zip")
    archive_path.write_bytes(archive_path.read_bytes() + b"T" * 4096)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "archive contains bytes after the end of central directory"
        for error in _integrity_errors(result)
    )


def test_verify_bundle_rejects_gap_before_central_directory(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "central-gap-control.tmk")
    archive_path = _copy_bundle(tmp_path, "central-gap.tmk")
    _inject_gap_before_central_directory(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "archive contains bytes after the final member record"
        for error in _integrity_errors(result)
    )


def test_verify_bundle_accepts_central_directory_external_attr_change(tmp_path: Path) -> None:
    """CD-only external_attr is unauthenticated and must not reject a valid bundle."""
    _assert_unchanged_bundle_is_valid(tmp_path, "central-directory-control.tmk")
    archive_path = _copy_bundle(tmp_path, "central-directory-special-member.tmk")
    with zipfile.ZipFile(archive_path) as archive:
        start_dir = archive.start_dir
    payload = bytearray(archive_path.read_bytes())
    payload[start_dir + 38 : start_dir + 42] = ((0o120777) << 16).to_bytes(4, "little")
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)
    assert "special_member" not in _verification_codes(result)


def test_verify_bundle_accepts_foreign_writer_central_directory_metadata(
    tmp_path: Path,
) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "foreign-writer-control.tmk")
    archive_path = _copy_bundle(tmp_path, "foreign-writer-metadata.tmk")
    with zipfile.ZipFile(archive_path) as archive:
        start_dir = archive.start_dir
        count = len(archive.infolist())
    payload = bytearray(archive_path.read_bytes())
    for central_offset in _central_directory_offsets(payload, start_dir, count):
        payload[central_offset + 4 : central_offset + 6] = (0x0014).to_bytes(2, "little")
        payload[central_offset + 36 : central_offset + 38] = (1).to_bytes(2, "little")
        payload[central_offset + 38 : central_offset + 42] = (
            (0o100666 << 16) | 0x20
        ).to_bytes(4, "little")
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)


def test_verify_bundle_accepts_bundle_repacked_from_the_filesystem(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "extracted"
    with zipfile.ZipFile(_copy_bundle(tmp_path, "repack-source.tmk")) as source:
        names = [info.filename for info in source.infolist()]
        source.extractall(source_root)
    archive_path = tmp_path / "repacked-from-filesystem.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name in names:
            output.write(source_root / name, name)

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)


def test_verify_bundle_rejects_inconsistent_eocd_fields(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "eocd-control.tmk")
    with zipfile.ZipFile(_BUNDLE_FIXTURE) as archive:
        count = len(archive.infolist())
        start_dir = archive.start_dir
    # Each case pins the exact set of codes: a case that also emitted an unrelated code
    # would report a cause the tampering did not create.
    for field_name, field_offset, value, expected_codes, expected_message in (
        # The four disk/count fields are only ever rejected by the EOCD field checks.
        ("disk", 4, (1).to_bytes(2, "little"), {"archive_trailing_bytes"}, _NO_END_RECORD),
        ("central-directory-disk", 6, (1).to_bytes(2, "little"), {"archive_trailing_bytes"}, _NO_END_RECORD),
        ("entries-on-disk", 8, (count - 1).to_bytes(2, "little"), {"archive_trailing_bytes"}, _NO_END_RECORD),
        ("entries-total", 10, (count - 1).to_bytes(2, "little"), {"archive_trailing_bytes"}, _NO_END_RECORD),
        # zipfile itself refuses to open a truncated central directory.
        ("central-size", 12, (1).to_bytes(4, "little"), {"invalid_archive"}, None),
        # A shifted central-directory offset relocates every member record for zipfile, so
        # the whole physical preflight — and only it — has to fail.
        ("central-offset", 16, (start_dir - 1).to_bytes(4, "little"), set(_PREFLIGHT_CODES), None),
    ):
        archive_path = _copy_bundle(tmp_path, f"eocd-{field_name}.tmk")
        payload = bytearray(archive_path.read_bytes())
        eocd_offset = _eocd_offset(payload)
        payload[eocd_offset + field_offset : eocd_offset + field_offset + len(value)] = value
        archive_path.write_bytes(payload)

        result = verify_bundle(archive_path)

        assert result["valid"] is False, field_name
        assert result["verdicts"]["integrity"] == "fail", field_name
        assert _verification_codes(result) == expected_codes, field_name
        if expected_message is not None:
            assert any(
                error["message"] == expected_message
                for error in _integrity_errors(result)
            ), field_name


def test_verify_bundle_rejects_unsupported_general_purpose_flags(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "flag-bits-control.tmk")
    # Both bits make zipfile.open() raise NotImplementedError, so without a preflight check
    # the member is blamed as unreadable instead of the flag that actually rejects it.
    for label, mask in (("compressed-patched-data", 0x20), ("strong-encryption", 0x40)):
        archive_path = _copy_bundle(tmp_path, f"flag-bits-{label}.tmk")
        _set_first_member_flag_bits(archive_path, mask)

        with zipfile.ZipFile(archive_path) as archive:
            assert archive.infolist()[0].flag_bits & mask

        result = verify_bundle(archive_path)

        assert result["valid"] is False, label
        assert result["verdicts"]["integrity"] == "fail", label
        assert _verification_codes(result) == {"unsupported_member_flags"}, label

        inspection = inspect_bundle(archive_path)

        assert inspection["valid"] is False, label
        assert inspection["verdicts"]["integrity"] == "fail", label


def test_verify_bundle_accepts_foreign_writer_zip64_end_record_versions(
    tmp_path: Path,
) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "zip64-version-control.tmk")
    archive_path = _copy_bundle(tmp_path, "zip64-foreign-versions.tmk")
    # version-made-by carries OS bits (0x03 = Unix) and version-needed-to-extract may name a
    # newer compatible release; neither has a source of truth in the archive, so neither may
    # reject a Zip64 trailer that agrees with the central directory.
    _inject_zip64_trailer(archive_path, create_version=0x032D, read_version=62)

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)


def test_verify_bundle_accepts_data_descriptors(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-descriptor-source.bundle")
    archive_path = tmp_path / "unrelated-descriptor-result.zip"
    _write_data_descriptor_archive(source_path, archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_accepts_zip64_data_descriptors(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-zip64-descriptor-source.bundle")
    archive_path = tmp_path / "unrelated-zip64-descriptor-result.zip"
    _write_data_descriptor_archive(source_path, archive_path, force_zip64=True)

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_accepts_zip64_end_records(tmp_path: Path) -> None:
    archive_path = _copy_bundle(tmp_path, "unrelated-zip64-end-records.bundle")
    _inject_zip64_trailer(archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.read("manifest.json")

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_accepts_central_directory_in_reverse_physical_order(
    tmp_path: Path,
) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-central-order-source.bundle")
    archive_path = tmp_path / "unrelated-central-order-result.bundle"
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w") as destination:
            for info in source.infolist():
                destination.writestr(info, source.read(info))
            destination.filelist.reverse()

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_accepts_real_zip64_local_extra(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unrelated-zip64-source.bundle")
    archive_path = tmp_path / "unrelated-zip64-result.zip"
    with zipfile.ZipFile(source_path) as source:
        with zipfile.ZipFile(archive_path, "w") as destination:
            for info in source.infolist():
                payload = source.read(info)
                with destination.open(info, "w", force_zip64=True) as target:
                    target.write(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is True


def test_verify_bundle_rejects_oversized_zip64_end_record(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "zip64-size-control.tmk")
    archive_path = _copy_bundle(tmp_path, "zip64-size-overflow.tmk")
    _inject_zip64_trailer(archive_path, 2**64 - 1)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    if _stdlib_reads_archive(archive_path):
        assert "archive_trailing_bytes" in _verification_codes(result)
    else:
        assert "invalid_archive" in _verification_codes(result)


def test_verify_bundle_rejects_zip64_data_descriptor_extra_payload(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "zip64-extra-control.tmk")
    source_path = _copy_bundle(tmp_path, "zip64-extra-source.tmk")
    archive_path = tmp_path / "zip64-extra-payload.zip"
    _write_data_descriptor_archive(source_path, archive_path, force_zip64=True)
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.infolist()[0]
    payload = bytearray(archive_path.read_bytes())
    name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_offset = info.header_offset + 30 + name_size
    assert payload[extra_offset : extra_offset + 4] == b"\x01\x00\x10\x00"
    assert payload[extra_offset + 4 : extra_offset + 20] == b"\x00" * 16
    payload[extra_offset + 4 : extra_offset + 20] = (
        info.file_size.to_bytes(8, "little")
        + info.compress_size.to_bytes(8, "little")
    )
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "entry_extra_field" in _verification_codes(result)


def test_verify_bundle_rejects_data_descriptor_payload(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "descriptor-control.tmk")
    source_path = _copy_bundle(tmp_path, "descriptor-source.tmk")
    archive_path = tmp_path / "descriptor-payload.zip"
    _write_data_descriptor_archive(source_path, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.infolist()[0]
    payload = bytearray(archive_path.read_bytes())
    name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_size = int.from_bytes(payload[info.header_offset + 28 : info.header_offset + 30], "little")
    descriptor_offset = info.header_offset + 30 + name_size + extra_size + info.compress_size
    assert payload[descriptor_offset : descriptor_offset + 4] == b"PK\x07\x08"
    payload[descriptor_offset + 4 : descriptor_offset + 16] = b"COVERT-BYTES"
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "archive_trailing_bytes" in _verification_codes(result)


def test_verify_bundle_accepts_unsigned_data_descriptor_with_signature_valued_crc(
    tmp_path: Path,
) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "unsigned-descriptor-control.tmk")
    source_path = _copy_bundle(tmp_path, "unsigned-descriptor-source.tmk")
    archive_path = tmp_path / "unsigned-descriptor-signature-crc.zip"
    _write_unsigned_data_descriptor_archive(source_path, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        manifest = next(
            info for info in archive.infolist() if info.filename == "manifest.json"
        )
        assert manifest.flag_bits & 0x8
        assert manifest.CRC == _SIGNATURE_VALUED_CRC
        # Every ZIP reader takes the descriptor length from the flag rather than from
        # those four bytes, so this archive reads correctly and must not be rejected.
        assert archive.testzip() is None

    result = verify_bundle(archive_path)

    assert result["valid"] is True, _verification_codes(result)


def test_verify_bundle_rejects_tampered_unsigned_data_descriptor(tmp_path: Path) -> None:
    source_path = _copy_bundle(tmp_path, "unsigned-descriptor-tamper-source.tmk")
    archive_path = tmp_path / "unsigned-descriptor-tampered.zip"
    _write_unsigned_data_descriptor_archive(source_path, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        manifest = next(
            info for info in archive.infolist() if info.filename == "manifest.json"
        )
    payload = bytearray(archive_path.read_bytes())
    descriptor_offset = _descriptor_offset(payload, manifest)
    assert payload[descriptor_offset : descriptor_offset + 4] == _DATA_DESCRIPTOR_SIGNATURE
    payload[descriptor_offset + 4 : descriptor_offset + 8] = (
        manifest.compress_size + 1
    ).to_bytes(4, "little")
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert any(
        error["code"] == "archive_trailing_bytes"
        and error["message"] == "member data descriptor does not match the central directory"
        and error.get("path") == "manifest.json"
        for error in _integrity_errors(result)
    )


def test_verify_bundle_reports_nul_member_path_before_eocd_error(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "nul-path-control.tmk")
    archive_path = _copy_bundle(tmp_path, "nul-path.tmk")
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.infolist()[0]
        start_dir = archive.start_dir
    payload = bytearray(archive_path.read_bytes())
    local_name_size = int.from_bytes(payload[info.header_offset + 26 : info.header_offset + 28], "little")
    central_name_size = int.from_bytes(payload[start_dir + 28 : start_dir + 30], "little")
    payload[info.header_offset + 30 + local_name_size - 1] = 0
    payload[start_dir + 46 + central_name_size - 1] = 0
    archive_path.write_bytes(payload)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert "unsafe_member_path" in _verification_codes(result)
    assert not any(
        error["message"] == "archive central directory has no end record"
        for error in _integrity_errors(result)
    )


def test_verify_bundle_rejects_corrupt_compressed_payload(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "corrupt-stream-control.tmk")
    for member, expected_code in (
        ("manifest.json", "manifest_unreadable"),
        ("run/run.json", "member_unreadable"),
    ):
        archive_path = _copy_bundle(tmp_path, f"corrupt-stream-{expected_code}.tmk")
        _corrupt_compressed_payload(archive_path, member)

        result = verify_bundle(archive_path)

        assert result["valid"] is False, member
        assert result["verdicts"]["integrity"] == "fail", member
        # Headers, CRC and sizes are untouched, so the physical preflight passes and the
        # corruption can only surface when the deflate stream is decompressed.
        assert expected_code in _verification_codes(result), member
        assert not _verification_codes(result) & _PREFLIGHT_CODES, member

        inspection = inspect_bundle(archive_path)

        assert inspection["valid"] is False, member
        assert inspection["verdicts"]["integrity"] == "fail", member


def test_verify_bundle_rejects_invalid_utf8_member_name(tmp_path: Path) -> None:
    _assert_unchanged_bundle_is_valid(tmp_path, "invalid-utf8-control.tmk")
    archive_path = _copy_bundle(tmp_path, "invalid-utf8-name.tmk")
    _inject_invalid_utf8_member_name(archive_path)

    result = verify_bundle(archive_path)

    assert result["valid"] is False
    assert result["verdicts"]["integrity"] == "fail"
    assert _verification_codes(result) == {"invalid_archive"}

    inspection = inspect_bundle(archive_path)

    assert inspection["valid"] is False
    assert inspection["verdicts"]["integrity"] == "fail"
