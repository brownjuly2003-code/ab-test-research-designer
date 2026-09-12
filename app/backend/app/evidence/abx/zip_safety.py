"""What the archive is allowed to be, before anything reads it as evidence.

A bundle arrives as an untrusted ZIP. Everything here answers one
question -- can these bytes be read at all -- and nothing here knows what
evidence means."""

from __future__ import annotations

import os
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import IO, Any, Protocol

from app.backend.app.evidence.abx._core import (
    _SUPPORTED_FLAG_BITS,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_BYTES,
    AbxError,
)


def _find_eocd_offset(source: Any, archive_size: int) -> int | None:
    """Return the physical offset of the classic EOCD, matching zipfile's search."""
    if archive_size < 22:
        return None
    source.seek(archive_size - 22)
    tail = source.read(22)
    if len(tail) == 22 and tail[:4] == b"PK\x05\x06" and tail[20:22] == b"\x00\x00":
        return archive_size - 22
    search_size = min(archive_size, (1 << 16) + 22)
    source.seek(archive_size - search_size)
    data = source.read(search_size)
    start = int(data.rfind(b"PK\x05\x06"))
    if start < 0 or start + 22 > len(data):
        return None
    comment_size = int.from_bytes(data[start + 20 : start + 22], "little")
    comment = data[start + 22 : start + 22 + comment_size]
    if comment_size != len(comment):
        return None
    return int(archive_size - search_size + start)


def _stored_central_directory_offset(source: Any, archive_size: int) -> int | None:
    """Return the CD offset stored in Zip64 EOCD when present, else classic EOCD."""
    eocd_offset = _find_eocd_offset(source, archive_size)
    if eocd_offset is None:
        return None
    locator_offset = eocd_offset - 20
    if locator_offset >= 0:
        zip64_start = locator_offset - 56
        if zip64_start >= 0:
            source.seek(zip64_start)
            zip64 = source.read(56)
            locator = source.read(20)
            if (
                zip64[:4] == b"PK\x06\x06"
                and int.from_bytes(zip64[4:12], "little") == 44
                and locator[:4] == b"PK\x06\x07"
            ):
                return int.from_bytes(zip64[48:56], "little")
    source.seek(eocd_offset)
    eocd = source.read(22)
    if len(eocd) != 22 or eocd[:4] != b"PK\x05\x06":
        return None
    return int.from_bytes(eocd[16:20], "little")


def _fallback_local_record_span(info: zipfile.ZipInfo) -> int:
    """Return the local-record size implied by ZipInfo when the physical walk missed it."""
    filename = info.orig_filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437")
    zip64 = info.file_size >= 0xFFFFFFFF or info.compress_size >= 0xFFFFFFFF
    extra = 20 if zip64 else 0
    span = 30 + len(filename) + extra + info.compress_size
    if info.flag_bits & 0x8:
        span += 24 if zip64 else 16
    return span


def _sequential_local_header_offsets(
    infos: list[zipfile.ZipInfo], spans: dict[int, int]
) -> dict[int, int]:
    """Map each member to the offset a sequential packing from 0 would assign it.

    Walk physical order (``header_offset``), not CD order: a well-formed archive may
    list central-directory entries in any order as long as each stored offset points
    at the packed local record.
    """
    cursor = 0
    offsets: dict[int, int] = {}
    for info in sorted(infos, key=lambda item: item.header_offset):
        offsets[id(info)] = cursor
        cursor += spans.get(id(info), _fallback_local_record_span(info))
    return offsets


def _stored_offsets_match_physical_layout(
    archive: zipfile.ZipFile, source: Any, archive_size: int
) -> bool:
    """Return True when stored CD/EOCD offsets already match zipfile's physical layout.

    zipfile records ``start_dir`` and every ``header_offset`` as physical offsets. When
    the on-disk EOCD/Zip64 CD offset equals ``archive.start_dir``, those stored fields
    can be compared directly to ``info.header_offset``, ``archive.start_dir`` and the
    physical EOCD offset. A mismatch means the stored offsets do not describe this byte
    stream; it is reported as ``archive_trailing_bytes`` and must not be used as an
    authenticated unshift. An SFX stub whose CD/EOCD offsets are already absolute still
    matches (the first member simply starts at > 0).
    """
    stored = _stored_central_directory_offset(source, archive_size)
    if stored is None:
        return True
    return archive.start_dir == stored


