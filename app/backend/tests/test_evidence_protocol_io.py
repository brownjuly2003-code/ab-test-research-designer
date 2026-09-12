from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.backend.app.evidence._common import canonical_json_bytes, sha256_hex

_VALID_PROTOCOL = (
    Path(__file__).parent / "fixtures" / "abx" / "0.1" / "valid" / "protocol.json"
)


def _protocol() -> dict[str, Any]:
    protocol = json.loads(_VALID_PROTOCOL.read_text(encoding="utf-8"))
    protocol["analysis"]["method"] = {
        "method_id": "binary_pooled_z_newcombe",
        "method_version": "binary_pooled_z_newcombe_v1",
    }
    return protocol


def _write_yaml(path: Path, value: object, *, sort_keys: bool = False) -> Path:
    path.write_bytes(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=sort_keys).encode("utf-8")
    )
    return path


def test_load_protocol_accepts_the_supported_analysis_pair(tmp_path: Path) -> None:
    from app.backend.app.evidence.protocol_io import load_protocol

    expected = _protocol()
    path = _write_yaml(tmp_path / "protocol.yaml", expected)

    assert load_protocol(path) == expected


def test_freeze_uses_canonical_bytes_and_their_sha256_identity() -> None:
    from app.backend.app.evidence.protocol_io import freeze

    protocol = _protocol()
    frozen = freeze(protocol)
    expected_bytes = canonical_json_bytes(protocol)

    assert frozen.canonical_bytes == expected_bytes
    assert frozen.protocol_revision_id == sha256_hex(expected_bytes)
    with pytest.raises(FrozenInstanceError):
        frozen.canonical_bytes = b"changed"  # type: ignore[misc]


def test_equivalent_yaml_key_orders_freeze_identically(tmp_path: Path) -> None:
    from app.backend.app.evidence.protocol_io import freeze, load_protocol

    protocol = _protocol()
    reversed_protocol = dict(reversed(tuple(protocol.items())))
    first = _write_yaml(tmp_path / "first.yaml", protocol, sort_keys=False)
    second = _write_yaml(tmp_path / "second.yaml", reversed_protocol, sort_keys=True)

    assert freeze(load_protocol(first)) == freeze(load_protocol(second))


def test_freeze_is_detached_from_later_caller_mutation() -> None:
    from app.backend.app.evidence.protocol_io import freeze

    protocol = _protocol()
    frozen = freeze(protocol)
    expected = (frozen.canonical_bytes, frozen.protocol_revision_id)

    protocol["protocol"]["title"] = "A title changed after freezing"

    assert (frozen.canonical_bytes, frozen.protocol_revision_id) == expected


def test_schema_error_reports_the_nested_json_pointer(tmp_path: Path) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    protocol = _protocol()
    protocol["analysis"]["alpha"] = "not-a-probability"
    path = _write_yaml(tmp_path / "invalid-schema.yaml", protocol)

    with pytest.raises(ProtocolIoError, match=r"/analysis/alpha"):
        load_protocol(path)


@pytest.mark.parametrize(
    ("field", "value", "pointer"),
    (
        ("method_id", "welch_t", "/analysis/method/method_id"),
        ("method_version", "binary_pooled_z_newcombe_v2", "/analysis/method/method_version"),
    ),
)
def test_unsupported_analysis_pair_reports_exact_pointer(
    tmp_path: Path,
    field: str,
    value: str,
    pointer: str,
) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    protocol = _protocol()
    protocol["analysis"]["method"][field] = value
    path = _write_yaml(tmp_path / f"unsupported-{field}.yaml", protocol)

    with pytest.raises(ProtocolIoError, match=pointer):
        load_protocol(path)


def test_duplicate_nested_key_is_rejected_before_schema_validation(tmp_path: Path) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    path = tmp_path / "duplicate.yaml"
    path.write_bytes(
        b"analysis:\n"
        b"  method:\n"
        b"    method_id: binary_pooled_z_newcombe\n"
        b"    method_id: binary_pooled_z_newcombe\n"
    )

    with pytest.raises(ProtocolIoError) as raised:
        load_protocol(path)

    message = str(raised.value)
    assert path.name in message
    assert "duplicate" in message.lower()
    assert "method_id" in message


@pytest.mark.parametrize(
    "raw",
    (
        b"",
        b"- item\n",
        b"---\na: 1\n---\nb: 2\n",
        b"a: [\n",
        b"!!python/object/apply:os.system ['echo unsafe']\n",
    ),
    ids=("empty", "root-list", "multiple-documents", "malformed", "unsafe-tag"),
)
def test_non_protocol_yaml_is_rejected_with_the_source_path(
    tmp_path: Path,
    raw: bytes,
) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    path = tmp_path / "invalid.yaml"
    path.write_bytes(raw)

    with pytest.raises(ProtocolIoError, match=path.name):
        load_protocol(path)


@pytest.mark.parametrize(
    "raw",
    (
        b"value: .nan\n",
        b"value: 9007199254740992\n",
        b"value: 2026-09-01\n",
    ),
    ids=("non-finite", "unsafe-integer", "yaml-timestamp"),
)
def test_yaml_only_or_non_ijson_values_are_rejected(tmp_path: Path, raw: bytes) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    path = tmp_path / "non-ijson.yaml"
    path.write_bytes(raw)

    with pytest.raises(ProtocolIoError, match=r"JSON"):
        load_protocol(path)


def test_missing_and_non_utf8_sources_are_boundary_errors(tmp_path: Path) -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, load_protocol

    missing = tmp_path / "missing.yaml"
    with pytest.raises(ProtocolIoError, match=missing.name):
        load_protocol(missing)

    non_utf8 = tmp_path / "non-utf8.yaml"
    non_utf8.write_bytes(b"title: \xff\n")
    with pytest.raises(ProtocolIoError, match=non_utf8.name):
        load_protocol(non_utf8)


def test_direct_freeze_revalidates_the_boundary() -> None:
    from app.backend.app.evidence.protocol_io import ProtocolIoError, freeze

    protocol = _protocol()
    protocol["analysis"]["method"]["method_id"] = "not_supported"

    with pytest.raises(ProtocolIoError, match=r"/analysis/method/method_id"):
        freeze(protocol)
