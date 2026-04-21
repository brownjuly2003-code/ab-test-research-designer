import base64
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


def _comparison_project_payload(name: str, metric_type: str = "binary") -> dict:
    return {
        "project": {
            "project_name": name,
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "Comparison fixture project.",
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
            "primary_metric_name": "avg_order_value" if metric_type == "continuous" else "purchase_conversion",
            "metric_type": metric_type,
            "baseline_value": 45.0 if metric_type == "continuous" else 0.042,
            "expected_uplift_pct": 6 if metric_type == "continuous" else 8,
            "mde_pct": 4.4444444444 if metric_type == "continuous" else 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": 12.0 if metric_type == "continuous" else None,
            "secondary_metrics": ["add_to_cart_rate"],
            "guardrail_metrics": [],
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
        "additional_context": {
        "llm_context": "Saved comparison export fixture",
        "observed_results": {
            "request": (
                {
                    "metric_type": "continuous",
                    "continuous": {
                        "control_mean": 45.0,
                        "control_std": 12.0,
                        "control_n": 200,
                        "treatment_mean": 47.1,
                        "treatment_std": 12.2,
                        "treatment_n": 205,
                        "alpha": 0.05,
                    },
                }
                if metric_type == "continuous"
                else {
                    "metric_type": "binary",
                    "binary": {
                        "control_conversions": 410,
                        "control_users": 10000,
                        "treatment_conversions": 470,
                        "treatment_users": 10020,
                        "alpha": 0.05,
                    },
                }
            ),
            "analysis": (
                {
                    "metric_type": "continuous",
                    "observed_effect": 2.1,
                    "observed_effect_relative": 4.67,
                    "control_rate": None,
                    "treatment_rate": None,
                    "ci_lower": 0.3,
                    "ci_upper": 3.9,
                    "ci_level": 0.95,
                    "p_value": 0.028,
                    "test_statistic": 2.2,
                    "is_significant": True,
                    "power_achieved": 0.7,
                    "verdict": "Ship candidate",
                    "interpretation": "Treatment improved the metric.",
                }
                if metric_type == "continuous"
                else {
                    "metric_type": "binary",
                    "observed_effect": 0.6,
                    "observed_effect_relative": 14.63,
                    "control_rate": 0.041,
                    "treatment_rate": 0.047,
                    "ci_lower": 0.1,
                    "ci_upper": 1.1,
                    "ci_level": 0.95,
                    "p_value": 0.021,
                    "test_statistic": 2.31,
                    "is_significant": True,
                    "power_achieved": 0.82,
                    "verdict": "Ship candidate",
                    "interpretation": "Treatment improved conversion.",
                }
            ),
            "saved_at": "2026-03-07T13:15:00Z",
        },
    }
    }


def _comparison_analysis_payload(
    *,
    metric_type: str = "binary",
    total_sample_size: int = 240,
    estimated_duration_days: int = 9,
) -> dict:
    sample_size_per_variant = total_sample_size // 2
    primary_metric = "purchase_conversion" if metric_type == "binary" else "avg_order_value"
    baseline_value = 0.042 if metric_type == "binary" else 45.0
    return {
        "calculations": {
            "calculation_summary": {
                "metric_type": metric_type,
                "baseline_value": baseline_value,
                "mde_pct": 5,
                "mde_absolute": 0.0021 if metric_type == "binary" else 2.0,
                "alpha": 0.05,
                "power": 0.8,
            },
            "results": {
                "sample_size_per_variant": sample_size_per_variant,
                "total_sample_size": total_sample_size,
                "effective_daily_traffic": 5000,
                "estimated_duration_days": estimated_duration_days,
            },
            "assumptions": ["Baseline is stable"],
            "warnings": [
                {
                    "code": "LOW_TRAFFIC",
                    "severity": "medium",
                    "message": "LOW_TRAFFIC may affect the result.",
                    "source": "rules_engine",
                }
            ],
        },
        "report": {
            "executive_summary": f"{primary_metric} summary",
            "calculations": {
                "sample_size_per_variant": sample_size_per_variant,
                "total_sample_size": total_sample_size,
                "estimated_duration_days": estimated_duration_days,
                "assumptions": ["Baseline is stable"],
            },
            "experiment_design": {
                "variants": [
                    {"name": "Control", "description": "current"},
                    {"name": "Treatment", "description": "candidate"},
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
                "primary": [primary_metric],
                "secondary": ["add_to_cart_rate"],
                "guardrail": ["payment_error_rate"],
                "diagnostic": ["assignment_rate"],
            },
            "guardrail_metrics": [],
            "risks": {
                "statistical": ["Power tradeoff"],
                "product": ["Behavior may differ on mobile."],
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
            "available": True,
            "provider": "local_orchestrator",
            "model": "offline",
            "advice": {
                "brief_assessment": "Feasible with monitoring.",
                "key_risks": ["Tracking quality"],
                "design_improvements": ["Validate assignment logging"],
                "metric_recommendations": ["Track checkout step completion"],
                "interpretation_pitfalls": ["Do not stop early"],
                "additional_checks": ["Verify exposure balance"],
            },
            "raw_text": None,
            "error": None,
            "error_code": None,
        },
    }


def test_export_markdown_endpoint_returns_markdown_document() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/export/markdown", json=_report_payload())

    assert response.status_code == 200
    content = response.json()["content"]
    assert "# Experiment Report" in content
    assert "## Executive Summary" in content


def test_export_markdown_endpoint_localizes_content_for_russian() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/export/markdown",
        json=_report_payload(),
        headers={"Accept-Language": "ru"},
    )

    assert response.status_code == 200
    content = response.json()["content"]
    assert "## Резюме" in content
    assert "## Executive Summary" not in content


def test_export_markdown_endpoint_localizes_content_for_german() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/export/markdown",
        json=_report_payload(),
        headers={"Accept-Language": "de"},
    )

    assert response.status_code == 200
    content = response.json()["content"]
    assert "## Zusammenfassung" in content
    assert "## Executive Summary" not in content


def test_export_markdown_endpoint_localizes_content_for_spanish() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/export/markdown",
        json=_report_payload(),
        headers={"Accept-Language": "es"},
    )

    assert response.status_code == 200
    content = response.json()["content"]
    assert "## Resumen" in content
    assert "## Executive Summary" not in content


