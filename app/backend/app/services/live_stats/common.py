"""Shared helpers: arm stats, multiple-comparison note, always-valid block, design payload."""
from __future__ import annotations

import math
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.stats.always_valid import evaluate_always_valid

from .constants import _ALWAYS_VALID_DECIMALS


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
