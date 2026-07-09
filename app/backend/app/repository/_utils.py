"""Pure helpers shared by the repository backends: no IO, no connection."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _normalize_occurred_at(value: Any, fallback: str) -> str:
    """Normalize a client-supplied event time to a UTC ISO-8601 string (P4.1, event-time).

    ``occurred_at`` is when the event happened on the client; ``created_at`` (the ``fallback``)
    is when the server received it. ``value`` may be a ``datetime`` (parsed by the ingest schema),
    an ISO string, or ``None``. A naive datetime is assumed UTC; ``None`` or an unparseable value
    falls back to the server-receive time, so ``occurred_at`` defaults to the received time. This
    only records event-time; out-of-window / late attribution is layered on in P4.2.
    """
    if value is None:
        return fallback
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return fallback
    else:
        return fallback
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    """Parse a stored ISO-8601 timestamp back to a tz-aware datetime, or ``None`` if unparseable.

    Stored ``occurred_at`` / ``created_at`` values are UTC-aware ISO strings (see
    ``_normalize_occurred_at``); a naive value is treated as UTC so comparisons never mix
    naive/aware datetimes. Used by the P4.2 event-timing classification.
    """
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)

def decode_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def flatten_payload(value: Any, *, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value.keys()):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(flatten_payload(value[key], prefix=child_prefix))
        return flattened
    if isinstance(value, list):
        return {prefix: value}
    return {prefix: value}


def compute_payload_diff(previous_payload: dict[str, Any], next_payload: dict[str, Any]) -> dict[str, list[Any]]:
    previous = flatten_payload(previous_payload)
    current = flatten_payload(next_payload)
    changed_keys = sorted(set(previous.keys()) | set(current.keys()))
    diff: dict[str, list[Any]] = {}
    for key in changed_keys:
        if previous.get(key) != current.get(key):
            diff[key] = [previous.get(key), current.get(key)]
    return diff


def hash_api_key(plaintext_key: str) -> str:
    return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()
