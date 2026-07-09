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

    def create_webhook_delivery(
        self,
        *,
        subscription_id: str,
        event_id: int,
        status: str = "pending",
    ) -> dict[str, Any]:
        delivery_id = str(uuid.uuid4())
        with self._connect() as connection:
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
                    error_message
                )
                VALUES (?, ?, ?, ?, 0, NULL, NULL, NULL, NULL, NULL)
                """,
                (delivery_id, subscription_id, event_id, status),
            )

        delivery = self.get_webhook_delivery(delivery_id)
        if delivery is None:
            raise ApiError("Webhook delivery not found", error_code="webhook_delivery_not_found", status_code=404)
        return delivery

    def get_webhook_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    subscription_id,
                    event_id,
                    status,
                    attempt_count,
                    last_attempt_at,
                    delivered_at,
                    response_code,
                    response_body,
                    error_message
                FROM webhook_deliveries
                WHERE id = ?
                """,
                (delivery_id,),
            ).fetchone()

        if row is None:
            return None
        return webhook_delivery_row_to_record(row)

    def update_webhook_delivery(
        self,
        delivery_id: str,
        *,
        subscription_id: str,
        status: str,
        response_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
        truncated_body = response_body[:2048] if response_body else None

        with self._connect() as connection:
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
                    error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    timestamp,
                    timestamp if status == "delivered" else None,
                    response_code,
                    truncated_body,
                    error_message,
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
                SELECT
                    id,
                    subscription_id,
                    event_id,
                    status,
                    attempt_count,
                    last_attempt_at,
                    delivered_at,
                    response_code,
                    response_body,
                    error_message
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
