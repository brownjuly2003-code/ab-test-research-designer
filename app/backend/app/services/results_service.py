import math
from statistics import NormalDist
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ObservedResultsCount,
    ObservedResultsRanked,
    ResultsRequest,
    ResultsResponse,
)
from app.backend.app.stats.binary import normal_ppf
from app.backend.app.stats.bootstrap_permutation import bootstrap_permutation_test
from app.backend.app.stats.fisher_exact import MAX_FISHER_EXACT_TOTAL, fisher_exact_test
from app.backend.app.stats.mann_whitney import mann_whitney_u_test
from app.backend.app.stats.poisson_rate import MAX_POISSON_EVENTS, poisson_rate_test
from app.backend.app.stats.quantile_te import quantile_treatment_effect_test
from app.backend.app.stats.student_t import t_cdf, t_ppf

_STANDARD_NORMAL = NormalDist()


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    if request.metric_type == "binary":
        return _analyze_binary(request.binary)
    if request.metric_type == "fisher_exact":
        return _analyze_fisher_exact(request.binary)
    if request.metric_type == "mann_whitney":
        return _analyze_mann_whitney(request.ranked)
    if request.metric_type == "bootstrap":
        return _analyze_bootstrap(request.ranked)
    if request.metric_type == "quantile":
        return _analyze_quantile(request.ranked)
    if request.metric_type == "count":
        return _analyze_count(request.count)
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
    p1 = result["control_rate"]
    p2 = result["treatment_rate"]
    effect = result["risk_difference"]
    p_value = result["p_value"]
    is_significant = p_value < obs.alpha
    odds_ratio = result["odds_ratio"]

    # The p-value is exact; the interval and achieved power are the large-sample normal
    # approximation on the risk difference, reported for continuity with the binary view and
    # clearly framed as descriptive (an exact 2x2 CI is a separate, heavier construction).
    z_critical = normal_ppf(1 - obs.alpha / 2)
    ci_standard_error = math.sqrt(
        max((p1 * (1 - p1) / obs.control_users) + (p2 * (1 - p2) / obs.treatment_users), 0.0)
    )
    if ci_standard_error == 0:
        ci_lower = ci_upper = effect
        power_achieved = 0.0
    else:
        ci_lower = effect - z_critical * ci_standard_error
        ci_upper = effect + z_critical * ci_standard_error
        standardized = abs(effect) / ci_standard_error
        power_achieved = standard_normal_cdf(
            standardized - z_critical
        ) + standard_normal_cdf(-z_critical - standardized)

    return ResultsResponse(
        metric_type="fisher_exact",
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
        interpretation=_interpretation_fisher_exact(
            p1=p1,
            p2=p2,
            effect=effect,
            odds_ratio=odds_ratio,
            p_value=p_value,
            is_significant=is_significant,
        ),
        effect_size=round(odds_ratio, 4) if odds_ratio is not None else None,
        effect_size_label=translate("results.effect_size.odds_ratio"),
    )


def _interpretation_fisher_exact(
    *,
    p1: float,
    p2: float,
    effect: float,
    odds_ratio: float | None,
    p_value: float,
    is_significant: bool,
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
    return translate(
        "results.interpretation.fisher_exact",
        {
            "treatment": f"{p2 * 100:.4f}",
            "control": f"{p1 * 100:.4f}",
            "effect": f"{effect * 100:+.4f}",
            "oddsRatio": odds_ratio_text,
            "pValue": f"{p_value:.6f}",
            "significance": significance_text,
        },
    )


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
