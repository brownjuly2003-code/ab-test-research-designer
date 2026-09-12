from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.backend.app.evidence import abx, query_identity
from app.backend.app.evidence._common import (
    MAX_SAFE_INTEGER,
    CanonicalJsonError,
    IJsonError,
    IJsonObjectError,
    canonical_digest,
    canonical_json_bytes,
    fsync_directory,
    load_ijson,
    load_ijson_object,
    sha256_hex,
)


def test_canonical_digest_is_sha256_of_rfc8785_bytes() -> None:
    value = {"b": 1, "a": [True, None]}
    encoded = canonical_json_bytes(value)
    assert encoded == b'{"a":[true,null],"b":1}'
    assert canonical_digest(value) == sha256_hex(encoded)
    assert canonical_digest({"a": [True, None], "b": 1}) == canonical_digest(value)


def test_canonical_json_bytes_rejects_noncanonicalizable_values() -> None:
    with pytest.raises(CanonicalJsonError, match="RFC 8785 canonicalizable"):
        canonical_json_bytes(object())


def test_abx_canonical_json_bytes_maps_common_failures() -> None:
    with pytest.raises(abx.AbxError, match="RFC 8785 canonicalizable"):
        abx.canonical_json_bytes(object())


def test_load_ijson_rejects_duplicate_keys() -> None:
    with pytest.raises(IJsonError, match="duplicate JSON key: a"):
        load_ijson(b'{"a":1,"a":2}')


@pytest.mark.parametrize(
    "payload",
    (
        str(MAX_SAFE_INTEGER + 1).encode("ascii"),
        str(-(MAX_SAFE_INTEGER + 1)).encode("ascii"),
    ),
)
def test_load_ijson_rejects_unsafe_integers(payload: bytes) -> None:
    with pytest.raises(IJsonError, match="integer outside the I-JSON safe range"):
        load_ijson(payload)


@pytest.mark.parametrize("payload", (b"NaN", b"Infinity", b"-Infinity"))
def test_load_ijson_rejects_non_finite_numbers(payload: bytes) -> None:
    with pytest.raises(IJsonError, match="non-I-JSON numeric constant"):
        load_ijson(payload)


def test_load_ijson_rejects_lone_surrogates() -> None:
    with pytest.raises(IJsonError, match="non-Unicode scalar value"):
        load_ijson(b'{"a":"\\uD800"}')


def test_load_ijson_rejects_invalid_utf8() -> None:
    with pytest.raises(IJsonError):
        load_ijson(b"\xff")


def test_load_ijson_object_rejects_non_objects() -> None:
    assert load_ijson(b"[1]") == [1]
    with pytest.raises(IJsonObjectError, match="JSON value must be an object"):
        load_ijson_object(b"[1]")
    assert load_ijson_object(b'{"a":1}') == {"a": 1}


def test_query_identity_sha256_prefixed_is_the_common_helper() -> None:
    assert query_identity.sha256_prefixed is sha256_hex


def test_fsync_directory_opens_fsyncs_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opened: list[tuple[Path, int]] = []
    fsynced: list[int] = []
    closed: list[int] = []

    def fake_open(path: Path | str, flags: int, *args: object, **kwargs: object) -> int:
        opened.append((Path(path), flags))
        return 7

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "fsync", lambda descriptor: fsynced.append(descriptor))
    monkeypatch.setattr(os, "close", lambda descriptor: closed.append(descriptor))

    fsync_directory(tmp_path)

    assert opened == [(tmp_path, os.O_RDONLY)]
    assert fsynced == [7]
    assert closed == [7]


def test_fsync_directory_open_failure_is_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_open(*args: object, **kwargs: object) -> int:
        raise OSError("directory fsync is unavailable")

    monkeypatch.setattr(os, "open", fake_open)
    fsync_directory(tmp_path)


def test_fsync_directory_closes_after_fsync_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    closed: list[int] = []

    def fake_fsync(descriptor: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(os, "open", lambda path, flags, *args, **kwargs: 3)
    monkeypatch.setattr(os, "fsync", fake_fsync)
    monkeypatch.setattr(os, "close", lambda descriptor: closed.append(descriptor))

    fsync_directory(tmp_path)
    assert closed == [3]


def test_abx_and_artifact_store_delegate_directory_fsync() -> None:
    from app.backend.app.evidence import artifact_store

    # `pack` is the only writer in the package, so it is the only module
    # that fsyncs a directory.
    assert abx.pack._fsync_directory is fsync_directory
    assert artifact_store._fsync_directory is fsync_directory
