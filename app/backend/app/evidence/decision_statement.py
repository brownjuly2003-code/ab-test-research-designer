"""Unsigned DSSE envelopes for Trialmark in-toto decision statements."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Final, cast

from app.backend.app.evidence._common import canonical_json_bytes, load_ijson_object

DECISION_RECORD_SCHEMA_ID: Final = "urn:evidenceos:abx:schema:0.1:decision"
DECISION_STATEMENT_SCHEMA_ID: Final = (
    "urn:evidenceos:abx:schema:0.1:decision-statement"
)
DECISION_STATEMENT_MEDIA_TYPE: Final = "application/vnd.dsse.envelope.v1+json"
DECISION_STATEMENT_PAYLOAD_TYPE: Final = "application/vnd.in-toto+json"
DECISION_STATEMENT_TYPE: Final = "https://in-toto.io/Statement/v1"
DECISION_PREDICATE_TYPE: Final = (
    "https://trialmark.dev/attestation/decision/v1"
)
DECISION_SUBJECT_NAME: Final = "trialmark-bundle"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class DecisionStatementError(ValueError):
    """Raised when a decision statement cannot be decoded unambiguously."""


def build_decision_statement_envelope(
    decision: dict[str, Any],
    *,
    subject_bundle_id: str,
) -> dict[str, Any]:
    """Wrap one decision record in an unsigned DSSE in-toto Statement v1."""

    digest = subject_bundle_id.removeprefix("sha256:")
    if _SHA256_HEX_RE.fullmatch(digest) is None:
        raise DecisionStatementError("decision statement subject must be a SHA-256 digest")
    statement = {
        "_type": DECISION_STATEMENT_TYPE,
        "subject": [
            {
                "name": DECISION_SUBJECT_NAME,
                "digest": {"sha256": digest},
            }
        ],
        "predicateType": DECISION_PREDICATE_TYPE,
        "predicate": decision,
    }
    return {
        "payload": base64.b64encode(canonical_json_bytes(statement)).decode("ascii"),
        "payloadType": DECISION_STATEMENT_PAYLOAD_TYPE,
        "signatures": [],
    }


def parse_decision_artifact(
    document: dict[str, Any],
    *,
    schema_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    """Return the decision record plus optional Statement and normalized subject."""

    if schema_id != DECISION_STATEMENT_SCHEMA_ID:
        return document, None, None
    if document.get("payloadType") != DECISION_STATEMENT_PAYLOAD_TYPE:
        raise DecisionStatementError("decision DSSE payloadType is unsupported")
    if document.get("signatures") != []:
        raise DecisionStatementError("decision DSSE envelope must be unsigned")
    encoded_payload = document.get("payload")
    if not isinstance(encoded_payload, str):
        raise DecisionStatementError("decision DSSE payload must be base64 text")
    try:
        payload = base64.b64decode(
            encoded_payload,
            altchars=b"-_",
            validate=True,
        )
        statement = load_ijson_object(payload)
    except (binascii.Error, UnicodeEncodeError, ValueError) as error:
        raise DecisionStatementError(
            f"decision DSSE payload is not strict base64 I-JSON: {error}"
        ) from error
    if statement.get("_type") != DECISION_STATEMENT_TYPE:
        raise DecisionStatementError("decision statement has an unsupported _type")
    if statement.get("predicateType") != DECISION_PREDICATE_TYPE:
        raise DecisionStatementError("decision statement has an unsupported predicateType")
    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise DecisionStatementError("decision statement predicate must be an object")
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1:
        raise DecisionStatementError("decision statement must have exactly one subject")
    subject = subjects[0]
    if not isinstance(subject, dict):
        raise DecisionStatementError("decision statement subject must be an object")
    digest_map = subject.get("digest")
    if not isinstance(digest_map, dict):
        raise DecisionStatementError("decision statement subject must contain a digest")
    digest = digest_map.get("sha256")
    if not isinstance(digest, str) or _SHA256_HEX_RE.fullmatch(digest) is None:
        raise DecisionStatementError(
            "decision statement subject must contain one lowercase SHA-256 digest"
        )
    return cast(dict[str, Any], predicate), statement, f"sha256:{digest}"


__all__ = [
    "DECISION_PREDICATE_TYPE",
    "DECISION_RECORD_SCHEMA_ID",
    "DECISION_STATEMENT_MEDIA_TYPE",
    "DECISION_STATEMENT_PAYLOAD_TYPE",
    "DECISION_STATEMENT_SCHEMA_ID",
    "DECISION_STATEMENT_TYPE",
    "DecisionStatementError",
    "build_decision_statement_envelope",
    "parse_decision_artifact",
]
