"""Poisson rate (count) analyzer."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import ObservedResultsCount, ResultsResponse
from app.backend.app.stats.poisson_rate import MAX_POISSON_EVENTS, poisson_rate_test

from .common import _degenerate_response, _verdict


def _analyze_count(obs: ObservedResultsCount | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("count observations are required")
    if obs.control_events + obs.treatment_events > MAX_POISSON_EVENTS:
        # The exact binomial enumeration is only worthwhile up to the cap; beyond it the normal
        # approximation is exact and far cheaper.
        raise ValueError(translate("errors.schemas.count_events_too_large"))

    result = poisson_rate_test(
        obs.control_events,
        obs.control_exposure,
        obs.treatment_events,
        obs.treatment_exposure,
        obs.alpha,
    )
    if result is None:
        # No events in either arm: the rate test carries no signal.
        return _degenerate_response(metric_type="count", ci_level=1 - obs.alpha)

    rate_difference = result["rate_difference"]
    rate_ratio = result["rate_ratio"]
    is_significant = result["is_significant"]

    return ResultsResponse(
        metric_type="count",
        observed_effect=round(rate_difference, 6),
        observed_effect_relative=round(result["relative_effect"], 2),
        control_rate=None,
        treatment_rate=None,
        ci_lower=round(result["ci_lower"], 6),
        ci_upper=round(result["ci_upper"], 6),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(rate_ratio, 4) if rate_ratio is not None else 0.0,
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, rate_difference, obs.alpha),
        interpretation=_interpretation_count(result, is_significant),
        effect_size=round(rate_ratio, 4) if rate_ratio is not None else None,
        effect_size_label=translate("results.effect_size.rate_ratio"),
    )


def _interpretation_count(result: dict[str, Any], is_significant: bool) -> str:
    significance_text = translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )
    rate_ratio_text = (
        f"{result['rate_ratio']:.4f}"
        if result["rate_ratio"] is not None
        else translate("results.count.rate_ratio_undefined")
    )
    return translate(
        "results.interpretation.count",
        {
            "treatmentRate": f"{result['treatment_rate']:.6f}",
            "controlRate": f"{result['control_rate']:.6f}",
            "rateRatio": rate_ratio_text,
            "rateDifference": f"{result['rate_difference']:+.6f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.6f}",
            "ciUpper": f"{result['ci_upper']:.6f}",
            "pValue": f"{result['p_value']:.6f}",
            "significance": significance_text,
        },
    )

