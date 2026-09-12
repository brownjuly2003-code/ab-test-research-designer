"""Verification: the answer a reader needs about a bundle they were sent."""

from __future__ import annotations

import unicodedata
import zipfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, cast

from app.backend.app.evidence._common import (
    sha256_hex as _sha256,
)
from app.backend.app.evidence.abx._core import (
    _VERIFY_EXCEPTIONS,
    KNOWN_CAPABILITIES,
    MANIFEST_SCHEMA_ID,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_BYTES,
    STRUCTURED_ROLES,
    AbxError,
    _load_json_bytes,
    _schema_catalog,
    _schema_errors,
    manifest_bundle_id,
)
from app.backend.app.evidence.abx.lineage import (
    _base_result,
    _check_references,
    _finish,
    _prepare_decision_document,
    _record_error,
)
from app.backend.app.evidence.abx.privacy import (
    _privacy_issues,
    _text_privacy_issues,
)
from app.backend.app.evidence.abx.zip_safety import (
    _archive_preflight,
    _read_member,
    _safe_member_path,
)


def _scan_logical_members(
    members: tuple[tuple[str, bytes], ...],
    manifest_payload: bytes,
    result: dict[str, Any],
) -> tuple[list[str], dict[str, bytes]]:
    """Check the members as a set, before anything is parsed as a document.

    Returns the member paths in the order they were given, which the manifest
    has to match, and their payloads by path.
    """

    names: list[str] = []
    payloads_by_path: dict[str, bytes] = {}
    normalized: dict[str, str] = {}
    total_size = len(manifest_payload)
    for member in members:
        if (
            not isinstance(member, tuple)
            or len(member) != 2
            or not isinstance(member[0], str)
            or not isinstance(member[1], bytes)
        ):
            _record_error(
                result,
                "integrity",
                "invalid_logical_member",
                "logical members must be exact (path, bytes) tuples",
            )
            continue
        name, payload = member
        names.append(name)
        if name in payloads_by_path:
            _record_error(
                result,
                "integrity",
                "duplicate_member",
                "logical member path is duplicated",
                name,
            )
        payloads_by_path[name] = payload
        if not _safe_member_path(name):
            _record_error(
                result,
                "integrity",
                "unsafe_member_path",
                "member path is not a safe relative POSIX path",
                name,
            )
        collision_key = unicodedata.normalize("NFC", name).casefold()
        previous = normalized.get(collision_key)
        if previous is not None and previous != name:
            _record_error(
                result,
                "integrity",
                "normalized_name_collision",
                f"member collides with {previous!r} after NFC+casefold",
                name,
            )
        normalized[collision_key] = name
        if len(payload) > MAX_MEMBER_BYTES:
            _record_error(
                result,
                "integrity",
                "member_size_exceeded",
                f"member is larger than {MAX_MEMBER_BYTES} bytes",
                name,
            )
        total_size += len(payload)
    if total_size > MAX_TOTAL_BYTES:
        _record_error(
            result,
            "integrity",
            "total_size_exceeded",
            f"logical members contain {total_size} bytes; limit is {MAX_TOTAL_BYTES}",
        )
    return names, payloads_by_path


