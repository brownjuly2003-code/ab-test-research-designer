from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


class ProjectRepository:
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list_projects(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, project_name, created_at, updated_at FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_project(self, payload: dict) -> dict:
        project_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, project_name, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, project_name, json.dumps(payload), timestamp, timestamp),
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

        project = dict(row)
        project["payload"] = json.loads(project.pop("payload_json"))
        return project

    def update_project(self, project_id: str, payload: dict) -> dict | None:
        timestamp = datetime.now(timezone.utc).isoformat()
        project_name = payload["project"]["project_name"]

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET project_name = ?, payload_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (project_name, json.dumps(payload), timestamp, project_id),
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
