import csv
from datetime import datetime, timezone
import hmac
import hashlib
from io import StringIO
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
from typing import Any
import uuid

from pydantic import ValidationError

from app.backend.app.errors import ApiError
from app.backend.app.schemas.api import ExperimentInput


class ProjectRepository:
    schema_version = 6
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
            self._create_history_tables(connection)
            self._create_audit_tables(connection)
            self._create_api_key_tables(connection)
            self._create_template_tables(connection)
            self._migrate_db(connection)
            connection.execute(f"PRAGMA user_version = {self.schema_version}")

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict:
        project = dict(row)
        payload_json = project.pop("payload_json")
        project["payload"] = json.loads(payload_json)
        project["has_analysis_snapshot"] = bool(project.get("last_analysis_run_id"))
        project["is_archived"] = bool(project.get("archived_at"))
        return project

    @staticmethod
    def _create_history_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_runs_project_created
            ON analysis_runs (project_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS export_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                analysis_run_id TEXT,
                format TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_run_id) REFERENCES analysis_runs(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_export_events_project_created
            ON export_events (project_id, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_revisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_revisions_project_created
            ON project_revisions (project_id, created_at DESC)
            """
        )

    @staticmethod
    def _create_audit_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                project_id TEXT,
                project_name TEXT,
                key_id TEXT,
                actor TEXT,
                request_id TEXT,
                payload_diff TEXT,
                ip_address TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_created
            ON audit_log (ts DESC, id DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_project
            ON audit_log (project_id, ts DESC, id DESC)
            """
        )

    @staticmethod
    def _create_api_key_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                rate_limit_requests INTEGER,
                rate_limit_window_seconds INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_keys_scope_active
            ON api_keys (scope, revoked_at, created_at DESC)
            """
        )

    @staticmethod
    def _create_template_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS project_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                built_in INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_templates_updated
            ON project_templates (built_in DESC, updated_at DESC, id ASC)
            """
        )

    @staticmethod
    def _migrate_db(connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        required_columns = {
            "payload_schema_version": "INTEGER NOT NULL DEFAULT 1",
            "archived_at": "TEXT",
            "last_analysis_json": "TEXT",
            "last_analysis_at": "TEXT",
            "last_analysis_run_id": "TEXT",
            "last_exported_at": "TEXT",
        }

        for column_name, column_definition in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE projects ADD COLUMN {column_name} {column_definition}"
                )
        audit_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        if "key_id" not in audit_columns:
            connection.execute("ALTER TABLE audit_log ADD COLUMN key_id TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_key
            ON audit_log (key_id, ts DESC, id DESC)
            """
        )

        def normalize_payload_json(payload_json: str) -> str | None:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                return None

            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                return None

            guardrail_metrics = metrics.get("guardrail_metrics")
            if not isinstance(guardrail_metrics, list):
                return None

            normalized_guardrails = []
            changed = False
            for item in guardrail_metrics:
                if item == "payment_error_rate":
                    normalized_guardrails.append(
                        {
                            "name": "Payment error rate",
                            "metric_type": "binary",
                            "baseline_rate": 2.4,
                        }
                    )
                    changed = True
                else:
                    normalized_guardrails.append(item)

            if not changed:
                return None

            normalized_metrics = dict(metrics)
            normalized_metrics["guardrail_metrics"] = normalized_guardrails
            normalized_payload = dict(payload)
            normalized_payload["metrics"] = normalized_metrics
            return json.dumps(normalized_payload)

        ProjectRepository._create_history_tables(connection)
        ProjectRepository._create_audit_tables(connection)
        ProjectRepository._create_api_key_tables(connection)
        ProjectRepository._create_template_tables(connection)
        for table_name in ("projects", "project_revisions"):
            rows = connection.execute(
                f"SELECT id, payload_json FROM {table_name}"
            ).fetchall()
            for row in rows:
                normalized_payload_json = normalize_payload_json(row["payload_json"])
                if normalized_payload_json is not None:
                    connection.execute(
                        f"UPDATE {table_name} SET payload_json = ? WHERE id = ?",
                        (normalized_payload_json, row["id"]),
                    )
        ProjectRepository._backfill_analysis_runs(connection)
        ProjectRepository._backfill_project_revisions(connection)

    @staticmethod
    def _flatten_payload(value: Any, *, prefix: str = "") -> dict[str, Any]:
        if isinstance(value, dict):
            flattened: dict[str, Any] = {}
            for key in sorted(value.keys()):
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                flattened.update(ProjectRepository._flatten_payload(value[key], prefix=child_prefix))
            return flattened
        if isinstance(value, list):
            return {prefix: value}
        return {prefix: value}

    @staticmethod
    def build_payload_diff(previous_payload: dict[str, Any], next_payload: dict[str, Any]) -> dict[str, list[Any]]:
        previous = ProjectRepository._flatten_payload(previous_payload)
        current = ProjectRepository._flatten_payload(next_payload)
        changed_keys = sorted(set(previous.keys()) | set(current.keys()))
        diff: dict[str, list[Any]] = {}
        for key in changed_keys:
            if previous.get(key) != current.get(key):
                diff[key] = [previous.get(key), current.get(key)]
        return diff

    @staticmethod
    def _backfill_analysis_runs(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, last_analysis_json, last_analysis_at, last_analysis_run_id
            FROM projects
            WHERE last_analysis_json IS NOT NULL AND last_analysis_json != ''
            """
        ).fetchall()

        for row in rows:
            existing_run = connection.execute(
                """
                SELECT id
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if existing_run is None:
                run_id = row["last_analysis_run_id"] or str(uuid.uuid4())
                created_at = row["last_analysis_at"] or datetime.now(timezone.utc).isoformat()
                connection.execute(
                    """
                    INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, row["id"], row["last_analysis_json"], created_at),
                )
                connection.execute(
                    "UPDATE projects SET last_analysis_run_id = ? WHERE id = ?",
                    (run_id, row["id"]),
                )
            elif row["last_analysis_run_id"] is None:
                connection.execute(
                    "UPDATE projects SET last_analysis_run_id = ? WHERE id = ?",
                    (existing_run["id"], row["id"]),
                )

    @staticmethod
    def _backfill_project_revisions(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, payload_json, created_at
            FROM projects
            WHERE id NOT IN (
                SELECT project_id
                FROM project_revisions
            )
            """
        ).fetchall()

        for row in rows:
            connection.execute(
                """
                INSERT INTO project_revisions (id, project_id, payload_json, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["id"],
                    row["payload_json"],
                    "create",
                    row["created_at"],
                ),
            )

    @staticmethod
    def _build_analysis_summary(analysis_payload: dict) -> dict:
        calculations = analysis_payload.get("calculations", {})
        calculation_summary = calculations.get("calculation_summary", {})
        results = calculations.get("results", {})
        warnings = calculations.get("warnings", [])
        advice = analysis_payload.get("advice", {})

        return {
            "metric_type": calculation_summary.get("metric_type"),
            "sample_size_per_variant": results.get("sample_size_per_variant"),
            "total_sample_size": results.get("total_sample_size"),
            "estimated_duration_days": results.get("estimated_duration_days"),
            "warnings_count": len(warnings) if isinstance(warnings, list) else 0,
            "advice_available": bool(advice.get("available")),
        }

    @classmethod
    def _analysis_row_to_record(cls, row: sqlite3.Row) -> dict:
        analysis = json.loads(row["analysis_json"])
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "created_at": row["created_at"],
            "summary": cls._build_analysis_summary(analysis),
            "analysis": analysis,
        }

    @staticmethod
    def _analysis_row_to_workspace_record(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "created_at": row["created_at"],
            "analysis": json.loads(row["analysis_json"]),
        }

    @staticmethod
    def _export_row_to_record(row: sqlite3.Row) -> dict:
        return dict(row)

    @staticmethod
    def _revision_row_to_record(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "source": row["source"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }

    @staticmethod
    def _api_key_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
            "revoked_at": row["revoked_at"],
            "rate_limit_requests": row["rate_limit_requests"],
            "rate_limit_window_seconds": row["rate_limit_window_seconds"],
        }

    @staticmethod
    def build_api_key_hash(plaintext_key: str) -> str:
        return hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()

    @classmethod
    def _project_row_to_workspace_record(cls, row: sqlite3.Row) -> dict:
        project = cls._row_to_project(row)
        project.pop("revision_count", None)
        project.pop("last_revision_at", None)
        project.pop("has_analysis_snapshot", None)
        project.pop("is_archived", None)
        return project

    @staticmethod
    def _project_list_row_to_record(row: sqlite3.Row) -> dict:
        project = dict(row)
        project["has_analysis_snapshot"] = bool(project.get("has_analysis_snapshot"))
        project["is_archived"] = bool(project.get("is_archived"))
        return project

    @staticmethod
    def _create_revision(
        connection: sqlite3.Connection,
        project_id: str,
        payload: dict,
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
        return connection.execute(
            f"""
            SELECT {self.project_select_columns}
            FROM projects
            WHERE id = ? {archived_clause}
            """,
            (project_id,),
        ).fetchone()

    @staticmethod
    def _normalize_history_limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    @staticmethod
    def _normalize_history_offset(offset: int) -> int:
        return max(0, int(offset))

    def list_projects(self, *, include_archived: bool = False) -> list[dict]:
        archived_filter = "" if include_archived else "WHERE projects.archived_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement') AS hypothesis,
                    json_extract(projects.payload_json, '$.metrics.metric_type') AS metric_type,
                    CAST(
                        json_extract(
                            (
                                SELECT analysis_json
                                FROM analysis_runs
                                WHERE analysis_runs.project_id = projects.id
                                ORDER BY created_at DESC, id DESC
                                LIMIT 1
                            ),
                            '$.report.calculations.estimated_duration_days'
                        ) AS INTEGER
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
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
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {archived_filter}
                ORDER BY projects.updated_at DESC
                """
            ).fetchall()
        return [self._project_list_row_to_record(row) for row in rows]

    def query_projects(
        self,
        *,
        q: str | None = None,
        status: str = "active",
        metric_type: str = "all",
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        normalized_query = q.strip().lower() if isinstance(q, str) else ""
        normalized_status = status if status in {"active", "archived", "all"} else "active"
        normalized_metric_type = metric_type if metric_type in {"binary", "continuous", "all"} else "all"
        normalized_sort_by = sort_by if sort_by in {"created_at", "updated_at", "name", "duration_days"} else "updated_at"
        normalized_sort_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        where_clauses: list[str] = []
        params: list[object] = []

        if normalized_status == "active":
            where_clauses.append("projects.archived_at IS NULL")
        elif normalized_status == "archived":
            where_clauses.append("projects.archived_at IS NOT NULL")

        if normalized_metric_type != "all":
            where_clauses.append("json_extract(projects.payload_json, '$.metrics.metric_type') = ?")
            params.append(normalized_metric_type)

        if normalized_query:
            like_pattern = f"%{normalized_query}%"
            where_clauses.append(
                """
                (
                    lower(projects.project_name) LIKE ?
                    OR lower(COALESCE(json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement'), '')) LIKE ?
                    OR lower(COALESCE(json_extract(projects.payload_json, '$.hypothesis.change_description'), '')) LIKE ?
                )
                """
            )
            params.extend([like_pattern, like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        if normalized_sort_by == "name":
            order_sql = f"ORDER BY lower(projects.project_name) {normalized_sort_dir}, projects.updated_at DESC"
        elif normalized_sort_by == "duration_days":
            order_sql = f"ORDER BY duration_days IS NULL, duration_days {normalized_sort_dir}, projects.updated_at DESC"
        else:
            order_column = "projects.created_at" if normalized_sort_by == "created_at" else "projects.updated_at"
            order_sql = f"ORDER BY {order_column} {normalized_sort_dir}, projects.id DESC"

        with self._connect() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM projects
                {where_sql}
                """,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT
                    projects.id,
                    projects.project_name,
                    json_extract(projects.payload_json, '$.hypothesis.hypothesis_statement') AS hypothesis,
                    json_extract(projects.payload_json, '$.metrics.metric_type') AS metric_type,
                    CAST(
                        json_extract(
                            (
                                SELECT analysis_json
                                FROM analysis_runs
                                WHERE analysis_runs.project_id = projects.id
                                ORDER BY created_at DESC, id DESC
                                LIMIT 1
                            ),
                            '$.report.calculations.estimated_duration_days'
                        ) AS INTEGER
                    ) AS duration_days,
                    projects.payload_schema_version,
                    projects.archived_at,
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
                    projects.last_analysis_at,
                    projects.last_analysis_run_id,
                    projects.last_exported_at,
                    CASE WHEN projects.last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    CASE WHEN projects.archived_at IS NOT NULL THEN 1 ELSE 0 END AS is_archived,
                    projects.created_at,
                    projects.updated_at
                FROM projects
                {where_sql}
                {order_sql}
                LIMIT ?
                OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "projects": [self._project_list_row_to_record(row) for row in rows],
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < int(total),
        }

    def create_project(self, payload: dict) -> dict:
        project_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id,
                    project_name,
                    payload_json,
                    payload_schema_version,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    project_name,
                    json.dumps(payload),
                    self.payload_schema_version,
                    timestamp,
                    timestamp,
                ),
            )
            self._create_revision(connection, project_id, payload, "create", timestamp)

        return self.get_project(project_id, include_archived=True)

    def get_project(self, project_id: str, *, include_archived: bool = False) -> dict | None:
        with self._connect() as connection:
            row = self._get_project_row(connection, project_id, include_archived=include_archived)

        if row is None:
            return None

        return self._row_to_project(row)

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

    def update_project(self, project_id: str, payload: dict) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)
            cursor = connection.execute(
                """
                UPDATE projects
                SET project_name = ?, payload_json = ?, payload_schema_version = ?, updated_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (
                    project_name,
                    json.dumps(payload),
                    self.payload_schema_version,
                    timestamp,
                    project_id,
                ),
            )
            if cursor.rowcount > 0:
                self._create_revision(connection, project_id, payload, "update", timestamp)

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    def record_analysis(self, project_id: str, analysis_payload: dict) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        analysis_run_id = str(uuid.uuid4())

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)

            connection.execute(
                """
                INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (analysis_run_id, project_id, json.dumps(analysis_payload), timestamp),
            )
            cursor = connection.execute(
                """
                UPDATE projects
                SET last_analysis_at = ?, last_analysis_run_id = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (timestamp, analysis_run_id, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    def record_export(self, project_id: str, export_format: str, analysis_run_id: str | None = None) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        export_event_id = str(uuid.uuid4())

        with self._connect() as connection:
            self._ensure_project_active(connection, project_id)

            if analysis_run_id is not None:
                linked_run = connection.execute(
                    """
                    SELECT 1
                    FROM analysis_runs
                    WHERE id = ? AND project_id = ?
                    """,
                    (analysis_run_id, project_id),
                ).fetchone()
                if linked_run is None:
                    raise ApiError(
                        "Analysis run not found for project",
                        error_code="analysis_run_not_found",
                    )

            connection.execute(
                """
                INSERT INTO export_events (id, project_id, analysis_run_id, format, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (export_event_id, project_id, analysis_run_id, export_format, timestamp),
            )
            cursor = connection.execute(
                """
                UPDATE projects
                SET last_exported_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id, include_archived=True)

    @staticmethod
    def _template_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "description": row["description"],
            "built_in": bool(row["built_in"]),
            "tags": json.loads(row["tags_json"]),
            "payload": json.loads(row["payload_json"]),
            "usage_count": int(row["usage_count"]),
        }

    def upsert_template(
        self,
        *,
        template_id: str,
        name: str,
        category: str,
        description: str,
        built_in: bool,
        tags: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO project_templates (
                    id,
                    name,
                    category,
                    description,
                    built_in,
                    tags_json,
                    payload_json,
                    usage_count,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    built_in = excluded.built_in,
                    tags_json = excluded.tags_json,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    template_id,
                    name,
                    category,
                    description,
                    1 if built_in else 0,
                    json.dumps(tags),
                    json.dumps(payload),
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()

        return self._template_row_to_record(row)

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                ORDER BY built_in DESC, usage_count DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._template_row_to_record(row) for row in rows]

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()
        return self._template_row_to_record(row) if row is not None else None

    def create_template(
        self,
        *,
        name: str,
        category: str,
        description: str,
        tags: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.upsert_template(
            template_id=str(uuid.uuid4()),
            name=name,
            category=category,
            description=description,
            built_in=False,
            tags=tags,
            payload=payload,
        )

    def use_template(self, template_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE project_templates
                SET usage_count = usage_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, template_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                WHERE id = ?
                """,
                (template_id,),
            ).fetchone()
        return self._template_row_to_record(row) if row is not None else None

    def delete_template(self, template_id: str) -> dict[str, Any] | None:
        existing = self.get_template(template_id)
        if existing is None:
            return None
        if existing["built_in"]:
            raise ApiError(
                "Built-in templates cannot be deleted",
                error_code="template_delete_forbidden",
                status_code=403,
            )
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM project_templates WHERE id = ?",
                (template_id,),
            )
        return {
            "id": template_id,
            "deleted": True,
        }

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
        scopes = scope_filters.get(scope, None)
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
        key_hash = self.build_api_key_hash(plaintext_key)
        created_at = datetime.now(timezone.utc).isoformat()

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

        keys = [self._api_key_row_to_record(row) for row in rows]
        return {
            "keys": keys,
            "total": len(keys),
        }

    def revoke_api_key(self, api_key_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(timezone.utc).isoformat()
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

        return self._api_key_row_to_record(row) if row is not None else None

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
        key_hash = self.build_api_key_hash(plaintext_key)
        last_used_at = datetime.now(timezone.utc).isoformat()
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

        return self._api_key_row_to_record(row) if row is not None else None

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
    ) -> None:
        timestamp = ts or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
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
            entry = dict(row)
            payload_diff_json = entry.get("payload_diff")
            entry["payload_diff"] = json.loads(payload_diff_json) if payload_diff_json else None
            entries.append(entry)
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

    def get_project_history(
        self,
        project_id: str,
        *,
        analysis_limit: int = 20,
        analysis_offset: int = 0,
        export_limit: int = 20,
        export_offset: int = 0,
    ) -> dict | None:
        analysis_limit = self._normalize_history_limit(analysis_limit)
        analysis_offset = self._normalize_history_offset(analysis_offset)
        export_limit = self._normalize_history_limit(export_limit)
        export_offset = self._normalize_history_offset(export_offset)

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

            analysis_total = connection.execute(
                """
                SELECT COUNT(*)
                FROM analysis_runs
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            export_total = connection.execute(
                """
                SELECT COUNT(*)
                FROM export_events
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            analysis_rows = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, analysis_limit, analysis_offset),
            ).fetchall()
            export_rows = connection.execute(
                """
                SELECT id, project_id, analysis_run_id, format, created_at
                FROM export_events
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, export_limit, export_offset),
            ).fetchall()

        return {
            "project_id": project_id,
            "analysis_total": analysis_total,
            "analysis_limit": analysis_limit,
            "analysis_offset": analysis_offset,
            "export_total": export_total,
            "export_limit": export_limit,
            "export_offset": export_offset,
            "analysis_runs": [self._analysis_row_to_record(row) for row in analysis_rows],
            "export_events": [self._export_row_to_record(row) for row in export_rows],
        }

    def get_project_revisions(
        self,
        project_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict | None:
        limit = self._normalize_history_limit(limit)
        offset = self._normalize_history_offset(offset)

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

            total = connection.execute(
                """
                SELECT COUNT(*)
                FROM project_revisions
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            revision_rows = connection.execute(
                """
                SELECT id, project_id, payload_json, source, created_at
                FROM project_revisions
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                OFFSET ?
                """,
                (project_id, limit, offset),
            ).fetchall()

        return {
            "project_id": project_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "revisions": [self._revision_row_to_record(row) for row in revision_rows],
        }

    def get_analysis_run(self, project_id: str, analysis_run_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, analysis_run_id),
            ).fetchone()

        if row is None:
            return None

        return self._analysis_row_to_record(row)

    def get_latest_analysis_run(self, project_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

        if row is None:
            return None

        return self._analysis_row_to_record(row)

    def get_diagnostics_summary(self) -> dict:
        disk_free_bytes = shutil.disk_usage(self.db_path.parent).free
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        write_probe_ok, write_probe_detail = self._run_write_probe()

        with self._connect() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous_raw = connection.execute("PRAGMA synchronous").fetchone()[0]
            sqlite_user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NULL"
            ).fetchone()[0]
            archived_projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects WHERE archived_at IS NOT NULL"
            ).fetchone()[0]
            analysis_runs_total = connection.execute(
                "SELECT COUNT(*) FROM analysis_runs"
            ).fetchone()[0]
            export_events_total = connection.execute(
                "SELECT COUNT(*) FROM export_events"
            ).fetchone()[0]
            project_revisions_total = connection.execute(
                "SELECT COUNT(*) FROM project_revisions"
            ).fetchone()[0]
            latest_project_updated_at_row = connection.execute(
                "SELECT MAX(updated_at) AS updated_at FROM projects"
            ).fetchone()

        synchronous_labels = {
            0: "OFF",
            1: "NORMAL",
            2: "FULL",
            3: "EXTRA",
        }
        synchronous = synchronous_labels.get(synchronous_raw, str(synchronous_raw))

        return {
            "db_path": str(self.db_path),
            "db_parent_path": str(self.db_path.parent),
            "db_exists": self.db_path.exists(),
            "db_size_bytes": db_size_bytes,
            "disk_free_bytes": disk_free_bytes,
            "schema_version": self.schema_version,
            "sqlite_user_version": sqlite_user_version,
            "busy_timeout_ms": self.busy_timeout_ms,
            "journal_mode": str(journal_mode).upper(),
            "synchronous": synchronous,
            "write_probe_ok": write_probe_ok,
            "write_probe_detail": write_probe_detail,
            "projects_total": projects_total,
            "archived_projects_total": archived_projects_total,
            "analysis_runs_total": analysis_runs_total,
            "export_events_total": export_events_total,
            "project_revisions_total": project_revisions_total,
            "workspace_bundle_schema_version": self.workspace_schema_version,
            "workspace_signature_enabled": self.workspace_signing_key is not None,
            "latest_project_updated_at": (
                latest_project_updated_at_row["updated_at"]
                if latest_project_updated_at_row is not None
                else None
            ),
        }

    def _run_write_probe(self) -> tuple[bool, str]:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
            return True, "BEGIN IMMEDIATE succeeded"
        except sqlite3.Error as exc:
            return False, str(exc)

    def export_workspace(self) -> dict:
        with self._connect() as connection:
            project_rows = connection.execute(
                f"""
                SELECT {self.project_select_columns}
                FROM projects
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            analysis_rows = connection.execute(
                """
                SELECT id, project_id, analysis_json, created_at
                FROM analysis_runs
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            export_rows = connection.execute(
                """
                SELECT id, project_id, analysis_run_id, format, created_at
                FROM export_events
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            revision_rows = connection.execute(
                """
                SELECT id, project_id, payload_json, source, created_at
                FROM project_revisions
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()

        bundle = {
            "schema_version": self.workspace_schema_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "projects": [self._project_row_to_workspace_record(row) for row in project_rows],
            "analysis_runs": [self._analysis_row_to_workspace_record(row) for row in analysis_rows],
            "export_events": [self._export_row_to_record(row) for row in export_rows],
            "project_revisions": [self._revision_row_to_record(row) for row in revision_rows],
        }
        bundle["integrity"] = self._build_workspace_integrity(bundle)
        return bundle

    @classmethod
    def _workspace_integrity_source(cls, bundle: dict) -> dict:
        def normalize_project_payload(payload: object) -> object:
            if not isinstance(payload, dict):
                return payload
            try:
                return ExperimentInput.model_validate(payload).model_dump()
            except ValidationError:
                return payload

        def normalize_workspace_project(record: object) -> object:
            if not isinstance(record, dict):
                return record
            normalized_record = dict(record)
            normalized_record["payload"] = normalize_project_payload(normalized_record.get("payload"))
            return normalized_record

        return {
            "schema_version": bundle.get("schema_version"),
            "generated_at": bundle.get("generated_at"),
            "projects": [normalize_workspace_project(project) for project in bundle.get("projects", [])],
            "analysis_runs": bundle.get("analysis_runs", []),
            "export_events": bundle.get("export_events", []),
            "project_revisions": [
                normalize_workspace_project(revision) for revision in bundle.get("project_revisions", [])
            ],
        }

    @classmethod
    def _workspace_counts(cls, bundle: dict) -> dict[str, int]:
        source = cls._workspace_integrity_source(bundle)
        return {
            "projects": len(source["projects"]),
            "analysis_runs": len(source["analysis_runs"]),
            "export_events": len(source["export_events"]),
            "project_revisions": len(source["project_revisions"]),
        }

    @classmethod
    def _workspace_checksum(cls, bundle: dict) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _workspace_signature(cls, bundle: dict, signing_key: str) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(signing_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _build_workspace_integrity(self, bundle: dict) -> dict:
        integrity = {
            "counts": self._workspace_counts(bundle),
            "checksum_sha256": self._workspace_checksum(bundle),
        }
        if self.workspace_signing_key:
            integrity["signature_hmac_sha256"] = self._workspace_signature(bundle, self.workspace_signing_key)
        return integrity

    def _validate_workspace_bundle(self, bundle: dict) -> bool:
        schema_version = int(bundle.get("schema_version", 1))
        if schema_version not in {1, 2, 3}:
            raise ApiError(
                "Unsupported workspace bundle schema_version",
                error_code="workspace_schema_unsupported",
            )

        integrity = bundle.get("integrity")
        if integrity is None:
            if schema_version >= 2:
                raise ApiError(
                    "Workspace bundle integrity block is required for schema_version 2 or later",
                    error_code="workspace_integrity_required",
                )
            return False

        actual_counts = self._workspace_counts(bundle)
        expected_counts = integrity.get("counts", {})
        if {
            "projects": int(expected_counts.get("projects", -1)),
            "analysis_runs": int(expected_counts.get("analysis_runs", -1)),
            "export_events": int(expected_counts.get("export_events", -1)),
            "project_revisions": int(expected_counts.get("project_revisions", -1)),
        } != actual_counts:
            raise ApiError(
                "Workspace bundle integrity counts mismatch",
                error_code="workspace_integrity_counts_mismatch",
            )

        expected_checksum = str(integrity.get("checksum_sha256") or "").strip()
        if not expected_checksum:
            raise ApiError(
                "Workspace bundle checksum is missing",
                error_code="workspace_integrity_checksum_missing",
            )
        if expected_checksum != self._workspace_checksum(bundle):
            raise ApiError(
                "Workspace bundle checksum mismatch",
                error_code="workspace_integrity_checksum_mismatch",
            )

        expected_signature = str(integrity.get("signature_hmac_sha256") or "").strip()
        if self.workspace_signing_key:
            if not expected_signature:
                raise ApiError(
                    "Workspace bundle signature is required on this runtime",
                    error_code="workspace_signature_required",
                )
            actual_signature = self._workspace_signature(bundle, self.workspace_signing_key)
            if not hmac.compare_digest(expected_signature, actual_signature):
                raise ApiError(
                    "Workspace bundle signature mismatch",
                    error_code="workspace_signature_mismatch",
                )
            signature_verified = True
        else:
            if expected_signature:
                raise ApiError(
                    "Workspace bundle signature cannot be verified on this runtime",
                    error_code="workspace_signature_verification_unavailable",
                )
            signature_verified = False

        project_ids = [str(project.get("id", "")) for project in bundle.get("projects", [])]
        analysis_run_ids = [str(run.get("id", "")) for run in bundle.get("analysis_runs", [])]
        revision_ids = [str(revision.get("id", "")) for revision in bundle.get("project_revisions", [])]
        for label, identifiers in (
            ("project", project_ids),
            ("analysis_run", analysis_run_ids),
            ("project_revision", revision_ids),
        ):
            cleaned = [identifier for identifier in identifiers if identifier]
            if len(cleaned) != len(set(cleaned)):
                raise ApiError(
                    f"Workspace bundle contains duplicate {label} ids",
                    error_code=f"workspace_duplicate_{label}_id",
                )
        return signature_verified

    def validate_workspace_bundle(self, bundle: dict) -> dict:
        signature_verified = self._validate_workspace_bundle(bundle)
        imported_projects = bundle.get("projects", [])
        imported_analysis_runs = bundle.get("analysis_runs", [])
        imported_export_events = bundle.get("export_events", [])
        imported_project_revisions = bundle.get("project_revisions", [])

        project_ids = {project["id"] for project in imported_projects}
        analysis_run_ids = {analysis_run["id"] for analysis_run in imported_analysis_runs}

        for analysis_run in imported_analysis_runs:
            if analysis_run["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in analysis_runs",
                    error_code="workspace_analysis_unknown_project",
                )

        for export_event in imported_export_events:
            if export_event["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in export_events",
                    error_code="workspace_export_unknown_project",
                )
            analysis_run_id = export_event.get("analysis_run_id")
            if analysis_run_id and analysis_run_id not in analysis_run_ids:
                raise ApiError(
                    "Workspace bundle references an unknown analysis run in export_events",
                    error_code="workspace_export_unknown_analysis_run",
                )

        for revision in imported_project_revisions:
            if revision["project_id"] not in project_ids:
                raise ApiError(
                    "Workspace bundle references an unknown project in project_revisions",
                    error_code="workspace_revision_unknown_project",
                )

        integrity = self._build_workspace_integrity(bundle)
        return {
            "status": "valid",
            "schema_version": int(bundle.get("schema_version", 1)),
            "counts": integrity["counts"],
            "checksum_sha256": integrity["checksum_sha256"],
            "signature_verified": signature_verified,
        }

    def import_workspace(self, bundle: dict) -> dict:
        self.validate_workspace_bundle(bundle)
        imported_projects = bundle.get("projects", [])
        imported_analysis_runs = bundle.get("analysis_runs", [])
        imported_export_events = bundle.get("export_events", [])
        imported_project_revisions = bundle.get("project_revisions", [])

        project_id_map = {
            project["id"]: str(uuid.uuid4())
            for project in imported_projects
        }
        analysis_run_id_map = {
            analysis_run["id"]: str(uuid.uuid4())
            for analysis_run in imported_analysis_runs
        }
        revision_id_map = {
            revision["id"]: str(uuid.uuid4())
            for revision in imported_project_revisions
        }
        projects_with_imported_revisions = {
            revision["project_id"]
            for revision in imported_project_revisions
        }
        imported_revision_count = 0

        with self._connect() as connection:
            for project in imported_projects:
                old_project_id = project["id"]
                connection.execute(
                    """
                    INSERT INTO projects (
                        id,
                        project_name,
                        payload_json,
                        payload_schema_version,
                        archived_at,
                        last_analysis_at,
                        last_analysis_run_id,
                        last_exported_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id_map[old_project_id],
                        project["project_name"],
                        json.dumps(project["payload"]),
                        int(project.get("payload_schema_version", self.payload_schema_version)),
                        project.get("archived_at"),
                        project.get("last_analysis_at"),
                        analysis_run_id_map.get(project.get("last_analysis_run_id")),
                        project.get("last_exported_at"),
                        project["created_at"],
                        project["updated_at"],
                    ),
                )
                if old_project_id not in projects_with_imported_revisions:
                    self._create_revision(
                        connection,
                        project_id_map[old_project_id],
                        project["payload"],
                        "workspace_import",
                        project.get("updated_at") or project["created_at"],
                    )
                    imported_revision_count += 1

            for analysis_run in imported_analysis_runs:
                new_project_id = project_id_map.get(analysis_run["project_id"])
                connection.execute(
                    """
                    INSERT INTO analysis_runs (id, project_id, analysis_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        analysis_run_id_map[analysis_run["id"]],
                        new_project_id,
                        json.dumps(analysis_run["analysis"]),
                        analysis_run["created_at"],
                    ),
                )

            for export_event in imported_export_events:
                new_project_id = project_id_map.get(export_event["project_id"])
                old_analysis_run_id = export_event.get("analysis_run_id")
                new_analysis_run_id = analysis_run_id_map.get(old_analysis_run_id) if old_analysis_run_id else None
                connection.execute(
                    """
                    INSERT INTO export_events (id, project_id, analysis_run_id, format, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        new_project_id,
                        new_analysis_run_id,
                        export_event["format"],
                        export_event["created_at"],
                    ),
                )

            for revision in imported_project_revisions:
                new_project_id = project_id_map.get(revision["project_id"])
                self._create_revision(
                    connection,
                    new_project_id,
                    revision["payload"],
                    revision["source"],
                    revision["created_at"],
                    revision_id=revision_id_map[revision["id"]],
                )
                imported_revision_count += 1

        return {
            "status": "imported",
            "imported_projects": len(imported_projects),
            "imported_analysis_runs": len(imported_analysis_runs),
            "imported_export_events": len(imported_export_events),
            "imported_project_revisions": imported_revision_count,
        }

    def archive_project(self, project_id: str) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                """
                UPDATE projects
                SET
                    archived_at = COALESCE(archived_at, ?),
                    updated_at = CASE WHEN archived_at IS NULL THEN ? ELSE updated_at END
                WHERE id = ?
                """,
                (timestamp, timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        archived_project = self.get_project(project_id, include_archived=True)
        if archived_project is None:
            return None

        return {
            "id": project_id,
            "archived": True,
            "archived_at": archived_project.get("archived_at"),
        }

    def delete_project(self, project_id: str) -> dict | None:
        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        if cursor.rowcount == 0:
            return None

        return {
            "id": project_id,
            "deleted": True,
        }

    def restore_project(self, project_id: str) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            if not self._project_exists(connection, project_id):
                return None
            cursor = connection.execute(
                """
                UPDATE projects
                SET archived_at = NULL, updated_at = ?
                WHERE id = ? AND archived_at IS NOT NULL
                """,
                (timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return self.get_project(project_id, include_archived=True)

        return self.get_project(project_id, include_archived=True)
