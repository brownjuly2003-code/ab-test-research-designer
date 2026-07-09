"""Connection handling, schema bootstrap and the primitives every domain shares.

The domain mixins in this package inherit from `_BackendCore`, so they can rely on
`_connect()`, the class-level schema constants and the project/revision helpers
without importing one another.
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, cast

from app.backend.app.errors import ApiError
from app.backend.app.repository._schema import (
    create_api_key_tables,
    create_audit_tables,
    create_execution_tables,
    create_history_tables,
    create_slack_tables,
    create_template_tables,
    create_webhook_tables,
    migrate_db,
)
from app.backend.app.repository._utils import compute_payload_diff


class _BackendCore:
    backend_name = "sqlite"
    supports_snapshots = True
    schema_version = 14
    payload_schema_version = 1
    workspace_schema_version = 3
    project_select_columns = """
        projects.id,
        projects.project_name,
        projects.payload_json,
        projects.payload_schema_version,
        projects.archived_at,
        projects.last_analysis_at,
        projects.last_analysis_run_id,
        projects.last_exported_at,
        (
            SELECT COUNT(*)
            FROM project_revisions
            WHERE project_revisions.project_id = projects.id
        ) AS revision_count,
        (
            SELECT MAX(created_at)
            FROM project_revisions
            WHERE project_revisions.project_id = projects.id
        ) AS last_revision_at,
        projects.created_at,
        projects.updated_at
    """

    def __init__(
        self,
        db_path: str,
        *,
        busy_timeout_ms: int = 5000,
        journal_mode: str = "WAL",
        synchronous: str = "NORMAL",
        workspace_signing_key: str | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.journal_mode = journal_mode
        self.synchronous = synchronous
        self.workspace_signing_key = workspace_signing_key.strip() if workspace_signing_key else None
        self.webhook_service: Any | None = None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute(f"PRAGMA journal_mode = {self.journal_mode}")
        connection.execute(f"PRAGMA synchronous = {self.synchronous}")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_schema_version INTEGER NOT NULL DEFAULT 1,
                    archived_at TEXT,
                    last_analysis_json TEXT,
                    last_analysis_at TEXT,
                    last_analysis_run_id TEXT,
                    last_exported_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            create_history_tables(connection)
            create_audit_tables(connection)
            create_api_key_tables(connection)
            create_webhook_tables(connection)
            create_slack_tables(connection)
            create_template_tables(connection)
            create_execution_tables(connection)
            migrate_db(connection)
            connection.execute(f"PRAGMA user_version = {self.schema_version}")

    def set_webhook_service(self, webhook_service: Any | None) -> None:
        self.webhook_service = webhook_service

    @staticmethod
    def _create_revision(
        connection: sqlite3.Connection,
        project_id: str,
        payload: dict[str, Any],
        source: str,
        created_at: str,
        revision_id: str | None = None,
    ) -> str:
        resolved_revision_id = revision_id or str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO project_revisions (id, project_id, payload_json, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                resolved_revision_id,
                project_id,
                json.dumps(payload),
                source,
                created_at,
            ),
        )
        return resolved_revision_id

    def _get_project_row(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        *,
        include_archived: bool = False,
    ) -> sqlite3.Row | None:
        archived_clause = "" if include_archived else "AND archived_at IS NULL"
        return cast(
            "sqlite3.Row | None",
            connection.execute(
                f"""
            SELECT {self.project_select_columns}
            FROM projects
            WHERE id = ? {archived_clause}
            """,
                (project_id,),
            ).fetchone(),
        )

    @staticmethod
    def _normalize_history_limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    @staticmethod
    def _normalize_history_offset(offset: int) -> int:
        return max(0, int(offset))

    def _project_exists(self, connection: sqlite3.Connection, project_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        return row is not None

    def _ensure_project_active(self, connection: sqlite3.Connection, project_id: str) -> None:
        row = connection.execute(
            "SELECT archived_at FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ApiError("Project not found", error_code="project_not_found", status_code=404)
        if row["archived_at"] is not None:
            raise ApiError("Project is archived", error_code="project_archived")

    def _run_write_probe(self) -> tuple[bool, str]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
            return True, "BEGIN IMMEDIATE succeeded"
        except sqlite3.Error as exc:
            return False, str(exc)

    @staticmethod
    def build_payload_diff(previous_payload: dict[str, Any], next_payload: dict[str, Any]) -> dict[str, list[Any]]:
        """Kept on the backend surface: routes reach it through ProjectRepository."""
        return compute_payload_diff(previous_payload, next_payload)
