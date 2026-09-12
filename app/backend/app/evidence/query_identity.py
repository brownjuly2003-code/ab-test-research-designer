from __future__ import annotations

import json

from app.backend.app.evidence._common import sha256_hex as sha256_prefixed

__all__ = ["digest_json", "query_identity_digest", "sha256_prefixed"]


def digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_prefixed(encoded)


def query_identity_digest(
    *,
    dialect: str,
    parameters_digest: str,
    source_fingerprint: object,
    statement_digest: str,
) -> str:
    """Return the stable identity digest shared by query producers and ABX verification."""
    return digest_json(
        {
            "dialect": dialect,
            "parameters_digest": parameters_digest,
            "source_fingerprint": source_fingerprint,
            "statement_digest": statement_digest,
        }
    )
