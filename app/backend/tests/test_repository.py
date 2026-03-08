from pathlib import Path
import sqlite3
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository
from app.backend.app.errors import ApiError


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
    history = repository.get_project_history("legacy-project")

    assert project is not None
    assert project["payload_schema_version"] == 1
    assert project["revision_count"] == 1
    assert project["last_revision_at"] == "2026-03-07T10:00:00+00:00"
    assert project["last_analysis_at"] is None
    assert project["last_exported_at"] is None
    assert project["has_analysis_snapshot"] is False
    assert history is not None
    assert history["analysis_runs"] == []
    assert history["export_events"] == []


def test_repository_backfills_legacy_analysis_snapshot_into_history() -> None:
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
                last_analysis_json TEXT,
                last_analysis_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects (
                id,
                project_name,
                payload_json,
                last_analysis_json,
                last_analysis_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-project",
                "Legacy checkout",
                '{"project":{"project_name":"Legacy checkout"}}',
                '{"calculations":{"calculation_summary":{"metric_type":"binary"},"results":{"sample_size_per_variant":100,"total_sample_size":200,"estimated_duration_days":10},"warnings":[]},"report":{"executive_summary":"summary","calculations":{"sample_size_per_variant":100,"total_sample_size":200,"estimated_duration_days":10,"assumptions":[]},"experiment_design":{"variants":[{"name":"A","description":"current"}],"randomization_unit":"user","traffic_split":[50,50],"target_audience":"new users","inclusion_criteria":"new users","exclusion_criteria":"staff","recommended_duration_days":10,"stopping_conditions":["planned duration reached"]},"metrics_plan":{"primary":["purchase_conversion"],"secondary":[],"guardrail":[],"diagnostic":[]},"risks":{"statistical":[],"product":[],"technical":[],"operational":[]},"recommendations":{"before_launch":[],"during_test":[],"after_test":[]},"open_questions":[]},"advice":{"available":false,"provider":"local_orchestrator","model":"offline","advice":null,"raw_text":null,"error":"offline","error_code":"request_error"}}',
                "2026-03-07T10:30:00+00:00",
                "2026-03-07T10:00:00+00:00",
                "2026-03-07T10:00:00+00:00",
            ),
        )

    repository = ProjectRepository(str(db_path))
    project = repository.get_project("legacy-project")
    history = repository.get_project_history("legacy-project")

    assert project is not None
    assert project["last_analysis_run_id"] is not None
    assert project["has_analysis_snapshot"] is True
    assert history is not None
    assert len(history["analysis_runs"]) == 1
    assert history["analysis_runs"][0]["summary"]["metric_type"] == "binary"
    assert history["analysis_runs"][0]["summary"]["sample_size_per_variant"] == 100


def test_repository_records_analysis_and_export_history() -> None:
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
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 100,
                    "total_sample_size": 200,
                    "estimated_duration_days": 10,
                },
                "warnings": [{"code": "LONG_DURATION"}],
            },
            "report": {"executive_summary": "Summary"},
            "advice": {"available": False},
        },
    )
    recorded_export = repository.record_export(project["id"], "markdown")
    history = repository.get_project_history(project["id"])

    assert recorded_analysis is not None
    assert recorded_analysis["has_analysis_snapshot"] is True
    assert recorded_analysis["last_analysis_at"] is not None
    assert recorded_analysis["last_analysis_run_id"] is not None
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT last_analysis_json, last_analysis_run_id FROM projects WHERE id = ?",
            (project["id"],),
        ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] == recorded_analysis["last_analysis_run_id"]

    assert recorded_export is not None
    assert recorded_export["last_exported_at"] is not None
    assert history is not None
    assert history["analysis_total"] == 1
    assert history["analysis_limit"] == 20
    assert history["analysis_offset"] == 0
    assert history["export_total"] == 1
    assert history["export_limit"] == 20
    assert history["export_offset"] == 0
    assert len(history["analysis_runs"]) == 1
    assert len(history["export_events"]) == 1
    assert history["analysis_runs"][0]["summary"]["warnings_count"] == 1
    assert history["export_events"][0]["format"] == "markdown"
    assert history["export_events"][0]["analysis_run_id"] is None


