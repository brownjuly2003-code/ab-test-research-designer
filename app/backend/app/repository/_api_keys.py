"""Scoped API keys: issue, list, revoke, and constant-time authentication."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any, Final

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import api_key_row_to_record
from app.backend.app.repository._utils import hash_api_key

# Issued (database-backed) API keys. Operator access is AB_ADMIN_TOKEN only.
ISSUED_API_KEY_SCOPES: Final[frozenset[str]] = frozenset({"read", "write"})


class _ApiKeysMixin(_BackendCore):
    def has_api_keys(self) -> bool:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM api_keys
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def has_active_api_keys(self, *, scope: str | None = None) -> bool:
        # Issued keys are only read/write. Legacy "admin" rows are normalized at boot.
        scope_filters = {
            "write": ("write",),
            "read": ("read", "write"),
        }
        scopes = scope_filters.get(scope) if scope is not None else None
        with self._transaction() as connection:
            if scopes is None:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM api_keys
                    WHERE revoked_at IS NULL
                    LIMIT 1
                    """
                ).fetchone()
            else:
                placeholders = ", ".join("?" for _ in scopes)
                row = connection.execute(
                    f"""
                    SELECT 1
                    FROM api_keys
                    WHERE revoked_at IS NULL AND scope IN ({placeholders})
                    LIMIT 1
                    """,
                    scopes,
                ).fetchone()
        return row is not None

    def normalize_legacy_admin_api_key_scopes(self) -> int:
        """Rewrite stored scope=admin keys to write and audit each change.

        Pre-F-09 keys labeled ``admin`` never received operator privileges; they
        behaved as write keys with a misleading label. Normalization is idempotent.
        """
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM api_keys
                WHERE scope = 'admin'
                """
            ).fetchall()
            if not rows:
                return 0
            connection.execute(
                """
                UPDATE api_keys
                SET scope = 'write'
                WHERE scope = 'admin'
                """
            )
        key_ids = [str(row["id"]) for row in rows]
        log_audit = getattr(self, "log_audit_entry", None)
        if callable(log_audit):
            for key_id in key_ids:
                log_audit(
                    action="api_key_scope_normalized",
                    key_id=key_id,
                    actor="system:schema_migration",
                    request_id=None,
                    ip_address=None,
                    payload_diff={"scope": ["admin", "write"]},
                    dispatch_webhooks=False,
                )
        return len(key_ids)

    def create_api_key(
        self,
        *,
        name: str,
        scope: str,
        rate_limit_requests: int | None = None,
        rate_limit_window_seconds: int | None = None,
    ) -> dict[str, Any]:
        if scope not in ISSUED_API_KEY_SCOPES:
            raise ApiError(
                "Issued API keys support only read or write scope; "
                "operator access uses AB_ADMIN_TOKEN",
                error_code="api_key_scope_invalid",
                status_code=400,
            )
        api_key_id = str(uuid.uuid4())
        plaintext_key = f"abk_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(plaintext_key)
        created_at = datetime.now(UTC).isoformat()

        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (
                    id,
                    name,
                    key_hash,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    api_key_id,
                    name,
                    key_hash,
                    scope,
                    created_at,
                    rate_limit_requests,
                    rate_limit_window_seconds,
                ),
            )

        return {
            "id": api_key_id,
            "name": name,
            "scope": scope,
            "created_at": created_at,
            "last_used_at": None,
            "revoked_at": None,
            "rate_limit_requests": rate_limit_requests,
            "rate_limit_window_seconds": rate_limit_window_seconds,
            "plaintext_key": plaintext_key,
        }

    def list_api_keys(self) -> dict[str, Any]:
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        keys = [api_key_row_to_record(row) for row in rows]
        return {
            "keys": keys,
            "total": len(keys),
        }

    def revoke_api_key(self, api_key_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE api_keys
                SET revoked_at = COALESCE(revoked_at, ?)
                WHERE id = ?
                """,
                (timestamp, api_key_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE id = ?
                """,
                (api_key_id,),
            ).fetchone()

        return api_key_row_to_record(row) if row is not None else None

    def delete_api_key(self, api_key_id: str) -> dict[str, Any] | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT id, revoked_at FROM api_keys WHERE id = ?",
                (api_key_id,),
            ).fetchone()
            if row is None:
                return None
            if row["revoked_at"] is None:
                raise ApiError(
                    "API key must be revoked before deletion",
                    error_code="api_key_not_revoked",
                    status_code=409,
                )
            connection.execute(
                "DELETE FROM api_keys WHERE id = ?",
                (api_key_id,),
            )

        return {
            "id": api_key_id,
            "deleted": True,
        }

    def authenticate_api_key(self, plaintext_key: str) -> dict[str, Any] | None:
        key_hash = hash_api_key(plaintext_key)
        last_used_at = datetime.now(UTC).isoformat()
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE key_hash = ? AND revoked_at IS NULL
                """,
                (key_hash,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (last_used_at, row["id"]),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    scope,
                    created_at,
                    last_used_at,
                    revoked_at,
                    rate_limit_requests,
                    rate_limit_window_seconds
                FROM api_keys
                WHERE id = ?
                """,
                (row["id"],),
            ).fetchone()

        if row is None:
            return None
        record = api_key_row_to_record(row)
        # Defensive: never surface legacy admin as an issued operator privilege.
        if record.get("scope") == "admin":
            record["scope"] = "write"
        return record
