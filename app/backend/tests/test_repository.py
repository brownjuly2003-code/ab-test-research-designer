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
    history = repository.get_project_history("legacy-project")

    assert project is not None
    assert project["payload_schema_version"] == 1
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
