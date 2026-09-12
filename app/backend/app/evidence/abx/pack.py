"""Packing: the only writer of a bundle, and it verifies what it wrote."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence._common import (
    fsync_directory as _fsync_directory,
)
from app.backend.app.evidence.abx._core import (
    MANIFEST_SCHEMA_ID,
    UNBOUND_REFERENCE,
    AbxError,
    _load_json_bytes,
    _schema_errors,
)
from app.backend.app.evidence.abx.verify import verify_bundle
from app.backend.app.evidence.abx.zip_safety import _safe_member_path


def _source_file_map(source: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for candidate in source.rglob("*"):
        relative = candidate.relative_to(source).as_posix()
        if candidate.is_symlink():
            raise AbxError(f"source contains a symlink: {relative}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise AbxError(f"source contains a special file: {relative}")
        if not _safe_member_path(relative):
            raise AbxError(f"source contains an unsafe member path: {relative}")
        collision_key = unicodedata.normalize("NFC", relative).casefold()
        if collision_key in files:
            raise AbxError(f"source contains a normalized path collision: {relative}")
        files[collision_key] = candidate
    return {candidate.relative_to(source).as_posix(): candidate for candidate in files.values()}


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def pack_bundle(
    source_directory: str | Path,
    destination: str | Path,
    *,
    require_valid: bool = True,
) -> dict[str, Any]:
    """Pack a prepared logical ABX directory into a deterministic archive.

    ``require_valid=False`` is a narrow escape hatch: packing still fails unless
    every verification error is ``lineage/unbound_reference``. Other lineage
    codes continue to block packing.
    """
    source = Path(source_directory)
    output = Path(destination)
    if not source.is_dir() or source.is_symlink():
        raise AbxError(f"source is not a regular directory: {source}")
    if os.path.lexists(output):
        raise AbxError(f"destination already exists: {output}")
    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if output_resolved == source_resolved or output_resolved.is_relative_to(source_resolved):
        raise AbxError("destination must be outside the source directory")

    files = _source_file_map(source)
    manifest_path = files.get("manifest.json")
    if manifest_path is None:
        raise AbxError("source has no manifest.json")
    manifest = _load_json_bytes(manifest_path.read_bytes(), "manifest.json")
    errors = _schema_errors(manifest, MANIFEST_SCHEMA_ID)
    if errors:
        raise AbxError(f"manifest schema is invalid: {errors[0][1]}")
    expected_files = {cast(str, entry["path"]) for entry in cast(list[dict[str, Any]], manifest["entries"])} | {"manifest.json"}
    unlisted = sorted(set(files) - expected_files)
    missing = sorted(expected_files - set(files))
    if unlisted:
        raise AbxError(f"source contains unlisted files: {unlisted!r}")
    if missing:
        raise AbxError(f"source is missing manifest-listed files: {missing!r}")

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", allowZip64=False) as archive:
                for relative in ["manifest.json", *sorted(expected_files - {"manifest.json"})]:
                    with archive.open(_zip_info(relative), "w") as target, files[relative].open("rb") as payload:
                        shutil.copyfileobj(payload, target, length=64 * 1024)
            stream.flush()
            os.fsync(stream.fileno())
        verification = verify_bundle(temporary)
        if not verification["valid"] and (
            require_valid
            or any(
                cast(str, error["code"]) != UNBOUND_REFERENCE
                for error in cast(list[dict[str, Any]], verification["errors"])
            )
        ):
            codes = sorted({error["code"] for error in cast(list[dict[str, Any]], verification["errors"])})
            raise AbxError(f"packed bundle failed verification: {', '.join(codes)}")
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise AbxError(f"destination appeared during packing: {output}") from exc
        except OSError as exc:
            raise AbxError(f"unable to publish packed bundle: {exc}") from exc
        _fsync_directory(output.parent)
        verification["archive"] = str(output)
        return verification
    finally:
        temporary.unlink(missing_ok=True)
