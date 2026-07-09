"""Persistence layer.

`ProjectRepository` is the only entry point callers need: it owns a backend chosen from
the database URL and forwards attribute access to it. The backend itself is assembled
from per-domain mixins (projects, history, templates, api keys, webhooks, slack, audit,
workspace, diagnostics, execution) defined in the sibling modules.

`create_backend` resolves `SQLiteBackend` / `PostgresBackend` from this module's namespace,
so tests can patch them here.
"""

from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from app.backend.app.repository._postgres import PostgresBackend
from app.backend.app.repository._sqlite import SQLiteBackend

__all__ = [
    "DatabaseBackend",
    "PostgresBackend",
    "ProjectRepository",
    "SQLiteBackend",
    "create_backend",
]


class DatabaseBackend(Protocol):
    backend_name: str
    supports_snapshots: bool
    schema_version: int
    workspace_schema_version: int

    def set_webhook_service(self, webhook_service: Any | None) -> None: ...


def _sqlite_path_from_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return database_url
    if parsed.netloc and parsed.path:
        return unquote(f"{parsed.netloc}{parsed.path}")
    if parsed.path:
        resolved_path = unquote(parsed.path)
        if len(resolved_path) >= 4 and resolved_path[0] == "/" and resolved_path[2] == ":":
            return resolved_path[1:]
        if resolved_path.startswith("//"):
            return resolved_path[1:]
        return resolved_path
    return database_url.removeprefix("sqlite:///")


def create_backend(
    database_url: str,
    *,
    busy_timeout_ms: int = 5000,
    journal_mode: str = "WAL",
    synchronous: str = "NORMAL",
    workspace_signing_key: str | None = None,
    pool_size: int = 10,
) -> DatabaseBackend:
    parsed = urlparse(database_url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return PostgresBackend(
            database_url,
            pool_size=pool_size,
            workspace_signing_key=workspace_signing_key,
        )
    return SQLiteBackend(
        _sqlite_path_from_database_url(database_url),
        busy_timeout_ms=busy_timeout_ms,
        journal_mode=journal_mode,
        synchronous=synchronous,
        workspace_signing_key=workspace_signing_key,
    )


class ProjectRepository:
    def __init__(
        self,
        database_url: str,
        *,
        busy_timeout_ms: int = 5000,
        journal_mode: str = "WAL",
        synchronous: str = "NORMAL",
        workspace_signing_key: str | None = None,
        pool_size: int = 10,
    ) -> None:
        self._backend = create_backend(
            database_url,
            busy_timeout_ms=busy_timeout_ms,
            journal_mode=journal_mode,
            synchronous=synchronous,
            workspace_signing_key=workspace_signing_key,
            pool_size=pool_size,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    def set_webhook_service(self, webhook_service: Any | None) -> None:
        self._backend.set_webhook_service(webhook_service)

    def close(self) -> None:
        backend_close = getattr(self._backend, "close", None)
        if callable(backend_close):
            backend_close()
