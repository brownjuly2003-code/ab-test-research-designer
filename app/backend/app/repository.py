from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from app.backend.app.errors import ApiError


class ProjectRepository:
    schema_version = 2
    payload_schema_version = 1
    workspace_schema_version = 2
    project_select_columns = """
        projects.id,
        projects.project_name,
        projects.payload_json,
        projects.payload_schema_version,
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
    ) -> None:
        self.db_path = Path(db_path)
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.journal_mode = journal_mode
        self.synchronous = synchronous
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
            self._migrate_db(connection)
            connection.execute(f"PRAGMA user_version = {self.schema_version}")

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict:
        project = dict(row)
        payload_json = project.pop("payload_json")
        project["payload"] = json.loads(payload_json)
        project["has_analysis_snapshot"] = bool(project.get("last_analysis_run_id"))
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
    def _migrate_db(connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }
        required_columns = {
            "payload_schema_version": "INTEGER NOT NULL DEFAULT 1",
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

        ProjectRepository._create_history_tables(connection)
        ProjectRepository._backfill_analysis_runs(connection)
        ProjectRepository._backfill_project_revisions(connection)

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

    @classmethod
    def _project_row_to_workspace_record(cls, row: sqlite3.Row) -> dict:
        project = cls._row_to_project(row)
        project.pop("revision_count", None)
        project.pop("last_revision_at", None)
        project.pop("has_analysis_snapshot", None)
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

    def _get_project_row(self, connection: sqlite3.Connection, project_id: str) -> sqlite3.Row | None:
        return connection.execute(
            f"""
            SELECT {self.project_select_columns}
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

    @staticmethod
    def _normalize_history_limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    @staticmethod
    def _normalize_history_offset(offset: int) -> int:
        return max(0, int(offset))

    def list_projects(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    projects.id,
                    projects.project_name,
                    projects.payload_schema_version,
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
                    projects.created_at,
                    projects.updated_at
                FROM projects
                ORDER BY projects.updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

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

        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict | None:
        with self._connect() as connection:
            row = self._get_project_row(connection, project_id)

        if row is None:
            return None

        return self._row_to_project(row)

    def update_project(self, project_id: str, payload: dict) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET project_name = ?, payload_json = ?, payload_schema_version = ?, updated_at = ?
                WHERE id = ?
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

        return self.get_project(project_id)

    def record_analysis(self, project_id: str, analysis_payload: dict) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        analysis_run_id = str(uuid.uuid4())

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

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
                WHERE id = ?
                """,
                (timestamp, analysis_run_id, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id)

    def record_export(self, project_id: str, export_format: str, analysis_run_id: str | None = None) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        export_event_id = str(uuid.uuid4())

        with self._connect() as connection:
            project_row = connection.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project_row is None:
                return None

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
                WHERE id = ?
                """,
                (timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id)

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
        with self._connect() as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            synchronous_raw = connection.execute("PRAGMA synchronous").fetchone()[0]
            sqlite_user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects"
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
            "db_exists": self.db_path.exists(),
            "schema_version": self.schema_version,
            "sqlite_user_version": sqlite_user_version,
            "busy_timeout_ms": self.busy_timeout_ms,
            "journal_mode": str(journal_mode).upper(),
            "synchronous": synchronous,
            "projects_total": projects_total,
            "analysis_runs_total": analysis_runs_total,
            "export_events_total": export_events_total,
            "project_revisions_total": project_revisions_total,
            "latest_project_updated_at": (
                latest_project_updated_at_row["updated_at"]
                if latest_project_updated_at_row is not None
                else None
            ),
        }

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
        return {
            "schema_version": bundle.get("schema_version"),
            "generated_at": bundle.get("generated_at"),
            "projects": bundle.get("projects", []),
            "analysis_runs": bundle.get("analysis_runs", []),
            "export_events": bundle.get("export_events", []),
            "project_revisions": bundle.get("project_revisions", []),
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
    def _build_workspace_integrity(cls, bundle: dict) -> dict:
        return {
            "counts": cls._workspace_counts(bundle),
            "checksum_sha256": cls._workspace_checksum(bundle),
        }

    @classmethod
    def _validate_workspace_bundle(cls, bundle: dict) -> None:
        schema_version = int(bundle.get("schema_version", 1))
        if schema_version not in {1, 2}:
            raise ApiError(
                "Unsupported workspace bundle schema_version",
                error_code="workspace_schema_unsupported",
            )

        integrity = bundle.get("integrity")
        if integrity is None:
            if schema_version >= 2:
                raise ApiError(
                    "Workspace bundle integrity block is required for schema_version 2",
                    error_code="workspace_integrity_required",
                )
            return

        actual_counts = cls._workspace_counts(bundle)
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

        expected_checksum = str(integrity.get("checksum_sha256", "")).strip()
        if not expected_checksum:
            raise ApiError(
                "Workspace bundle checksum is missing",
                error_code="workspace_integrity_checksum_missing",
            )
        if expected_checksum != cls._workspace_checksum(bundle):
            raise ApiError(
                "Workspace bundle checksum mismatch",
                error_code="workspace_integrity_checksum_mismatch",
            )

    def import_workspace(self, bundle: dict) -> dict:
        self._validate_workspace_bundle(bundle)
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
                        last_analysis_at,
                        last_analysis_run_id,
                        last_exported_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id_map[old_project_id],
                        project["project_name"],
                        json.dumps(project["payload"]),
                        int(project.get("payload_schema_version", self.payload_schema_version)),
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
                if new_project_id is None:
                    raise ApiError(
                        "Workspace bundle references an unknown project in analysis_runs",
                        error_code="workspace_analysis_unknown_project",
                    )
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
                if new_project_id is None:
                    raise ApiError(
                        "Workspace bundle references an unknown project in export_events",
                        error_code="workspace_export_unknown_project",
                    )
                old_analysis_run_id = export_event.get("analysis_run_id")
                new_analysis_run_id = analysis_run_id_map.get(old_analysis_run_id) if old_analysis_run_id else None
                if old_analysis_run_id and new_analysis_run_id is None:
                    raise ApiError(
                        "Workspace bundle references an unknown analysis run in export_events",
                        error_code="workspace_export_unknown_analysis_run",
                    )
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
                if new_project_id is None:
                    raise ApiError(
                        "Workspace bundle references an unknown project in project_revisions",
                        error_code="workspace_revision_unknown_project",
                    )
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

    def delete_project(self, project_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        return cursor.rowcount > 0
