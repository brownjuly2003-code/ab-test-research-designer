"""Append-only audit trail and its CSV export."""

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import audit_row_to_record


class _AuditMixin(_BackendCore):
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
        timestamp = ts or datetime.now(UTC).isoformat()
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
        if dispatch_webhooks and self.webhook_service is not None:
            try:
                self.webhook_service.dispatch_audit_event(event)
            except Exception:
                pass
        return event

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
