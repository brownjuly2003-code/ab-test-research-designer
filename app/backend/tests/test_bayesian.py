from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.main import create_app
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.stats.bayesian import (
    bayesian_sample_size_binary,
    bayesian_sample_size_continuous,
)


def _full_payload() -> dict:
    return {
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
            "baseline_value": 0.035,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
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
            "analysis_mode": "bayesian",
            "desired_precision": 0.5,
            "credibility": 0.95,
        },
        "additional_context": {
            "llm_context": "Previous tests showed mixed results.",
        },
    }


def test_binary_bayesian_precision() -> None:
    n = bayesian_sample_size_binary(0.035, desired_precision=0.005)

    assert 10000 < n < 11000


def test_binary_bayesian_larger_precision_needs_fewer_users() -> None:
    n_precise = bayesian_sample_size_binary(0.035, desired_precision=0.005)
    n_relaxed = bayesian_sample_size_binary(0.035, desired_precision=0.01)

    assert n_relaxed < n_precise


def test_continuous_bayesian_precision() -> None:
    n = bayesian_sample_size_continuous(std_dev=12.0, desired_precision=2.0)

    assert 250 < n < 300


def test_calculation_service_returns_bayesian_fields_for_binary_mode() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.035,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "analysis_mode": "bayesian",
            "desired_precision": 0.5,
            "credibility": 0.95,
        }
    )

    assert result["results"]["sample_size_per_variant"] > 0
    assert 10000 < result["bayesian_sample_size_per_variant"] < 11000
    assert result["bayesian_credibility"] == pytest.approx(0.95)
    assert "credible interval" in result["bayesian_note"]


def test_calculate_endpoint_requires_precision_in_bayesian_mode() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.035,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "analysis_mode": "bayesian",
        },
    )

    assert response.status_code == 422
    assert "desired_precision" in str(response.json()["detail"])


def test_analyze_endpoint_propagates_bayesian_calculation(monkeypatch) -> None:
    monkeypatch.setattr(
        LocalOrchestratorAdapter,
        "request_advice",
        lambda self, payload: {
            "available": False,
            "provider": "local_orchestrator",
            "model": "offline",
            "advice": None,
            "raw_text": None,
            "error": "offline",
            "error_code": "request_error",
        },
    )
    client = TestClient(create_app())

    response = client.post("/api/v1/analyze", json=_full_payload())

    assert response.status_code == 200
    calculations = response.json()["calculations"]
    assert 10000 < calculations["bayesian_sample_size_per_variant"] < 11000
    assert calculations["bayesian_credibility"] == pytest.approx(0.95)
    assert "0.5" in calculations["bayesian_note"]