def test_repository_records_project_revisions_for_create_update_and_history() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    repository = ProjectRepository(str(db_path))
    project = repository.create_project(
        {
            "project": {"project_name": "Checkout redesign"},
            "hypothesis": {"change_description": "Simplify flow"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        }
    )

    updated_project = repository.update_project(
        project["id"],
        {
            "project": {"project_name": "Checkout redesign v2"},
            "hypothesis": {"change_description": "Simplify flow further"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        },
    )
    revisions = repository.get_project_revisions(project["id"], limit=10, offset=0)

    assert updated_project is not None
    assert updated_project["revision_count"] == 2
    assert updated_project["last_revision_at"] is not None
    assert revisions is not None
    assert revisions["project_id"] == project["id"]
    assert revisions["total"] == 2
    assert revisions["limit"] == 10
    assert revisions["offset"] == 0
    assert revisions["revisions"][0]["source"] == "update"
    assert revisions["revisions"][0]["payload"]["project"]["project_name"] == "Checkout redesign v2"
    assert revisions["revisions"][1]["source"] == "create"
    assert revisions["revisions"][1]["payload"]["project"]["project_name"] == "Checkout redesign"


def test_repository_reports_sqlite_runtime_and_schema_metadata() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    repository = ProjectRepository(
        str(db_path),
        busy_timeout_ms=7000,
        journal_mode="WAL",
        synchronous="NORMAL",
    )

    diagnostics = repository.get_diagnostics_summary()

    assert diagnostics["schema_version"] == repository.schema_version
    assert diagnostics["sqlite_user_version"] == repository.schema_version
    assert diagnostics["busy_timeout_ms"] == 7000
    assert diagnostics["journal_mode"] == "WAL"
    assert diagnostics["synchronous"] == "NORMAL"


def test_repository_returns_latest_and_specific_analysis_runs_and_clamps_history_limits() -> None:
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

    repository.record_analysis(
        project["id"],
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 100,
                    "total_sample_size": 200,
                    "estimated_duration_days": 10,
                },
                "warnings": [],
            },
            "report": {"executive_summary": "First summary"},
            "advice": {"available": False},
        },
    )
    second_record = repository.record_analysis(
        project["id"],
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 120,
                    "total_sample_size": 240,
                    "estimated_duration_days": 12,
                },
                "warnings": [{"code": "LOW_TRAFFIC"}],
            },
            "report": {"executive_summary": "Second summary"},
            "advice": {"available": True},
        },
    )
    third_record = repository.record_analysis(
        project["id"],
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 140,
                    "total_sample_size": 280,
                    "estimated_duration_days": 14,
                },
                "warnings": [{"code": "LONG_DURATION"}],
            },
            "report": {"executive_summary": "Third summary"},
            "advice": {"available": True},
        },
    )

    latest_run = repository.get_latest_analysis_run(project["id"])
    specific_run = repository.get_analysis_run(project["id"], second_record["last_analysis_run_id"])
    history = repository.get_project_history(
        project["id"],
        analysis_limit=1,
        analysis_offset=1,
        export_limit=0,
        export_offset=-5,
    )

    assert second_record is not None
    assert third_record is not None
    assert latest_run is not None
    assert latest_run["id"] == third_record["last_analysis_run_id"]
    assert latest_run["analysis"]["report"]["executive_summary"] == "Third summary"
    assert specific_run is not None
    assert specific_run["id"] == second_record["last_analysis_run_id"]
    assert specific_run["analysis"]["report"]["executive_summary"] == "Second summary"
    assert history is not None
    assert history["analysis_total"] == 3
    assert history["analysis_limit"] == 1
    assert history["analysis_offset"] == 1
    assert history["export_total"] == 0
    assert history["export_limit"] == 1
    assert history["export_offset"] == 0
    assert len(history["analysis_runs"]) == 1
    assert history["analysis_runs"][0]["analysis"]["report"]["executive_summary"] == "Second summary"


def test_repository_can_export_and_import_workspace_bundle() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(str(source_db_path))
    project = source_repository.create_project(
        {
            "project": {"project_name": "Checkout redesign"},
            "hypothesis": {"change_description": "Simplify flow"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        }
    )
    analyzed_project = source_repository.record_analysis(
        project["id"],
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 100,
                    "total_sample_size": 200,
                    "estimated_duration_days": 10,
                },
                "warnings": [{"code": "LONG_DURATION"}],
            },
            "report": {"executive_summary": "Summary"},
            "advice": {"available": False},
        },
    )
    assert analyzed_project is not None
    exported_project = source_repository.record_export(
        project["id"],
        "markdown",
        analyzed_project["last_analysis_run_id"],
    )
    assert exported_project is not None

    bundle = source_repository.export_workspace()

    assert bundle["schema_version"] == 2
    assert len(bundle["projects"]) == 1
    assert len(bundle["analysis_runs"]) == 1
    assert len(bundle["export_events"]) == 1
    assert len(bundle["project_revisions"]) == 1
    assert bundle["integrity"]["counts"] == {
        "projects": 1,
        "analysis_runs": 1,
        "export_events": 1,
        "project_revisions": 1,
    }
    assert len(bundle["integrity"]["checksum_sha256"]) == 64

    target_repository = ProjectRepository(str(target_db_path))
    import_summary = target_repository.import_workspace(bundle)
    imported_projects = target_repository.list_projects()

    assert import_summary == {
        "status": "imported",
        "imported_projects": 1,
        "imported_analysis_runs": 1,
        "imported_export_events": 1,
        "imported_project_revisions": 1,
    }
    assert len(imported_projects) == 1
    assert imported_projects[0]["project_name"] == "Checkout redesign"
    assert imported_projects[0]["id"] != project["id"]
    assert imported_projects[0]["revision_count"] == 1

    imported_project = target_repository.get_project(imported_projects[0]["id"])
    assert imported_project is not None
    assert imported_project["payload"]["project"]["project_name"] == "Checkout redesign"
    assert imported_project["last_analysis_run_id"] is not None

    history = target_repository.get_project_history(imported_project["id"])
    assert history is not None
    assert history["analysis_total"] == 1
    assert history["export_total"] == 1
    assert history["export_events"][0]["analysis_run_id"] == imported_project["last_analysis_run_id"]

    revisions = target_repository.get_project_revisions(imported_project["id"])
    assert revisions is not None
    assert revisions["total"] == 1
    assert revisions["revisions"][0]["source"] == "create"


def test_repository_rejects_workspace_bundle_with_invalid_checksum() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(str(source_db_path))
    source_repository.create_project(
        {
            "project": {"project_name": "Checksum source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()
    bundle["projects"][0]["project_name"] = "Tampered source"

    target_repository = ProjectRepository(str(target_db_path))

    with pytest.raises(ApiError, match="Workspace bundle checksum mismatch") as exc_info:
        target_repository.import_workspace(bundle)
    assert exc_info.value.error_code == "workspace_integrity_checksum_mismatch"
