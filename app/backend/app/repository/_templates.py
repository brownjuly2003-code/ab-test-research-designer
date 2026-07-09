"""Experiment templates: the seeded catalogue plus user-created entries."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore
from app.backend.app.repository._rows import template_row_to_record


class _TemplatesMixin(_BackendCore):
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
        timestamp = datetime.now(UTC).isoformat()
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

        return template_row_to_record(row)

    def list_templates(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, category, description, built_in, tags_json, payload_json, usage_count
                FROM project_templates
                ORDER BY built_in DESC, usage_count DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [template_row_to_record(row) for row in rows]

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
        return template_row_to_record(row) if row is not None else None

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
        timestamp = datetime.now(UTC).isoformat()
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
        return template_row_to_record(row) if row is not None else None

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
