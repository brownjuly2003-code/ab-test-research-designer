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
            "guardrail_metrics": [
                {
                    "name": "Payment error rate",
                    "metric_type": "binary",
                    "baseline_rate": 2.4,
                },
                {
                    "name": "Refund value",
                    "metric_type": "continuous",
                    "baseline_mean": 18.0,
                    "std_dev": 6.5,
                },
            ],
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


def _standalone_payload() -> dict:
    report = _report_payload()
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
    return {
        "project_name": "Checkout redesign",
        "hypothesis": "If we simplify checkout, conversion will increase.",
        "calculation": calculation_result,
        "design": report["experiment_design"],
        "ai_advice": {
            "summary": "Watch guardrail metrics during the first week.",
            "recommendations": ["Validate event quality before launch."],
        },
        "sensitivity": {
            "cells": [
                {"mde": 5, "power": 0.8, "sample_size_per_variant": 11234, "duration_days": 8.4},
                {"mde": 5, "power": 0.9, "sample_size_per_variant": 14456, "duration_days": 10.9},
                {"mde": 7.5, "power": 0.8, "sample_size_per_variant": 6234, "duration_days": 4.8},
            ],
            "current_mde": 5,
            "current_power": 0.8,
        },
        "results": {
            "metric_type": "binary",
            "observed_effect": 0.011,
            "observed_effect_relative": 12.4,
            "control_rate": 0.041,
            "treatment_rate": 0.052,
            "ci_lower": 0.004,
            "ci_upper": 0.018,
            "ci_level": 0.95,
            "p_value": 0.021,
            "test_statistic": 2.31,
            "is_significant": True,
            "power_achieved": 0.83,
            "verdict": "Ship candidate",
            "interpretation": "Treatment beat control within the planned error budget.",
        },
    }


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
    assert "@media print" in content
    assert "Executive Summary" in content


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


def test_export_html_standalone_endpoint_returns_self_contained_html_document() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/export/html-standalone", json=_standalone_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Checkout redesign-report.html" in response.headers["content-disposition"]
    assert "@media print" in response.text
    assert "<svg" in response.text
    assert "Sensitivity Table" in response.text
    assert "Checkout redesign" in response.text
