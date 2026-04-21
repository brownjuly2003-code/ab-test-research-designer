import json
from pathlib import Path
import sqlite3
import sys
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import app.backend.app.repository as repository_module
from app.backend.app.repository import ProjectRepository
from app.backend.app.errors import ApiError
from app.backend.app.schemas.api import WorkspaceBundle


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


def test_repository_migrates_api_keys_table_and_audit_key_id_column() -> None:
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
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                project_id TEXT,
                project_name TEXT,
                actor TEXT,
                request_id TEXT,
                payload_diff TEXT,
                ip_address TEXT
            )
            """
        )

    ProjectRepository(str(db_path))

    with sqlite3.connect(db_path) as connection:
        api_key_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(api_keys)").fetchall()
        }
        audit_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(audit_log)").fetchall()
        }

    assert api_key_columns == {
        "id",
        "name",
        "key_hash",
        "scope",
        "created_at",
        "last_used_at",
        "revoked_at",
        "rate_limit_requests",
        "rate_limit_window_seconds",
    }
    assert "key_id" in audit_columns


def test_repository_normalizes_legacy_guardrail_metric_strings_for_workspace_export() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    legacy_payload = {
        "project": {
            "project_name": "Legacy workspace",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "Legacy export coverage.",
        },
        "hypothesis": {
            "change_description": "Shorten checkout",
            "target_audience": "new users",
            "business_problem": "checkout abandonment",
            "hypothesis_statement": "If checkout is shorter, conversion will improve.",
            "what_to_validate": "conversion impact",
            "desired_result": "measurable uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "new users only",
            "exclusion_criteria": "internal staff",
        },
        "metrics": {
            "primary_metric_name": "purchase_conversion",
            "metric_type": "binary",
            "baseline_value": 0.042,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "secondary_metrics": ["add_to_cart_rate"],
            "guardrail_metrics": ["payment_error_rate"],
        },
        "constraints": {
            "seasonality_present": False,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "low",
            "technical_constraints": "none",
            "legal_or_ethics_constraints": "none",
            "known_risks": "none",
            "deadline_pressure": "low",
            "long_test_possible": True,
        },
        "additional_context": {
            "llm_context": "",
        },
    }

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_schema_version INTEGER NOT NULL DEFAULT 1,
                archived_at TEXT,
                last_analysis_json TEXT,
                last_analysis_at TEXT,
                last_analysis_run_id TEXT,
                last_exported_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE project_revisions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
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
                "legacy-project",
                "Legacy workspace",
                json.dumps(legacy_payload),
                1,
                "2026-04-21T05:00:00+00:00",
                "2026-04-21T05:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO project_revisions (id, project_id, payload_json, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "legacy-revision",
                "legacy-project",
                json.dumps(legacy_payload),
                "create",
                "2026-04-21T05:00:00+00:00",
            ),
        )

    repository = ProjectRepository(str(db_path))
    bundle = WorkspaceBundle.model_validate(repository.export_workspace()).model_dump()

    expected_guardrails = [
        {
            "name": "Payment error rate",
            "metric_type": "binary",
            "baseline_rate": 2.4,
            "baseline_mean": None,
            "std_dev": None,
        }
    ]
    assert bundle["projects"][0]["payload"]["metrics"]["guardrail_metrics"] == expected_guardrails
    assert bundle["project_revisions"][0]["payload"]["metrics"]["guardrail_metrics"] == expected_guardrails


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
    assert diagnostics["db_parent_path"] == str(db_path.parent)
    assert diagnostics["db_size_bytes"] >= 0
    assert diagnostics["disk_free_bytes"] > 0
    assert diagnostics["write_probe_ok"] is True
    assert diagnostics["write_probe_detail"] == "BEGIN IMMEDIATE succeeded"
    assert diagnostics["archived_projects_total"] == 0
    assert diagnostics["workspace_bundle_schema_version"] == repository.workspace_schema_version
    assert diagnostics["workspace_signature_enabled"] is False


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

    assert bundle["schema_version"] == 3
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
    assert bundle["integrity"].get("signature_hmac_sha256") is None

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


def test_repository_validates_workspace_bundle_without_importing() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(str(source_db_path))
    source_repository.create_project(
        {
            "project": {"project_name": "Validation source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()
    target_repository = ProjectRepository(str(target_db_path))

    validation = target_repository.validate_workspace_bundle(bundle)

    assert validation["status"] == "valid"
    assert validation["schema_version"] == 3
    assert validation["counts"] == {
        "projects": 1,
        "analysis_runs": 0,
        "export_events": 0,
        "project_revisions": 1,
    }
    assert len(validation["checksum_sha256"]) == 64
    assert validation["signature_verified"] is False
    assert target_repository.list_projects() == []


def test_repository_exports_and_validates_signed_workspace_bundles() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"
    signing_key = "0123456789abcdef-signed-backup"

    source_repository = ProjectRepository(
        str(source_db_path),
        workspace_signing_key=signing_key,
    )
    source_repository.create_project(
        {
            "project": {"project_name": "Signed source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()

    assert bundle["schema_version"] == 3
    assert len(bundle["integrity"]["signature_hmac_sha256"]) == 64

    target_repository = ProjectRepository(
        str(target_db_path),
        workspace_signing_key=signing_key,
    )
    validation = target_repository.validate_workspace_bundle(bundle)
    import_summary = target_repository.import_workspace(bundle)

    assert validation["signature_verified"] is True
    assert import_summary["status"] == "imported"
    assert target_repository.get_diagnostics_summary()["workspace_signature_enabled"] is True


def test_repository_rejects_unsigned_workspace_bundle_when_signing_is_required() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(str(source_db_path))
    source_repository.create_project(
        {
            "project": {"project_name": "Unsigned source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()

    target_repository = ProjectRepository(
        str(target_db_path),
        workspace_signing_key="0123456789abcdef-signed-backup",
    )

    with pytest.raises(ApiError, match="signature is required") as exc_info:
        target_repository.validate_workspace_bundle(bundle)
    assert exc_info.value.error_code == "workspace_signature_required"


def test_repository_uses_constant_time_workspace_signature_comparison(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"
    signing_key = "0123456789abcdef-signed-backup"

    source_repository = ProjectRepository(
        str(source_db_path),
        workspace_signing_key=signing_key,
    )
    source_repository.create_project(
        {
            "project": {"project_name": "Signed source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()

    compare_digest_calls: list[tuple[str, str]] = []
    original_compare_digest = repository_module.hmac.compare_digest

    def tracking_compare_digest(expected: str, actual: str) -> bool:
        compare_digest_calls.append((expected, actual))
        return original_compare_digest(expected, actual)

    monkeypatch.setattr(repository_module.hmac, "compare_digest", tracking_compare_digest)

    target_repository = ProjectRepository(
        str(target_db_path),
        workspace_signing_key=signing_key,
    )
    validation = target_repository.validate_workspace_bundle(bundle)

    assert validation["signature_verified"] is True
    assert compare_digest_calls == [
        (
            str(bundle["integrity"]["signature_hmac_sha256"]),
            target_repository._workspace_signature(bundle, signing_key),
        )
    ]


def test_repository_rejects_signed_workspace_bundle_when_verification_key_is_unavailable() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(
        str(source_db_path),
        workspace_signing_key="0123456789abcdef-signed-backup",
    )
    source_repository.create_project(
        {
            "project": {"project_name": "Signed source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()

    target_repository = ProjectRepository(str(target_db_path))

    with pytest.raises(ApiError, match="cannot be verified") as exc_info:
        target_repository.validate_workspace_bundle(bundle)
    assert exc_info.value.error_code == "workspace_signature_verification_unavailable"


def test_repository_rejects_workspace_bundle_with_duplicate_project_ids() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    source_db_path = temp_dir / f"{uuid.uuid4()}-source.sqlite3"
    target_db_path = temp_dir / f"{uuid.uuid4()}-target.sqlite3"

    source_repository = ProjectRepository(str(source_db_path))
    source_repository.create_project(
        {
            "project": {"project_name": "Duplicate source"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    bundle = source_repository.export_workspace()
    bundle["projects"].append(dict(bundle["projects"][0]))
    bundle["integrity"] = source_repository._build_workspace_integrity(bundle)
    target_repository = ProjectRepository(str(target_db_path))

    with pytest.raises(ApiError, match="duplicate project ids") as exc_info:
        target_repository.validate_workspace_bundle(bundle)
    assert exc_info.value.error_code == "workspace_duplicate_project_id"


def test_repository_archives_and_restores_projects_without_destroying_history() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    repository = ProjectRepository(str(db_path))
    project = repository.create_project(
        {
            "project": {"project_name": "Archive me"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )

    archive_result = repository.archive_project(project["id"])

    assert archive_result is not None
    assert archive_result["id"] == project["id"]
    assert archive_result["archived"] is True
    assert archive_result["archived_at"] is not None
    assert repository.get_project(project["id"]) is None
    archived_project = repository.get_project(project["id"], include_archived=True)
    assert archived_project is not None
    assert archived_project["is_archived"] is True
    assert repository.list_projects() == []
    archived_projects = repository.list_projects(include_archived=True)
    assert len(archived_projects) == 1
    assert archived_projects[0]["is_archived"] is True
    diagnostics = repository.get_diagnostics_summary()
    assert diagnostics["projects_total"] == 0
    assert diagnostics["archived_projects_total"] == 1

    with pytest.raises(ApiError, match="Project is archived") as exc_info:
        repository.update_project(
            project["id"],
            {
                "project": {"project_name": "Archived update"},
                "hypothesis": {},
                "setup": {},
                "metrics": {},
                "constraints": {},
                "additional_context": {},
            },
        )
    assert exc_info.value.error_code == "project_archived"

    restored_project = repository.restore_project(project["id"])

    assert restored_project is not None
    assert restored_project["archived_at"] is None
    assert restored_project["is_archived"] is False
    assert len(repository.list_projects()) == 1


def test_repository_hard_deletes_project_and_cascades_history() -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    repository = ProjectRepository(str(db_path))
    project = repository.create_project(
        {
            "project": {"project_name": "Delete me"},
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
            "report": {"executive_summary": "Summary"},
            "advice": {"available": False},
        },
    )
    repository.record_export(project["id"], "markdown")

    delete_result = repository.delete_project(project["id"])

    assert delete_result == {
        "id": project["id"],
        "deleted": True,
    }
    assert repository.get_project(project["id"], include_archived=True) is None
    assert repository.get_project_history(project["id"]) is None
    assert repository.get_project_revisions(project["id"]) is None
