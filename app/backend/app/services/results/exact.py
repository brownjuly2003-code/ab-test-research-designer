"""Exact 2x2 binary analyzers: Fisher, Boschloo, Barnard."""
from __future__ import annotations

import math
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import ObservedResultsBinary, ResultsResponse
from app.backend.app.stats.binary import newcombe_difference_interval, normal_ppf
from app.backend.app.stats.fisher_exact import (
    MAX_FISHER_EXACT_TOTAL,
    fisher_exact_odds_ratio_midp_ci,
    fisher_exact_test,
)
from app.backend.app.stats.unconditional_exact import (
    MAX_UNCONDITIONAL_EXACT_TOTAL,
    barnard_exact_test,
    boschloo_exact_test,
)

from .common import _bounded_probability, _verdict, standard_normal_cdf


def _analyze_fisher_exact(obs: ObservedResultsBinary | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("binary observations are required")
    if obs.control_users + obs.treatment_users > MAX_FISHER_EXACT_TOTAL:
        # The exact enumeration is only worthwhile on small tables; beyond the cap the
        # normal-approximation binary test is accurate and far cheaper.
        raise ValueError(translate("errors.schemas.fisher_exact_table_too_large"))

    result = fisher_exact_test(
        obs.control_conversions,
        obs.control_users,
        obs.treatment_conversions,
        obs.treatment_users,
    )
    return _binary_exact_response(
        obs,
        result,
        metric_type="fisher_exact",
        interpretation_key="results.interpretation.fisher_exact",
    )


def _analyze_boschloo_exact(obs: ObservedResultsBinary | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("binary observations are required")
    if obs.control_users + obs.treatment_users > MAX_UNCONDITIONAL_EXACT_TOTAL:
        # The unconditional grid-search is far heavier than Fisher's single-margin sweep; above the cap
        # the unconditional advantage over the z-test / Fisher test has vanished, so redirect the caller.
        raise ValueError(translate("errors.schemas.unconditional_exact_table_too_large"))

    result = boschloo_exact_test(
        obs.control_conversions,
        obs.control_users,
        obs.treatment_conversions,
        obs.treatment_users,
    )
    return _binary_exact_response(
        obs,
        result,
        metric_type="boschloo_exact",
        interpretation_key="results.interpretation.boschloo_exact",
    )


def _analyze_barnard_exact(obs: ObservedResultsBinary | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("binary observations are required")
    if obs.control_users + obs.treatment_users > MAX_UNCONDITIONAL_EXACT_TOTAL:
        # Same cap as Boschloo's — the nuisance-supremum grid search is the shared expensive part.
        raise ValueError(translate("errors.schemas.unconditional_exact_table_too_large"))

    result = barnard_exact_test(
        obs.control_conversions,
        obs.control_users,
        obs.treatment_conversions,
        obs.treatment_users,
    )
    return _binary_exact_response(
        obs,
        result,
        metric_type="barnard_exact",
        interpretation_key="results.interpretation.barnard_exact",
    )


def _binary_exact_response(
    obs: ObservedResultsBinary,
    result: dict[str, Any],
    *,
    metric_type: str,
    interpretation_key: str,
) -> ResultsResponse:
    """Assemble the ``ResultsResponse`` for a 2x2 exact analyzer (Fisher or Boschloo).

    Both exact tests read the same 2x2 counts and report the same descriptive effect (risk difference +
    Newcombe CI, odds ratio + mid-p conditional CI, descriptive large-sample power) — they differ only
    in the p-value (supplied in ``result``), the ``metric_type`` tag, and the interpretation sentence's
    lead-in key. ``result`` carries the p-value plus the test-agnostic table statistics (rates, odds
    ratio, risk difference) produced by :func:`fisher_exact_test` / :func:`boschloo_exact_test`.
    """
    p1 = result["control_rate"]
    p2 = result["treatment_rate"]
    effect = result["risk_difference"]
    p_value = result["p_value"]
    is_significant = p_value < obs.alpha
    odds_ratio = result["odds_ratio"]

    # The p-value is exact. The risk-difference interval uses Newcombe's hybrid-score method (accurate
    # in exactly the small-n / rare-event regime where an exact test is the right analyzer). Achieved
    # power stays the large-sample normal approximation on the risk difference, framed as descriptive.
    z_critical = normal_ppf(1 - obs.alpha / 2)
    ci_lower, ci_upper = newcombe_difference_interval(
        obs.treatment_conversions,
        obs.treatment_users,
        obs.control_conversions,
        obs.control_users,
        obs.alpha,
    )
    ci_standard_error = math.sqrt(
        max((p1 * (1 - p1) / obs.control_users) + (p2 * (1 - p2) / obs.treatment_users), 0.0)
    )
    if ci_standard_error == 0:
        power_achieved = 0.0
    else:
        standardized = abs(effect) / ci_standard_error
        power_achieved = standard_normal_cdf(
            standardized - z_critical
        ) + standard_normal_cdf(-z_critical - standardized)

    # Mid-p conditional exact CI for the odds ratio — the honest completion of the exact family.
    # ``None`` when the margins are degenerate or the conditional support is too wide (large-sample
    # regime); a ``None`` upper limit means the interval is unbounded above (+∞).
    odds_ratio_ci = fisher_exact_odds_ratio_midp_ci(
        obs.control_conversions,
        obs.control_users,
        obs.treatment_conversions,
        obs.treatment_users,
        obs.alpha,
    )
    if odds_ratio_ci is None:
        effect_size_ci_lower: float | None = None
        effect_size_ci_upper: float | None = None
    else:
        or_lower, or_upper = odds_ratio_ci
        effect_size_ci_lower = round(or_lower, 4)
        effect_size_ci_upper = None if or_upper is None else round(or_upper, 4)

    return ResultsResponse(
        metric_type=metric_type,
        observed_effect=round(effect * 100, 4),
        observed_effect_relative=round(result["relative_risk_difference"] * 100, 2),
        control_rate=round(p1 * 100, 4),
        treatment_rate=round(p2 * 100, 4),
        ci_lower=round(ci_lower * 100, 4),
        ci_upper=round(ci_upper * 100, 4),
        ci_level=round(1 - obs.alpha, 4),
        p_value=round(_bounded_probability(p_value), 6),
        test_statistic=round(odds_ratio, 4) if odds_ratio is not None else 0.0,
        is_significant=is_significant,
        power_achieved=round(_bounded_probability(power_achieved), 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=_interpretation_binary_exact(
            interpretation_key=interpretation_key,
            p1=p1,
            p2=p2,
            effect=effect,
            odds_ratio=odds_ratio,
            p_value=p_value,
            is_significant=is_significant,
            odds_ratio_ci=odds_ratio_ci,
            ci_level=1 - obs.alpha,
        ),
        effect_size=round(odds_ratio, 4) if odds_ratio is not None else None,
        effect_size_label=translate("results.effect_size.odds_ratio"),
        effect_size_ci_lower=effect_size_ci_lower,
        effect_size_ci_upper=effect_size_ci_upper,
    )


def _interpretation_binary_exact(
    *,
    interpretation_key: str,
    p1: float,
    p2: float,
    effect: float,
    odds_ratio: float | None,
    p_value: float,
    is_significant: bool,
    odds_ratio_ci: tuple[float, float | None] | None = None,
    ci_level: float,
) -> str:
    significance_text = translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )
    odds_ratio_text = (
        f"{odds_ratio:.4f}"
        if odds_ratio is not None
        else translate("results.fisher_exact.odds_ratio_undefined")
    )
    interpretation = translate(
        interpretation_key,
        {
            "treatment": f"{p2 * 100:.4f}",
            "control": f"{p1 * 100:.4f}",
            "effect": f"{effect * 100:+.4f}",
            "oddsRatio": odds_ratio_text,
            "pValue": f"{p_value:.6f}",
            "significance": significance_text,
        },
    )
    if odds_ratio_ci is not None:
        or_lower, or_upper = odds_ratio_ci
        interpretation += " " + translate(
            "results.fisher_exact.odds_ratio_midp_ci",
            {
                "ciLevel": f"{ci_level * 100:.1f}",
                "lower": f"{or_lower:.4f}",
                "upper": "∞" if or_upper is None else f"{or_upper:.4f}",
            },
        )
    return interpretation

