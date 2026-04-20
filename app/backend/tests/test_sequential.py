from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app
from app.backend.app.stats.sequential import (
    obrien_fleming_boundaries,
    sequential_sample_size_inflation,
)


def test_single_look_is_standard_z() -> None:
    boundaries = obrien_fleming_boundaries(1, alpha=0.05)

    assert len(boundaries) == 1
    assert abs(boundaries[0]["z_boundary"] - 1.96) < 0.01


def test_five_looks_final_boundary() -> None:
    boundaries = obrien_fleming_boundaries(5, alpha=0.05)

    assert len(boundaries) == 5
    assert abs(boundaries[-1]["z_boundary"] - 2.04) < 0.1


def test_boundaries_monotone_decreasing() -> None:
    boundaries = obrien_fleming_boundaries(5, alpha=0.05)
    z_values = [entry["z_boundary"] for entry in boundaries]

    assert all(z_values[index] >= z_values[index + 1] for index in range(len(z_values) - 1))


def test_inflation_increases_with_looks() -> None:
    factors = [sequential_sample_size_inflation(looks) for looks in range(1, 6)]

    assert all(factors[index] <= factors[index + 1] for index in range(len(factors) - 1))
    assert factors[0] == 1.0


def test_calculate_endpoint_returns_sequential_boundaries_and_warning() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "n_looks": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["sequential_boundaries"] is not None
    assert len(payload["sequential_boundaries"]) == 5
    assert payload["sequential_adjusted_sample_size"] > payload["results"]["sample_size_per_variant"]
    assert payload["sequential_inflation_factor"] > 1.0
    assert any(
        warning["code"] == "INTERIM_LOOKS_INCREASE_SAMPLE"
        for warning in payload["warnings"]
    )


def test_calculate_endpoint_keeps_fixed_horizon_response_when_n_looks_is_one() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/calculate",
        json={
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "n_looks": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["sequential_boundaries"] is None
    assert payload["sequential_adjusted_sample_size"] is None
    assert payload["sequential_inflation_factor"] is None


def test_analyze_endpoint_propagates_n_looks_from_constraints() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/analyze",
        json={
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
                "n_looks": 5,
            },
            "additional_context": {
                "llm_context": "Previous tests showed mixed results.",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["calculations"]["sequential_boundaries"] is not None
    assert len(payload["calculations"]["sequential_boundaries"]) == 5
    assert payload["calculations"]["sequential_adjusted_sample_size"] > payload["calculations"]["results"]["sample_size_per_variant"]
