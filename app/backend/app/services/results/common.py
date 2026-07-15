"""Shared helpers for post-hoc results analyzers."""
from __future__ import annotations

import math
from statistics import NormalDist

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import ObservedResultsContinuous, ResultsResponse

_STANDARD_NORMAL = NormalDist()


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


def _significance_text(is_significant: bool) -> str:
    return translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )


def _verdict(is_significant: bool, effect: float, alpha: float) -> str:
    alpha_str = f"{alpha:.3f}"
    if not is_significant:
        return translate("results.verdict.no_difference", {"alpha": alpha_str})
    if effect > 0:
        return translate("results.verdict.uplift", {"alpha": alpha_str})
    if effect < 0:
        return translate("results.verdict.decline", {"alpha": alpha_str})
    return translate("results.verdict.significant", {"alpha": alpha_str})


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

