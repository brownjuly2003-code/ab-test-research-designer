from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Final, cast

import rfc8785

MAX_SAFE_INTEGER: Final = 9_007_199_254_740_991
SHA256_PATTERN: Final = r"^sha256:[0-9a-f]{64}$"
SHA256_RE: Final = re.compile(SHA256_PATTERN)


class CanonicalJsonError(ValueError):
    """Raised when a value cannot be serialized as RFC 8785 bytes."""


class IJsonError(ValueError):
    """Raised when bytes are not strict UTF-8 I-JSON."""


class IJsonObjectError(IJsonError):
    """Raised when I-JSON is valid but the domain requires a JSON object."""


def sha256_hex(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Return RFC 8785 canonical UTF-8 bytes."""
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError) as exc:
        raise CanonicalJsonError(f"value is not RFC 8785 canonicalizable: {exc}") from exc


def canonical_digest(value: Any) -> str:
    return sha256_hex(canonical_json_bytes(value))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _parse_int(raw: str) -> int:
    value = int(raw)
    if abs(value) > MAX_SAFE_INTEGER:
        raise ValueError(f"integer outside the I-JSON safe range: {raw}")
    return value


def _parse_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"number outside the I-JSON finite range: {raw}")
    return value


def _reject_non_json_number(raw: str) -> None:
    raise ValueError(f"non-I-JSON numeric constant: {raw}")


def _reject_lone_surrogates(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("string contains a non-Unicode scalar value")
        return
    if isinstance(value, list):
        for item in value:
            _reject_lone_surrogates(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_lone_surrogates(key)
            _reject_lone_surrogates(item)


def load_ijson(payload: bytes) -> Any:
    """Parse bytes as strict UTF-8 I-JSON without requiring a JSON object."""
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_json_number,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
        _reject_lone_surrogates(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IJsonError(str(exc)) from exc
    return value


def load_ijson_object(payload: bytes) -> dict[str, Any]:
    """Parse bytes as a strict UTF-8 I-JSON object."""
    value = load_ijson(payload)
    if not isinstance(value, dict):
        raise IJsonObjectError("JSON value must be an object")
    return cast(dict[str, Any], value)


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
