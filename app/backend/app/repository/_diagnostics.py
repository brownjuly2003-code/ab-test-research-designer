"""Operational summary surfaced by /api/v1/diagnostics."""

import shutil
from typing import Any

from app.backend.app.repository._core import _BackendCore


class _DiagnosticsMixin(_BackendCore):
    def get_diagnostics_summary(self) -> dict[str, Any]:
        disk_free_bytes = shutil.disk_usage(self.db_path.parent).free
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        write_probe_ok, write_probe_detail = self._run_write_probe()

        with self._transaction() as connection:
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
