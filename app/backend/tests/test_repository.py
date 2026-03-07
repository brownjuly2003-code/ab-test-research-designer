from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository


def test_repository_migrates_legacy_projects_table() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects (id, project_name, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-project",
                "Legacy checkout",
                '{"project":{"project_name":"Legacy checkout"}}',
                "2026-03-07T10:00:00+00:00",
                "2026-03-07T10:00:00+00:00",
            ),
        )

    repository = ProjectRepository(str(db_path))
    project = repository.get_project("legacy-project")

    assert project is not None
    assert project["payload_schema_version"] == 1
    assert project["last_analysis_at"] is None
    assert project["last_exported_at"] is None
    assert project["has_analysis_snapshot"] is False


def test_repository_records_analysis_and_export_metadata() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    repository = ProjectRepository(str(db_path))
    project = repository.create_project(
        {
            "project": {"project_name": "Checkout redesign"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )

    recorded_analysis = repository.record_analysis(
        project["id"],
        {"calculations": {"results": {"sample_size_per_variant": 100}}},
    )
    recorded_export = repository.record_export(project["id"])

    assert recorded_analysis is not None
    assert recorded_analysis["has_analysis_snapshot"] is True
    assert recorded_analysis["last_analysis_at"] is not None

    assert recorded_export is not None
    assert recorded_export["last_exported_at"] is not None
