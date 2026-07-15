"""Append-only audit trail and its CSV export.

Inherits the webhooks mixin: enqueuing a delivery outbox row must share the audit
insert's transaction (F-09), so this domain depends on that one by design.
"""

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._rows import audit_row_to_record
from app.backend.app.repository._webhooks import _WebhooksMixin


class _AuditMixin(_WebhooksMixin):
    def _resolve_audit_timestamp(self, ts: str | None) -> str:
        """Prefer an explicit ts, then the webhook service clock (test injection), else wall clock.

        Outbox claim compares ``next_attempt_at`` to the worker clock. If enqueue stamped wall
        time while tests drive a FakeClock fixed in the past, every due-claim would miss.
        """
        if ts is not None:
            return ts
        service = getattr(self, "webhook_service", None)
        clock = getattr(service, "clock", None) if service is not None else None
        if callable(clock):
            stamped = clock()
            return stamped.isoformat() if isinstance(stamped, datetime) else str(stamped)
        return datetime.now(UTC).isoformat()

    def log_audit_entry(
        self,
        *,
        action: str,
        key_id: str | None = None,
        actor: str,
        request_id: str | None,
        ip_address: str | None,
        project_id: str | None = None,
        project_name: str | None = None,
        payload_diff: dict[str, list[Any]] | None = None,
        ts: str | None = None,
        dispatch_webhooks: bool = True,
    ) -> dict[str, Any]:
        timestamp = self._resolve_audit_timestamp(ts)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_log (
                    ts,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    payload_diff,
                    ip_address
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    timestamp,
                    action,
                    project_id,
                    project_name,
                    key_id,
                    actor,
                    request_id,
                    json.dumps(payload_diff) if payload_diff else None,
                    ip_address,
                ),
            )
            inserted = cursor.fetchone()
            inserted_id = inserted["id"] if inserted is not None else None
            row = connection.execute(
                """
                SELECT id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                FROM audit_log
                WHERE id = ?
                """,
                (inserted_id,),
            ).fetchone()

            if row is None:
                raise ApiError("Audit event not found", error_code="audit_event_not_found", status_code=500)
            event = audit_row_to_record(row)

            # Durable outbox (F-09): the delivery rows commit with the audit row —
            # a crash right after this transaction leaves claimable pending rows,
            # never a recorded event with no deliveries. The worker is only nudged
            # after commit; without a service (standalone repository) nothing is
            # enqueued, matching the old dispatch behavior.
            enqueued = 0
            if dispatch_webhooks and self.webhook_service is not None:
                subscriptions = self.list_matching_webhook_subscriptions(
                    event_type=action,
                    key_id=key_id,
                )
                for subscription in subscriptions:
                    self._insert_webhook_delivery(
                        connection,
                        subscription_id=str(subscription["id"]),
                        event_id=int(event["id"]),
                        status="pending",
                        next_attempt_at=timestamp,
                    )
                    enqueued += 1

        if enqueued and self.webhook_service is not None:
            try:
                self.webhook_service.notify_enqueued()
            except Exception:
                pass
        return event

    def get_audit_entry(self, event_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                FROM audit_log
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return audit_row_to_record(row)

    def list_audit_entries(
        self,
        *,
        project_id: str | None = None,
        key_id: str | None = None,
        action: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        normalized_limit = max(1, min(int(limit), 500))
        where_clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        if key_id:
            where_clauses.append("key_id = ?")
            params.append(key_id)
        if action:
            where_clauses.append("action = ?")
            params.append(action)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM audit_log {where_sql}",
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT id, ts, action, project_id, project_name, key_id, actor, request_id, payload_diff, ip_address
                FROM audit_log
                {where_sql}
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                [*params, normalized_limit],
            ).fetchall()

        entries = []
        for row in rows:
            entries.append(audit_row_to_record(row))
        return {
            "entries": entries,
            "total": total,
        }

    def export_audit_entries_csv(
        self,
        *,
        project_id: str | None = None,
        key_id: str | None = None,
        action: str | None = None,
    ) -> str:
        audit_log = self.list_audit_entries(project_id=project_id, key_id=key_id, action=action, limit=500)
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            ["ts", "action", "project_id", "project_name", "actor", "key_id", "request_id", "payload_diff", "ip_address"]
        )
        for entry in audit_log["entries"]:
            writer.writerow([
                entry["ts"],
                entry["action"],
                entry.get("project_id") or "",
                entry.get("project_name") or "",
                entry.get("actor") or "",
                entry.get("key_id") or "",
                entry.get("request_id") or "",
                json.dumps(entry["payload_diff"], sort_keys=True) if entry.get("payload_diff") else "",
                entry.get("ip_address") or "",
            ])
        return buffer.getvalue()
