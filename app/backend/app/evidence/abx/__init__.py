"""The Trialmark bundle format: pack one, verify one, look inside one.

`abx` names the format and Trialmark names the product (ADR 0006), so the
module names stay until a format version 0.2. This package is the split of
what was a single 2 100-line module; the surface below is exactly what that
module exported, so no importer had to change. Underscore names are here
because tests reach for them, not because they are public.
"""

from __future__ import annotations

from app.backend.app.evidence.abx._core import (
    ABX_VERSION,
    BUNDLE_MEDIA_TYPE,
    BUNDLE_SUFFIX,
    KNOWN_CAPABILITIES,
    MANIFEST_SCHEMA_ID,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_BYTES,
    PROTOCOL_SCHEMA_ID,
    STRUCTURED_ROLES,
    UNBOUND_REFERENCE,
    VERDICT_DIMENSIONS,
    AbxError,
    _canonical_digest,
    _query_identity_digest,
    canonical_json_bytes,
    load_abx_document,
    manifest_bundle_id,
    schema_violations,
    validate_abx_document,
)
from app.backend.app.evidence.abx.pack import (
    pack_bundle,
)
from app.backend.app.evidence.abx.privacy import (
    _privacy_issues,
    _text_privacy_issues,
)
from app.backend.app.evidence.abx.verify import (
    inspect_bundle,
    verify_bundle,
    verify_logical_bundle,
)
from app.backend.app.evidence.abx.zip_safety import (
    _stored_offsets_match_physical_layout,
)

__all__ = [
    "ABX_VERSION",
    "AbxError",
    "BUNDLE_MEDIA_TYPE",
    "BUNDLE_SUFFIX",
    "KNOWN_CAPABILITIES",
    "MANIFEST_SCHEMA_ID",
    "MAX_COMPRESSION_RATIO",
    "MAX_MEMBERS",
    "MAX_MEMBER_BYTES",
    "MAX_TOTAL_BYTES",
    "PROTOCOL_SCHEMA_ID",
    "STRUCTURED_ROLES",
    "UNBOUND_REFERENCE",
    "VERDICT_DIMENSIONS",
    "_canonical_digest",
    "_privacy_issues",
    "_query_identity_digest",
    "_stored_offsets_match_physical_layout",
    "_text_privacy_issues",
    "canonical_json_bytes",
    "inspect_bundle",
    "load_abx_document",
    "manifest_bundle_id",
    "pack_bundle",
    "schema_violations",
    "validate_abx_document",
    "verify_bundle",
    "verify_logical_bundle",
]
