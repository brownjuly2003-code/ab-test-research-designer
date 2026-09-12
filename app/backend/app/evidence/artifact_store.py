from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.backend.app.evidence._common import (
    SHA256_RE,
    sha256_hex,
)
from app.backend.app.evidence._common import (
    fsync_directory as _fsync_directory,
)
from app.backend.app.evidence.abx import MAX_MEMBER_BYTES


class ArtifactStoreCorruptionError(RuntimeError):
    """Raised when content-addressed bytes are missing or no longer match."""


def _storage_key(digest: str) -> str:
    if SHA256_RE.fullmatch(digest) is None:
        raise ValueError("artifact digest must be a lowercase SHA-256 identity")
    hexadecimal = digest.removeprefix("sha256:")
    return f"sha256/{hexadecimal[:2]}/{hexadecimal}"


class FileArtifactStore:
    """Same-volume atomic content-addressed storage for immutable artifact bytes."""

    def __init__(self, root: str | Path) -> None:
        requested_root = Path(root)
        if requested_root.exists() and requested_root.is_symlink():
            raise ValueError("artifact root must not be a symlink")
        requested_root.mkdir(parents=True, exist_ok=True)
        self._root = requested_root.resolve()

    def put(self, payload: bytes, *, expected_digest: str) -> str:
        if len(payload) > MAX_MEMBER_BYTES:
            raise ValueError("artifact payload exceeds the ABX member-size limit")
        if sha256_hex(payload) != expected_digest:
            raise ValueError("artifact payload does not match its expected digest")
        storage_key = _storage_key(expected_digest)
        destination = self._root / Path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self.get(
                storage_key,
                expected_digest=expected_digest,
                expected_size=len(payload),
            )
            return storage_key

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
            _fsync_directory(destination.parent)
        finally:
            temporary.unlink(missing_ok=True)

        self.get(
            storage_key,
            expected_digest=expected_digest,
            expected_size=len(payload),
        )
        return storage_key

    def get(
        self,
        storage_key: str,
        *,
        expected_digest: str,
        expected_size: int,
    ) -> bytes:
        expected_key = _storage_key(expected_digest)
        if storage_key != expected_key:
            raise ArtifactStoreCorruptionError(
                f"artifact storage key does not match {expected_digest}"
            )
        path = self._root / Path(storage_key)
        try:
            stat_result = path.lstat()
        except FileNotFoundError as error:
            raise ArtifactStoreCorruptionError(
                f"artifact payload is missing for {expected_digest}"
            ) from error
        if path.is_symlink() or not path.is_file():
            raise ArtifactStoreCorruptionError(
                f"artifact payload is not a regular file for {expected_digest}"
            )
        if stat_result.st_size != expected_size or expected_size > MAX_MEMBER_BYTES:
            raise ArtifactStoreCorruptionError(
                f"artifact size does not match {expected_digest}"
            )
        payload = path.read_bytes()
        if len(payload) != expected_size or sha256_hex(payload) != expected_digest:
            raise ArtifactStoreCorruptionError(
                f"artifact bytes do not match {expected_digest}"
            )
        return payload


__all__ = ["ArtifactStoreCorruptionError", "FileArtifactStore"]
