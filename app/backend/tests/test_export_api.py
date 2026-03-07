from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report


def _report_payload() -> dict:
    payload = {
        "project": {
            "project_name": "Checkout redesign",
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
    calculation_result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "seasonality_present": True,
            "active_campaigns_present": False,
            "long_test_possible": True,
        }
    )
    return build_experiment_report(payload, calculation_result)


def test_export_markdown_endpoint_returns_markdown_document() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/export/markdown", json=_report_payload())

    assert response.status_code == 200
    content = response.json()["content"]
    assert "# Experiment Report" in content
    assert "## Executive Summary" in content


def test_export_html_endpoint_returns_html_document() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/export/html", json=_report_payload())

    assert response.status_code == 200
    content = response.json()["content"]
    assert "<!doctype html>" in content.lower()
    assert "<h1>Experiment Report</h1>" in content


def test_export_html_escapes_user_supplied_content() -> None:
    client = TestClient(create_app())
    payload = _report_payload()
    payload["executive_summary"] = "<script>alert(1)</script>"
    payload["recommendations"]["before_launch"] = ["<img src=x onerror=alert(2)>"]

    response = client.post("/api/v1/export/html", json=payload)

    assert response.status_code == 200
    content = response.json()["content"]
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<img src=x onerror=alert(2)>" not in content
    assert "&lt;img src=x onerror=alert(2)&gt;" in content
