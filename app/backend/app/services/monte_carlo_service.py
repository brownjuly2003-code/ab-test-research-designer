from __future__ import annotations

import math
from typing import Any

import numpy as np

PERCENTILE_LEVELS = (5, 25, 50, 75, 95)
THRESHOLD_LEVELS = tuple(round(value / 100, 2) for value in range(1, 11))
EPSILON = 1e-12


def _as_probability(value: Any, field_name: str) -> float:
    probability = float(value)
    if probability < 0 or probability > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return probability


def _as_positive_int(value: Any, field_name: str) -> int:
    integer = int(value)
    if integer <= 0:
        raise ValueError(f"{field_name} must be positive")
    return integer


def _rate_to_count(rate: float, sample_size: int) -> int:
    count = int(round(rate * sample_size))
    return max(0, min(count, sample_size))


def _summarize_simulated_uplifts(uplifts: np.ndarray, *, num_simulations: int) -> dict[str, Any]:
    percentile_values = np.percentile(uplifts, PERCENTILE_LEVELS)
    return {
        "num_simulations": num_simulations,
        "percentiles": {
            str(level): float(value)
            for level, value in zip(PERCENTILE_LEVELS, percentile_values, strict=True)
        },
        "probability_uplift_positive": float(np.mean(uplifts > 0)),
        "probability_uplift_above_threshold": {
            f"{threshold:.2f}": float(np.mean(uplifts > threshold))
            for threshold in THRESHOLD_LEVELS
        },
        "simulated_uplifts": uplifts.astype(float).tolist(),
    }


def simulate_uplift_distribution(
    baseline_conversion: float,
    observed_conversion_a: float,
    sample_size_a: int,
    observed_conversion_b: float,
    sample_size_b: int,
    num_simulations: int = 10000,
    seed: int | None = 42,
) -> dict[str, Any]:
    baseline_rate = _as_probability(baseline_conversion, "baseline_conversion")
    control_rate = _as_probability(observed_conversion_a, "observed_conversion_a")
    treatment_rate = _as_probability(observed_conversion_b, "observed_conversion_b")
    control_sample_size = _as_positive_int(sample_size_a, "sample_size_a")
    treatment_sample_size = _as_positive_int(sample_size_b, "sample_size_b")
    simulations = _as_positive_int(num_simulations, "num_simulations")

    rng = np.random.default_rng(seed)
    control_conversions = _rate_to_count(control_rate, control_sample_size)
    treatment_conversions = _rate_to_count(treatment_rate, treatment_sample_size)

    control_draws = rng.beta(
        control_conversions + 1,
        control_sample_size - control_conversions + 1,
        size=simulations,
    )
    treatment_draws = rng.beta(
        treatment_conversions + 1,
        treatment_sample_size - treatment_conversions + 1,
        size=simulations,
    )

    if math.isclose(baseline_rate, control_rate, rel_tol=0.0, abs_tol=1e-12):
        baseline_draws = np.maximum(control_draws, EPSILON)
    else:
        baseline_draws = np.maximum(float(baseline_rate), EPSILON)

    uplift_draws = (treatment_draws - baseline_draws) / baseline_draws
    return _summarize_simulated_uplifts(uplift_draws, num_simulations=simulations)


def _simulate_continuous_uplift_distribution(
    *,
    control_mean: float,
    control_std: float,
    control_n: int,
    treatment_mean: float,
    treatment_std: float,
    treatment_n: int,
    num_simulations: int,
    seed: int | None,
) -> dict[str, Any]:
    control_mean_value = float(control_mean)
    treatment_mean_value = float(treatment_mean)
    control_std_value = float(control_std)
    treatment_std_value = float(treatment_std)
    control_sample_size = _as_positive_int(control_n, "control_n")
    treatment_sample_size = _as_positive_int(treatment_n, "treatment_n")
    simulations = _as_positive_int(num_simulations, "num_simulations")

    if control_std_value <= 0 or treatment_std_value <= 0:
        raise ValueError("continuous standard deviation must be positive")

    rng = np.random.default_rng(seed)
    control_draws = rng.normal(
        loc=control_mean_value,
        scale=control_std_value / math.sqrt(control_sample_size),
        size=simulations,
    )
    treatment_draws = rng.normal(
        loc=treatment_mean_value,
        scale=treatment_std_value / math.sqrt(treatment_sample_size),
        size=simulations,
    )
    baseline_draws = np.maximum(np.abs(control_draws), EPSILON)
    uplift_draws = (treatment_draws - control_draws) / baseline_draws
    return _summarize_simulated_uplifts(uplift_draws, num_simulations=simulations)


