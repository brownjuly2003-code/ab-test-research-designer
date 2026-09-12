"""Constants, digests and schema validation shared by the whole package."""

from __future__ import annotations

import re
import zipfile
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal, cast

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
)
from referencing import Registry, Resource

from app.backend.app.evidence import query_identity
from app.backend.app.evidence._common import (
    SHA256_RE,
    CanonicalJsonError,
    IJsonError,
    IJsonObjectError,
    load_ijson_object,
)
from app.backend.app.evidence._common import (
    canonical_json_bytes as _common_canonical_json_bytes,
)
from app.backend.app.evidence._common import (
    sha256_hex as _sha256,
)

ABX_VERSION = "0.1.0"
BUNDLE_SUFFIX: Final = ".tmk"
BUNDLE_MEDIA_TYPE: Final = "application/vnd.trialmark.bundle+zip"
MANIFEST_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:manifest"
PROTOCOL_SCHEMA_ID = "urn:evidenceos:abx:schema:0.1:protocol"
MAX_MEMBERS = 512
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
KNOWN_CAPABILITIES = frozenset({"lineage-v1", "protocol-core"})
STRUCTURED_ROLES = frozenset(
    {
        "protocol",
        "amendments",
        "run",
        "source",
        "metric",
        "method",
        "finding",
        "estimate",
        "decision",
    }
)
VERDICT_DIMENSIONS = (
    "integrity",
    "schema_conformance",
    "reference_integrity",
    "lineage",
    "privacy_policy",
)

# The general-purpose flag bits whose meaning this verifier can reproduce: 0x1 has its own
# `encrypted_member` code, 0x2/0x4 are deflate level hints, 0x8 marks a data descriptor and
# 0x800 a UTF-8 name. Every other bit (compressed patched data, strong encryption, masked
# local header values) changes how the member bytes must be read, and zipfile refuses to
# decompress the first two, so an unreadable member would be blamed instead of the flag.
_SUPPORTED_FLAG_BITS: Final = 0x1 | 0x2 | 0x4 | 0x8 | 0x800

