import math
from statistics import NormalDist
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ResultsRequest,
    ResultsResponse,
)
from app.backend.app.stats.binary import normal_ppf
from app.backend.app.stats.student_t import t_cdf, t_ppf

_STANDARD_NORMAL = NormalDist()


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    if request.metric_type == "binary":
        return _analyze_binary(request.binary)
    return _analyze_continuous(request.continuous)


def _analyze_binary(obs: ObservedResultsBinary | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("binary observations are required")

    p1 = obs.control_conversions / obs.control_users
    p2 = obs.treatment_conversions / obs.treatment_users
    effect = p2 - p1
    pooled_rate = (
        (obs.control_conversions + obs.treatment_conversions)
        / (obs.control_users + obs.treatment_users)
    )
    standard_error = math.sqrt(
        max(
            pooled_rate
            * (1 - pooled_rate)
            * ((1 / obs.control_users) + (1 / obs.treatment_users)),
            0.0,
        )
    )

    if standard_error == 0:
        return _degenerate_response(
            metric_type="binary",
            ci_level=1 - obs.alpha,
            control_rate=round(p1 * 100, 4),
            treatment_rate=round(p2 * 100, 4),
        )

    test_statistic = effect / standard_error
    p_value = 2 * (1 - standard_normal_cdf(abs(test_statistic)))
    ci_standard_error = math.sqrt(
        max(
            (p1 * (1 - p1) / obs.control_users) + (p2 * (1 - p2) / obs.treatment_users),
            0.0,
        )
    )
    z_critical = normal_ppf(1 - obs.alpha / 2)
    ci_lower = effect - z_critical * ci_standard_error
    ci_upper = effect + z_critical * ci_standard_error
    relative_effect = (effect / p1 * 100) if p1 > 0 else 0.0
    is_significant = p_value < obs.alpha
    power_achieved = standard_normal_cdf(
        abs(test_statistic) - z_critical
    ) + standard_normal_cdf(-z_critical - abs(test_statistic))

    return ResultsResponse(
        metric_type="binary",
        observed_effect=round(effect * 100, 4),
        observed_effect_relative=round(relative_effect, 2),
        control_rate=round(p1 * 100, 4),
        treatment_rate=round(p2 * 100, 4),
        ci_lower=round(ci_lower * 100, 4),
        ci_upper=round(ci_upper * 100, 4),
        ci_level=round(1 - obs.alpha, 4),
        p_value=round(_bounded_probability(p_value), 6),
        test_statistic=round(test_statistic, 4),
        is_significant=is_significant,
        power_achieved=round(_bounded_probability(power_achieved), 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=_interpretation_binary(
            p1=p1,
            p2=p2,
            effect=effect,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            ci_level=1 - obs.alpha,
            p_value=p_value,
            is_significant=is_significant,
        ),
    )


def _analyze_continuous(obs: ObservedResultsContinuous | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("continuous observations are required")

    control_variance = (obs.control_std**2) / obs.control_n
    treatment_variance = (obs.treatment_std**2) / obs.treatment_n
    standard_error = math.sqrt(max(control_variance + treatment_variance, 0.0))
    effect = obs.treatment_mean - obs.control_mean

    if standard_error == 0:
        return _degenerate_response(
            metric_type="continuous",
            ci_level=1 - obs.alpha,
        )

    test_statistic = effect / standard_error
    degrees_of_freedom = _welch_df(obs)
    p_value = 2 * (1 - t_cdf(abs(test_statistic), degrees_of_freedom))
    t_critical = t_ppf(1 - obs.alpha / 2, degrees_of_freedom)
    ci_lower = effect - t_critical * standard_error
    ci_upper = effect + t_critical * standard_error
    relative_effect = (effect / obs.control_mean * 100) if obs.control_mean != 0 else 0.0
    is_significant = p_value < obs.alpha
    upper_tail = 1.0 - t_cdf(t_critical - abs(test_statistic), degrees_of_freedom)
    lower_tail = t_cdf(-t_critical - abs(test_statistic), degrees_of_freedom)
    power_achieved = upper_tail + lower_tail

    return ResultsResponse(
        metric_type="continuous",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(ci_lower, 4),
        ci_upper=round(ci_upper, 4),
        ci_level=round(1 - obs.alpha, 4),
        p_value=round(_bounded_probability(p_value), 6),
        test_statistic=round(test_statistic, 4),
        is_significant=is_significant,
        power_achieved=round(_bounded_probability(power_achieved), 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=translate(
            "results.interpretation.continuous",
            {
                "treatmentMean": f"{obs.treatment_mean:.4f}",
                "controlMean": f"{obs.control_mean:.4f}",
                "effect": f"{effect:+.4f}",
                "ciLevel": f"{(1 - obs.alpha) * 100:.1f}",
                "ciLower": f"{ci_lower:.4f}",
                "ciUpper": f"{ci_upper:.4f}",
                "pValue": f"{p_value:.6f}",
            },
        ),
    )


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


def standard_normal_cdf(value: float) -> float:
    return _STANDARD_NORMAL.cdf(value)


def _welch_df(obs: ObservedResultsContinuous) -> float:
    control_term = (obs.control_std**2) / obs.control_n
    treatment_term = (obs.treatment_std**2) / obs.treatment_n
    denominator = 0.0
    if obs.control_n > 1:
        denominator += (control_term**2) / (obs.control_n - 1)
    if obs.treatment_n > 1:
        denominator += (treatment_term**2) / (obs.treatment_n - 1)
    if denominator == 0:
        return math.inf
    return ((control_term + treatment_term) ** 2) / denominator


def _verdict(is_significant: bool, effect: float, alpha: float) -> str:
    alpha_str = f"{alpha:.3f}"
    if not is_significant:
        return translate("results.verdict.no_difference", {"alpha": alpha_str})
    if effect > 0:
        return translate("results.verdict.uplift", {"alpha": alpha_str})
    if effect < 0:
        return translate("results.verdict.decline", {"alpha": alpha_str})
    return translate("results.verdict.significant", {"alpha": alpha_str})


def _interpretation_binary(
    *,
    p1: float,
    p2: float,
    effect: float,
    ci_lower: float,
    ci_upper: float,
    ci_level: float,
    p_value: float,
    is_significant: bool,
) -> str:
    significance_text = translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.binary",
        {
            "treatment": f"{p2 * 100:.4f}",
            "control": f"{p1 * 100:.4f}",
            "effect": f"{effect * 100:+.4f}",
            "ciLevel": f"{ci_level * 100:.1f}",
            "ciLower": f"{ci_lower * 100:.4f}",
            "ciUpper": f"{ci_upper * 100:.4f}",
            "pValue": f"{p_value:.6f}",
            "significance": significance_text,
        },
    )


def _degenerate_response(
    *,
    metric_type: str,
    ci_level: float,
    control_rate: float | None = None,
    treatment_rate: float | None = None,
) -> ResultsResponse:
    return ResultsResponse(
        metric_type=metric_type,
        observed_effect=0.0,
        observed_effect_relative=0.0,
        control_rate=control_rate,
        treatment_rate=treatment_rate,
        ci_lower=0.0,
        ci_upper=0.0,
        ci_level=round(ci_level, 4),
        p_value=1.0,
        test_statistic=0.0,
        is_significant=False,
        power_achieved=0.0,
        verdict=translate("results.verdict.degenerate"),
        interpretation=translate("results.interpretation.degenerate"),
    )


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))