def _extract_metric_type(project: dict[str, Any]) -> str | None:
    metric_type = project.get("metric_type")
    if isinstance(metric_type, str) and metric_type:
        return metric_type

    payload = project.get("payload")
    if isinstance(payload, dict):
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            resolved = metrics.get("metric_type")
            if isinstance(resolved, str) and resolved:
                return resolved

    observed_results = project.get("observed_results")
    if isinstance(observed_results, dict):
        resolved = observed_results.get("metric_type")
        if isinstance(resolved, str) and resolved:
            return resolved

    return None


def _extract_saved_observed_request(project: dict[str, Any]) -> dict[str, Any] | None:
    request = project.get("observed_results_request")
    if isinstance(request, dict):
        return request

    payload = project.get("payload")
    if not isinstance(payload, dict):
        return None

    additional_context = payload.get("additional_context")
    if not isinstance(additional_context, dict):
        return None

    observed_results = additional_context.get("observed_results")
    if not isinstance(observed_results, dict):
        return None

    request = observed_results.get("request")
    return request if isinstance(request, dict) else None


def simulate_comparison(
    projects: list[dict[str, Any]],
    num_simulations: int = 10000,
    seed: int | None = 42,
) -> dict[str, dict[str, Any]]:
    simulation_results: dict[str, dict[str, Any]] = {}

    for index, project in enumerate(projects):
        project_id = project.get("id")
        if not isinstance(project_id, str) or not project_id:
            continue

        metric_type = _extract_metric_type(project)
        project_seed = None if seed is None else seed + index

        if metric_type == "binary":
            request = _extract_saved_observed_request(project)
            if isinstance(request, dict):
                binary_request = request.get("binary")
                if not isinstance(binary_request, dict):
                    continue
                control_users = _as_positive_int(binary_request.get("control_users"), "control_users")
                treatment_users = _as_positive_int(binary_request.get("treatment_users"), "treatment_users")
                control_conversions = max(0, min(int(binary_request.get("control_conversions", 0)), control_users))
                treatment_conversions = max(0, min(int(binary_request.get("treatment_conversions", 0)), treatment_users))
                control_rate = control_conversions / control_users
                treatment_rate = treatment_conversions / treatment_users
            else:
                observed_results = project.get("observed_results")
                sample_sizes = project.get("observed_sample_sizes")
                if not isinstance(observed_results, dict) or not isinstance(sample_sizes, dict):
                    continue
                control_rate = _as_probability(observed_results.get("control_rate"), "control_rate")
                treatment_rate = _as_probability(observed_results.get("treatment_rate"), "treatment_rate")
                control_users = _as_positive_int(sample_sizes.get("control"), "control")
                treatment_users = _as_positive_int(sample_sizes.get("treatment"), "treatment")

            simulation_results[project_id] = simulate_uplift_distribution(
                baseline_conversion=control_rate,
                observed_conversion_a=control_rate,
                sample_size_a=control_users,
                observed_conversion_b=treatment_rate,
                sample_size_b=treatment_users,
                num_simulations=num_simulations,
                seed=project_seed,
            )
            continue

        if metric_type == "continuous":
            request = _extract_saved_observed_request(project)
            if not isinstance(request, dict):
                continue
            continuous_request = request.get("continuous")
            if not isinstance(continuous_request, dict):
                continue

            simulation_results[project_id] = _simulate_continuous_uplift_distribution(
                control_mean=float(continuous_request.get("control_mean")),
                control_std=float(continuous_request.get("control_std")),
                control_n=_as_positive_int(continuous_request.get("control_n"), "control_n"),
                treatment_mean=float(continuous_request.get("treatment_mean")),
                treatment_std=float(continuous_request.get("treatment_std")),
                treatment_n=_as_positive_int(continuous_request.get("treatment_n"), "treatment_n"),
                num_simulations=num_simulations,
                seed=project_seed,
            )

    return simulation_results
