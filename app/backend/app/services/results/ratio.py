"""Ratio metric post-hoc analyzer and shared response builder."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import RatioArm, RatioResultsRequest, ResultsResponse
from app.backend.app.stats.ratio import compare_ratios

from .common import _verdict


def analyze_ratio_results(request: RatioResultsRequest) -> ResultsResponse:
    """Post-hoc delta-method z-test on a ratio metric from raw per-user pairs.

    The math and the response assembly are exactly the live executor's (``stats.ratio.compare_ratios``
    + ``build_ratio_results_response``) — only the entry differs: raw per-user (numerator, denominator)
    pairs are reduced to the per-arm sufficient statistics here. A degenerate comparison (a zero
    denominator mean, so the ratio blows up, or zero pooled variance, so there is no usable signal)
    returns ``None`` from the stats layer and raises ``ValueError``, which the global handler maps to
    HTTP 400 rather than inventing a z-statistic.
    """
    result = compare_ratios(
        _ratio_arm_sufficient_stats(request.control_arm),
        _ratio_arm_sufficient_stats(request.treatment_arm),
        request.alpha,
    )
    if result is None:
        raise ValueError(translate("errors.schemas.ratio_degenerate"))
    return build_ratio_results_response(result, request.alpha)


def _ratio_arm_sufficient_stats(arm: RatioArm) -> dict[str, float]:
    # x = denominator, y = numerator — the orientation ``stats.ratio`` documents.
    return {
        "n": len(arm.numerators),
        "sum_x": sum(arm.denominators),
        "sum_x2": sum(value * value for value in arm.denominators),
        "sum_y": sum(arm.numerators),
        "sum_y2": sum(value * value for value in arm.numerators),
        "sum_xy": sum(x * y for x, y in zip(arm.denominators, arm.numerators, strict=True)),
    }


def build_ratio_results_response(result: dict[str, Any], alpha: float) -> ResultsResponse:
    """Assemble a ``ResultsResponse`` from an already-computed ratio comparison
    (``stats.ratio.compare_ratios``).

    Kept separate from the math so the live executor can reuse ``result["effect"]`` and
    ``result["variance"]`` for the always-valid view without recomputing. Ratio metrics do not
    enter through ``ResultsRequest`` — they are computed live from the per-arm sufficient
    statistics. The per-arm ratios ``R̂`` are carried separately on the arm stats, so
    ``control_rate`` / ``treatment_rate`` stay ``None`` here (a ratio is not a percentage rate).
    """
    effect = result["effect"]
    is_significant = result["is_significant"]
    return ResultsResponse(
        metric_type="ratio",
        observed_effect=round(effect, 6),
        observed_effect_relative=round(result["relative_effect"], 2),
        control_rate=None,
        treatment_rate=None,
        ci_lower=round(result["ci_lower"], 6),
        ci_upper=round(result["ci_upper"], 6),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, effect, alpha),
        interpretation=_interpretation_ratio(result, is_significant),
    )


def _interpretation_ratio(result: dict[str, Any], is_significant: bool) -> str:
    significance_text = translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.ratio",
        {
            "treatmentRatio": f"{result['treatment_ratio']:.6f}",
            "controlRatio": f"{result['control_ratio']:.6f}",
            "effect": f"{result['effect']:+.6f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.6f}",
            "ciUpper": f"{result['ci_upper']:.6f}",
            "pValue": f"{result['p_value']:.6f}",
            "significance": significance_text,
        },
    )

