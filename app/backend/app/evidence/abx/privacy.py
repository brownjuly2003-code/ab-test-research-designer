"""What must never leave a workspace inside a bundle."""

from __future__ import annotations

import ipaddress
import math
import re
from typing import Any

from app.backend.app.evidence._common import (
    SHA256_RE,
)
from app.backend.app.evidence.abx._core import (
    _DIGEST_BACKED_ID_RE,
    _GIT_COMMIT_RE,
    _HEX_DIGEST_RE,
    _IPV4_CANDIDATE,
    _IPV6_CANDIDATE,
    _LONG_NUMERIC_VALUE,
    _NUMERIC_IDENTIFIER_KEY_TOKENS,
    _SECRET_KEYS,
    _SENSITIVE_TEXT_PATTERNS,
)


def _normalize_privacy_key(key: str) -> str:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    separated = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", separated)
    return re.sub(r"[^a-z0-9]+", "_", separated.casefold()).strip("_")


def _is_long_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value) and abs(value) >= 1_000_000
    return isinstance(value, str) and _LONG_NUMERIC_VALUE.fullmatch(value.strip()) is not None


def _numeric_identifier_issues(value: Any, pointer: str, key: str) -> list[tuple[str, str]]:
    if _is_long_numeric_value(value):
        return [(pointer, f"detected numeric_identifier in field {key!r}")]
    if isinstance(value, list):
        return [
            issue
            for index, item in enumerate(value)
            for issue in _numeric_identifier_issues(item, f"{pointer}/{index}", key)
        ]
    return []


def _contains_ip_address(text: str, pattern: re.Pattern[str], version: int) -> bool:
    for match in pattern.finditer(text):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        if address.version == version:
            return True
    return False


def _sensitive_text_codes(text: str) -> list[str]:
    phone_safe_text = _DIGEST_BACKED_ID_RE.sub("generated_identity", text)
    phone_safe_text = _HEX_DIGEST_RE.sub("generated_digest", phone_safe_text)
    codes = [
        code
        for code, pattern in _SENSITIVE_TEXT_PATTERNS
        if pattern.search(phone_safe_text if code == "phone_number" else text)
    ]
    if SHA256_RE.fullmatch(text) is not None:
        codes = [code for code in codes if code != "phone_number"]
    if _contains_ip_address(text, _IPV4_CANDIDATE, 4):
        codes.append("ipv4_address")
    if _contains_ip_address(text, _IPV6_CANDIDATE, 6):
        codes.append("ipv6_address")
    return codes


def _privacy_issues(value: Any, pointer: str = "") -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}"
            normalized_key = _normalize_privacy_key(key)
            if normalized_key in _SECRET_KEYS and item not in (None, "", [], {}):
                issues.append((child, f"secret-bearing field {key!r} is forbidden"))
            if _NUMERIC_IDENTIFIER_KEY_TOKENS.intersection(normalized_key.split("_")):
                issues.extend(_numeric_identifier_issues(item, child, key))
            issues.extend(_privacy_issues(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_privacy_issues(item, f"{pointer}/{index}"))
    elif isinstance(value, str):
        pointer_key = pointer.rsplit("/", 1)[-1].replace("~1", "/").replace("~0", "~")
        codes = _sensitive_text_codes(value)
        normalized_pointer_key = _normalize_privacy_key(pointer_key)
        if normalized_pointer_key == "json_pointer":
            codes = [code for code in codes if code != "absolute_path"]
        if normalized_pointer_key == "git_commit" and _GIT_COMMIT_RE.fullmatch(value):
            codes = [code for code in codes if code != "phone_number"]
        issues.extend((pointer, f"detected {code}") for code in codes)
    return issues


def _text_privacy_issues(text: str) -> list[tuple[str, str]]:
    return [("", f"detected {code}") for code in _sensitive_text_codes(text)]
