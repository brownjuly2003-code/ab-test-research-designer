import math
from statistics import NormalDist

from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ResultsRequest,
    ResultsResponse,
)
from app.backend.app.stats.binary import normal_ppf

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
    power_achieved = standard_normal_cdf(abs(test_statistic) - z_critical)

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
    z_critical = normal_ppf(1 - obs.alpha / 2)
    ci_lower = effect - z_critical * standard_error
    ci_upper = effect + z_critical * standard_error
    relative_effect = (effect / obs.control_mean * 100) if obs.control_mean != 0 else 0.0
    is_significant = p_value < obs.alpha

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
        power_achieved=0.0,
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=(
            f"Treatment mean {obs.treatment_mean:.4f} vs control {obs.control_mean:.4f}. "
            f"Effect {effect:+.4f} with {(1 - obs.alpha) * 100:.1f}% CI [{ci_lower:.4f}, {ci_upper:.4f}]. "
            f"Two-sided p-value {p_value:.6f}."
        ),
    )


def standard_normal_cdf(value: float) -> float:
    return _STANDARD_NORMAL.cdf(value)


def t_cdf(value: float, df: float) -> float:
    if not math.isfinite(df) or df <= 0:
        return standard_normal_cdf(value)
    return standard_normal_cdf(value)


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
    if not is_significant:
        return f"No statistically significant difference at alpha={alpha:.3f}"
    if effect > 0:
        return f"Statistically significant uplift at alpha={alpha:.3f}"
    if effect < 0:
        return f"Statistically significant decline at alpha={alpha:.3f}"
    return f"Statistically significant result at alpha={alpha:.3f}"


def _interpretation_binary(
    *,
    p1: float,
    p2: float,
    effect: float,
    ci_lower: float,
    ci_upper: float,
    p_value: float,
    is_significant: bool,
) -> str:
    significance_text = "statistically significant" if is_significant else "not statistically significant"
    return (
        f"Treatment conversion {p2 * 100:.4f}% vs control {p1 * 100:.4f}%. "
        f"Absolute effect {effect * 100:+.4f} pp with 95.0% CI [{ci_lower * 100:.4f}, {ci_upper * 100:.4f}] pp. "
        f"Two-sided p-value {p_value:.6f}; result is {significance_text}."
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
        verdict="Cannot compute: zero standard error",
        interpretation="Observed inputs are degenerate, so the test statistic cannot be computed.",
    )


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))