def test_export_markdown_endpoint_falls_back_to_primary_language_for_regional_locales() -> None:
    client = TestClient(create_app())

    de_response = client.post(
        "/api/v1/export/markdown",
        json=_report_payload(),
        headers={"Accept-Language": "de-AT"},
    )
    es_response = client.post(
        "/api/v1/export/markdown",
        json=_report_payload(),
        headers={"Accept-Language": "es-MX"},
    )

    assert de_response.status_code == 200
    assert "## Zusammenfassung" in de_response.json()["content"]
    assert "## Executive Summary" not in de_response.json()["content"]

    assert es_response.status_code == 200
    assert "## Resumen" in es_response.json()["content"]
    assert "## Executive Summary" not in es_response.json()["content"]


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


def test_export_comparison_markdown() -> None:
    client = TestClient(create_app())
    project_ids: list[str] = []

    for index, metric_type in enumerate(("binary", "binary", "continuous"), start=1):
        created = client.post(
            "/api/v1/projects",
            json=_comparison_project_payload(f"Comparison project {index}", metric_type),
        )
        assert created.status_code == 200
        project_ids.append(created.json()["id"])

        analysis = client.post(
            f"/api/v1/projects/{created.json()['id']}/analysis",
            json=_comparison_analysis_payload(
                metric_type=metric_type,
                total_sample_size=220 + (index * 40),
                estimated_duration_days=8 + index,
            ),
        )
        assert analysis.status_code == 200

    response = client.post(
        "/api/v1/export/comparison",
        json={"project_ids": project_ids, "format": "markdown"},
    )

    assert response.status_code == 200
    content = response.json()["content"]
    assert "# Multi-project comparison" in content
    assert "## Shared insights" in content
    assert "Comparison project 1" in content
    assert "Comparison project 3" in content


def test_export_comparison_pdf() -> None:
    client = TestClient(create_app())
    project_ids: list[str] = []

    for index in range(2):
        created = client.post(
            "/api/v1/projects",
            json=_comparison_project_payload(f"PDF project {index + 1}"),
        )
        assert created.status_code == 200
        project_ids.append(created.json()["id"])

        analysis = client.post(
            f"/api/v1/projects/{created.json()['id']}/analysis",
            json=_comparison_analysis_payload(
                total_sample_size=240 + (index * 40),
                estimated_duration_days=9 + index,
            ),
        )
        assert analysis.status_code == 200

    response = client.post(
        "/api/v1/export/comparison",
        json={"project_ids": project_ids, "format": "pdf"},
    )

    assert response.status_code == 200
    pdf_bytes = base64.b64decode(response.json()["content"])
    assert pdf_bytes.startswith(b"%PDF")
