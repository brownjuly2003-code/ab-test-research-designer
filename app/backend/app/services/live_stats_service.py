"""Phase D — live experiment statistics over ingested exposures/conversions.

The data plumbing (Phase C) already deduplicates exposures (first-exposure-wins) and
conversions (idempotency key). This module re-runs the *existing* statistics engine over
the current aggregates — there is no new math here:

- **SRM guardrail**     reuses ``stats.srm.chi_square_srm`` over per-variation exposure counts.
- **Frequentist test**  reuses ``services.results_service.analyze_results`` (two-proportion /
                        Welch t) per control-vs-treatment comparison.
- **Bayesian P(B>A)**   reuses ``services.monte_carlo_service.simulate_uplift_distribution``
                        (Beta-Bernoulli draws), binary metrics only.
- **Sequential look**   reuses ``services.calculations_service.calculate_experiment_metrics``
                        for the planned sample size + O'Brien-Fleming boundary schedule, then
                        compares the live z-statistic to the boundary at the current
                        information fraction.

CUPED is honestly marked unavailable: the MVP ingests no per-user pre-period covariate, which
CUPED requires. Continuous Bayesian is out of MVP scope (frequentist continuous is supported).
"""

from __future__ import annotations

import math
from typing import Any

from app.backend.app.execution.experiment_assignment import normalize_weights
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ResultsRequest,
)
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.monte_carlo_service import (
    simulate_continuous_uplift_distribution,
    simulate_uplift_distribution,
)
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats.srm import chi_square_srm

DISCLAIMER = (
    "MVP execution layer — a full plan -> run -> analyze cycle demonstration, not built for "
    "high-traffic production. Live stats are recomputed on demand over deduplicated exposures "
    "and conversions."
)

_BAYESIAN_SIMULATIONS = 10000
_BAYESIAN_SEED = 42


