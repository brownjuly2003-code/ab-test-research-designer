"""Primary live comparisons: SRM, binary/continuous/ratio, sequential look."""
from __future__ import annotations

import math
from typing import Any, cast

from app.backend.app.i18n import translate
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
from app.backend.app.services.results_service import (
    analyze_results,
    build_ratio_results_response,
)
from app.backend.app.stats.ratio import compare_ratios, ratio_estimate
from app.backend.app.stats.srm import chi_square_srm

from .common import (
    _always_valid_block,
    _arm_stat,
    _calc_payload_from_design,
    _continuous_moments,
)
from .constants import (
    _BAYESIAN_PROBABILITY_DECIMALS,
    _BAYESIAN_SEED,
    _BAYESIAN_SIMULATIONS,
)


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
            "verdict": translate("live_stats.srm.insufficient_data"),
        }
    chi_square, p_value, is_srm = chi_square_srm(observed_counts, expected_fractions)
    expected_counts = [round(fraction * total, 4) for fraction in expected_fractions]
    verdict = (
        translate("live_stats.srm.detected")
        if is_srm
        else translate("live_stats.srm.ok")
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

def _build_comparison(
    *,
    metric_type: str,
    baseline_value: float,
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
    mixture_variance: float | None = None,
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
        "always_valid": None,
        "note": None,
    }

    if control["exposed_users"] < 2 or treatment["exposed_users"] < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.comparison.insufficient_data")
        return base

    if metric_type == "binary":
        return _binary_comparison(base, alpha, baseline_value, control, treatment, mixture_variance)
    return _continuous_comparison(base, alpha, control, treatment, mixture_variance)


def _binary_comparison(
    base: dict[str, Any],
    alpha: float,
    baseline_value: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
    mixture_variance: float | None = None,
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
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    # Anytime-valid view over the same observed difference. Unpooled variance matches the variance
    # behind the displayed frequentist confidence interval, so the two readouts stay consistent.
    effect = treatment_rate - control_rate
    variance = control_rate * (1 - control_rate) / control["exposed_users"] + (
        treatment_rate * (1 - treatment_rate) / treatment["exposed_users"]
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


def _continuous_comparison(
    base: dict[str, Any],
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
    mixture_variance: float | None = None,
) -> dict[str, Any]:
    control_mean, control_std = _continuous_moments(control)
    treatment_mean, treatment_std = _continuous_moments(treatment)
    if not control_std or not treatment_std:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.comparison.continuous_zero_variance")
        return base
    # A non-None/non-zero std is only returned when exposed_users >= 2, which is
    # exactly the branch where _continuous_moments also yields a non-None mean.
    control_mean = cast("float", control_mean)
    treatment_mean = cast("float", treatment_mean)
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
    base["probability_treatment_beats_control"] = round(
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    # Anytime-valid view over the same observed mean difference (Welch variance of the estimate).
    effect = treatment_mean - control_mean
    variance = (
        control_std**2 / control["exposed_users"]
        + treatment_std**2 / treatment["exposed_users"]
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


# --- Ratio metrics on live data (F2) --------------------------------------------------------
#
# A ratio metric R = sum(Y)/sum(X) is randomized on the user (X = denominator events, Y =
# numerator events, both per user). The naive variance is wrong because the analysis unit differs
# from the randomization unit; ``stats.ratio`` applies the delta method to recover the correct
# variance from the per-user (co)variances. The two ingested conversion metrics (numerator and
# denominator) roll up to per-variation sufficient statistics via
# ``repository.get_ratio_aggregates``; here we run the two-sample delta-method test per
# control-vs-treatment comparison, reusing the same always-valid (mSPRT) view and FWER-adjusted
# alpha as the binary/continuous paths. No new test statistic enters the binary/continuous paths.


def _empty_ratio_arm(index: int) -> dict[str, Any]:
    return {
        "variation_index": index,
        "n": 0,
        "sum_x": 0.0,
        "sum_x2": 0.0,
        "sum_y": 0.0,
        "sum_y2": 0.0,
        "sum_xy": 0.0,
    }


def _ratio_arm_stat(arm: dict[str, Any]) -> dict[str, Any]:
    n = int(arm["n"])
    estimate = ratio_estimate(arm) if n >= 2 else None
    return {
        "variation_index": int(arm["variation_index"]),
        "exposed_users": n,
        "converted_users": 0,  # a ratio metric has no single per-user conversion count
        "ratio": round(estimate["ratio"], 6) if estimate is not None else None,
    }


def _build_ratio_comparison(
    control: dict[str, Any],
    treatment: dict[str, Any],
    alpha: float,
    mixture_variance: float | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "treatment_index": int(treatment["variation_index"]),
        "control": _ratio_arm_stat(control),
        "treatment": _ratio_arm_stat(treatment),
        "analysis": None,
        "probability_treatment_beats_control": None,
        "sequential_significant": None,
        "always_valid": None,
        "note": None,
    }
    if int(control["n"]) < 2 or int(treatment["n"]) < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.comparison.ratio_insufficient_data")
        return base
    result = compare_ratios(control, treatment, alpha)
    if result is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.comparison.ratio_degenerate")
        return base
    base["status"] = "ok"
    base["analysis"] = build_ratio_results_response(result, alpha).model_dump()
    # Anytime-valid view over the same ratio difference Δ and its delta-method variance.
    base["always_valid"] = _always_valid_block(
        result["effect"], result["variance"], mixture_variance, alpha
    )
    return base


def _build_ratio_comparisons(
    *,
    ratio_aggregates: dict[str, Any] | None,
    variants_count: int,
    alpha: float,
    mixture_variance: float | None,
) -> list[dict[str, Any]]:
    by_index = {
        int(item["variation_index"]): item
        for item in (ratio_aggregates or {}).get("variations", [])
    }
    arms = [by_index.get(index, _empty_ratio_arm(index)) for index in range(variants_count)]
    return [
        _build_ratio_comparison(arms[0], arms[treatment_index], alpha, mixture_variance)
        for treatment_index in range(1, variants_count)
    ]

def _build_sequential_block(
    *,
    project_payload: dict[str, Any],
    n_looks: int,
    variants_count: int,
    total_exposed: int,
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    if n_looks <= 1:
        # A fixed-horizon design has no boundary to place, but the planned sample size still
        # matters: it tells the decision readout whether the current read *is* the planned single
        # read or an early peek (see services.decision_service). Sizing can be unavailable for a
        # design (e.g. a legacy ratio design without std_dev) — then the fraction stays None and
        # the decision falls back to treating the read as the planned one.
        planned_per_variant: int | None = None
        information_fraction: float | None = None
        try:
            calculation = calculate_experiment_metrics(_calc_payload_from_design(project_payload))
            planned_per_variant = (
                int((calculation.get("results") or {}).get("sample_size_per_variant") or 0) or None
            )
        except (ValueError, KeyError):
            planned_per_variant = None
        if planned_per_variant is not None:
            information_fraction = round(
                min(1.0, total_exposed / (planned_per_variant * variants_count)), 4
            )
        return {
            "status": "fixed_horizon",
            "n_looks": n_looks,
            "planned_sample_size_per_variant": planned_per_variant,
            "total_exposed": total_exposed,
            "information_fraction": information_fraction,
            "note": translate("live_stats.sequential.fixed_horizon"),
        }

    try:
        calculation = calculate_experiment_metrics(_calc_payload_from_design(project_payload))
    except (ValueError, KeyError):
        # Some legacy or partially specified designs still cannot produce a planned sample size.
        # Without that denominator the sequential boundary cannot be placed, so report insufficient
        # data rather than crash the whole live read; the frequentist comparison stays valid at the
        # planned horizon.
        return {
            "status": "insufficient_data",
            "n_looks": n_looks,
            "planned_sample_size_per_variant": None,
            "total_exposed": total_exposed,
            "note": translate("live_stats.sequential.unsupported_metric"),
        }
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
            "note": translate("live_stats.sequential.insufficient_data"),
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
        "note": translate("live_stats.sequential.active"),
    }


# --- CUPED on live data (E5 single covariate, F3a multi-covariate) ---------------------------
#
# CUPED (Deng et al. 2013) reduces variance using pre-experiment covariates X that are correlated
# with the outcome Y but, being measured *before* assignment, are independent of the treatment.
# With a covariate vector X = (X_1, ..., X_k) the adjusted outcome is the regression (ANCOVA) form
#
#     Y_adj = Y - theta^T (X - mean(X)),   theta = Sigma_xx^{-1} Sigma_xy   (normal equations)
#
# estimated on the pooled data (pooling is unbiased because X is pre-treatment). Subtracting the
# global mean(X) keeps E[Y_adj] = E[Y], so the treatment-effect estimate is unchanged in
# expectation while its variance drops by a factor of (1 - R^2), R^2 the regression fit. For k = 1
# this is exactly the E5 single-covariate CUPED (theta = cov(X, Y) / var(X)).
#
# No per-user loop is needed: from the per-arm sufficient statistics (n, sum_y, sum_y2 and, over
# the covariate vector, sum_x[], sum_xy[], sum_xx[][]) the adjusted arm mean and variance follow
# in closed form
#
#     mean(Y_adj)_a = mean(Y)_a - theta^T (mean(X)_a - global mean(X))
#     var(Y_adj)_a  = var(Y)_a - 2*theta^T Sigma_xy_a + theta^T Sigma_xx_a theta
#
# (the centering constant does not affect variance; the pooled theta meets each arm's own
# moments). Those per-arm adjusted moments feed the existing continuous t-test (``analyze_results``)
# — no new test statistic here. The linear algebra lives in ``stats.cuped`` (stdlib).
