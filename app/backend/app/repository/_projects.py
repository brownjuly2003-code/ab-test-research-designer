"""Project CRUD, listing/filtering, analysis + export bookkeeping, archive lifecycle."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.backend.app.constants import METRIC_TYPE_FILTERS
from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import project_list_row_to_record, row_to_project


class _ProjectsMixin(_BackendCore):
    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
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
        return [project_list_row_to_record(row) for row in rows]

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
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        normalized_query = q.strip().lower() if isinstance(q, str) else ""
        normalized_status = status if status in {"active", "archived", "all"} else "active"
        normalized_metric_type = metric_type if metric_type in METRIC_TYPE_FILTERS else "all"
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
            "projects": [project_list_row_to_record(row) for row in rows],
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < int(total),
        }

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
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

        # The project was just inserted in this transaction, so it always exists.
        return cast("dict[str, Any]", self.get_project(project_id, include_archived=True))

    def get_project(self, project_id: str, *, include_archived: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = self._get_project_row(connection, project_id, include_archived=include_archived)

        if row is None:
            return None

        return row_to_project(row)

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
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

    def record_analysis(self, project_id: str, analysis_payload: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
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

    def record_export(self, project_id: str, export_format: str, analysis_run_id: str | None = None) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
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

    def archive_project(self, project_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()
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

    def delete_project(self, project_id: str) -> dict[str, Any] | None:
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

    def restore_project(self, project_id: str) -> dict[str, Any] | None:
        timestamp = datetime.now(UTC).isoformat()

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

    # --- Execution layer (Phase C): exposure / conversion ingestion -----------------