def build_live_stats(
    experiment_id: str,
    project_payload: dict[str, Any],
    aggregates: dict[str, Any],
    cuped_aggregates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the live-stats payload from a stored experiment design and the current
    per-variation analysis aggregates (``repository.get_experiment_analysis_aggregates``).

    ``cuped_aggregates`` (``repository.get_cuped_aggregates``) carries the per-variation CUPED
    sufficient statistics over users with a pre-period covariate; ``None`` / empty keeps the
    CUPED block ``unavailable``."""
    metrics = project_payload.get("metrics", {})
    setup = project_payload.get("setup", {})
    constraints = project_payload.get("constraints", {})

    metric_type = metrics.get("metric_type", "binary")
    primary_metric_name = metrics.get("primary_metric_name", "")
    baseline_value = float(metrics.get("baseline_value", 0.0))
    alpha = float(metrics.get("alpha", 0.05))
    variants_count = int(setup.get("variants_count", 2))
    traffic_split = setup.get("traffic_split", [])
    n_looks = int(constraints.get("n_looks", 1))

    # Build a dense per-variation view (0..variants_count-1), filling arms with no exposures.
    by_index = {int(item["variation_index"]): item for item in aggregates.get("variations", [])}
    arms = [
        by_index.get(
            index,
            {
                "variation_index": index,
                "exposed_users": 0,
                "converted_users": 0,
                "value_sum": 0.0,
                "value_sq_sum": 0.0,
            },
        )
        for index in range(variants_count)
    ]

    exposures_total = sum(arm["exposed_users"] for arm in arms)
    conversions_total = sum(arm["converted_users"] for arm in arms)

    expected_fractions = normalize_weights(traffic_split) if traffic_split else []

    srm = _build_srm_block(arms, expected_fractions)
    comparisons = [
        _build_comparison(
            metric_type=metric_type,
            baseline_value=baseline_value,
            alpha=alpha,
            control=arms[0],
            treatment=arms[treatment_index],
        )
        for treatment_index in range(1, variants_count)
    ]
    sequential = _build_sequential_block(
        project_payload=project_payload,
        n_looks=n_looks,
        variants_count=variants_count,
        total_exposed=exposures_total,
        comparisons=comparisons,
    )
    cuped = _build_cuped_block(
        metric_type=metric_type,
        alpha=alpha,
        variants_count=variants_count,
        exposed_total=exposures_total,
        cuped_aggregates=cuped_aggregates,
    )

    return {
        "experiment_id": experiment_id,
        "metric_type": metric_type,
        "primary_metric_name": primary_metric_name,
        "exposures_total": exposures_total,
        "conversions_total": conversions_total,
        "disclaimer": DISCLAIMER,
        "srm": srm,
        "comparisons": comparisons,
        "sequential": sequential,
        "cuped": cuped,
    }


def _build_srm_block(
    arms: list[dict[str, Any]],
    expected_fractions: list[float],
) -> dict[str, Any]:
    observed_counts = [arm["exposed_users"] for arm in arms]
    total = sum(observed_counts)
    if total == 0 or len(observed_counts) < 2 or len(expected_fractions) != len(observed_counts):
        return {
            "status": "insufficient_data",
            "is_srm": False,
            "observed_counts": observed_counts,
            "expected_counts": [],
            "verdict": "Not enough exposures yet to check sample-ratio mismatch.",
        }
    chi_square, p_value, is_srm = chi_square_srm(observed_counts, expected_fractions)
    expected_counts = [round(fraction * total, 4) for fraction in expected_fractions]
    verdict = (
        "Sample-ratio mismatch detected (p < 0.001) — assignment looks broken; do not trust results."
        if is_srm
        else "No sample-ratio mismatch; traffic split matches the design."
    )
    return {
        "status": "srm_detected" if is_srm else "ok",
        "chi_square": round(chi_square, 4),
        "p_value": round(p_value, 6),
        "is_srm": is_srm,
        "observed_counts": observed_counts,
        "expected_counts": expected_counts,
        "verdict": verdict,
    }


def _arm_stat(metric_type: str, arm: dict[str, Any]) -> dict[str, Any]:
    exposed = arm["exposed_users"]
    stat: dict[str, Any] = {
        "variation_index": arm["variation_index"],
        "exposed_users": exposed,
        "converted_users": arm["converted_users"],
    }
    if metric_type == "binary":
        stat["conversion_rate"] = round(arm["converted_users"] / exposed, 6) if exposed else None
    else:
        mean, std = _continuous_moments(arm)
        stat["mean"] = round(mean, 6) if mean is not None else None
        stat["std"] = round(std, 6) if std is not None else None
    return stat


def _continuous_moments(arm: dict[str, Any]) -> tuple[float | None, float | None]:
    n = arm["exposed_users"]
    if n < 1:
        return None, None
    mean = arm["value_sum"] / n
    if n < 2:
        return mean, None
    variance = (arm["value_sq_sum"] - n * mean * mean) / (n - 1)
    return mean, math.sqrt(variance) if variance > 0 else 0.0


def _build_comparison(
    *,
    metric_type: str,
    baseline_value: float,
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    control_stat = _arm_stat(metric_type, control)
    treatment_stat = _arm_stat(metric_type, treatment)
    base: dict[str, Any] = {
        "treatment_index": treatment["variation_index"],
        "control": control_stat,
        "treatment": treatment_stat,
        "analysis": None,
        "probability_treatment_beats_control": None,
        "sequential_significant": None,
        "note": None,
    }

    if control["exposed_users"] < 2 or treatment["exposed_users"] < 2:
        base["status"] = "insufficient_data"
        base["note"] = "Each arm needs at least 2 exposed users before a test can run."
        return base

    if metric_type == "binary":
        return _binary_comparison(base, alpha, baseline_value, control, treatment)
    return _continuous_comparison(base, alpha, control, treatment)


def _binary_comparison(
    base: dict[str, Any],
    alpha: float,
    baseline_value: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    request = ResultsRequest(
        metric_type="binary",
        binary=ObservedResultsBinary(
            control_conversions=control["converted_users"],
            control_users=control["exposed_users"],
            treatment_conversions=treatment["converted_users"],
            treatment_users=treatment["exposed_users"],
            alpha=alpha,
        ),
    )
    analysis = analyze_results(request)
    control_rate = control["converted_users"] / control["exposed_users"]
    treatment_rate = treatment["converted_users"] / treatment["exposed_users"]
    # Passing baseline == control_rate makes the simulation compare treatment draws against
    # control draws (true P(B>A)) rather than against a fixed baseline.
    simulation = simulate_uplift_distribution(
        baseline_conversion=control_rate,
        observed_conversion_a=control_rate,
        sample_size_a=control["exposed_users"],
        observed_conversion_b=treatment_rate,
        sample_size_b=treatment["exposed_users"],
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    base["status"] = "ok"
    base["analysis"] = analysis.model_dump()
    base["probability_treatment_beats_control"] = round(
        simulation["probability_uplift_positive"], 6
    )
    return base


def _continuous_comparison(
    base: dict[str, Any],
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    control_mean, control_std = _continuous_moments(control)
    treatment_mean, treatment_std = _continuous_moments(treatment)
    if not control_std or not treatment_std:
        base["status"] = "insufficient_data"
        base["note"] = (
            "Per-user values show zero variance in an arm, so a t-test cannot be computed yet."
        )
        return base
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=control_mean,
            control_std=control_std,
            control_n=control["exposed_users"],
            treatment_mean=treatment_mean,
            treatment_std=treatment_std,
            treatment_n=treatment["exposed_users"],
            alpha=alpha,
        ),
    )
    simulation = simulate_continuous_uplift_distribution(
        control_mean=control_mean,
        control_std=control_std,
        control_n=control["exposed_users"],
        treatment_mean=treatment_mean,
        treatment_std=treatment_std,
        treatment_n=treatment["exposed_users"],
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    base["status"] = "ok"
    base["analysis"] = analyze_results(request).model_dump()
    base["probability_treatment_beats_control"] = round(simulation["probability_uplift_positive"], 6)
    return base


def _calc_payload_from_design(project_payload: dict[str, Any]) -> dict[str, Any]:
    """Flat ``calculate_experiment_metrics`` payload from a stored ``ExperimentInput`` dict —
    mirrors ``routes.analysis._build_calculation_payload`` without importing the routes layer."""
    metrics = project_payload.get("metrics", {})
    setup = project_payload.get("setup", {})
    constraints = project_payload.get("constraints", {})
    return {
        "metric_type": metrics.get("metric_type"),
        "baseline_value": metrics.get("baseline_value"),
        "std_dev": metrics.get("std_dev"),
        "cuped_pre_experiment_std": metrics.get("cuped_pre_experiment_std"),
        "cuped_correlation": metrics.get("cuped_correlation"),
        "mde_pct": metrics.get("mde_pct"),
        "alpha": metrics.get("alpha"),
        "power": metrics.get("power"),
        "expected_daily_traffic": setup.get("expected_daily_traffic"),
        "audience_share_in_test": setup.get("audience_share_in_test"),
        "traffic_split": setup.get("traffic_split"),
        "variants_count": setup.get("variants_count"),
        "seasonality_present": constraints.get("seasonality_present"),
        "active_campaigns_present": constraints.get("active_campaigns_present"),
        "long_test_possible": constraints.get("long_test_possible"),
        "n_looks": constraints.get("n_looks", 1),
        "analysis_mode": constraints.get("analysis_mode", "frequentist"),
        "desired_precision": constraints.get("desired_precision"),
        "credibility": constraints.get("credibility", 0.95),
        "holdout_fraction": constraints.get("holdout_fraction"),
        "mutually_exclusive_experiments": constraints.get("mutually_exclusive_experiments"),
    }


def _build_sequential_block(
    *,
    project_payload: dict[str, Any],
    n_looks: int,
    variants_count: int,
    total_exposed: int,
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    if n_looks <= 1:
        return {
            "status": "fixed_horizon",
            "n_looks": n_looks,
            "total_exposed": total_exposed,
            "note": (
                "Fixed-horizon design (n_looks=1): read the frequentist p-value only once at the "
                "planned sample size — peeking early inflates the false-positive rate."
            ),
        }

    calculation = calculate_experiment_metrics(_calc_payload_from_design(project_payload))
    planned_per_variant = int(
        calculation.get("sequential_adjusted_sample_size")
        or calculation.get("sample_size_per_variant")
        or 0
    )
    boundaries = calculation.get("sequential_boundaries") or []
    planned_total = planned_per_variant * variants_count

    if planned_total <= 0 or not boundaries or total_exposed == 0:
        return {
            "status": "insufficient_data",
            "n_looks": n_looks,
            "planned_sample_size_per_variant": planned_per_variant or None,
            "total_exposed": total_exposed,
            "note": "Not enough exposures yet to evaluate the sequential boundary.",
        }

    information_fraction = min(1.0, total_exposed / planned_total)
    # The final-look boundary (info_fraction == 1) anchors the O'Brien-Fleming spending function;
    # the critical value at the current information fraction is z_final / sqrt(fraction).
    z_final = float(boundaries[-1]["z_boundary"])
    current_boundary_z = z_final / math.sqrt(information_fraction) if information_fraction > 0 else None

    if current_boundary_z is not None:
        for comparison in comparisons:
            analysis = comparison.get("analysis")
            if analysis is not None:
                comparison["sequential_significant"] = (
                    abs(analysis["test_statistic"]) > current_boundary_z
                )

    return {
        "status": "active",
        "n_looks": n_looks,
        "planned_sample_size_per_variant": planned_per_variant,
        "total_exposed": total_exposed,
        "information_fraction": round(information_fraction, 4),
        "current_boundary_z": round(current_boundary_z, 4) if current_boundary_z is not None else None,
        "note": (
            "O'Brien-Fleming sequential boundary at the current information fraction. A treatment "
            "is sequential-significant only when |z| exceeds this (stricter early, ~nominal at the end)."
        ),
    }


# --- CUPED on live data (E5) ----------------------------------------------------------------
#
# CUPED (Deng et al. 2013) reduces variance using a pre-experiment covariate X that is
# correlated with the outcome Y but, being measured *before* assignment, is independent of the
# treatment. The adjusted outcome is
#
#     Y_adj = Y - theta * (X - mean(X)),   theta = cov(X, Y) / var(X)
#
# estimated on the pooled data (pooling is unbiased because X is pre-treatment). Subtracting the
# global mean(X) keeps E[Y_adj] = E[Y], so the treatment-effect estimate is unchanged in
# expectation while its variance drops by a factor of (1 - rho^2), rho = corr(X, Y).
#
# No per-user loop is needed: from the per-arm sufficient statistics (n, sum_x, sum_x2, sum_y,
# sum_y2, sum_xy) the adjusted arm mean and variance follow in closed form
#
#     mean(Y_adj)_a = mean(Y)_a - theta * (mean(X)_a - global mean(X))
#     var(Y_adj)_a  = var(Y)_a - 2*theta*cov(X,Y)_a + theta^2 * var(X)_a
#
# (the centering constant theta*global_mean(X) does not affect variance). Those per-arm adjusted
# moments feed the existing continuous t-test (``analyze_results``) — no new test statistic here.

_NOTE_NOT_APPLICABLE = (
    "Live CUPED applies to continuous metrics — the adjusted outcome is analysed with the "
    "continuous t-test. This experiment uses a binary metric, so CUPED is not applied here."
)
_NOTE_UNAVAILABLE = (
    "CUPED needs a per-user pre-experiment covariate. Ingest pre-period values via "
    "POST /api/v1/experiments/{id}/pre-period to enable variance reduction on live data."
)
_NOTE_AVAILABLE = (
    "CUPED-adjusted estimates over users with a pre-period covariate: "
    "Y_adj = Y - theta*(X - mean X), theta = cov(X,Y)/var(X) pooled across arms. The adjusted "
    "outcome is analysed with the continuous t-test; the effect is unchanged in expectation "
    "while variance drops with the covariate's correlation."
)


def _moments(items: list[dict[str, Any]]) -> dict[str, float] | None:
    """Sample means / variances / covariance from pooled sufficient statistics, or ``None``
    when there are fewer than 2 observations (variance undefined)."""
    n = sum(int(item["n"]) for item in items)
    if n < 2:
        return None
    sum_x = sum(item["sum_x"] for item in items)
    sum_x2 = sum(item["sum_x2"] for item in items)
    sum_y = sum(item["sum_y"] for item in items)
    sum_y2 = sum(item["sum_y2"] for item in items)
    sum_xy = sum(item["sum_xy"] for item in items)
    mean_x = sum_x / n
    mean_y = sum_y / n
    return {
        "n": n,
        "mean_x": mean_x,
        "mean_y": mean_y,
        "var_x": (sum_x2 - n * mean_x * mean_x) / (n - 1),
        "var_y": (sum_y2 - n * mean_y * mean_y) / (n - 1),
        "cov_xy": (sum_xy - n * mean_x * mean_y) / (n - 1),
    }


def _cuped_arm_stat(
    arm: dict[str, Any] | None, index: int, theta: float, global_mean_x: float
) -> dict[str, Any]:
    n = int(arm["n"]) if arm else 0
    if n == 0:
        return {
            "variation_index": index,
            "covariate_users": 0,
            "unadjusted_mean": None,
            "adjusted_mean": None,
            "adjusted_std": None,
        }
    mean_x = arm["sum_x"] / n
    mean_y = arm["sum_y"] / n
    adjusted_mean = mean_y - theta * (mean_x - global_mean_x)
    adjusted_std: float | None = None
    arm_moments = _moments([arm])
    if arm_moments is not None:
        adjusted_var = (
            arm_moments["var_y"]
            - 2 * theta * arm_moments["cov_xy"]
            + theta * theta * arm_moments["var_x"]
        )
        adjusted_std = math.sqrt(adjusted_var) if adjusted_var > 0 else 0.0
    return {
        "variation_index": index,
        "covariate_users": n,
        "unadjusted_mean": round(mean_y, 6),
        "adjusted_mean": round(adjusted_mean, 6),
        "adjusted_std": round(adjusted_std, 6) if adjusted_std is not None else None,
    }


def _cuped_comparison(
    control: dict[str, Any], treatment: dict[str, Any], alpha: float
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "treatment_index": treatment["variation_index"],
        "control": control,
        "treatment": treatment,
        "analysis": None,
        "note": None,
    }
    if control["covariate_users"] < 2 or treatment["covariate_users"] < 2:
        base["status"] = "insufficient_data"
        base["note"] = "Each arm needs at least 2 users with a pre-period covariate."
        return base
    if not control["adjusted_std"] or not treatment["adjusted_std"]:
        base["status"] = "insufficient_data"
        base["note"] = (
            "CUPED-adjusted values show zero variance in an arm, so a t-test cannot be computed yet."
        )
        return base
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=control["adjusted_mean"],
            control_std=control["adjusted_std"],
            control_n=control["covariate_users"],
            treatment_mean=treatment["adjusted_mean"],
            treatment_std=treatment["adjusted_std"],
            treatment_n=treatment["covariate_users"],
            alpha=alpha,
        ),
    )
    base["status"] = "ok"
    base["analysis"] = analyze_results(request).model_dump()
    return base


def _build_cuped_block(
    *,
    metric_type: str,
    alpha: float,
    variants_count: int,
    exposed_total: int,
    cuped_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    empty = {
        "theta": None,
        "variance_reduction_pct": None,
        "covariate_users_total": None,
        "exposed_users_total": None,
        "comparisons": [],
    }
    if metric_type != "continuous":
        return {"status": "not_applicable", "note": _NOTE_NOT_APPLICABLE, **empty}

    by_index = {
        int(item["variation_index"]): item
        for item in (cuped_aggregates or {}).get("variations", [])
    }
    covariate_users_total = sum(int(item["n"]) for item in by_index.values())
    if covariate_users_total == 0:
        return {
            "status": "unavailable",
            "note": _NOTE_UNAVAILABLE,
            **empty,
            "covariate_users_total": 0,
            "exposed_users_total": exposed_total,
        }

    pooled = _moments(list(by_index.values()))
    # theta needs var(X) > 0; a constant covariate carries no information -> theta = 0 (CUPED
    # collapses to the unadjusted estimate).
    if pooled is None or pooled["var_x"] <= 0:
        theta = 0.0
        global_mean_x = pooled["mean_x"] if pooled else 0.0
    else:
        theta = pooled["cov_xy"] / pooled["var_x"]
        global_mean_x = pooled["mean_x"]

    arm_stats = [
        _cuped_arm_stat(by_index.get(index), index, theta, global_mean_x)
        for index in range(variants_count)
    ]
    comparisons = [
        _cuped_comparison(arm_stats[0], arm_stats[treatment_index], alpha)
        for treatment_index in range(1, variants_count)
    ]

    variance_reduction_pct = None
    if pooled is not None and pooled["var_y"] > 0:
        adjusted_var = (
            pooled["var_y"] - 2 * theta * pooled["cov_xy"] + theta * theta * pooled["var_x"]
        )
        variance_reduction_pct = round((1 - adjusted_var / pooled["var_y"]) * 100, 4)

    return {
        "status": "available",
        "note": _NOTE_AVAILABLE,
        "theta": round(theta, 6),
        "variance_reduction_pct": variance_reduction_pct,
        "covariate_users_total": covariate_users_total,
        "exposed_users_total": exposed_total,
        "comparisons": comparisons,
    }
