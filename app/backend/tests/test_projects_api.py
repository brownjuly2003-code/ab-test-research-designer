from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.main import create_app


def _payload(name: str) -> dict:
    return {
        "project": {
            "project_name": name,
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "We want to test a simplified checkout flow.",
        },
        "hypothesis": {
            "change_description": "Reduce checkout from 4 steps to 2",
            "target_audience": "new users on web",
            "business_problem": "checkout abandonment is high",
            "hypothesis_statement": "If we simplify checkout, conversion will increase.",
            "what_to_validate": "impact on conversion",
            "desired_result": "statistically meaningful uplift",
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
            "std_dev": None,
            "secondary_metrics": ["add_to_cart_rate"],
            "guardrail_metrics": ["payment_error_rate", "refund_rate"],
        },
        "constraints": {
            "seasonality_present": True,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "medium",
            "technical_constraints": "legacy event logging",
            "legal_or_ethics_constraints": "none",
            "known_risks": "tracking quality",
            "deadline_pressure": "medium",
            "long_test_possible": True,
        },
    }


def _analysis_payload(
    *,
    total_sample_size: int,
    estimated_duration_days: int,
    executive_summary: str,
    warning_codes: list[str],
) -> dict:
    return {
        "calculations": {
            "calculation_summary": {
                "metric_type": "binary",
                "baseline_value": 0.042,
                "mde_pct": 5,
                "mde_absolute": 0.0021,
                "alpha": 0.05,
                "power": 0.8,
            },
            "results": {
                "sample_size_per_variant": total_sample_size // 2,
                "total_sample_size": total_sample_size,
                "effective_daily_traffic": 5000,
                "estimated_duration_days": estimated_duration_days,
            },
            "assumptions": ["Baseline is stable"],
            "warnings": [
                {
                    "code": code,
                    "severity": "medium",
                    "message": f"{code} warning",
                    "source": "rules_engine",
                }
                for code in warning_codes
            ],
        },
        "report": {
            "executive_summary": executive_summary,
            "calculations": {
                "sample_size_per_variant": total_sample_size // 2,
                "total_sample_size": total_sample_size,
                "estimated_duration_days": estimated_duration_days,
                "assumptions": ["Baseline is stable"],
            },
            "experiment_design": {
                "variants": [
                    {"name": "A", "description": "current"},
                    {"name": "B", "description": "new"},
                ],
                "randomization_unit": "user",
                "traffic_split": [50, 50],
                "target_audience": "new users on web",
                "inclusion_criteria": "new users only",
                "exclusion_criteria": "internal staff",
                "recommended_duration_days": estimated_duration_days,
                "stopping_conditions": ["planned duration reached"],
            },
            "metrics_plan": {
                "primary": ["purchase_conversion"],
                "secondary": ["add_to_cart_rate"],
                "guardrail": ["payment_error_rate"],
                "diagnostic": ["assignment_rate"],
            },
            "risks": {
                "statistical": ["Power tradeoff"],
                "product": ["Expected result depends on user behavior."],
                "technical": ["legacy event logging"],
                "operational": ["tracking quality"],
            },
            "recommendations": {
                "before_launch": ["Verify tracking"],
                "during_test": ["Watch SRM"],
                "after_test": ["Segment the result"],
            },
            "open_questions": ["Will mobile respond differently?"],
        },
        "advice": {
            "available": False,
            "provider": "local_orchestrator",
            "model": "offline",
            "advice": None,
            "raw_text": None,
            "error": "offline",
            "error_code": "request_error",
        },
    }


