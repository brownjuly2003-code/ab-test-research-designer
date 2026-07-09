"""Audit-log payloads."""

from typing import Any

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: int
    ts: str
    action: str
    project_id: str | None = None
    project_name: str | None = None
    key_id: str | None = None
    actor: str | None = None
    request_id: str | None = None
    payload_diff: dict[str, list[Any]] | None = None
    ip_address: str | None = None


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int = 0
