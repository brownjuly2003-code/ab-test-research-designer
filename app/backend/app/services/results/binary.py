"""Two-proportion z-test binary analyzer."""
from __future__ import annotations

import math

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import ObservedResultsBinary, ResultsResponse
from app.backend.app.stats.binary import newcombe_difference_interval, normal_ppf

from .common import (
    _bounded_probability,
    _degenerate_response,
    _verdict,
    standard_normal_cdf,
)


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
    z_critical = normal_ppf(1 - obs.alpha / 2)
    # Newcombe (1998) hybrid-score interval for the risk difference, replacing the Wald interval that
    # mis-covers at small n or extreme rates. The p-value / verdict stay on the pooled z-test — only
    # the reported interval estimate changes to the better-calibrated score construction.
    ci_lower, ci_upper = newcombe_difference_interval(
        obs.treatment_conversions,
        obs.treatment_users,
        obs.control_conversions,
        obs.control_users,
        obs.alpha,
    )
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

