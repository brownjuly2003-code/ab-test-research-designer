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

- **CUPED**             variance reduction with one or more ingested per-user pre-period
                        covariates (``stats.cuped``); marked unavailable until a covariate is
                        ingested. Continuous Bayesian is out of MVP scope (frequentist supported).
"""

from __future__ import annotations

import math
from typing import Any, cast

from app.backend.app.execution.experiment_assignment import normalize_weights
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
from app.backend.app.stats import cuped, stratification
from app.backend.app.stats.always_valid import (
    default_mixture_variance,
    evaluate_always_valid,
)
from app.backend.app.stats.guardrail import (
    INCREASE_IS_BAD,
    STATUS_BREACHED,
    STATUS_OK,
    STATUS_WARNING,
    evaluate_guardrail,
    worst_status,
)
from app.backend.app.stats.ratio import compare_ratios, ratio_estimate
from app.backend.app.stats.srm import chi_square_srm

_BAYESIAN_SIMULATIONS = 10000
_BAYESIAN_SEED = 42
# P(treatment > control) is a Monte-Carlo estimate. With 10k draws its standard
# error is sqrt(p(1-p)/N) <= sqrt(0.25/10000) = 0.005, so anything past the third
# decimal is simulation noise, not signal. Round there to avoid reporting false
# precision (e.g. 0.732518 implying 6-digit certainty from a +/-0.5% estimate).
_BAYESIAN_PROBABILITY_DECIMALS = 3


def build_live_stats(
    experiment_id: str,
    project_payload: dict[str, Any],
    aggregates: dict[str, Any],
    cuped_aggregates: dict[str, Any] | None = None,
    ratio_aggregates: dict[str, Any] | None = None,
    stratified_aggregates: dict[str, Any] | None = None,
    guardrail_aggregates: dict[str, Any] | None = None,
    holdout_aggregates: dict[str, Any] | None = None,
    event_timing_summary: dict[str, Any] | None = None,
    identity_resolution_summary: dict[str, Any] | None = None,
    exclusion_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the live-stats payload from a stored experiment design and the current
    per-variation analysis aggregates (``repository.get_experiment_analysis_aggregates``).

    ``cuped_aggregates`` (``repository.get_cuped_aggregates``) carries the per-variation CUPED
    sufficient statistics over users with a pre-period covariate; ``None`` / empty keeps the
    CUPED block ``unavailable``.

    ``ratio_aggregates`` (``repository.get_ratio_aggregates``) carries the per-variation ratio
    sufficient statistics (numerator/denominator per user); it drives the comparisons when the
    design's ``metric_type`` is ``ratio`` (delta method) and is ignored otherwise.

    ``guardrail_aggregates`` maps each declared guardrail metric name to its per-variation analysis
    aggregates (same shape as ``aggregates``, one entry per guardrail); ``None`` / empty keeps the
    guardrail block ``unavailable``.

    ``holdout_aggregates`` (``repository.get_holdout_aggregates``) carries the held-back
    (``variation_index = -1``) group's rollup for the cumulative treated-vs-holdout read; ``None`` /
    no holdout users keeps the holdout block ``unavailable``.

    ``event_timing_summary`` (``repository.get_event_timing_summary``) carries the late /
    out-of-order conversion counts on the primary metric (P4.2); ``None`` keeps the event-timing
    block ``unavailable``. It is informational only — it does not change any comparison or verdict.

    ``identity_resolution_summary`` (``repository.get_identity_resolution_summary``) carries the
    anonymous → canonical link counts (P4.3); ``None`` / no links keeps the block ``inactive``. The
    resolution itself already happened inside the primary rollup — this block only reports it.

    ``exclusion_summary`` (``repository.get_exclusion_summary``) carries the bot / fraud filter counts
    (P4.4 — manual deny-list + rate-spike); ``None`` / nothing filtered keeps the block ``inactive``.
    The exclusion already happened inside the primary rollup — this block only reports it."""
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

    # Family-wise error control at analysis time, mirroring the planning side (stats.binary /
    # stats.continuous Bonferroni): every control-vs-treatment test runs at alpha / (#treatments),
    # so the live readout's false-positive rate matches the alpha the sample size was planned for.
    # One treatment -> adjusted == nominal, so two-variant experiments are unchanged.
    comparison_count = max(1, variants_count - 1)
    adjusted_alpha = alpha / comparison_count

    # Mixing variance tau^2 for the anytime-valid (mSPRT) view, derived from the design's MDE so it
    # is fixed *before* any data is seen (a precondition for the anytime-valid guarantee) and
    # concentrates power around the effect the experiment was sized for. None -> per-comparison
    # fallback to the observed variance scale (only when the design carries no usable MDE).
    expected_effect = _expected_absolute_effect(baseline_value, metrics)
    design_mixture_variance = (
        default_mixture_variance(expected_effect) if expected_effect else None
    )

    srm = _build_srm_block(arms, expected_fractions)
    if metric_type == "ratio":
        comparisons = _build_ratio_comparisons(
            ratio_aggregates=ratio_aggregates,
            variants_count=variants_count,
            alpha=adjusted_alpha,
            mixture_variance=design_mixture_variance,
        )
    else:
        comparisons = [
            _build_comparison(
                metric_type=metric_type,
                baseline_value=baseline_value,
                alpha=adjusted_alpha,
                control=arms[0],
                treatment=arms[treatment_index],
                mixture_variance=design_mixture_variance,
            )
            for treatment_index in range(1, variants_count)
        ]
    if comparison_count > 1:
        _annotate_multiple_comparison(comparisons, alpha, adjusted_alpha, comparison_count)
    sequential = _build_sequential_block(
        project_payload=project_payload,
        n_looks=n_looks,
        variants_count=variants_count,
        total_exposed=exposures_total,
        comparisons=comparisons,
    )
    cuped = _build_cuped_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        variants_count=variants_count,
        exposed_total=exposures_total,
        cuped_aggregates=cuped_aggregates,
    )
    if comparison_count > 1:
        _annotate_multiple_comparison(
            cuped.get("comparisons", []), alpha, adjusted_alpha, comparison_count
        )
    stratified = _build_stratified_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        variants_count=variants_count,
        exposed_total=exposures_total,
        stratified_aggregates=stratified_aggregates,
    )
    guardrail = _build_guardrail_block(
        guardrail_metrics=metrics.get("guardrail_metrics", []),
        guardrail_aggregates=guardrail_aggregates,
        variants_count=variants_count,
        alpha=adjusted_alpha,
    )
    holdout = _build_holdout_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        arms=arms,
        holdout_aggregates=holdout_aggregates,
        mixture_variance=design_mixture_variance,
    )
    event_timing = _build_event_timing_block(event_timing_summary)
    identity_resolution = _build_identity_resolution_block(identity_resolution_summary)
    exclusions = _build_exclusion_block(exclusion_summary)

    return {
        "experiment_id": experiment_id,
        "metric_type": metric_type,
        "primary_metric_name": primary_metric_name,
        "exposures_total": exposures_total,
        "conversions_total": conversions_total,
        "disclaimer": translate("live_stats.disclaimer"),
        "srm": srm,
        "comparisons": comparisons,
        "sequential": sequential,
        "cuped": cuped,
        "stratified": stratified,
        "guardrail": guardrail,
        "holdout": holdout,
        "event_timing": event_timing,
        "identity_resolution": identity_resolution,
        "exclusions": exclusions,
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


def _annotate_multiple_comparison(
    comparisons: list[dict[str, Any]],
    nominal_alpha: float,
    adjusted_alpha: float,
    comparison_count: int,
) -> None:
    """Record the Bonferroni context on each evaluable comparison so the adjusted significance and
    confidence interval are transparent. The live tests already ran at ``adjusted_alpha`` (see
    ``build_live_stats``); this only annotates the ``ok`` comparisons, leaving the insufficient-data
    notes intact."""
    note = translate(
        "live_stats.comparison.bonferroni_note",
        {
            "adjusted_alpha": f"{adjusted_alpha:.6g}",
            "comparison_count": comparison_count,
            "nominal_alpha": f"{nominal_alpha:.6g}",
        },
    )
    for comparison in comparisons:
        if comparison.get("status") == "ok":
            comparison["note"] = note


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


_ALWAYS_VALID_DECIMALS = 6


def _always_valid_block(
    effect: float,
    variance: float,
    mixture_variance: float | None,
    alpha: float,
) -> dict[str, Any]:
    """mSPRT anytime-valid p-value + confidence sequence for one comparison.

    ``mixture_variance`` (tau^2) comes from the design MDE when available; otherwise it falls back
    to the observed variance scale so the block still renders. A degenerate (zero) variance — both
    arms fully (non-)converting — leaves the block ``not_evaluable``.
    """
    tau_squared = mixture_variance if (mixture_variance and mixture_variance > 0) else variance
    if variance <= 0 or tau_squared <= 0:
        return {
            "status": "not_evaluable",
            "always_valid_p_value": None,
            "confidence_level": None,
            "ci_sequence_lower": None,
            "ci_sequence_upper": None,
            "is_significant": None,
            "mixture_variance": None,
            "note": translate("live_stats.always_valid.not_evaluable"),
        }
    result = evaluate_always_valid(effect, variance, tau_squared, alpha)
    return {
        "status": "ok",
        "always_valid_p_value": round(result["always_valid_p_value"], _ALWAYS_VALID_DECIMALS),
        "confidence_level": round(result["confidence_level"], _ALWAYS_VALID_DECIMALS),
        "ci_sequence_lower": round(result["ci_sequence_lower"], _ALWAYS_VALID_DECIMALS),
        "ci_sequence_upper": round(result["ci_sequence_upper"], _ALWAYS_VALID_DECIMALS),
        "is_significant": result["is_significant"],
        "mixture_variance": round(tau_squared, 8),
        "note": translate("live_stats.always_valid.ok"),
    }


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


def _expected_absolute_effect(
    baseline_value: float,
    metrics: dict[str, Any],
) -> float | None:
    """Absolute effect the experiment was sized for, used to derive the mSPRT mixing variance.

    MDE is a relative uplift over the baseline (rate for binary, mean for continuous), so the
    absolute scale is ``baseline_value * mde_pct / 100``. Returns ``None`` when the design carries
    no usable MDE/baseline (then the always-valid block falls back to the observed scale)."""
    mde_pct = metrics.get("mde_pct")
    if mde_pct is None or baseline_value <= 0:
        return None
    try:
        mde = float(mde_pct)
    except (TypeError, ValueError):
        return None
    if mde <= 0:
        return None
    return baseline_value * (mde / 100.0)


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
        # Sizing is not yet available for every metric type (e.g. ratio metrics, whose sample-size
        # planning is a later sub-phase). Without a planned sample size the boundary cannot be
        # placed, so report insufficient data rather than crash the whole live read; the
        # frequentist comparison stays valid at the planned horizon.
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


def _multi_moments(
    n: int,
    sum_y: float,
    sum_y2: float,
    sum_x: list[float],
    sum_xy: list[float],
    sum_xx: list[list[float]],
) -> dict[str, Any] | None:
    """Means, outcome variance, the covariate covariance matrix ``Sigma_xx`` and the
    covariate/outcome covariance vector ``Sigma_xy`` from pooled sufficient statistics, or
    ``None`` when there are fewer than 2 observations (a sample variance is undefined)."""
    if n < 2:
        return None
    k = len(sum_x)
    mean_y = sum_y / n
    mean_x = [value / n for value in sum_x]
    var_y = (sum_y2 - n * mean_y * mean_y) / (n - 1)
    sigma_xy = [(sum_xy[j] - n * mean_x[j] * mean_y) / (n - 1) for j in range(k)]
    sigma_xx = [
        [(sum_xx[i][j] - n * mean_x[i] * mean_x[j]) / (n - 1) for j in range(k)]
        for i in range(k)
    ]
    return {
        "n": n,
        "mean_y": mean_y,
        "mean_x": mean_x,
        "var_y": var_y,
        "sigma_xy": sigma_xy,
        "sigma_xx": sigma_xx,
    }


def _pool_sufficient(arms: list[dict[str, Any]], k: int) -> dict[str, Any]:
    """Sum per-arm sufficient statistics into pooled totals (X is pre-treatment, so pooling
    across arms is unbiased)."""
    total_n = 0
    sum_y = 0.0
    sum_y2 = 0.0
    sum_x = [0.0] * k
    sum_xy = [0.0] * k
    sum_xx = [[0.0] * k for _ in range(k)]
    for arm in arms:
        total_n += int(arm["n"])
        sum_y += float(arm["sum_y"])
        sum_y2 += float(arm["sum_y2"])
        for i in range(k):
            sum_x[i] += float(arm["sum_x"][i])
            sum_xy[i] += float(arm["sum_xy"][i])
            for j in range(k):
                sum_xx[i][j] += float(arm["sum_xx"][i][j])
    return {
        "n": total_n,
        "sum_y": sum_y,
        "sum_y2": sum_y2,
        "sum_x": sum_x,
        "sum_xy": sum_xy,
        "sum_xx": sum_xx,
    }


def _cuped_arm_stat(
    arm: dict[str, Any] | None,
    index: int,
    theta: list[float],
    global_mean_x: list[float],
) -> dict[str, Any]:
    n = int(arm["n"]) if arm else 0
    if n == 0 or arm is None:
        return {
            "variation_index": index,
            "covariate_users": 0,
            "unadjusted_mean": None,
            "adjusted_mean": None,
            "adjusted_std": None,
        }
    k = len(theta)
    mean_x = [arm["sum_x"][j] / n for j in range(k)]
    mean_y = arm["sum_y"] / n
    adjusted_mean = mean_y - cuped.dot(theta, [mean_x[j] - global_mean_x[j] for j in range(k)])
    adjusted_std: float | None = None
    arm_moments = _multi_moments(
        n, arm["sum_y"], arm["sum_y2"], arm["sum_x"], arm["sum_xy"], arm["sum_xx"]
    )
    if arm_moments is not None:
        adjusted_var = cuped.adjusted_variance(
            arm_moments["var_y"], theta, arm_moments["sigma_xy"], arm_moments["sigma_xx"]
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
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base
    if not control["adjusted_std"] or not treatment["adjusted_std"]:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.zero_variance")
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
    empty: dict[str, Any] = {
        "theta": None,
        "num_covariates": None,
        "covariates": [],
        "variance_reduction_pct": None,
        "covariate_users_total": None,
        "exposed_users_total": None,
        "comparisons": [],
    }
    if metric_type != "continuous":
        return {"status": "not_applicable", "note": translate("live_stats.cuped.not_applicable"), **empty}

    aggregates = cuped_aggregates or {}
    if aggregates.get("too_many_covariates"):
        return {
            "status": "too_many_covariates",
            "note": translate("live_stats.cuped.too_many"),
            **empty,
            "num_covariates": len(aggregates.get("covariate_names", [])),
            "exposed_users_total": exposed_total,
        }

    covariate_names = list(aggregates.get("covariate_names", []))
    k = len(covariate_names)
    by_index = {int(item["variation_index"]): item for item in aggregates.get("variations", [])}
    covariate_users_total = sum(int(item["n"]) for item in by_index.values())
    if k == 0 or covariate_users_total == 0:
        return {
            "status": "unavailable",
            "note": translate("live_stats.cuped.unavailable"),
            **empty,
            "num_covariates": k or None,
            "covariate_users_total": 0,
            "exposed_users_total": exposed_total,
        }

    sums = _pool_sufficient(list(by_index.values()), k)
    pooled = _multi_moments(
        sums["n"], sums["sum_y"], sums["sum_y2"], sums["sum_x"], sums["sum_xy"], sums["sum_xx"]
    )
    # theta needs an invertible Sigma_xx; collinear / constant covariates carry no usable signal
    # -> theta = 0 vector (CUPED collapses to the unadjusted estimate).
    if pooled is None:
        theta = [0.0] * k
        global_mean_x = [0.0] * k
    else:
        global_mean_x = pooled["mean_x"]
        solved = cuped.cuped_theta(pooled["sigma_xx"], pooled["sigma_xy"])
        theta = solved if solved is not None else [0.0] * k

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
        adjusted_var = cuped.adjusted_variance(
            pooled["var_y"], theta, pooled["sigma_xy"], pooled["sigma_xx"]
        )
        variance_reduction_pct = round((1 - adjusted_var / pooled["var_y"]) * 100, 4)

    covariates = [{"name": covariate_names[j], "theta": round(theta[j], 6)} for j in range(k)]
    return {
        "status": "available",
        "note": translate("live_stats.cuped.available"),
        # Single-covariate convenience (backward compatible); the vector lives in `covariates`.
        "theta": round(theta[0], 6) if k == 1 else None,
        "num_covariates": k,
        "covariates": covariates,
        "variance_reduction_pct": variance_reduction_pct,
        "covariate_users_total": covariate_users_total,
        "exposed_users_total": exposed_total,
        "comparisons": comparisons,
    }


# --- Post-stratification on live data (F3b) --------------------------------------------------
#
# Post-stratification splits the exposed users into strata of a categorical attribute known at
# assignment time (ingested via POST .../strata), estimates the control-vs-treatment effect within
# each stratum, and recombines the per-stratum effects weighted by stratum size:
#
#     w_s = N_s / N,   Δ = Σ_s w_s·Δ_s,   Var(Δ) = Σ_s w_s²·Var(Δ_s)
#
# (the conditional post-stratification estimator — Miratrix, Sekhon & Yu 2013). When the stratum
# explains outcome variation the between-strata variation leaves the estimator's error and the
# effect estimate gets more precise. Each per-stratum effect/variance reuses the same unpooled
# binary (p(1−p)/n) or continuous (s²/n) moments as the main comparison — no new statistic. The
# size-weighted combine + z-test live in ``stats.stratification`` (stdlib). Supported for binary and
# continuous metrics; a ratio metric has no single per-user outcome the combine reads.



def _stratum_arm_estimate(metric_type: str, arm: dict[str, Any]) -> tuple[float, float] | None:
    """``(point estimate, variance of that estimate)`` for one stratum arm, or ``None`` when the arm
    has fewer than 2 users (too small to contribute a per-stratum effect variance)."""
    n = int(arm["exposed_users"])
    if n < 2:
        return None
    if metric_type == "binary":
        return stratification.binary_point_variance(int(arm["converted_users"]), n)
    return stratification.continuous_point_variance(
        float(arm["value_sum"]), float(arm["value_sq_sum"]), n
    )


def _empty_stratum_arm() -> dict[str, Any]:
    return {"exposed_users": 0, "converted_users": 0, "value_sum": 0.0, "value_sq_sum": 0.0}


def _accumulate_stratum_arm(target: dict[str, Any], arm: dict[str, Any]) -> None:
    target["exposed_users"] += int(arm["exposed_users"])
    target["converted_users"] += int(arm["converted_users"])
    target["value_sum"] += float(arm["value_sum"])
    target["value_sq_sum"] += float(arm["value_sq_sum"])


def _stratified_comparison(
    metric_type: str,
    strata: list[dict[str, Any]],
    treatment_index: int,
    alpha: float,
) -> dict[str, Any]:
    strata_effects: list[dict[str, Any]] = []
    combine_input: list[dict[str, Any]] = []
    pooled_control = _empty_stratum_arm()
    pooled_treatment = _empty_stratum_arm()
    for stratum in strata:
        by_index = {int(arm["variation_index"]): arm for arm in stratum.get("variations", [])}
        control = by_index.get(0)
        treatment = by_index.get(treatment_index)
        control_n = int(control["exposed_users"]) if control else 0
        treatment_n = int(treatment["exposed_users"]) if treatment else 0
        if control is not None:
            _accumulate_stratum_arm(pooled_control, control)
        if treatment is not None:
            _accumulate_stratum_arm(pooled_treatment, treatment)
        delta: float | None = None
        if control is not None and treatment is not None:
            control_estimate = _stratum_arm_estimate(metric_type, control)
            treatment_estimate = _stratum_arm_estimate(metric_type, treatment)
            if control_estimate is not None and treatment_estimate is not None:
                difference = stratification.stratum_difference(control_estimate, treatment_estimate)
                delta = difference["delta"]
                combine_input.append(
                    {
                        "n": control_n + treatment_n,
                        "delta": difference["delta"],
                        "variance": difference["variance"],
                    }
                )
        strata_effects.append(
            {
                "stratum": str(stratum["stratum"]),
                "users": control_n + treatment_n,
                "control_users": control_n,
                "treatment_users": treatment_n,
                "effect": round(delta, 6) if delta is not None else None,
            }
        )

    base: dict[str, Any] = {
        "treatment_index": treatment_index,
        "status": "insufficient_data",
        "effect": None,
        "standard_error": None,
        "test_statistic": None,
        "p_value": None,
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": None,
        "is_significant": None,
        "variance_reduction_pct": None,
        "num_strata": None,
        "strata": strata_effects,
        "note": translate("live_stats.stratified.insufficient_data"),
    }
    combined = stratification.combine_strata(combine_input, alpha) if combine_input else None
    if combined is None:
        return base

    # Variance reduction vs the naive estimate that ignores strata, over the *same* covered users
    # (pool every stratum into one control/treatment arm) — an apples-to-apples comparison.
    variance_reduction: float | None = None
    pooled_control_estimate = _stratum_arm_estimate(metric_type, pooled_control)
    pooled_treatment_estimate = _stratum_arm_estimate(metric_type, pooled_treatment)
    if pooled_control_estimate is not None and pooled_treatment_estimate is not None:
        pooled_variance = pooled_control_estimate[1] + pooled_treatment_estimate[1]
        variance_reduction = stratification.variance_reduction_pct(
            pooled_variance, combined["variance"]
        )

    return {
        "treatment_index": treatment_index,
        "status": "ok",
        "effect": round(combined["effect"], 6),
        "standard_error": round(combined["standard_error"], 6),
        "test_statistic": round(combined["test_statistic"], 6),
        "p_value": round(combined["p_value"], 6),
        "ci_lower": round(combined["ci_lower"], 6),
        "ci_upper": round(combined["ci_upper"], 6),
        "ci_level": round(combined["ci_level"], 6),
        "is_significant": combined["is_significant"],
        "variance_reduction_pct": (
            round(variance_reduction, 4) if variance_reduction is not None else None
        ),
        "num_strata": combined["num_strata"],
        "strata": strata_effects,
        "note": None,
    }


def _build_stratified_block(
    *,
    metric_type: str,
    alpha: float,
    variants_count: int,
    exposed_total: int,
    stratified_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "num_strata": None,
        "stratified_users_total": None,
        "exposed_users_total": None,
        "comparisons": [],
    }
    if metric_type not in ("binary", "continuous"):
        return {"status": "unavailable", "note": translate("live_stats.stratified.not_applicable"), **empty}

    aggregates = stratified_aggregates or {}
    if aggregates.get("too_many_strata"):
        return {
            "status": "too_many_strata",
            "note": translate("live_stats.stratified.too_many"),
            **empty,
            "num_strata": aggregates.get("num_strata"),
            "exposed_users_total": exposed_total,
        }

    strata = list(aggregates.get("strata", []))
    covered_total = sum(
        int(arm["exposed_users"]) for stratum in strata for arm in stratum.get("variations", [])
    )
    if not strata or covered_total == 0:
        return {
            "status": "unavailable",
            "note": translate("live_stats.stratified.unavailable"),
            **empty,
            "num_strata": len(strata) or None,
            "stratified_users_total": 0,
            "exposed_users_total": exposed_total,
        }

    comparisons = [
        _stratified_comparison(metric_type, strata, treatment_index, alpha)
        for treatment_index in range(1, variants_count)
    ]
    return {
        "status": "available",
        "note": translate("live_stats.stratified.available"),
        "num_strata": len(strata),
        "stratified_users_total": covered_total,
        "exposed_users_total": exposed_total,
        "comparisons": comparisons,
    }


# --- Guardrail metrics on live data (F4) -----------------------------------------------------
#
# A guardrail metric must not be harmed by the treatment. Unlike the two-sided primary test, each
# guardrail is checked with a *directed* one-sided breach test (``stats.guardrail``): the harm is the
# treatment−control difference signed by the guardrail's harm direction, its variance is the same
# unpooled (binary p(1−p)/n) / Welch (continuous s²/n) variance the primary comparison uses, and a
# breach is a statistically significant degradation beyond an optional tolerance margin. Guardrail
# outcomes are ingested through the ordinary conversion stream (one conversion metric per guardrail
# name) and rolled up by ``repository.get_experiment_analysis_aggregates`` per guardrail — no new
# store and no new test statistic. A breach feeds the decision readout as a ship blocker.


def _guardrail_baseline(metric: dict[str, Any]) -> float | None:
    """Design baseline of a guardrail in natural units: the rate (``baseline_rate`` is a percent) for
    a binary guardrail, the mean for a continuous one. ``None`` when the design omits it (then no
    relative margin can be scaled and the margin falls back to 0)."""
    if metric.get("metric_type") == "binary":
        baseline_rate = metric.get("baseline_rate")
        return float(baseline_rate) / 100.0 if baseline_rate is not None else None
    baseline_mean = metric.get("baseline_mean")
    return float(baseline_mean) if baseline_mean is not None else None


def _guardrail_margin_abs(metric: dict[str, Any]) -> float:
    """Tolerated degradation in natural units = baseline · margin_pct/100; 0 when no margin (any
    significant degradation breaches) or no usable baseline to scale a relative margin against."""
    margin_pct = metric.get("non_inferiority_margin_pct")
    if margin_pct is None:
        return 0.0
    baseline = _guardrail_baseline(metric)
    if baseline is None:
        return 0.0
    return abs(baseline) * float(margin_pct) / 100.0


def _guardrail_point(metric_type: str, arm: dict[str, Any]) -> tuple[float, float] | None:
    """``(point estimate, variance of that estimate)`` for one guardrail arm, or ``None`` when the
    arm has fewer than 2 exposed users. Reuses the same unpooled binary / continuous moments as
    post-stratification — no new statistic."""
    n = int(arm["exposed_users"])
    if n < 2:
        return None
    if metric_type == "binary":
        return stratification.binary_point_variance(int(arm["converted_users"]), n)
    return stratification.continuous_point_variance(
        float(arm["value_sum"]), float(arm["value_sq_sum"]), n
    )


def _guardrail_arm_stat(metric_type: str, arm: dict[str, Any]) -> dict[str, Any]:
    point = _guardrail_point(metric_type, arm)
    return {
        "variation_index": int(arm["variation_index"]),
        "exposed_users": int(arm["exposed_users"]),
        "point_estimate": round(point[0], 6) if point is not None else None,
    }


def _guardrail_comparison(
    *,
    metric_type: str,
    direction: str,
    margin_abs: float,
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "treatment_index": int(treatment["variation_index"]),
        "control": _guardrail_arm_stat(metric_type, control),
        "treatment": _guardrail_arm_stat(metric_type, treatment),
        "effect": None,
        "harm": None,
        "harm_lower_bound": None,
        "margin": round(margin_abs, 8),
        "p_value": None,
        "is_breached": None,
        "note": None,
    }
    control_point = _guardrail_point(metric_type, control)
    treatment_point = _guardrail_point(metric_type, treatment)
    if control_point is None or treatment_point is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.guardrail.insufficient_data")
        return base
    effect = treatment_point[0] - control_point[0]
    variance = control_point[1] + treatment_point[1]
    result = evaluate_guardrail(
        effect, variance, direction=direction, margin=margin_abs, alpha=alpha
    )
    if result is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.guardrail.zero_variance")
        return base
    base["status"] = result["status"]
    base["effect"] = round(effect, 6)
    base["harm"] = round(result["harm"], 6)
    base["harm_lower_bound"] = round(result["harm_lower_bound"], 6)
    base["p_value"] = round(result["p_value"], 6)
    base["is_breached"] = result["is_breached"]
    return base


def _guardrail_metric_result(
    *,
    metric: dict[str, Any],
    aggregates: dict[str, Any] | None,
    variants_count: int,
    alpha: float,
) -> dict[str, Any]:
    metric_type = str(metric.get("metric_type", "binary"))
    direction = str(metric.get("direction", INCREASE_IS_BAD))
    margin_abs = _guardrail_margin_abs(metric)
    by_index = {
        int(item["variation_index"]): item
        for item in (aggregates or {}).get("variations", [])
    }
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
    comparisons = [
        _guardrail_comparison(
            metric_type=metric_type,
            direction=direction,
            margin_abs=margin_abs,
            alpha=alpha,
            control=arms[0],
            treatment=arms[treatment_index],
        )
        for treatment_index in range(1, variants_count)
    ]
    evaluated = [c["status"] for c in comparisons if c["status"] != "insufficient_data"]
    status = worst_status(evaluated) if evaluated else "insufficient_data"
    margin_pct = metric.get("non_inferiority_margin_pct")
    return {
        "name": str(metric.get("name", "")),
        "metric_type": metric_type,
        "direction": direction,
        "margin_pct": float(margin_pct) if margin_pct is not None else None,
        "status": status,
        "comparisons": comparisons,
    }


def _build_guardrail_block(
    *,
    guardrail_metrics: list[dict[str, Any]],
    guardrail_aggregates: dict[str, Any] | None,
    variants_count: int,
    alpha: float,
) -> dict[str, Any]:
    if not guardrail_metrics:
        return {
            "status": "unavailable",
            "note": translate("live_stats.guardrail.none"),
            "any_breached": False,
            "metrics": [],
        }

    aggregates_by_name = guardrail_aggregates or {}
    metrics = [
        _guardrail_metric_result(
            metric=metric,
            aggregates=aggregates_by_name.get(str(metric.get("name", ""))),
            variants_count=variants_count,
            alpha=alpha,
        )
        for metric in guardrail_metrics
    ]
    evaluated = [m["status"] for m in metrics if m["status"] != "insufficient_data"]
    any_breached = any(m["status"] == STATUS_BREACHED for m in metrics)
    if not evaluated:
        return {
            "status": "unavailable",
            "note": translate("live_stats.guardrail.unavailable"),
            "any_breached": False,
            "metrics": metrics,
        }
    block_status = worst_status(evaluated)
    note = {
        STATUS_BREACHED: translate("live_stats.guardrail.breached"),
        STATUS_WARNING: translate("live_stats.guardrail.warning"),
        STATUS_OK: translate("live_stats.guardrail.ok"),
    }[block_status]
    return {
        "status": block_status,
        "note": note,
        "any_breached": any_breached,
        "metrics": metrics,
    }


# --- Holdout groups on live data (F5) --------------------------------------------------------
#
# A holdout is a long-lived group held back from the rollout (variation_index = -1). The cumulative
# read compares the *pooled treated arms* (variation_index >= 1) against the holdout on the primary
# metric: it answers "what is the standing effect of everything we rolled out, vs users who got
# nothing" — distinct from the per-variant primary test, and a check on the winner's-curse tendency
# of summed individual wins to overstate reality. Pooling the treatment arms is a sum of sufficient
# statistics; the treated-vs-holdout effect then reuses the same two-proportion / Welch test
# (``analyze_results``), Bayesian P(B>A) (``simulate_uplift_distribution``) and anytime-valid view the
# primary path uses — no new statistic. The control arm (variation_index = 0) stays out of the treated
# pool: it is the in-window baseline, whereas the holdout is the long-lived held-back group. Supported
# for binary and continuous metrics; a ratio metric has no single per-user outcome the pool reads.


def _pool_treated_arms(arms: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold the treatment arms (variation_index >= 1) into one pooled treated arm by summing their
    sufficient statistics. The control arm (index 0) is excluded — it is the in-window baseline, not
    part of the rolled-out treatment."""
    pooled = {"exposed_users": 0, "converted_users": 0, "value_sum": 0.0, "value_sq_sum": 0.0}
    for arm in arms[1:]:
        pooled["exposed_users"] += int(arm["exposed_users"])
        pooled["converted_users"] += int(arm["converted_users"])
        pooled["value_sum"] += float(arm["value_sum"])
        pooled["value_sq_sum"] += float(arm["value_sq_sum"])
    return pooled


def _holdout_arm_stat(metric_type: str, arm: dict[str, Any], label: str) -> dict[str, Any]:
    exposed = int(arm["exposed_users"])
    stat: dict[str, Any] = {
        "label": label,
        "exposed_users": exposed,
        "converted_users": int(arm["converted_users"]),
    }
    if metric_type == "binary":
        stat["conversion_rate"] = (
            round(int(arm["converted_users"]) / exposed, 6) if exposed else None
        )
    else:
        mean, std = _continuous_moments(arm)
        stat["mean"] = round(mean, 6) if mean is not None else None
        stat["std"] = round(std, 6) if std is not None else None
    return stat


def _holdout_binary(
    base: dict[str, Any],
    alpha: float,
    holdout: dict[str, Any],
    treated: dict[str, Any],
    mixture_variance: float | None,
) -> dict[str, Any]:
    holdout_rate = int(holdout["converted_users"]) / int(holdout["exposed_users"])
    treated_rate = int(treated["converted_users"]) / int(treated["exposed_users"])
    request = ResultsRequest(
        metric_type="binary",
        binary=ObservedResultsBinary(
            control_conversions=int(holdout["converted_users"]),
            control_users=int(holdout["exposed_users"]),
            treatment_conversions=int(treated["converted_users"]),
            treatment_users=int(treated["exposed_users"]),
            alpha=alpha,
        ),
    )
    analysis = analyze_results(request)
    simulation = simulate_uplift_distribution(
        baseline_conversion=holdout_rate,
        observed_conversion_a=holdout_rate,
        sample_size_a=int(holdout["exposed_users"]),
        observed_conversion_b=treated_rate,
        sample_size_b=int(treated["exposed_users"]),
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    # holdout is the baseline (A), the pooled treated arms the treatment (B): a positive effect means
    # the rollout improved the metric over holding users back. Same unpooled variance as the primary.
    effect = treated_rate - holdout_rate
    variance = holdout_rate * (1 - holdout_rate) / int(holdout["exposed_users"]) + (
        treated_rate * (1 - treated_rate) / int(treated["exposed_users"])
    )
    base["status"] = "ok"
    base["note"] = translate("live_stats.holdout.ok")
    base["analysis"] = analysis.model_dump()
    base["probability_treated_beats_holdout"] = round(
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


def _holdout_continuous(
    base: dict[str, Any],
    alpha: float,
    holdout: dict[str, Any],
    treated: dict[str, Any],
    mixture_variance: float | None,
) -> dict[str, Any]:
    holdout_mean, holdout_std = _continuous_moments(holdout)
    treated_mean, treated_std = _continuous_moments(treated)
    if not holdout_std or not treated_std:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.holdout.zero_variance")
        return base
    holdout_mean = cast("float", holdout_mean)
    treated_mean = cast("float", treated_mean)
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=holdout_mean,
            control_std=holdout_std,
            control_n=int(holdout["exposed_users"]),
            treatment_mean=treated_mean,
            treatment_std=treated_std,
            treatment_n=int(treated["exposed_users"]),
            alpha=alpha,
        ),
    )
    simulation = simulate_continuous_uplift_distribution(
        control_mean=holdout_mean,
        control_std=holdout_std,
        control_n=int(holdout["exposed_users"]),
        treatment_mean=treated_mean,
        treatment_std=treated_std,
        treatment_n=int(treated["exposed_users"]),
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    effect = treated_mean - holdout_mean
    variance = (
        holdout_std**2 / int(holdout["exposed_users"])
        + treated_std**2 / int(treated["exposed_users"])
    )
    base["status"] = "ok"
    base["note"] = translate("live_stats.holdout.ok")
    base["analysis"] = analyze_results(request).model_dump()
    base["probability_treated_beats_holdout"] = round(
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


def _build_holdout_block(
    *,
    metric_type: str,
    alpha: float,
    arms: list[dict[str, Any]],
    holdout_aggregates: dict[str, Any] | None,
    mixture_variance: float | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "treated": None,
        "holdout": None,
        "analysis": None,
        "probability_treated_beats_holdout": None,
        "always_valid": None,
        "treated_users_total": None,
        "holdout_users_total": None,
    }
    if metric_type not in ("binary", "continuous"):
        return {"status": "unavailable", "note": translate("live_stats.holdout.unavailable_ratio"), **empty}

    holdout = (holdout_aggregates or {}).get("holdout")
    holdout_users = int(holdout["exposed_users"]) if holdout else 0
    if not holdout or holdout_users == 0:
        return {"status": "unavailable", "note": translate("live_stats.holdout.unavailable"), **empty}

    treated = _pool_treated_arms(arms)
    treated_users = int(treated["exposed_users"])
    base: dict[str, Any] = {
        "treated": _holdout_arm_stat(metric_type, treated, "treated"),
        "holdout": _holdout_arm_stat(metric_type, holdout, "holdout"),
        "analysis": None,
        "probability_treated_beats_holdout": None,
        "always_valid": None,
        "treated_users_total": treated_users,
        "holdout_users_total": holdout_users,
    }
    if treated_users < 2 or holdout_users < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.holdout.insufficient_data")
        return base
    if metric_type == "binary":
        return _holdout_binary(base, alpha, holdout, treated, mixture_variance)
    return _holdout_continuous(base, alpha, holdout, treated, mixture_variance)


def _build_event_timing_block(
    event_timing_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Late / out-of-order conversion indicator (P4.2).

    Reports how conversions on the primary metric distribute relative to each user's exposure:
    ``in_window`` (attributed), ``late`` (after the attribution horizon), and ``out_of_order``
    (before the exposure — causally impossible). Purely informational — a data-quality indicator
    that never alters a comparison or the decision verdict. ``unavailable`` when no summary was
    computed (e.g. the experiment has no exposures yet).
    """
    if not event_timing_summary:
        return {
            "status": "unavailable",
            "metric": None,
            "horizon_days": None,
            "in_window": None,
            "late": None,
            "out_of_order": None,
            "total": None,
        }
    return {
        "status": "ok",
        "metric": event_timing_summary.get("metric_name"),
        "horizon_days": event_timing_summary.get("horizon_days"),
        "in_window": int(event_timing_summary.get("in_window", 0)),
        "late": int(event_timing_summary.get("late", 0)),
        "out_of_order": int(event_timing_summary.get("out_of_order", 0)),
        "total": int(event_timing_summary.get("total", 0)),
    }


def _build_identity_resolution_block(
    identity_resolution_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Identity-resolution indicator (P4.3).

    Reports how many anonymous → canonical links are active and how much they touched the rollup
    (``canonicalized_events`` re-attributed, ``merged_users`` whose double-count was prevented). The
    resolution already happened in the primary rollup; this block only surfaces it. ``inactive`` when
    no links exist (the common case) — the frontend hides the block then. Purely informational; it
    never alters a comparison or the decision verdict.
    """
    linked = int((identity_resolution_summary or {}).get("linked_identities", 0) or 0)
    if not identity_resolution_summary or linked <= 0:
        return {
            "status": "inactive",
            "linked_identities": linked,
            "canonicalized_events": None,
            "merged_users": None,
        }
    return {
        "status": "active",
        "linked_identities": linked,
        "canonicalized_events": int(identity_resolution_summary.get("canonicalized_events", 0) or 0),
        "merged_users": int(identity_resolution_summary.get("merged_users", 0) or 0),
    }


def _build_exclusion_block(
    exclusion_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Bot / fraud filter indicator (P4.4).

    Reports how many exposed users the rollup removed, split into the manual deny-list and the
    rate-spike heuristic. The exclusion already happened in the primary rollup; this block only
    surfaces it so the filter is never silent. ``inactive`` when nothing was filtered (the common
    case) — the frontend hides the block then. Purely informational; the per-reason split is disjoint
    so ``manual_filtered + rate_spike_filtered == total_filtered``.
    """
    total = int((exclusion_summary or {}).get("total_filtered", 0) or 0)
    if not exclusion_summary or total <= 0:
        return {
            "status": "inactive",
            "total_filtered": total,
            "manual_filtered": None,
            "rate_spike_filtered": None,
        }
    return {
        "status": "active",
        "total_filtered": total,
        "manual_filtered": int(exclusion_summary.get("manual_filtered", 0) or 0),
        "rate_spike_filtered": int(exclusion_summary.get("rate_spike_filtered", 0) or 0),
    }
