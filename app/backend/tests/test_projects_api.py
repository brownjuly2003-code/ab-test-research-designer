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
        assert created["last_analysis_at"] is None
        assert created["last_exported_at"] is None
        assert created["has_analysis_snapshot"] is False

        list_response = client.get("/api/v1/projects")
        assert list_response.status_code == 200
        assert len(list_response.json()["projects"]) == 1
        assert list_response.json()["projects"][0]["payload_schema_version"] == 1

        get_response = client.get(f"/api/v1/projects/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["payload"]["project"]["project_name"] == "Checkout redesign"

        update_response = client.put(
            f"/api/v1/projects/{created['id']}",
            json=_payload("Checkout redesign v2"),
        )
        assert update_response.status_code == 200
        assert update_response.json()["payload"]["project"]["project_name"] == "Checkout redesign v2"

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

        export_response = client.post(
            f"/api/v1/projects/{created['id']}/exports",
            json={"format": "markdown"},
        )
        assert export_response.status_code == 200
        assert export_response.json()["last_exported_at"] is not None

        delete_response = client.delete(f"/api/v1/projects/{created['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"id": created["id"], "deleted": True}

        missing_response = client.get(f"/api/v1/projects/{created['id']}")
        assert missing_response.status_code == 404
