"""Single place that strips credentials out of database URLs.

A PostgreSQL DSN carries the password inline. Anything that logs, serializes or
echoes `AB_DATABASE_URL` therefore leaks it, so every such call site must pass
through `redact_database_url()` instead of touching the raw value.
"""

from __future__ import annotations

import re

REDACTED = "***"

# Splits `scheme://` from the authority. The authority ends at the first `/`, `?`
# or `#`, so anything before that which contains an `@` is userinfo.
_SCHEME_AUTHORITY_RE = re.compile(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<authority>[^/?#]*)")

# libpq also accepts the password as a query parameter.
_SENSITIVE_QUERY_RE = re.compile(r"(?i)(?<![\w-])(password|passwd|pwd|sslpassword)=([^&\s]*)")

# Free-text fallback for arbitrary log lines: `scheme://user:pass@host`.
_INLINE_CREDENTIALS_RE = re.compile(r"(?i)([a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s/@]*:[^\s/@]*@")


def redact_database_url(database_url: str) -> str:
    """Return `database_url` with credentials removed, keeping host and database name.

    `postgresql://ab:s3cret@db.internal:5432/ab` -> `postgresql://***@db.internal:5432/ab`.
    Values without credentials (the SQLite default) are returned unchanged.
    """
    if not isinstance(database_url, str) or not database_url:
        return ""

    redacted = _SENSITIVE_QUERY_RE.sub(rf"\1={REDACTED}", database_url)

    match = _SCHEME_AUTHORITY_RE.match(redacted)
    if match is None:
        # Not a URL we can parse — never risk returning it verbatim.
        return REDACTED if "@" in redacted else redacted

    authority = match.group("authority")
    if "@" not in authority:
        return redacted

    # Split on the LAST `@`: an unencoded `@` inside the password would otherwise
    # leave its tail in the host part.
    host = authority.rsplit("@", 1)[1]
    return f"{match.group('scheme')}{REDACTED}@{host}{redacted[match.end():]}"


def database_host(database_url: str) -> str:
    """Return just the host[:port] of `database_url`, or "" when it has none."""
    match = _SCHEME_AUTHORITY_RE.match(database_url or "")
    if match is None:
        return ""
    authority = match.group("authority")
    return authority.rsplit("@", 1)[-1]


def mask_inline_credentials(value: str) -> str:
    """Mask `scheme://user:pass@` credentials anywhere inside free text."""
    return _INLINE_CREDENTIALS_RE.sub(rf"\1{REDACTED}@", value)
