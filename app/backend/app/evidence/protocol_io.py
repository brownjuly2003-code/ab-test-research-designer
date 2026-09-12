from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from app.backend.app.evidence._common import (
    CanonicalJsonError,
    canonical_json_bytes,
    sha256_hex,
)
from app.backend.app.evidence.abx import schema_violations

PROTOCOL_SCHEMA_ID: Final = "urn:evidenceos:abx:schema:0.1:protocol"
SUPPORTED_METHOD_ID: Final = "binary_pooled_z_newcombe"
SUPPORTED_METHOD_VERSION: Final = "binary_pooled_z_newcombe_v1"
_YAML_STRING_TAG: Final = "tag:yaml.org,2002:str"


class ProtocolIoError(ValueError):
    """Raised when a protocol cannot cross the YAML or freeze boundary."""


@dataclass(frozen=True, slots=True)
class FrozenProtocol:
    canonical_bytes: bytes
    protocol_revision_id: str


def _pointer_child(pointer: str, part: str) -> str:
    escaped = part.replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}"


def _check_yaml_mapping_keys(
    node: Node,
    *,
    source: Path,
    pointer: str = "",
    visited: set[int] | None = None,
) -> None:
    seen = visited if visited is not None else set()
    identity = id(node)
    if identity in seen:
        return
    seen.add(identity)

    if isinstance(node, MappingNode):
        keys: set[str] = set()
        for key_node, value_node in node.value:
            if not isinstance(key_node, ScalarNode) or key_node.tag != _YAML_STRING_TAG:
                raise ProtocolIoError(
                    f"{source}: JSON object keys must be strings at {pointer or '/'}"
                )
            key = key_node.value
            child_pointer = _pointer_child(pointer, key)
            if key in keys:
                raise ProtocolIoError(
                    f"{source}: duplicate mapping key at {child_pointer}"
                )
            keys.add(key)
            _check_yaml_mapping_keys(
                value_node,
                source=source,
                pointer=child_pointer,
                visited=seen,
            )
        return

    if isinstance(node, SequenceNode):
        for index, item in enumerate(node.value):
            _check_yaml_mapping_keys(
                item,
                source=source,
                pointer=_pointer_child(pointer, str(index)),
                visited=seen,
            )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ProtocolIoError(f"{path}: cannot read protocol: {exc}") from exc

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolIoError(f"{path}: protocol is not strict UTF-8: {exc}") from exc

    try:
        documents = tuple(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as exc:
        raise ProtocolIoError(f"{path}: malformed YAML: {exc}") from exc
    if len(documents) != 1:
        raise ProtocolIoError(
            f"{path}: expected exactly one YAML document, found {len(documents)}"
        )

    document = documents[0]
    if document is not None:
        _check_yaml_mapping_keys(document, source=path)

    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProtocolIoError(f"{path}: unsafe or malformed YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolIoError(f"{path}: /: protocol must be a YAML mapping")
    return cast(dict[str, Any], value)


def _validated_canonical_bytes(
    protocol: dict[str, Any],
    *,
    label: str,
) -> bytes:
    try:
        canonical_bytes = canonical_json_bytes(protocol)
    except (CanonicalJsonError, RecursionError) as exc:
        raise ProtocolIoError(
            f"{label}: protocol is not JSON/I-JSON compatible: {exc}"
        ) from exc

    violations = schema_violations(protocol, PROTOCOL_SCHEMA_ID)
    if violations:
        details = "; ".join(
            f"{pointer or '/'}: {message}" for pointer, message in violations
        )
        raise ProtocolIoError(f"{label}: protocol schema validation failed: {details}")

    method = protocol["analysis"]["method"]
    if method["method_id"] != SUPPORTED_METHOD_ID:
        raise ProtocolIoError(
            f"{label}: /analysis/method/method_id: unsupported analysis method; "
            f"expected {SUPPORTED_METHOD_ID!r}"
        )
    if method["method_version"] != SUPPORTED_METHOD_VERSION:
        raise ProtocolIoError(
            f"{label}: /analysis/method/method_version: unsupported analysis method "
            f"version; expected {SUPPORTED_METHOD_VERSION!r}"
        )
    return canonical_bytes


def load_protocol(path: Path) -> dict[str, Any]:
    protocol = _load_yaml(path)
    _validated_canonical_bytes(protocol, label=str(path))
    return protocol


def freeze(protocol: dict[str, Any]) -> FrozenProtocol:
    canonical_bytes = _validated_canonical_bytes(protocol, label="protocol")
    return FrozenProtocol(
        canonical_bytes=canonical_bytes,
        protocol_revision_id=sha256_hex(canonical_bytes),
    )