def _inventory_manifest_entries(
    manifest: dict[str, Any],
    names: list[str],
    payloads_by_path: dict[str, bytes],
    result: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    """Match what the manifest lists against what the bundle actually carries."""

    entries = cast(list[dict[str, Any]], manifest["entries"])
    entries_by_path: dict[str, dict[str, Any]] = {}
    listed_order: list[str] = []
    for entry in entries:
        entry_path = cast(str, entry["path"])
        listed_order.append(entry_path)
        if entry_path in entries_by_path:
            _record_error(
                result,
                "integrity",
                "duplicate_manifest_path",
                "manifest path is listed more than once",
                entry_path,
            )
        entries_by_path[entry_path] = entry
    if "manifest.json" in entries_by_path:
        _record_error(
            result,
            "integrity",
            "manifest_self_entry",
            "manifest.json must not list itself",
            "manifest.json",
        )
    if listed_order != names:
        _record_error(
            result,
            "integrity",
            "member_order_mismatch",
            "logical member order does not match manifest entries",
        )

    actual_names = set(payloads_by_path)
    listed_names = set(entries_by_path)
    for missing in sorted(listed_names - actual_names):
        _record_error(
            result,
            "integrity",
            "missing_member",
            "manifest-listed member is missing",
            missing,
        )
    for unlisted in sorted(actual_names - listed_names):
        _record_error(
            result,
            "integrity",
            "unlisted_member",
            "logical member is not listed in the manifest",
            unlisted,
        )
    return entries_by_path, listed_names, actual_names


def _verify_logical_entries(
    manifest: dict[str, Any],
    entries_by_path: dict[str, dict[str, Any]],
    payloads_by_path: dict[str, bytes],
    listed_names: set[str],
    actual_names: set[str],
    result: dict[str, Any],
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """Check each member that is both listed and present, and collect the documents.

    The returned map is what reference integrity and lineage are checked over,
    keyed by manifest role.
    """

    role_documents: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for entry_path in sorted(listed_names & actual_names):
        entry = entries_by_path[entry_path]
        payload = payloads_by_path[entry_path]
        if len(payload) != entry["size"]:
            _record_error(
                result,
                "integrity",
                "size_mismatch",
                f"manifest size {entry['size']} does not match exact payload size {len(payload)}",
                entry_path,
            )
        if _sha256(payload) != entry["digest"]:
            _record_error(
                result,
                "integrity",
                "digest_mismatch",
                "member SHA-256 does not match the manifest",
                entry_path,
            )

        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            _record_error(
                result,
                "schema_conformance",
                "invalid_utf8",
                str(exc),
                entry_path,
            )
            continue

        role = cast(str, entry["role"])
        if role in STRUCTURED_ROLES or role == "schema":
            try:
                document = _load_json_bytes(payload, entry_path)
            except AbxError as exc:
                _record_error(
                    result,
                    "schema_conformance",
                    "invalid_json",
                    str(exc),
                    entry_path,
                )
                continue
            for pointer, message in _privacy_issues(document):
                _record_error(
                    result,
                    "privacy_policy",
                    "sensitive_value",
                    message,
                    entry_path + pointer,
                )
            schema_id = cast(str, entry["schema_id"])
            if role == "schema":
                trusted_schema = _schema_catalog()[0].get(schema_id)
                if trusted_schema is None or document != trusted_schema:
                    _record_error(
                        result,
                        "schema_conformance",
                        "embedded_schema_mismatch",
                        "embedded schema is not an exact copy of the trusted catalog",
                        entry_path,
                    )
            else:
                for pointer, message in _schema_errors(document, schema_id):
                    _record_error(
                        result,
                        "schema_conformance",
                        "artifact_schema",
                        message,
                        entry_path + pointer,
                    )
                normalized_document = document
                if role == "decision":
                    prepared = _prepare_decision_document(
                        manifest,
                        entry,
                        document,
                        result,
                    )
                    if prepared is None:
                        continue
                    normalized_document, statement = prepared
                    if statement is not None:
                        role_documents.setdefault("_decision_statement", []).append(
                            (entry, statement)
                        )
                role_documents.setdefault(role, []).append(
                    (entry, normalized_document)
                )
        else:
            for pointer, message in _text_privacy_issues(text):
                _record_error(
                    result,
                    "privacy_policy",
                    "sensitive_value",
                    message,
                    entry_path + pointer,
                )
    return role_documents


def verify_logical_bundle(
    manifest_payload: bytes,
    members: tuple[tuple[str, bytes], ...],
) -> dict[str, Any]:
    """Verify exact ordered logical ABX members without a transport container."""
    result = _base_result(Path("<logical>"))
    evaluated = {"integrity"}

    member_count = len(members) + 1
    if member_count > MAX_MEMBERS:
        _record_error(
            result,
            "integrity",
            "member_count_exceeded",
            f"logical member count is {member_count}; limit is {MAX_MEMBERS}",
        )
    if len(manifest_payload) > MAX_MEMBER_BYTES:
        _record_error(
            result,
            "integrity",
            "member_size_exceeded",
            f"member is larger than {MAX_MEMBER_BYTES} bytes",
            "manifest.json",
        )

    names, payloads_by_path = _scan_logical_members(
        members, manifest_payload, result
    )
    if cast(dict[str, str], result["verdicts"])["integrity"] == "fail":
        return _finish(result, evaluated)

    try:
        manifest = _load_json_bytes(manifest_payload, "manifest.json")
    except AbxError as exc:
        _record_error(
            result,
            "integrity",
            "manifest_unreadable",
            str(exc),
            "manifest.json",
        )
        return _finish(result, evaluated)

    result["abx_version"] = manifest.get("abx_version")
    result["bundle_id"] = manifest.get("bundle_id")
    result["run_id"] = manifest.get("run_id")
    evaluated.update({"schema_conformance", "privacy_policy"})
    for pointer, message in _schema_errors(manifest, MANIFEST_SCHEMA_ID):
        _record_error(
            result,
            "schema_conformance",
            "manifest_schema",
            message,
            "manifest.json" + pointer,
        )
    for pointer, message in _privacy_issues(manifest):
        _record_error(
            result,
            "privacy_policy",
            "sensitive_value",
            message,
            "manifest.json" + pointer,
        )
    if cast(dict[str, str], result["verdicts"])["schema_conformance"] == "fail":
        return _finish(result, evaluated)

    unsupported = set(manifest["required_capabilities"]) - KNOWN_CAPABILITIES
    if unsupported:
        _record_error(
            result,
            "schema_conformance",
            "unsupported_capability",
            f"unsupported required capabilities: {sorted(unsupported)!r}",
        )
    try:
        expected_bundle_id = manifest_bundle_id(manifest)
    except AbxError as exc:
        _record_error(
            result,
            "integrity",
            "bundle_identity",
            str(exc),
            "manifest.json",
        )
    else:
        if manifest["bundle_id"] != expected_bundle_id:
            _record_error(
                result,
                "integrity",
                "bundle_id_mismatch",
                f"expected {expected_bundle_id}",
                "manifest.json",
            )

    entries_by_path, listed_names, actual_names = _inventory_manifest_entries(
        manifest, names, payloads_by_path, result
    )
    role_documents = _verify_logical_entries(
        manifest,
        entries_by_path,
        payloads_by_path,
        listed_names,
        actual_names,
        result,
    )

    if cast(dict[str, str], result["verdicts"])["schema_conformance"] != "fail":
        evaluated.update({"reference_integrity", "lineage"})
        _check_references(manifest, role_documents, entries_by_path, result)
    return _finish(result, evaluated)


def _verify_bundle(archive_path: str | Path) -> dict[str, Any]:
    """Verify an ABX archive offline without extracting any member."""
    path = Path(archive_path)
    result = _base_result(path)
    evaluated = {"integrity"}
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        _record_error(result, "integrity", "invalid_archive", str(exc))
        return _finish(result, evaluated)

    with archive:
        preflight_errors = _archive_preflight(archive)
        infos = archive.infolist()
        for code, message, member_path in preflight_errors:
            _record_error(result, "integrity", code, message, member_path)
        if preflight_errors:
            return _finish(result, evaluated)

        manifest_infos = [info for info in infos if info.filename == "manifest.json"]
        if len(manifest_infos) != 1:
            _record_error(result, "integrity", "manifest_cardinality", f"expected one manifest.json, found {len(manifest_infos)}")
            return _finish(result, evaluated)
        try:
            manifest_payload = _read_member(archive, manifest_infos[0])
            manifest = _load_json_bytes(manifest_payload, "manifest.json")
        except (AbxError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
            _record_error(result, "integrity", "manifest_unreadable", str(exc), "manifest.json")
            return _finish(result, evaluated)

        result["abx_version"] = manifest.get("abx_version")
        result["bundle_id"] = manifest.get("bundle_id")
        result["run_id"] = manifest.get("run_id")
        evaluated.update({"schema_conformance", "privacy_policy"})
        for pointer, message in _schema_errors(manifest, MANIFEST_SCHEMA_ID):
            _record_error(result, "schema_conformance", "manifest_schema", message, "manifest.json" + pointer)
        for pointer, message in _privacy_issues(manifest):
            _record_error(result, "privacy_policy", "sensitive_value", message, "manifest.json" + pointer)
        if cast(dict[str, str], result["verdicts"])["schema_conformance"] == "fail":
            return _finish(result, evaluated)

        unsupported = set(manifest["required_capabilities"]) - KNOWN_CAPABILITIES
        if unsupported:
            _record_error(result, "schema_conformance", "unsupported_capability", f"unsupported required capabilities: {sorted(unsupported)!r}")
        try:
            expected_bundle_id = manifest_bundle_id(manifest)
        except AbxError as exc:
            _record_error(result, "integrity", "bundle_identity", str(exc), "manifest.json")
        else:
            if manifest["bundle_id"] != expected_bundle_id:
                _record_error(result, "integrity", "bundle_id_mismatch", f"expected {expected_bundle_id}", "manifest.json")

        entries = cast(list[dict[str, Any]], manifest["entries"])
        entries_by_path: dict[str, dict[str, Any]] = {}
        for entry in entries:
            entry_path = cast(str, entry["path"])
            if entry_path in entries_by_path:
                _record_error(result, "integrity", "duplicate_manifest_path", "manifest path is listed more than once", entry_path)
            entries_by_path[entry_path] = entry
        if "manifest.json" in entries_by_path:
            _record_error(result, "integrity", "manifest_self_entry", "manifest.json must not list itself", "manifest.json")

        actual_names = {info.filename for info in infos}
        listed_names = set(entries_by_path)
        for missing in sorted(listed_names - actual_names):
            _record_error(result, "integrity", "missing_member", "manifest-listed member is missing", missing)
        for unlisted in sorted(actual_names - listed_names - {"manifest.json"}):
            _record_error(result, "integrity", "unlisted_member", "archive member is not listed in the manifest", unlisted)

        infos_by_name = {info.filename: info for info in infos}
        role_documents: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for entry_path in sorted(listed_names & actual_names):
            entry = entries_by_path[entry_path]
            info = infos_by_name[entry_path]
            if info.file_size != entry["size"]:
                _record_error(result, "integrity", "size_mismatch", f"manifest size {entry['size']} does not match ZIP size {info.file_size}", entry_path)
            try:
                payload = _read_member(archive, info)
            except (AbxError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
                _record_error(result, "integrity", "member_unreadable", str(exc), entry_path)
                continue
            if _sha256(payload) != entry["digest"]:
                _record_error(result, "integrity", "digest_mismatch", "member SHA-256 does not match the manifest", entry_path)

            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                _record_error(result, "schema_conformance", "invalid_utf8", str(exc), entry_path)
                continue

            role = cast(str, entry["role"])
            if role in STRUCTURED_ROLES or role == "schema":
                try:
                    document = _load_json_bytes(payload, entry_path)
                except AbxError as exc:
                    _record_error(result, "schema_conformance", "invalid_json", str(exc), entry_path)
                    continue
                for pointer, message in _privacy_issues(document):
                    _record_error(result, "privacy_policy", "sensitive_value", message, entry_path + pointer)
                schema_id = cast(str, entry["schema_id"])
                if role == "schema":
                    trusted_schema = _schema_catalog()[0].get(schema_id)
                    if trusted_schema is None or document != trusted_schema:
                        _record_error(result, "schema_conformance", "embedded_schema_mismatch", "embedded schema is not an exact copy of the trusted catalog", entry_path)
                else:
                    for pointer, message in _schema_errors(document, schema_id):
                        _record_error(result, "schema_conformance", "artifact_schema", message, entry_path + pointer)
                    normalized_document = document
                    if role == "decision":
                        prepared = _prepare_decision_document(
                            manifest,
                            entry,
                            document,
                            result,
                        )
                        if prepared is None:
                            continue
                        normalized_document, statement = prepared
                        if statement is not None:
                            role_documents.setdefault(
                                "_decision_statement", []
                            ).append((entry, statement))
                    role_documents.setdefault(role, []).append(
                        (entry, normalized_document)
                    )
            else:
                for pointer, message in _text_privacy_issues(text):
                    _record_error(result, "privacy_policy", "sensitive_value", message, entry_path + pointer)

        if cast(dict[str, str], result["verdicts"])["schema_conformance"] != "fail":
            evaluated.update({"reference_integrity", "lineage"})
            _check_references(manifest, role_documents, entries_by_path, result)

    return _finish(result, evaluated)


def verify_bundle(archive_path: str | Path) -> dict[str, Any]:
    """Verify an ABX archive offline without extracting any member."""
    path = Path(archive_path)
    result = _base_result(path)
    evaluated = {"integrity"}
    try:
        return _verify_bundle(path)
    # zlib.error derives straight from Exception, so a corrupt deflate stream would
    # otherwise escape verify_bundle instead of being reported as a verdict.
    except _VERIFY_EXCEPTIONS as exc:
        _record_error(result, "integrity", "invalid_archive", str(exc))
        return _finish(result, evaluated)



def inspect_bundle(archive_path: str | Path) -> dict[str, Any]:
    """Return a compact, machine-readable summary of an ABX archive."""
    verified = verify_bundle(archive_path)
    roles: Counter[str] = Counter()
    artifact_count = 0
    path = Path(archive_path)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest_infos = [info for info in archive.infolist() if info.filename == "manifest.json"]
            if len(manifest_infos) == 1 and manifest_infos[0].file_size <= MAX_MEMBER_BYTES:
                manifest = _load_json_bytes(_read_member(archive, manifest_infos[0]), "manifest.json")
                entries = manifest.get("entries", [])
                if isinstance(entries, list):
                    artifact_count = len(entries)
                    roles.update(
                        entry["role"]
                        for entry in entries
                        if isinstance(entry, dict) and isinstance(entry.get("role"), str)
                    )
    except _VERIFY_EXCEPTIONS:
        pass
    bindings = verified.get("unbound_bindings")
    return {
        "abx_version": verified["abx_version"],
        "artifact_count": artifact_count,
        "bundle_id": verified["bundle_id"],
        "roles": dict(sorted(roles.items())),
        "run_id": verified["run_id"],
        "unbound_bindings": None if bindings is None else list(bindings),
        "valid": verified["valid"],
        "verdicts": verified["verdicts"],
    }