def test_projects_crud_flow(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        create_response = client.post("/api/v1/projects", json=_payload("Checkout redesign"))
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["payload_schema_version"] == 1
        assert created["revision_count"] == 1
        assert created["last_revision_at"] is not None
        assert created["last_analysis_at"] is None
        assert created["last_analysis_run_id"] is None
        assert created["last_exported_at"] is None
        assert created["has_analysis_snapshot"] is False

        list_response = client.get("/api/v1/projects")
        assert list_response.status_code == 200
        assert len(list_response.json()["projects"]) == 1
        assert list_response.json()["projects"][0]["payload_schema_version"] == 1
        assert list_response.json()["projects"][0]["revision_count"] == 1

        get_response = client.get(f"/api/v1/projects/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["payload"]["project"]["project_name"] == "Checkout redesign"

        update_response = client.put(
            f"/api/v1/projects/{created['id']}",
            json=_payload("Checkout redesign v2"),
        )
        assert update_response.status_code == 200
        assert update_response.json()["payload"]["project"]["project_name"] == "Checkout redesign v2"
        assert update_response.json()["revision_count"] == 2

        revisions_response = client.get(f"/api/v1/projects/{created['id']}/revisions")
        assert revisions_response.status_code == 200
        revisions_payload = revisions_response.json()
        assert revisions_payload["project_id"] == created["id"]
        assert revisions_payload["total"] == 2
        assert revisions_payload["limit"] == 20
        assert revisions_payload["offset"] == 0
        assert revisions_payload["revisions"][0]["source"] == "update"
        assert revisions_payload["revisions"][0]["payload"]["project"]["project_name"] == "Checkout redesign v2"
        assert revisions_payload["revisions"][1]["source"] == "create"

        analysis_response = client.post(
            f"/api/v1/projects/{created['id']}/analysis",
            json={
                "calculations": {
                    "calculation_summary": {
                        "metric_type": "binary",
                        "baseline_value": 0.042,
                        "mde_pct": 5,
                        "mde_absolute": 0.0021,
                        "alpha": 0.05,
                        "power": 0.8,
                    },
                    "results": {
                        "sample_size_per_variant": 100,
                        "total_sample_size": 200,
                        "effective_daily_traffic": 5000,
                        "estimated_duration_days": 10,
                    },
                    "assumptions": ["Baseline is stable"],
                    "warnings": [],
                },
                "report": {
                    "executive_summary": "Summary",
                    "calculations": {
                        "sample_size_per_variant": 100,
                        "total_sample_size": 200,
                        "estimated_duration_days": 10,
                        "assumptions": ["Baseline is stable"],
                    },
                    "experiment_design": {
                        "variants": [
                            {"name": "A", "description": "current"},
                            {"name": "B", "description": "new"},
                        ],
                        "randomization_unit": "user",
                        "traffic_split": [50, 50],
                        "target_audience": "new users on web",
                        "inclusion_criteria": "new users only",
                        "exclusion_criteria": "internal staff",
                        "recommended_duration_days": 10,
                        "stopping_conditions": ["planned duration reached"],
                    },
                    "metrics_plan": {
                        "primary": ["purchase_conversion"],
                        "secondary": ["add_to_cart_rate"],
                        "guardrail": ["payment_error_rate"],
                        "diagnostic": ["assignment_rate"],
                    },
                    "risks": {
                        "statistical": ["No major deterministic warnings identified at this stage."],
                        "product": ["Expected result depends on user behavior."],
                        "technical": ["legacy event logging"],
                        "operational": ["tracking quality"],
                    },
                    "recommendations": {
                        "before_launch": ["Verify tracking"],
                        "during_test": ["Watch SRM"],
                        "after_test": ["Segment the result"],
                    },
                    "open_questions": ["Will mobile respond differently?"],
                },
                "advice": {
                    "available": False,
                    "provider": "local_orchestrator",
                    "model": "offline",
                    "advice": None,
                    "raw_text": None,
                    "error": "offline",
                    "error_code": "request_error",
                },
            },
        )
        assert analysis_response.status_code == 200
        assert analysis_response.json()["has_analysis_snapshot"] is True
        assert analysis_response.json()["last_analysis_at"] is not None
        assert analysis_response.json()["last_analysis_run_id"] is not None

        history_response = client.get(f"/api/v1/projects/{created['id']}/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["project_id"] == created["id"]
        assert history_payload["analysis_total"] == 1
        assert history_payload["analysis_limit"] == 20
        assert history_payload["analysis_offset"] == 0
        assert history_payload["export_total"] == 0
        assert len(history_payload["analysis_runs"]) == 1
        assert history_payload["analysis_runs"][0]["summary"]["metric_type"] == "binary"
        assert history_payload["analysis_runs"][0]["analysis"]["report"]["executive_summary"] == "Summary"

        export_response = client.post(
            f"/api/v1/projects/{created['id']}/exports",
            json={"format": "markdown"},
        )
        assert export_response.status_code == 200
        assert export_response.json()["last_exported_at"] is not None

        updated_history_response = client.get(f"/api/v1/projects/{created['id']}/history")
        assert updated_history_response.status_code == 200
        updated_history_payload = updated_history_response.json()
        assert updated_history_payload["export_total"] == 1
        assert len(updated_history_payload["export_events"]) == 1
        assert updated_history_payload["export_events"][0]["format"] == "markdown"
        assert updated_history_payload["export_events"][0]["analysis_run_id"] is None

        delete_response = client.delete(f"/api/v1/projects/{created['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"id": created["id"], "deleted": True}

        missing_response = client.get(f"/api/v1/projects/{created['id']}")
        assert missing_response.status_code == 404
        assert missing_response.json()["error_code"] == "not_found"
        assert missing_response.json()["status_code"] == 404


def test_projects_compare_endpoint_returns_saved_snapshot_differences(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        base_project = client.post("/api/v1/projects", json=_payload("Checkout baseline")).json()
        candidate_project = client.post("/api/v1/projects", json=_payload("Checkout challenger")).json()

        older_base_analysis = client.post(
            f"/api/v1/projects/{base_project['id']}/analysis",
            json=_analysis_payload(
                total_sample_size=160,
                estimated_duration_days=8,
                executive_summary="Older base summary",
                warning_codes=[],
            ),
        )
        base_analysis = client.post(
            f"/api/v1/projects/{base_project['id']}/analysis",
            json=_analysis_payload(
                total_sample_size=200,
                estimated_duration_days=10,
                executive_summary="Base summary",
                warning_codes=["SEASONALITY_PRESENT"],
            ),
        )
        candidate_analysis = client.post(
            f"/api/v1/projects/{candidate_project['id']}/analysis",
            json=_analysis_payload(
                total_sample_size=280,
                estimated_duration_days=14,
                executive_summary="Candidate summary",
                warning_codes=["LONG_DURATION", "LOW_TRAFFIC"],
            ),
        )

        assert older_base_analysis.status_code == 200
        assert base_analysis.status_code == 200
        assert candidate_analysis.status_code == 200

        compare_response = client.get(
            "/api/v1/projects/compare",
            params={
                "base_id": base_project["id"],
                "candidate_id": candidate_project["id"],
            },
        )

        assert compare_response.status_code == 200
        payload = compare_response.json()
        assert payload["base_project"]["project_name"] == "Checkout baseline"
        assert payload["candidate_project"]["project_name"] == "Checkout challenger"
        assert payload["base_project"]["analysis_run_id"] == base_analysis.json()["last_analysis_run_id"]
        assert payload["base_project"]["analysis_created_at"] == base_analysis.json()["last_analysis_at"]
        assert payload["deltas"]["total_sample_size"] == 80
        assert payload["deltas"]["estimated_duration_days"] == 4
        assert payload["shared_warning_codes"] == []
        assert payload["base_only_warning_codes"] == ["SEASONALITY_PRESENT"]
        assert payload["candidate_only_warning_codes"] == ["LONG_DURATION", "LOW_TRAFFIC"]
        assert payload["shared_assumptions"] == ["Baseline is stable"]
        assert payload["shared_risk_highlights"] == [
            "Power tradeoff",
            "Expected result depends on user behavior.",
            "legacy event logging",
            "tracking quality",
        ]
        assert payload["metric_alignment_note"] == "Both snapshots evaluate the same primary metric and metric family."
        assert payload["base_project"]["executive_summary"] == "Base summary"
        assert payload["candidate_project"]["warning_severity"] == "medium"
        assert payload["candidate_project"]["recommendation_highlights"] == ["Verify tracking", "Watch SRM", "Segment the result"]
        assert any("Checkout challenger" in item for item in payload["highlights"])

        latest_base_history = client.get(
            f"/api/v1/projects/{base_project['id']}/history",
            params={"analysis_limit": 1, "analysis_offset": 1},
        )
        assert latest_base_history.status_code == 200
        older_base_run = latest_base_history.json()["analysis_runs"][0]

        compare_specific_run_response = client.get(
            "/api/v1/projects/compare",
            params={
                "base_id": base_project["id"],
                "candidate_id": candidate_project["id"],
                "base_run_id": older_base_run["id"],
            },
        )

        assert compare_specific_run_response.status_code == 200
        specific_payload = compare_specific_run_response.json()
        assert specific_payload["base_project"]["analysis_run_id"] == older_base_run["id"]
        assert specific_payload["base_project"]["analysis_created_at"] == older_base_run["created_at"]
        assert specific_payload["deltas"]["total_sample_size"] == 120
        assert specific_payload["base_only_warning_codes"] == []
        assert specific_payload["candidate_only_warning_codes"] == ["LONG_DURATION", "LOW_TRAFFIC"]
        assert specific_payload["metric_alignment_note"] == "Both snapshots evaluate the same primary metric and metric family."


def test_workspace_export_and_import_routes_round_trip_history(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        created_project = client.post("/api/v1/projects", json=_payload("Workspace source")).json()
        analysis_response = client.post(
            f"/api/v1/projects/{created_project['id']}/analysis",
            json=_analysis_payload(
                total_sample_size=200,
                estimated_duration_days=10,
                executive_summary="Workspace summary",
                warning_codes=["SEASONALITY_PRESENT"],
            ),
        )
        assert analysis_response.status_code == 200
        project_with_analysis = analysis_response.json()

        export_response = client.post(
            f"/api/v1/projects/{created_project['id']}/exports",
            json={"format": "markdown", "analysis_run_id": project_with_analysis["last_analysis_run_id"]},
        )
        assert export_response.status_code == 200

        workspace_export = client.get("/api/v1/workspace/export")
        assert workspace_export.status_code == 200
        workspace_bundle = workspace_export.json()
        assert workspace_bundle["schema_version"] == 2
        assert len(workspace_bundle["projects"]) == 1
        assert len(workspace_bundle["analysis_runs"]) == 1
        assert len(workspace_bundle["export_events"]) == 1
        assert len(workspace_bundle["project_revisions"]) == 1
        assert workspace_bundle["integrity"]["counts"] == {
            "projects": 1,
            "analysis_runs": 1,
            "export_events": 1,
            "project_revisions": 1,
        }
        assert len(workspace_bundle["integrity"]["checksum_sha256"]) == 64

        workspace_validation = client.post("/api/v1/workspace/validate", json=workspace_bundle)
        assert workspace_validation.status_code == 200
        assert workspace_validation.json() == {
            "status": "valid",
            "schema_version": 2,
            "counts": {
                "projects": 1,
                "analysis_runs": 1,
                "export_events": 1,
                "project_revisions": 1,
            },
            "checksum_sha256": workspace_bundle["integrity"]["checksum_sha256"],
        }

        workspace_import = client.post("/api/v1/workspace/import", json=workspace_bundle)
        assert workspace_import.status_code == 200
        import_payload = workspace_import.json()
        assert import_payload == {
            "status": "imported",
            "imported_projects": 1,
            "imported_analysis_runs": 1,
            "imported_export_events": 1,
            "imported_project_revisions": 1,
        }

        listed_projects = client.get("/api/v1/projects")
        assert listed_projects.status_code == 200
        projects = listed_projects.json()["projects"]
        assert len(projects) == 2
        assert sum(1 for project in projects if project["project_name"] == "Workspace source") == 2
        assert all(project["revision_count"] == 1 for project in projects)


def test_workspace_import_rejects_tampered_bundle(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        created_project = client.post("/api/v1/projects", json=_payload("Workspace source")).json()
        workspace_export = client.get("/api/v1/workspace/export")
        assert workspace_export.status_code == 200
        workspace_bundle = workspace_export.json()
        workspace_bundle["projects"][0]["project_name"] = "Tampered source"

        workspace_import = client.post("/api/v1/workspace/import", json=workspace_bundle)

        assert created_project["project_name"] == "Workspace source"
        assert workspace_import.status_code == 400
        assert workspace_import.json()["detail"] == "Workspace bundle checksum mismatch"
        assert workspace_import.json()["error_code"] == "workspace_integrity_checksum_mismatch"


def test_workspace_validate_rejects_duplicate_project_ids(monkeypatch) -> None:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"

    monkeypatch.setenv("AB_DB_PATH", str(db_path))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        client.post("/api/v1/projects", json=_payload("Workspace source"))
        workspace_bundle = client.get("/api/v1/workspace/export").json()
        workspace_bundle["projects"].append(dict(workspace_bundle["projects"][0]))
        project_count = len(workspace_bundle["projects"])
        workspace_bundle["integrity"]["counts"]["projects"] = project_count

        import hashlib, json
        payload = {
            "schema_version": workspace_bundle["schema_version"],
            "generated_at": workspace_bundle["generated_at"],
            "projects": workspace_bundle["projects"],
            "analysis_runs": workspace_bundle["analysis_runs"],
            "export_events": workspace_bundle["export_events"],
            "project_revisions": workspace_bundle["project_revisions"],
        }
        workspace_bundle["integrity"]["checksum_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        response = client.post("/api/v1/workspace/validate", json=workspace_bundle)

    assert response.status_code == 400
    assert response.json()["error_code"] == "workspace_duplicate_project_id"
