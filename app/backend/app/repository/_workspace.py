"""Workspace backup bundles: export, integrity/signature, validation, import."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import ValidationError

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import (
    analysis_row_to_workspace_record,
    export_row_to_record,
    project_row_to_workspace_record,
    revision_row_to_record,
)
from app.backend.app.repository._utils import JsonParam
from app.backend.app.schemas.api import ExperimentInput


class _WorkspaceMixin(_BackendCore):
    def export_workspace(self) -> dict[str, Any]:
        with self._transaction() as connection:
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
            "generated_at": datetime.now(UTC).isoformat(),
            "projects": [project_row_to_workspace_record(row) for row in project_rows],
            "analysis_runs": [analysis_row_to_workspace_record(row) for row in analysis_rows],
            "export_events": [export_row_to_record(row) for row in export_rows],
            "project_revisions": [revision_row_to_record(row) for row in revision_rows],
        }
        bundle["integrity"] = self._build_workspace_integrity(bundle)
        return bundle

    @classmethod
    def _workspace_integrity_source(cls, bundle: dict[str, Any]) -> dict[str, Any]:
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
    def _workspace_counts(cls, bundle: dict[str, Any]) -> dict[str, int]:
        source = cls._workspace_integrity_source(bundle)
        return {
            "projects": len(source["projects"]),
            "analysis_runs": len(source["analysis_runs"]),
            "export_events": len(source["export_events"]),
            "project_revisions": len(source["project_revisions"]),
        }

    @classmethod
    def _workspace_checksum(cls, bundle: dict[str, Any]) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _workspace_signature(cls, bundle: dict[str, Any], signing_key: str) -> str:
        serialized = json.dumps(
            cls._workspace_integrity_source(bundle),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hmac.new(signing_key.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _build_workspace_integrity(self, bundle: dict[str, Any]) -> dict[str, Any]:
        integrity = {
            "counts": self._workspace_counts(bundle),
            "checksum_sha256": self._workspace_checksum(bundle),
        }
        if self.workspace_signing_key:
            integrity["signature_hmac_sha256"] = self._workspace_signature(bundle, self.workspace_signing_key)
        return integrity

    def _validate_workspace_bundle(self, bundle: dict[str, Any]) -> bool:
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

    def validate_workspace_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
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

    def import_workspace(self, bundle: dict[str, Any]) -> dict[str, Any]:
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

        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
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
                        JsonParam(project["payload"]),
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
                        JsonParam(analysis_run["analysis"]),
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
                # Revisions in a valid bundle always reference an imported project,
                # so the lookup resolves to a freshly minted project id.
                new_project_id = cast("str", project_id_map.get(revision["project_id"]))
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