# One directory deeper than before: this file is `evidence/abx/_core.py`,
# and the schemas stayed at `evidence/contracts/`.
_SCHEMA_ROOT = (
    Path(__file__).resolve().parents[1] / "contracts" / "schemas" / "abx" / "0.1"
)
_SECRET_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "api_token",
        "connection_string",
        "credentials",
        "dsn",
        "password",
        "passwd",
        "private_key",
        "secret",
        "secret_key",
    }
)
_NUMERIC_IDENTIFIER_KEY_TOKENS = frozenset(
    {"account", "id", "msisdn", "phone", "subject", "user"}
)
_LONG_NUMERIC_VALUE = re.compile(r"^[+-]?\d{7,}(?:\.\d+)?$")
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_DIGEST_BACKED_ID_RE = re.compile(
    r"\b(?:run(?:_decision)?|decision|finding|job(?:_decision)?|"
    r"source_aggregate_binary|estimate_aggregate_binary)_[0-9a-f]{16,64}\b"
)
# A SHA-256, labelled or bare, is 64 hex characters; ~0.4% of them contain a
# digit run that the Russian alternative of the phone pattern below matches
# (measured over 200 000 random digests). The whole-value SHA256_RE guard in
# _sensitive_text_codes clears that for a JSON scalar, but a rendered report or
# a .sql member is scanned as one text blob where no whole-value match applies,
# so one embedded digest was enough to make a bundle unpublishable. With three
# digests in rendered/report.html that is roughly one bundle in eighty, at
# random, with "detected phone_number" as the only explanation the operator got.
_HEX_DIGEST_RE = re.compile(r"(?<![0-9A-Za-z])(?:sha256:)?[0-9a-f]{64}(?![0-9A-Za-z])")
_IPV4_CANDIDATE = re.compile(
    r"(?<![0-9A-Za-z._-])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Za-z._-])"
)
_IPV6_CANDIDATE = re.compile(
    r"(?<![0-9A-Za-z:._-])(?=[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:)[0-9A-Fa-f:]{2,}(?![0-9A-Za-z:._-])"
)
_SENSITIVE_TEXT_PATTERNS = (
    ("connection_string", re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mssql|mongodb(?:\+srv)?|redis)://", re.I)),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("cloud_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("provider_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})\b")),
    ("email_address", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    (
        "phone_number",
        re.compile(
            r"(?<![\d+])(?:\+[1-9]\d{7,14}|(?:\+7|8)[\s.-]*(?:\(\d{3}\)|\d{3})[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2})(?!\d)"
        ),
    ),
    (
        "absolute_path",
        re.compile(
            r"(?<![A-Za-z0-9:+./\\-])(?<!<)(?<!&lt;)(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|/(?!/)[^\s\"'<>]+)"
        ),
    ),
)


class AbxError(ValueError):
    """Raised when a Trialmark bundle cannot be packed safely."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return RFC 8785 canonical UTF-8 bytes."""
    try:
        return _common_canonical_json_bytes(value)
    except CanonicalJsonError as exc:
        raise AbxError(str(exc)) from exc


UNBOUND_REFERENCE: Final = "lineage/unbound_reference"
_VERIFY_EXCEPTIONS = (
    OSError,
    ValueError,
    AbxError,
    RuntimeError,
    zipfile.BadZipFile,
    zlib.error,
)


def _is_content_bound_digest(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if SHA256_RE.fullmatch(value) is None:
        return False
    hex_digits = value.removeprefix("sha256:")
    return len(set(hex_digits)) > 1


def _canonical_digest(value: Any) -> str | None:
    try:
        return _sha256(canonical_json_bytes(value))
    except (AbxError, RecursionError):
        return None


def _query_identity_digest(query: dict[str, Any], source: dict[str, Any]) -> str | None:
    try:
        return query_identity.query_identity_digest(
            dialect=cast(str, query.get("dialect")),
            parameters_digest=cast(str, query.get("parameters_digest")),
            source_fingerprint=source.get("fingerprint"),
            statement_digest=cast(str, query.get("statement_digest")),
        )
    except (TypeError, ValueError, RecursionError):
        return None


def _metric_definition_content(
    metric: dict[str, Any],
) -> tuple[Literal["absent", "ambiguous", "present", "unlocated"], Any]:
    extensions = metric.get("extensions")
    if not isinstance(extensions, dict) or not extensions:
        return "absent", None
    found: list[Any] = []
    has_object_payload = False
    for payload in extensions.values():
        if not isinstance(payload, dict):
            continue
        has_object_payload = True
        if "definition" in payload:
            found.append(payload["definition"])
    if len(found) == 1:
        return "present", found[0]
    if len(found) > 1:
        return "ambiguous", None
    if not has_object_payload:
        return "absent", None
    return "unlocated", extensions


def _manifest_bundle_id(manifest: dict[str, Any]) -> str:
    core = {key: value for key, value in manifest.items() if key not in {"bundle_id", "signatures"}}
    return _sha256(canonical_json_bytes(core))


def manifest_bundle_id(manifest: dict[str, Any]) -> str:
    """Return the normative identity of one ABX logical manifest."""
    return _manifest_bundle_id(manifest)


def _load_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        return load_ijson_object(payload)
    except IJsonObjectError as exc:
        raise AbxError(f"{label} must contain a JSON object") from exc
    except IJsonError as exc:
        raise AbxError(f"{label} is not strict UTF-8 I-JSON: {exc}") from exc


def load_abx_document(payload: bytes, *, label: str) -> dict[str, Any]:
    """Parse one artifact as strict UTF-8 I-JSON without trusting its source."""
    return _load_json_bytes(payload, label)


@lru_cache(maxsize=1)
def _schema_catalog() -> tuple[dict[str, dict[str, Any]], Registry[Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(_SCHEMA_ROOT.glob("*.schema.json")):
        schema = _load_json_bytes(path.read_bytes(), path.name)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str):
            raise AbxError(f"trusted schema has no $id: {path.name}")
        Draft202012Validator.check_schema(schema)
        schemas[schema_id] = schema
        resources.append((schema_id, Resource.from_contents(schema)))
    if MANIFEST_SCHEMA_ID not in schemas:
        raise AbxError("trusted ABX manifest schema is missing")
    return schemas, Registry().with_resources(resources)


def schema_violations(instance: dict[str, Any], schema_id: str) -> tuple[tuple[str, str], ...]:
    """Return deterministic schema violations from the trusted offline catalog."""
    schemas, registry = _schema_catalog()
    schema = schemas.get(schema_id)
    if schema is None:
        return (("", f"schema is not in the trusted offline catalog: {schema_id}"),)
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: (list(error.absolute_path), error.message))
    output: list[tuple[str, str]] = []
    for error in errors:
        pointer = "/" + "/".join(
            str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path
        )
        output.append((pointer if pointer != "/" else "", error.message))
    return tuple(output)


def _schema_errors(instance: dict[str, Any], schema_id: str) -> list[tuple[str, str]]:
    return list(schema_violations(instance, schema_id))


def validate_abx_document(instance: dict[str, Any], schema_id: str) -> None:
    """Validate one structured document against the trusted offline catalog."""
    errors = _schema_errors(instance, schema_id)
    if not errors:
        return
    details = "; ".join(f"{pointer or '/'}: {message}" for pointer, message in errors)
    raise AbxError(f"document does not conform to {schema_id}: {details}")
