from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


class ProjectRepository:
    payload_schema_version = 1

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
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
                    last_exported_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_db(connection)

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> dict:
        project = dict(row)
        payload_json = project.pop("payload_json")
        last_analysis_json = project.pop("last_analysis_json", None)
        project["payload"] = json.loads(payload_json)
        project["has_analysis_snapshot"] = bool(last_analysis_json)
        return project

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
            "last_exported_at": "TEXT",
        }

        for column_name, column_definition in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE projects ADD COLUMN {column_name} {column_definition}"
                )

    def list_projects(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    project_name,
                    payload_schema_version,
                    last_analysis_at,
                    last_exported_at,
                    CASE WHEN last_analysis_json IS NULL OR last_analysis_json = '' THEN 0 ELSE 1 END AS has_analysis_snapshot,
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
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()

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

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET last_analysis_json = ?, last_analysis_at = ?
                WHERE id = ?
                """,
                (json.dumps(analysis_payload), timestamp, project_id),
            )

        if cursor.rowcount == 0:
            return None

        return self.get_project(project_id)

    def record_export(self, project_id: str) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
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

    def delete_project(self, project_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        return cursor.rowcount > 0
