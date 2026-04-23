from pathlib import Path
import sys
from time import perf_counter

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.main import create_app
from app.backend.app.services.monte_carlo_service import (
    simulate_comparison,
    simulate_uplift_distribution,
)
from app.backend.tests.test_api_routes import _create_saved_project


def test_simulate_uplift_distribution_is_deterministic_with_seed() -> None:
    first = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.0472,
        sample_size_a=10020,
        observed_conversion_b=0.0472,
        sample_size_b=10020,
        num_simulations=2000,
        seed=42,
    )
    second = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.0472,
        sample_size_a=10020,
        observed_conversion_b=0.0472,
        sample_size_b=10020,
        num_simulations=2000,
        seed=42,
    )

    assert first["percentiles"] == second["percentiles"]
    assert first["simulated_uplifts"] == second["simulated_uplifts"]


def test_simulate_uplift_distribution_is_stochastic_without_seed() -> None:
    first = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.0472,
        sample_size_a=10020,
        observed_conversion_b=0.0472,
        sample_size_b=10020,
        num_simulations=2000,
        seed=None,
    )
    second = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.0472,
        sample_size_a=10020,
        observed_conversion_b=0.0472,
        sample_size_b=10020,
        num_simulations=2000,
        seed=None,
    )

    assert first["percentiles"] != second["percentiles"]
    assert first["simulated_uplifts"] != second["simulated_uplifts"]


def test_simulate_uplift_distribution_stays_near_coin_flip_for_equal_rates() -> None:
    result = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.041,
        sample_size_a=10000,
        observed_conversion_b=0.041,
        sample_size_b=10000,
        num_simulations=10000,
        seed=42,
    )

    assert 0.45 <= result["probability_uplift_positive"] <= 0.55


def test_simulate_uplift_distribution_is_wide_for_tiny_samples() -> None:
    result = simulate_uplift_distribution(
        baseline_conversion=0.1,
        observed_conversion_a=0.2,
        sample_size_a=10,
        observed_conversion_b=0.2,
        sample_size_b=10,
        num_simulations=10000,
        seed=42,
    )

    width = result["percentiles"]["95"] - result["percentiles"]["5"]
    assert width > 0.3


def test_simulate_comparison_finishes_quickly_for_three_projects() -> None:
    projects = [
        {
            "id": "p-1",
            "metric_type": "binary",
            "observed_results": {
                "metric_type": "binary",
                "control_rate": 0.041,
                "treatment_rate": 0.0472,
            },
            "observed_sample_sizes": {"control": 10000, "treatment": 10020},
        },
        {
            "id": "p-2",
            "metric_type": "binary",
            "observed_results": {
                "metric_type": "binary",
                "control_rate": 0.041,
                "treatment_rate": 0.05,
            },
            "observed_sample_sizes": {"control": 10000, "treatment": 10010},
        },
        {
            "id": "p-3",
            "metric_type": "binary",
            "observed_results": {
                "metric_type": "binary",
                "control_rate": 0.041,
                "treatment_rate": 0.045,
            },
            "observed_sample_sizes": {"control": 10000, "treatment": 10040},
        },
    ]

    started_at = perf_counter()
    result = simulate_comparison(projects, num_simulations=10000)
    elapsed = perf_counter() - started_at

    assert set(result) == {"p-1", "p-2", "p-3"}
    assert elapsed < 0.5


def test_compare_projects_omits_monte_carlo_by_default() -> None:
    client = TestClient(create_app())
    project_ids = [
        _create_saved_project(client, "Project A")["id"],
        _create_saved_project(client, "Project B")["id"],
        _create_saved_project(client, "Project C")["id"],
    ]

    response = client.post("/api/v1/projects/compare", json={"project_ids": project_ids})

    assert response.status_code == 200
    assert "monte_carlo_distribution" not in response.json()


def test_compare_projects_includes_monte_carlo_when_requested() -> None:
    client = TestClient(create_app())
    project_ids = [
        _create_saved_project(client, "Project A")["id"],
        _create_saved_project(client, "Project B")["id"],
        _create_saved_project(client, "Project C")["id"],
    ]

    response = client.post(
        "/api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=10000",
        json={"project_ids": project_ids},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["monte_carlo_distribution"]) == set(project_ids)
    assert all(
        len(project_result["simulated_uplifts"]) == 10000
        for project_result in payload["monte_carlo_distribution"].values()
    )
