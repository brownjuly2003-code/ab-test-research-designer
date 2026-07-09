"""Scoped API keys: issue, list, revoke, and constant-time authentication."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import api_key_row_to_record
from app.backend.app.repository._utils import hash_api_key


class _ApiKeysMixin(_BackendCore):
    def has_api_keys(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM api_keys
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def has_active_api_keys(self, *, scope: str | None = None) -> bool:
        scope_filters = {
            "write": ("write", "admin"),
            "read": ("read", "write", "admin"),
            "admin": ("admin",),
        }
        scopes = scope_filters.get(scope) if scope is not None else None
        with self._connect() as connection:
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

    def create_api_key(
        self,
        *,
        name: str,
        scope: str,
        rate_limit_requests: int | None = None,
        rate_limit_window_seconds: int | None = None,
    ) -> dict[str, Any]:
        api_key_id = str(uuid.uuid4())
        plaintext_key = f"abk_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(plaintext_key)
        created_at = datetime.now(UTC).isoformat()

        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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

        return api_key_row_to_record(row) if row is not None else None
