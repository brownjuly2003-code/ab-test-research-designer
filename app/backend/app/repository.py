from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


class ProjectRepository:
    payload_schema_version = 1
    project_select_columns = """
        id,
        project_name,
        payload_json,
        payload_schema_version,
        last_analysis_at,
        last_analysis_run_id,
        last_exported_at,
        created_at,
        updated_at
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
    def _export_row_to_record(row: sqlite3.Row) -> dict:
        return dict(row)

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
                    id,
                    project_name,
                    payload_schema_version,
                    last_analysis_at,
                    last_analysis_run_id,
                    last_exported_at,
                    CASE WHEN last_analysis_run_id IS NOT NULL THEN 1 ELSE 0 END AS has_analysis_snapshot,
                    created_at,
                    updated_at
                FROM projects
                ORDER BY updated_at DESC
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
                    raise ValueError("Analysis run not found for project")

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
            projects_total = connection.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0]
            analysis_runs_total = connection.execute(
                "SELECT COUNT(*) FROM analysis_runs"
            ).fetchone()[0]
            export_events_total = connection.execute(
                "SELECT COUNT(*) FROM export_events"
            ).fetchone()[0]
            latest_project_updated_at_row = connection.execute(
                "SELECT MAX(updated_at) AS updated_at FROM projects"
            ).fetchone()

        return {
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "projects_total": projects_total,
            "analysis_runs_total": analysis_runs_total,
            "export_events_total": export_events_total,
            "latest_project_updated_at": (
                latest_project_updated_at_row["updated_at"]
                if latest_project_updated_at_row is not None
                else None
            ),
        }

    def delete_project(self, project_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        return cursor.rowcount > 0
