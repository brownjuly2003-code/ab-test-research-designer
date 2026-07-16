"""Continuous and ranked two-sample analyzers."""
from __future__ import annotations

import math
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    ObservedResultsContinuous,
    ObservedResultsRanked,
    ResultsResponse,
)
from app.backend.app.stats.bootstrap_permutation import bootstrap_permutation_test
from app.backend.app.stats.equivalence import tost_equivalence_test
from app.backend.app.stats.mann_whitney import mann_whitney_u_test
from app.backend.app.stats.quantile_te import quantile_treatment_effect_test
from app.backend.app.stats.student_t import t_cdf, t_ppf
from app.backend.app.stats.trimmed_t import trimmed_means_t_test

from .common import _bounded_probability, _degenerate_response, _verdict, _welch_df


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


def _analyze_equivalence(obs: ObservedResultsContinuous | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("continuous observations are required")
    if obs.equivalence_margin is None:
        raise ValueError("equivalence margin is required")

    result = tost_equivalence_test(
        control_mean=obs.control_mean,
        control_std=obs.control_std,
        control_n=obs.control_n,
        treatment_mean=obs.treatment_mean,
        treatment_std=obs.treatment_std,
        treatment_n=obs.treatment_n,
        margin=obs.equivalence_margin,
        alpha=obs.alpha,
    )
    if result is None:
        # Zero standard error in both arms: the TOST statistic is undefined.
        return _degenerate_response(metric_type="equivalence", ci_level=1 - 2 * obs.alpha)

    effect = result["effect"]
    relative_effect = (effect / obs.control_mean * 100) if obs.control_mean != 0 else 0.0
    is_equivalent = result["is_equivalent"]
    cohens_d = result.get("cohens_d")

    return ResultsResponse(
        metric_type="equivalence",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(result["ci_level"], 4),
        p_value=round(_bounded_probability(result["p_value"]), 6),
        test_statistic=round(result["test_statistic"], 4),
        # For an equivalence test a "positive" result means equivalence was demonstrated; the verdict
        # and interpretation carry the equivalence wording so this flag is not read as a difference.
        is_significant=is_equivalent,
        power_achieved=round(_bounded_probability(result["power_achieved"]), 3),
        verdict=_equivalence_verdict(is_equivalent, result["margin"], obs.alpha),
        interpretation=_interpretation_equivalence(result, obs.alpha),
        effect_size=round(cohens_d, 4) if cohens_d is not None else None,
        effect_size_label=(
            translate("results.effect_size.cohens_d") if cohens_d is not None else None
        ),
    )


def _equivalence_verdict(is_equivalent: bool, margin: float, alpha: float) -> str:
    placeholders = {"margin": f"{margin:.4f}", "alpha": f"{alpha:.3f}"}
    if is_equivalent:
        return translate("results.verdict.equivalent", placeholders)
    return translate("results.verdict.not_equivalent", placeholders)


def _interpretation_equivalence(result: dict[str, Any], alpha: float) -> str:
    equivalence_text = translate(
        "results.equivalence.demonstrated"
        if result["is_equivalent"]
        else "results.equivalence.not_demonstrated"
    )
    return translate(
        "results.interpretation.equivalence",
        {
            "treatmentMean": f"{result['treatment_mean']:.4f}",
            "controlMean": f"{result['control_mean']:.4f}",
            "effect": f"{result['effect']:+.4f}",
            "margin": f"{result['margin']:.4f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "equivalence": equivalence_text,
        },
    )


def _analyze_mann_whitney(obs: ObservedResultsRanked | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("ranked observations are required")

    result = mann_whitney_u_test(obs.control_values, obs.treatment_values, obs.alpha)
    if result is None:
        # Every observation tied across both arms (or an empty arm): no rank signal.
        return _degenerate_response(metric_type="mann_whitney", ci_level=1 - obs.alpha)

    shift = result["hodges_lehmann_shift"]
    control_median = result["control_median"]
    relative_effect = (shift / control_median * 100) if control_median != 0 else 0.0
    is_significant = result["is_significant"]

    return ResultsResponse(
        metric_type="mann_whitney",
        observed_effect=round(shift, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, shift, obs.alpha),
        interpretation=_interpretation_mann_whitney(result),
        effect_size=round(result["rank_biserial"], 4),
        effect_size_label=translate("results.effect_size.rank_biserial"),
    )


def _interpretation_mann_whitney(result: dict[str, Any]) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    method_text = translate(
        "results.mann_whitney.method_exact"
        if result["method"] == "exact"
        else "results.mann_whitney.method_asymptotic"
    )
    return translate(
        "results.interpretation.mann_whitney",
        {
            "treatmentMedian": f"{result['treatment_median']:.4f}",
            "controlMedian": f"{result['control_median']:.4f}",
            "shift": f"{result['hodges_lehmann_shift']:+.4f}",
            "cles": f"{result['common_language_effect'] * 100:.1f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "uStatistic": f"{result['u_statistic']:.1f}",
            "pValue": f"{result['p_value']:.6f}",
            "method": method_text,
            "significance": significance_text,
        },
    )


def _analyze_bootstrap(obs: ObservedResultsRanked | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("ranked observations are required")

    result = bootstrap_permutation_test(obs.control_values, obs.treatment_values, obs.alpha)
    if result is None:
        # An empty arm: the mean difference is undefined. (A fully tied pooled sample is a valid
        # p = 1 result, not degenerate, so it never reaches here.)
        return _degenerate_response(metric_type="bootstrap", ci_level=1 - obs.alpha)

    effect = result["observed_diff"]
    control_mean = result["control_mean"]
    relative_effect = (effect / control_mean * 100) if control_mean != 0 else 0.0
    is_significant = result["is_significant"]
    cohens_d = result["cohens_d"]

    return ResultsResponse(
        metric_type="bootstrap",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=_interpretation_bootstrap(result),
        effect_size=round(cohens_d, 4) if cohens_d is not None else None,
        effect_size_label=translate("results.effect_size.cohens_d"),
    )


def _interpretation_bootstrap(result: dict[str, Any]) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.bootstrap",
        {
            "treatmentMean": f"{result['treatment_mean']:.4f}",
            "controlMean": f"{result['control_mean']:.4f}",
            "effect": f"{result['observed_diff']:+.4f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "permutations": str(result["n_resamples"]),
            "significance": significance_text,
        },
    )


def _analyze_quantile(obs: ObservedResultsRanked | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("ranked observations are required")

    result = quantile_treatment_effect_test(
        obs.control_values, obs.treatment_values, obs.quantile, obs.alpha
    )
    if result is None:
        # An empty arm: the quantile difference is undefined. (A fully tied pooled sample is a valid
        # p = 1 result, not degenerate, so it never reaches here.)
        return _degenerate_response(metric_type="quantile", ci_level=1 - obs.alpha)

    effect = result["observed_diff"]
    control_quantile = result["control_quantile"]
    relative_effect = (effect / control_quantile * 100) if control_quantile != 0 else 0.0
    is_significant = result["is_significant"]

    return ResultsResponse(
        metric_type="quantile",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=_interpretation_quantile(result),
    )


def _interpretation_quantile(result: dict[str, Any]) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.quantile",
        {
            "percentile": f"{result['quantile'] * 100:g}",
            "treatmentQuantile": f"{result['treatment_quantile']:.4f}",
            "controlQuantile": f"{result['control_quantile']:.4f}",
            "effect": f"{result['observed_diff']:+.4f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "permutations": str(result["n_resamples"]),
            "significance": significance_text,
        },
    )


def _analyze_trimmed_t(obs: ObservedResultsRanked | None) -> ResultsResponse:
    if obs is None:
        raise ValueError("ranked observations are required")

    result = trimmed_means_t_test(obs.control_values, obs.treatment_values, obs.trim, obs.alpha)
    if result is None:
        # An effective per-arm size below 2, or zero Winsorized variance (constant arms): the
        # parametric trimmed-mean test has no standard error and is not evaluable.
        return _degenerate_response(metric_type="trimmed_t", ci_level=1 - obs.alpha)

    effect = result["observed_diff"]
    control_trimmed_mean = result["control_trimmed_mean"]
    relative_effect = (effect / control_trimmed_mean * 100) if control_trimmed_mean != 0 else 0.0
    is_significant = result["is_significant"]

    return ResultsResponse(
        metric_type="trimmed_t",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(relative_effect, 2),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(result["ci_level"], 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        power_achieved=round(result["power_achieved"], 3),
        verdict=_verdict(is_significant, effect, obs.alpha),
        interpretation=_interpretation_trimmed_t(result),
    )


def _interpretation_trimmed_t(result: dict[str, Any]) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.trimmed_t",
        {
            "trimPct": f"{result['trim'] * 100:g}",
            "treatmentMean": f"{result['treatment_trimmed_mean']:.4f}",
            "controlMean": f"{result['control_trimmed_mean']:.4f}",
            "effect": f"{result['observed_diff']:+.4f}",
            "ciLevel": f"{result['ci_level'] * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "controlEffectiveN": str(result["control_effective_n"]),
            "treatmentEffectiveN": str(result["treatment_effective_n"]),
            "df": f"{result['degrees_of_freedom']:.1f}",
            "significance": significance_text,
        },
    )

