"""Read models over the append-only history: revisions, analysis runs, exports."""

from typing import Any

from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import (
    analysis_row_to_record,
    export_row_to_record,
    revision_row_to_record,
)


class _HistoryMixin(_BackendCore):
    def get_project_history(
        self,
        project_id: str,
        *,
        analysis_limit: int = 20,
        analysis_offset: int = 0,
        export_limit: int = 20,
        export_offset: int = 0,
    ) -> dict[str, Any] | None:
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
            "analysis_runs": [analysis_row_to_record(row) for row in analysis_rows],
            "export_events": [export_row_to_record(row) for row in export_rows],
        }

    def get_project_revisions(
        self,
        project_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any] | None:
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
            "revisions": [revision_row_to_record(row) for row in revision_rows],
        }

    def get_analysis_run(self, project_id: str, analysis_run_id: str) -> dict[str, Any] | None:
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

        return analysis_row_to_record(row)

    def get_latest_analysis_run(self, project_id: str) -> dict[str, Any] | None:
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

        return analysis_row_to_record(row)
