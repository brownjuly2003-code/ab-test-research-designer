"""Webhook subscriptions and their delivery attempts."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import (
    webhook_delivery_row_to_record,
    webhook_subscription_row_to_record,
)

_DELIVERY_COLUMNS = """
    id,
    subscription_id,
    event_id,
    status,
    attempt_count,
    last_attempt_at,
    delivered_at,
    response_code,
    response_body,
    error_message,
    next_attempt_at,
    lease_expires_at
"""


class _WebhooksMixin(_BackendCore):
    def create_webhook_subscription(
        self,
        *,
        name: str,
        target_url: str,
        secret: str,
        format: str,
        event_filter: list[str],
        scope: str,
        api_key_id: str | None = None,
    ) -> dict[str, Any]:
        if scope == "api_key" and not api_key_id:
            raise ApiError("api_key_id is required for api_key scope", error_code="webhook_api_key_required")
        if scope == "global" and api_key_id is not None:
            raise ApiError("api_key_id is not allowed for global scope", error_code="webhook_scope_invalid")

        subscription_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        normalized_event_filter = [value for value in event_filter if value]

        with self._connect() as connection:
            if api_key_id is not None:
                key_row = connection.execute(
                    "SELECT 1 FROM api_keys WHERE id = ?",
                    (api_key_id,),
                ).fetchone()
                if key_row is None:
                    raise ApiError("API key not found", error_code="api_key_not_found", status_code=404)
            connection.execute(
                """
                INSERT INTO webhook_subscriptions (
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1)
                """,
                (
                    subscription_id,
                    name,
                    target_url,
                    secret,
                    format,
                    json.dumps(normalized_event_filter),
                    scope,
                    api_key_id,
                    timestamp,
                    timestamp,
                ),
            )

        subscription = self.get_webhook_subscription(subscription_id, include_secret=True)
        if subscription is None:
            raise ApiError("Webhook subscription not found", error_code="webhook_not_found", status_code=404)
        return subscription

    def list_webhook_subscriptions(self, *, include_secret: bool = False) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        subscriptions = [
            webhook_subscription_row_to_record(row, include_secret=include_secret)
            for row in rows
        ]
        return {
            "subscriptions": subscriptions,
            "total": len(subscriptions),
        }

    def get_webhook_subscription(self, subscription_id: str, *, include_secret: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                WHERE id = ?
                """,
                (subscription_id,),
            ).fetchone()

        if row is None:
            return None
        return webhook_subscription_row_to_record(row, include_secret=include_secret)

    def update_webhook_subscription(
        self,
        subscription_id: str,
        *,
        target_url: str | None = None,
        event_filter: list[str] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        updates: list[str] = []
        params: list[Any] = []

        if target_url is not None:
            updates.append("target_url = ?")
            params.append(target_url)
        if event_filter is not None:
            updates.append("event_filter = ?")
            params.append(json.dumps([value for value in event_filter if value]))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if enabled else 0)

        if not updates:
            return self.get_webhook_subscription(subscription_id)

        timestamp = datetime.now(UTC).isoformat()
        updates.append("updated_at = ?")
        params.append(timestamp)
        params.append(subscription_id)

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE webhook_subscriptions
                SET {", ".join(updates)}
                WHERE id = ?
                """,
                params,
            )
            if cursor.rowcount == 0:
                return None

        return self.get_webhook_subscription(subscription_id)

    def delete_webhook_subscription(self, subscription_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM webhook_subscriptions WHERE id = ?",
                (subscription_id,),
            )

        if cursor.rowcount == 0:
            return None
        return {"id": subscription_id, "deleted": True}

    def list_matching_webhook_subscriptions(
        self,
        *,
        event_type: str,
        key_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    name,
                    target_url,
                    secret,
                    format,
                    event_filter,
                    scope,
                    api_key_id,
                    created_at,
                    updated_at,
                    last_delivered_at,
                    last_error_at,
                    enabled
                FROM webhook_subscriptions
                WHERE enabled = 1
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()

        subscriptions: list[dict[str, Any]] = []
        for row in rows:
            subscription = webhook_subscription_row_to_record(row, include_secret=True)
            event_filter = subscription["event_filter"]
            if event_filter and event_type not in event_filter:
                continue
            if subscription["scope"] == "api_key":
                if key_id is None or subscription["api_key_id"] != key_id:
                    continue
            subscriptions.append(subscription)
        return subscriptions

    def _insert_webhook_delivery(
        self,
        connection: Any,
        *,
        subscription_id: str,
        event_id: int,
        status: str,
        next_attempt_at: str | None,
    ) -> str:
        """Insert an outbox row on an existing connection (transactional enqueue)."""
        delivery_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO webhook_deliveries (
                id,
                subscription_id,
                event_id,
                status,
                attempt_count,
                last_attempt_at,
                delivered_at,
                response_code,
                response_body,
                error_message,
                next_attempt_at,
                lease_expires_at
            )
            VALUES (?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL, ?, NULL)
            """,
            (delivery_id, subscription_id, event_id, status, next_attempt_at),
        )
        return delivery_id

    def create_webhook_delivery(
        self,
        *,
        subscription_id: str,
        event_id: int,
        status: str = "pending",
        next_attempt_at: str | None = None,
        enqueue: bool = True,
    ) -> dict[str, Any]:
        """Create a delivery row; with ``enqueue=False`` the row keeps a NULL
        next_attempt_at, so the outbox worker can never claim it (synchronous
        test deliveries own their single attempt)."""
        if next_attempt_at is None and enqueue:
            next_attempt_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            delivery_id = self._insert_webhook_delivery(
                connection,
                subscription_id=subscription_id,
                event_id=event_id,
                status=status,
                next_attempt_at=next_attempt_at,
            )

        delivery = self.get_webhook_delivery(delivery_id)
        if delivery is None:
            raise ApiError("Webhook delivery not found", error_code="webhook_delivery_not_found", status_code=404)
        return delivery

    def get_webhook_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT {_DELIVERY_COLUMNS}
                FROM webhook_deliveries
                WHERE id = ?
                """,
                (delivery_id,),
            ).fetchone()

        if row is None:
            return None
        return webhook_delivery_row_to_record(row)

    def claim_due_webhook_deliveries(
        self,
        *,
        now: str,
        lease_expires_at: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Atomically claim due outbox rows by taking a lease on each.

        The claim is a per-row conditional UPDATE, so it is safe on both backends
        without FOR UPDATE SKIP LOCKED: a row whose lease another worker won first
        updates zero rows here and is skipped. Expired leases (a worker died
        mid-attempt) become claimable again once lease_expires_at passes.
        """
        claimed_ids: list[str] = []
        with self._connect() as connection:
            candidates = connection.execute(
                """
                SELECT id
                FROM webhook_deliveries
                WHERE status IN ('pending', 'retrying')
                  AND next_attempt_at IS NOT NULL
                  AND next_attempt_at <= ?
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                ORDER BY next_attempt_at, id
                LIMIT ?
                """,
                (now, now, max(1, int(limit))),
            ).fetchall()
            for candidate in candidates:
                cursor = connection.execute(
                    """
                    UPDATE webhook_deliveries
                    SET lease_expires_at = ?
                    WHERE id = ?
                      AND status IN ('pending', 'retrying')
                      AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                    """,
                    (lease_expires_at, candidate["id"], now),
                )
                if cursor.rowcount == 1:
                    claimed_ids.append(str(candidate["id"]))

        claimed = []
        for delivery_id in claimed_ids:
            delivery = self.get_webhook_delivery(delivery_id)
            if delivery is not None:
                claimed.append(delivery)
        return claimed

    def get_webhook_queue_stats(self) -> dict[str, Any]:
        """Outbox visibility for diagnostics: per-status counts and the oldest due row."""
        now = datetime.now(UTC)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS n FROM webhook_deliveries GROUP BY status"
            ).fetchall()
            oldest_due = connection.execute(
                """
                SELECT MIN(next_attempt_at) AS oldest
                FROM webhook_deliveries
                WHERE status IN ('pending', 'retrying') AND next_attempt_at IS NOT NULL
                """
            ).fetchone()

        counts = {str(row["status"]): int(row["n"]) for row in rows}
        oldest_due_age_seconds: float | None = None
        oldest_raw = oldest_due["oldest"] if oldest_due is not None else None
        if oldest_raw:
            try:
                oldest_due_age_seconds = max(0.0, round((now - datetime.fromisoformat(str(oldest_raw))).total_seconds(), 3))
            except ValueError:
                oldest_due_age_seconds = None
        return {
            "pending": counts.get("pending", 0),
            "retrying": counts.get("retrying", 0),
            "delivered": counts.get("delivered", 0),
            "failed": counts.get("failed", 0),
            "oldest_due_age_seconds": oldest_due_age_seconds,
        }

    def update_webhook_delivery(
        self,
        delivery_id: str,
        *,
        subscription_id: str,
        status: str,
        response_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
        next_attempt_at: str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        truncated_body = response_body[:2048] if response_body else None

        with self._connect() as connection:
            # Recording an attempt outcome always releases the lease: the row is
            # either terminal or waits for next_attempt_at before the next claim.
            cursor = connection.execute(
                """
                UPDATE webhook_deliveries
                SET
                    status = ?,
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    delivered_at = ?,
                    response_code = ?,
                    response_body = ?,
                    error_message = ?,
                    next_attempt_at = ?,
                    lease_expires_at = NULL
                WHERE id = ?
                """,
                (
                    status,
                    timestamp,
                    timestamp if status == "delivered" else None,
                    response_code,
                    truncated_body,
                    error_message,
                    next_attempt_at,
                    delivery_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            if status == "delivered":
                connection.execute(
                    """
                    UPDATE webhook_subscriptions
                    SET last_delivered_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, timestamp, subscription_id),
                )
            elif status in {"failed", "retrying"}:
                connection.execute(
                    """
                    UPDATE webhook_subscriptions
                    SET last_error_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, timestamp, subscription_id),
                )

        return self.get_webhook_delivery(delivery_id)

    def list_webhook_deliveries(
        self,
        subscription_id: str,
        *,
        limit: int = 50,
        status: str | None = None,
    ) -> dict[str, Any]:
        normalized_limit = max(1, min(int(limit), 200))
        where_clauses = ["subscription_id = ?"]
        params: list[Any] = [subscription_id]
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM webhook_deliveries {where_sql}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT {_DELIVERY_COLUMNS}
                FROM webhook_deliveries
                {where_sql}
                ORDER BY COALESCE(last_attempt_at, delivered_at) DESC, id DESC
                LIMIT ?
                """,
                [*params, normalized_limit],
            ).fetchall()

        deliveries = [webhook_delivery_row_to_record(row) for row in rows]
        return {
            "deliveries": deliveries,
            "total": total,
        }