def _safe_member_path(name: str) -> bool:
    # Trailing '/' is a directory entry; rejected as unsafe_member_path.
    if not name or "\x00" in name or "\\" in name or name.endswith("/"):
        return False
    if name.startswith("/") or (len(name) >= 2 and name[0].isalpha() and name[1] == ":"):
        return False
    segments = name.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        return False
    return str(PurePosixPath(name)) == name


class _InBounds(Protocol):
    """`in_bounds(offset, size)` for one archive, so a helper need not carry its size."""

    def __call__(self, offset: int, size: int = 0) -> bool: ...


@dataclass(frozen=True)
class _LocalRecords:
    """What the walk over local file records found, for the checks that follow it.

    The four maps are keyed by `id(info)` rather than by name, because a
    hostile archive may name two members the same thing.
    """

    headers: dict[int, bytes]
    names: dict[int, bytes]
    uses_zip64: dict[int, bool]
    span: dict[int, int]
    end_offset: int


def _scan_local_records(
    archive: zipfile.ZipFile,
    source: IO[bytes],
    infos: list[zipfile.ZipInfo],
    in_bounds: _InBounds,
    errors: list[tuple[str, str, str | None]],
) -> _LocalRecords:
    """Walk the local file records in physical order, checking each against the CD.

    Every member is read where the central directory says it is, and its local
    header, name, Zip64 extra and optional data descriptor are compared with
    what the central directory claims. `end_offset` is where the walk ended, so
    the caller can tell whether the central directory starts exactly there.
    """

    local_headers: dict[int, bytes] = {}
    local_names: dict[int, bytes] = {}
    local_uses_zip64: dict[int, bool] = {}
    member_span: dict[int, int] = {}
    expected_offset = 0
    ordered = sorted(infos, key=lambda item: item.header_offset)
    for index, info in enumerate(ordered):
        if not in_bounds(info.header_offset, 30):
            errors.append(("archive_trailing_bytes", "member local file header exceeds archive bounds", info.filename))
            continue
        source.seek(info.header_offset)
        header = source.read(30)
        if header[:4] != b"PK\x03\x04":
            errors.append(("local_header_mismatch", "member local file header does not match the central directory", info.filename))
            continue
        local_headers[id(info)] = header
        name_size = int.from_bytes(header[26:28], "little")
        extra_size = int.from_bytes(header[28:30], "little")
        name_offset = info.header_offset + 30
        if not in_bounds(name_offset, name_size + extra_size):
            errors.append(("archive_trailing_bytes", "member local record exceeds archive bounds", info.filename))
            continue
        source.seek(name_offset)
        local_name = source.read(name_size)
        local_names[id(info)] = local_name
        local_extra = source.read(extra_size)
        if info.header_offset != expected_offset:
            if expected_offset == 0:
                errors.append(("archive_trailing_bytes", "archive contains bytes before the first member record", None))
            else:
                errors.append(("archive_trailing_bytes", "archive contains bytes outside member records", info.filename))
        expected_name = info.orig_filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437")
        year, month, day, hour, minute, second = info.date_time
        expected_time = (hour << 11) | (minute << 5) | (second // 2)
        expected_date = ((year - 1980) << 9) | (month << 5) | day
        local_compressed_size = int.from_bytes(header[18:22], "little")
        local_file_size = int.from_bytes(header[22:26], "little")
        uses_zip64 = local_compressed_size == local_file_size == 0xFFFFFFFF
        local_uses_zip64[id(info)] = uses_zip64
        has_data_descriptor = bool(info.flag_bits & 0x8)
        expected_crc = 0 if has_data_descriptor else info.CRC
        expected_compressed_size = 0 if has_data_descriptor else info.compress_size
        expected_file_size = 0 if has_data_descriptor else info.file_size
        if uses_zip64:
            expected_zip64_compressed_size = 0 if has_data_descriptor else info.compress_size
            expected_zip64_file_size = 0 if has_data_descriptor else info.file_size
            local_extra_is_canonical = (
                local_extra[:4] == b"\x01\x00\x10\x00"
                and len(local_extra) == 20
                and int.from_bytes(local_extra[4:12], "little") == expected_zip64_file_size
                and int.from_bytes(local_extra[12:20], "little") == expected_zip64_compressed_size
            )
        else:
            local_extra_is_canonical = not local_extra
        if (
            int.from_bytes(header[4:6], "little") != info.extract_version
            or int.from_bytes(header[6:8], "little") != info.flag_bits
            or int.from_bytes(header[8:10], "little") != info.compress_type
            or int.from_bytes(header[10:12], "little") != expected_time
            or int.from_bytes(header[12:14], "little") != expected_date
            or int.from_bytes(header[14:18], "little") != expected_crc
            or (
                (local_compressed_size, local_file_size) != (0xFFFFFFFF, 0xFFFFFFFF)
                if uses_zip64
                else (local_compressed_size, local_file_size)
                != (expected_compressed_size, expected_file_size)
            )
            or name_size != len(expected_name)
            or local_name != expected_name
        ):
            errors.append(("local_header_mismatch", "member local file header does not match the central directory", info.filename))
        if info.extra or info.comment or not local_extra_is_canonical:
            errors.append(("entry_extra_field", "member extra fields and comments are forbidden", info.filename))
        data_start = name_offset + name_size + extra_size
        if not in_bounds(data_start, info.compress_size):
            errors.append(("archive_trailing_bytes", "member data exceeds archive bounds", info.filename))
            continue
        data_end = data_start + info.compress_size
        if has_data_descriptor:
            descriptor_size = 20 if uses_zip64 else 12
            if not in_bounds(data_end, descriptor_size):
                errors.append(("archive_trailing_bytes", "member data descriptor exceeds archive bounds", info.filename))
                continue
            source.seek(data_end)
            has_signature = source.read(4) == b"PK\x07\x08"
            next_record_offset = (
                ordered[index + 1].header_offset if index + 1 < len(ordered) else archive.start_dir
            )
            # An unsigned descriptor whose CRC happens to be 0x08074b50 is a valid ZIP
            # that readers accept, so the leading four bytes cannot decide the form.
            # Both forms are parsed and only one that agrees with the central directory
            # *and* ends exactly on the next record boundary is accepted; the signed
            # form wins a tie because its own boundary is the unambiguous one.
            descriptor_end: int | None = None
            for signature_size in (4, 0):
                if signature_size and not has_signature:
                    continue
                descriptor_offset = data_end + signature_size
                record_end = descriptor_offset + descriptor_size
                if not in_bounds(descriptor_offset, descriptor_size):
                    continue
                if record_end != next_record_offset and record_end != archive.start_dir:
                    continue
                source.seek(descriptor_offset)
                descriptor = source.read(descriptor_size)
                if uses_zip64:
                    descriptor_matches = (
                        int.from_bytes(descriptor[:4], "little") == info.CRC
                        and int.from_bytes(descriptor[4:12], "little") == info.compress_size
                        and int.from_bytes(descriptor[12:20], "little") == info.file_size
                    )
                else:
                    descriptor_matches = (
                        int.from_bytes(descriptor[:4], "little") == info.CRC
                        and int.from_bytes(descriptor[4:8], "little") == info.compress_size
                        and int.from_bytes(descriptor[8:12], "little") == info.file_size
                    )
                if descriptor_matches:
                    descriptor_end = record_end
                    break
            if descriptor_end is None:
                errors.append(("archive_trailing_bytes", "member data descriptor does not match the central directory", info.filename))
                expected_offset = data_end + (4 if has_signature else 0) + descriptor_size
            else:
                expected_offset = descriptor_end
        else:
            expected_offset = data_end
        member_span[id(info)] = expected_offset - info.header_offset
    return _LocalRecords(
        headers=local_headers,
        names=local_names,
        uses_zip64=local_uses_zip64,
        span=member_span,
        end_offset=expected_offset,
    )


def _check_central_directory(
    archive: zipfile.ZipFile,
    source: IO[bytes],
    infos: list[zipfile.ZipInfo],
    records: _LocalRecords,
    layout_offsets: dict[int, int],
    dominant_layout_shift: int,
    in_bounds: _InBounds,
    errors: list[tuple[str, str, str | None]],
) -> tuple[int, bool]:
    """Compare every central-directory entry with the local record it points at.

    Returns the offset just past the last entry read and whether the walk got
    that far, which is what the trailer check needs to know.
    """

    local_headers = records.headers
    local_names = records.names
    local_uses_zip64 = records.uses_zip64
    central_offset = archive.start_dir
    central_directory_valid = in_bounds(central_offset)
    for info in infos:
        if not central_directory_valid or not in_bounds(central_offset, 46):
            errors.append(("archive_trailing_bytes", "central directory entry exceeds archive bounds", info.filename))
            central_directory_valid = False
            break
        source.seek(central_offset)
        central_header = source.read(46)
        if central_header[:4] != b"PK\x01\x02":
            errors.append(("central_directory_mismatch", "central directory entry does not match canonical ABX transport", info.filename))
            central_directory_valid = False
            break
        central_name_size = int.from_bytes(central_header[28:30], "little")
        central_extra_size = int.from_bytes(central_header[30:32], "little")
        central_comment_size = int.from_bytes(central_header[32:34], "little")
        central_record_size = 46 + central_name_size + central_extra_size + central_comment_size
        if not in_bounds(central_offset, central_record_size):
            errors.append(("archive_trailing_bytes", "central directory entry exceeds archive bounds", info.filename))
            central_directory_valid = False
            break
        source.seek(central_offset + 46)
        central_name = source.read(central_name_size)
        local_header = local_headers.get(id(info), b"")
        has_data_descriptor = len(local_header) == 30 and bool(int.from_bytes(local_header[6:8], "little") & 0x8)
        local_sizes_match = local_uses_zip64.get(id(info)) or has_data_descriptor or (
            len(local_header) == 30 and central_header[16:28] == local_header[14:26]
        )
        # version-made-by, external_attr and internal_attr have no source of truth in the
        # archive: authenticating them would reject bundles from other correct ZIP writers.
        # The CD relative-offset-of-local-header field is compared to the sequential
        # local-record walk, adjusted by the dominant layout shift, independently of
        # whether stored offsets are trusted as a physical unshift.
        stored_local_offset = int.from_bytes(central_header[42:46], "little")
        expected_local_offset = layout_offsets[id(info)]
        offset_mismatch = (
            stored_local_offset - dominant_layout_shift
        ) != expected_local_offset
        if (
            len(local_header) != 30
            or central_header[6:16] != local_header[4:14]
            or not local_sizes_match
            or central_name_size != int.from_bytes(local_header[26:28], "little")
            or central_name != local_names.get(id(info), b"")
            or int.from_bytes(central_header[34:36], "little") != 0
            or offset_mismatch
        ):
            errors.append(("central_directory_mismatch", "central directory entry does not match canonical ABX transport", info.filename))
        if central_extra_size or central_comment_size:
            errors.append(("entry_extra_field", "member extra fields and comments are forbidden", info.filename))
        central_offset += central_record_size
    return central_offset, central_directory_valid


def _check_archive_trailer(
    archive: zipfile.ZipFile,
    source: IO[bytes],
    infos: list[zipfile.ZipInfo],
    archive_size: int,
    central_offset: int,
    central_directory_valid: bool,
    stored_offsets_trusted: bool,
    in_bounds: _InBounds,
    errors: list[tuple[str, str, str | None]],
) -> None:
    """Check the optional Zip64 trailer and the end-of-central-directory record."""

    central_size = central_offset - archive.start_dir
    eocd_offset = central_offset
    zip64_trailer_valid = True
    if not central_directory_valid or not in_bounds(eocd_offset, 4):
        zip64_trailer_valid = False
    else:
        source.seek(eocd_offset)
        zip64_signature = source.read(4)
        if zip64_signature == b"PK\x06\x06" and not in_bounds(eocd_offset, 12):
            zip64_trailer_valid = False
        elif zip64_signature == b"PK\x06\x06":
            source.seek(eocd_offset + 4)
            zip64_size = int.from_bytes(source.read(8), "little")
            zip64_end = eocd_offset + 12 + zip64_size
            if zip64_size != 44 or not in_bounds(eocd_offset, 12 + zip64_size) or not in_bounds(zip64_end, 20):
                zip64_trailer_valid = False
            else:
                source.seek(eocd_offset + 12)
                zip64_record = source.read(zip64_size)
                source.seek(zip64_end)
                zip64_locator = source.read(20)
                # version-made-by and version-needed-to-extract carry OS and release
                # bits with no source of truth in the archive, so pinning them to a
                # single value would reject a Zip64 trailer that agrees with the
                # central directory in every field that is actually computable.
                # zip64_record[36:44] is the stored CD offset. The physical-layout
                # scan authenticates that field when it can locate one
                # (_stored_offsets_match_physical_layout): the Zip64 EOCD CD offset
                # if a well-formed Zip64 trailer is present, otherwise classic EOCD
                # bytes 16-20. A mismatch is archive_trailing_bytes. Re-comparing
                # it to archive.start_dir here cannot fire when that scan passed
                # and is skipped when it failed — the trailer is not the
                # authenticator. When no stored offset can be located
                # (_stored_central_directory_offset returns None because
                # _find_eocd_offset cannot locate a well-formed classic EOCD in
                # the trailing window) the scan returns True vacuously; the
                # archive is rejected by the surrounding EOCD/trailing-byte
                # checks instead.
                if (
                    int.from_bytes(zip64_record[4:8], "little") != 0
                    or int.from_bytes(zip64_record[8:12], "little") != 0
                    or int.from_bytes(zip64_record[12:20], "little") != len(infos)
                    or int.from_bytes(zip64_record[20:28], "little") != len(infos)
                    or int.from_bytes(zip64_record[28:36], "little") != central_size
                    or zip64_locator[:4] != b"PK\x06\x07"
                    or int.from_bytes(zip64_locator[4:8], "little") != 0
                    or (
                        # Locator EOCD offset (bytes 8-16) is not the CD offset and
                        # is not read by the layout scan. The comparison is un-gated.
                        # All three trailer offset comparisons are verdict-neutral.
                        # Whenever _stored_offsets_match_physical_layout fails,
                        # _archive_preflight has already appended
                        # archive_trailing_bytes and verify_bundle returns on any
                        # preflight error, so gating or un-gating changes only which
                        # fields are named in the diagnostics. That changes
                        # diagnostics only, never the verdict: whenever the
                        # stored_offsets_trusted gate would have suppressed it,
                        # _stored_offsets_match_physical_layout has already failed
                        # and verify_bundle returns on the preflight
                        # archive_trailing_bytes error. The scan never reads locator
                        # bytes 8-16 in any case, so the gate would suppress the only
                        # diagnostic naming that field precisely when the scan fails
                        # — that is why it is un-gated. Locator bytes 8-16 are
                        # reported by no other check, so the extra message names a
                        # field that would otherwise go unmentioned. A Zip64 archive
                        # whose offsets are relative to a prefix also collects
                        # "archive central directory has no end record"; that extra
                        # message is a diagnostic-quality cost on an already-failing
                        # input, not a false reject. Classic EOCD bytes 16-20 keep
                        # their stored_offsets_trusted gate: it never suppresses the
                        # only check on that field. It skips the comparison exactly
                        # when the layout scan has already failed and recorded its
                        # own error. When a well-formed Zip64 trailer is present the
                        # scan validates the Zip64 EOCD CD offset instead,
                        # stored_offsets_trusted stays True, and the classic
                        # comparison still runs — pinned by
                        # test_forged_classic_eocd_cd_offset_on_zip64_archive_is_rejected,
                        # which asserts _layout_trusted() is True and still rejects
                        # the forgery. The field-coverage argument used for the
                        # locator does not by itself distinguish the two fields.
                        # The asymmetry is diagnostic coverage, not security value.
                        int.from_bytes(zip64_locator[8:16], "little")
                        != eocd_offset
                    )
                    or int.from_bytes(zip64_locator[16:20], "little") != 1
                ):
                    zip64_trailer_valid = False
                else:
                    eocd_offset = zip64_end + 20
    if not zip64_trailer_valid or not in_bounds(eocd_offset, 22):
        errors.append(("archive_trailing_bytes", "archive central directory has no end record", None))
    else:
        source.seek(eocd_offset)
        eocd = source.read(22)
        comment_size = int.from_bytes(eocd[20:22], "little")
        expected_count = len(infos) if len(infos) <= 0xFFFF else 0xFFFF
        expected_central_size = central_size if central_size <= 0xFFFFFFFF else 0xFFFFFFFF
        expected_central_offset = (
            archive.start_dir if archive.start_dir <= 0xFFFFFFFF else 0xFFFFFFFF
        )
        # Classic EOCD CD offset (bytes 16-20). Without Zip64 the layout scan
        # already authenticated this field; a mismatch is archive_trailing_bytes
        # and re-comparing it here under stored_offsets_trusted is tautological.
        # With Zip64 the scan reads zip64_record[36:44] instead, so this is the
        # authenticator of the classic field (including the 0xFFFFFFFF sentinel)
        # and must stay. Keep the gate: it never suppresses the only check on
        # this field. It skips the comparison exactly when the layout scan has
        # already failed and recorded its own error. When a well-formed Zip64
        # trailer is present, stored_offsets_trusted stays True and the
        # comparison still runs (see
        # test_forged_classic_eocd_cd_offset_on_zip64_archive_is_rejected,
        # which asserts _layout_trusted() is True and still rejects the
        # forgery). The Zip64 locator (bytes 8-16) is reported by no other
        # check; un-gating it is diagnostic coverage, not a verdict change.
        if (
            eocd[:4] != b"PK\x05\x06"
            or not in_bounds(eocd_offset + 22, comment_size)
            or int.from_bytes(eocd[4:6], "little") != 0
            or int.from_bytes(eocd[6:8], "little") != 0
            or int.from_bytes(eocd[8:10], "little") != expected_count
            or int.from_bytes(eocd[10:12], "little") != expected_count
            or int.from_bytes(eocd[12:16], "little") != expected_central_size
            or (
                stored_offsets_trusted
                and int.from_bytes(eocd[16:20], "little") != expected_central_offset
            )
        ):
            errors.append(("archive_trailing_bytes", "archive central directory has no end record", None))
        elif eocd_offset + 22 + comment_size != archive_size:
            errors.append(("archive_trailing_bytes", "archive contains bytes after the end of central directory", None))


def _check_member_inventory(
    infos: list[zipfile.ZipInfo],
    errors: list[tuple[str, str, str | None]],
) -> None:
    """Check the members as a set: counts, names, sizes, ratios and flags.

    Nothing here reads the archive, so it runs whether or not the physical
    walk above got anywhere.
    """

    if len(infos) > MAX_MEMBERS:
        errors.append(("member_count_exceeded", f"archive has {len(infos)} members; limit is {MAX_MEMBERS}", None))

    names = [info.orig_filename for info in infos]
    for name, count in Counter(names).items():
        if count > 1:
            errors.append(("duplicate_member", f"archive contains {count} members named {name!r}", name))

    normalized: dict[str, str] = {}
    total_size = 0
    for info in infos:
        name = info.orig_filename
        if not _safe_member_path(name):
            errors.append(("unsafe_member_path", "member path is not a safe relative POSIX path", name))
        collision_key = unicodedata.normalize("NFC", name).casefold()
        previous = normalized.get(collision_key)
        if previous is not None and previous != name:
            errors.append(("normalized_name_collision", f"member collides with {previous!r} after NFC+casefold", name))
        normalized[collision_key] = name

        total_size += info.file_size
        if info.file_size > MAX_MEMBER_BYTES:
            errors.append(("member_size_exceeded", f"member is larger than {MAX_MEMBER_BYTES} bytes", name))
        if info.file_size and info.compress_size == 0:
            errors.append(("compression_ratio_exceeded", "non-empty member has zero compressed size", name))
        elif info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            errors.append(("compression_ratio_exceeded", f"member compression ratio exceeds {MAX_COMPRESSION_RATIO:g}", name))
        if info.flag_bits & 0x1:
            errors.append(("encrypted_member", "encrypted ZIP members are not supported", name))
        if info.flag_bits & ~_SUPPORTED_FLAG_BITS:
            errors.append(("unsupported_member_flags", f"unsupported ZIP general-purpose flags {info.flag_bits:#06x}", name))
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            errors.append(("unsupported_compression", f"unsupported ZIP compression method {info.compress_type}", name))

    if total_size > MAX_TOTAL_BYTES:
        errors.append(("total_size_exceeded", f"archive expands to {total_size} bytes; limit is {MAX_TOTAL_BYTES}", None))


def _archive_preflight(archive: zipfile.ZipFile) -> list[tuple[str, str, str | None]]:
    errors: list[tuple[str, str, str | None]] = []
    infos = archive.infolist()
    if archive.comment:
        errors.append(("entry_extra_field", "archive comment is forbidden", None))

    source = archive.fp
    assert source is not None
    position: int | None = None
    stored_offsets_trusted = True
    try:
        position = source.tell()
        source.seek(0, os.SEEK_END)
        archive_size = source.tell()
        source.seek(position)
        stored_offsets_trusted = _stored_offsets_match_physical_layout(
            archive, source, archive_size
        )
        if not stored_offsets_trusted:
            errors.append(
                (
                    "archive_trailing_bytes",
                    "stored offsets do not match the physical layout",
                    None,
                )
            )

        def in_bounds(offset: int, size: int = 0) -> bool:
            return 0 <= offset <= archive_size and 0 <= size <= archive_size - offset

        records = _scan_local_records(archive, source, infos, in_bounds, errors)
        if not in_bounds(archive.start_dir):
            errors.append(("archive_trailing_bytes", "archive central directory exceeds archive bounds", None))
        elif archive.start_dir != records.end_offset:
            errors.append(("archive_trailing_bytes", "archive contains bytes after the final member record", None))

        layout_offsets = _sequential_local_header_offsets(infos, records.span)
        stored_cd = _stored_central_directory_offset(source, archive_size)
        concat = 0 if stored_cd is None else archive.start_dir - stored_cd
        # Dominant shift of (physical local offset − sequential layout). A uniform
        # prefix/layout shift is an archive-level error (archive_trailing_bytes);
        # a single forged CD relative-offset field is named on that member.
        dominant_layout_shift = (
            Counter(
                (info.header_offset - concat) - layout_offsets[id(info)] for info in infos
            ).most_common(1)[0][0]
            if infos
            else 0
        )

        central_offset, central_directory_valid = _check_central_directory(
            archive,
            source,
            infos,
            records,
            layout_offsets,
            dominant_layout_shift,
            in_bounds,
            errors,
        )
        _check_archive_trailer(
            archive,
            source,
            infos,
            archive_size,
            central_offset,
            central_directory_valid,
            stored_offsets_trusted,
            in_bounds,
            errors,
        )
    except (OSError, OverflowError, UnicodeError, ValueError):
        errors.append(("archive_trailing_bytes", "archive contains invalid physical offsets", None))
    finally:
        if position is not None:
            try:
                source.seek(position)
            except (ValueError, OverflowError, OSError):
                errors.append(("archive_trailing_bytes", "archive contains invalid physical offsets", None))

    _check_member_inventory(infos, errors)
    return errors


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    payload = bytearray()
    with archive.open(info, "r") as source:
        while chunk := source.read(64 * 1024):
            payload.extend(chunk)
            if len(payload) > MAX_MEMBER_BYTES:
                raise AbxError(f"member exceeded the streaming limit: {info.filename}")
    return bytes(payload)
