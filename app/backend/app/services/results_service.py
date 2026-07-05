import math
from statistics import NormalDist
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    CategoricalResultsRequest,
    CategoricalResultsResponse,
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ObservedResultsCount,
    ObservedResultsRanked,
    OmnibusGroupSummary,
    OmnibusResultsRequest,
    OmnibusResultsResponse,
    PairedResultsRequest,
    PairedResultsResponse,
    ResultsRequest,
    ResultsResponse,
)
from app.backend.app.stats.binary import (
    newcombe_difference_interval,
    normal_ppf,
)
from app.backend.app.stats.bootstrap_permutation import bootstrap_permutation_test
from app.backend.app.stats.chi_square_independence import (
    chi_square_independence_test,
    g_test_independence,
)
from app.backend.app.stats.equivalence import tost_equivalence_test
from app.backend.app.stats.fisher_exact import (
    MAX_FISHER_EXACT_TOTAL,
    fisher_exact_odds_ratio_midp_ci,
    fisher_exact_test,
)
from app.backend.app.stats.mann_whitney import mann_whitney_u_test
from app.backend.app.stats.omnibus import kruskal_wallis_test, welch_anova_test
from app.backend.app.stats.paired import (
    mcnemar_test,
    paired_t_test,
    wilcoxon_signed_rank_test,
)
from app.backend.app.stats.poisson_rate import MAX_POISSON_EVENTS, poisson_rate_test
from app.backend.app.stats.quantile_te import quantile_treatment_effect_test
from app.backend.app.stats.student_t import t_cdf, t_ppf
from app.backend.app.stats.trimmed_t import trimmed_means_t_test
from app.backend.app.stats.unconditional_exact import (
    MAX_UNCONDITIONAL_EXACT_TOTAL,
    boschloo_exact_test,
)

_STANDARD_NORMAL = NormalDist()


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    if request.metric_type == "binary":
        return _analyze_binary(request.binary)
    if request.metric_type == "fisher_exact":
        return _analyze_fisher_exact(request.binary)
    if request.metric_type == "boschloo_exact":
        return _analyze_boschloo_exact(request.binary)
    if request.metric_type == "mann_whitney":
        return _analyze_mann_whitney(request.ranked)
    if request.metric_type == "bootstrap":
        return _analyze_bootstrap(request.ranked)
    if request.metric_type == "quantile":
        return _analyze_quantile(request.ranked)
    if request.metric_type == "trimmed_t":
        return _analyze_trimmed_t(request.ranked)
    if request.metric_type == "count":
        return _analyze_count(request.count)
    if request.metric_type == "equivalence":
        return _analyze_equivalence(request.continuous)
    return _analyze_continuous(request.continuous)


def analyze_categorical_results(request: CategoricalResultsRequest) -> CategoricalResultsResponse:
    """Test of independence on an r×c contingency table — Pearson chi-square or the G-test.

    Separate from ``analyze_results`` because the outcome is omnibus — a test statistic with degrees of
    freedom and Cramér's V, not the scalar effect + confidence interval that ``ResultsResponse`` carries.
    ``test_type`` selects Pearson's chi-square (default) or the G-test (likelihood-ratio chi-square) on
    the same table; both share this response shape. A degenerate table raises ``ValueError`` from the
    stats layer, which the global handler maps to HTTP 400.
    """
    if request.test_type == "g_test":
        result = g_test_independence(request.table, request.alpha)
    else:
        result = chi_square_independence_test(request.table, request.alpha)
    is_significant = result["is_significant"]
    return CategoricalResultsResponse(
        test_type=request.test_type,
        chi_square=round(result["chi_square"], 4),
        degrees_of_freedom=result["degrees_of_freedom"],
        p_value=round(result["p_value"], 6),
        is_significant=is_significant,
        cramers_v=round(result["cramers_v"], 4),
        n_total=result["n_total"],
        num_rows=result["num_rows"],
        num_cols=result["num_cols"],
        min_expected_count=round(result["min_expected_count"], 4),
        low_expected_warning=result["low_expected_warning"],
        verdict=translate(
            "results.categorical.verdict_associated"
            if is_significant
            else "results.categorical.verdict_independent"
        ),
        interpretation=_interpretation_categorical(result, request.test_type),
    )


def _interpretation_categorical(result: dict[str, Any], test_type: str) -> str:
    significance_text = translate(
        "results.significance.significant"
        if result["is_significant"]
        else "results.significance.not_significant"
    )
    return translate(
        "results.interpretation.g_test" if test_type == "g_test" else "results.interpretation.categorical",
        {
            "chiSquare": f"{result['chi_square']:.4f}",
            "df": str(result["degrees_of_freedom"]),
            "rows": str(result["num_rows"]),
            "cols": str(result["num_cols"]),
            "n": str(result["n_total"]),
            "pValue": f"{result['p_value']:.6f}",
            "cramersV": f"{result['cramers_v']:.4f}",
            "significance": significance_text,
        },
    )


def analyze_paired_results(request: PairedResultsRequest) -> PairedResultsResponse:
    """Dispatch a paired-family test (paired t / Wilcoxon signed-rank / McNemar) on paired samples.

    Separate from ``analyze_results`` because the observations are paired (two measurements of the same
    unit) rather than two independent arms. A degenerate paired t / Wilcoxon input (fewer than two
    usable pairs, zero difference variance / all magnitudes tied) raises ``ValueError`` — mapped to
    HTTP 400 by the global handler — rather than inventing a p-value; McNemar is always well-defined
    (no discordant pairs is a valid ``p = 1``).
    """
    if request.test_type == "paired_t":
        return _analyze_paired_t(request)
    if request.test_type == "wilcoxon":
        return _analyze_wilcoxon(request)
    return _analyze_mcnemar(request)


def _analyze_paired_t(request: PairedResultsRequest) -> PairedResultsResponse:
    result = paired_t_test(request.control_values, request.treatment_values, request.alpha)
    if result is None:
        raise ValueError(translate("errors.schemas.paired_t_degenerate"))
    is_significant = result["is_significant"]
    effect = result["mean_difference"]
    interpretation = translate(
        "results.interpretation.paired_t",
        {
            "treatmentMean": f"{result['treatment_mean']:.4f}",
            "controlMean": f"{result['control_mean']:.4f}",
            "meanDiff": f"{effect:+.4f}",
            "tStat": f"{result['test_statistic']:.4f}",
            "df": str(result["degrees_of_freedom"]),
            "ciLevel": f"{(1 - request.alpha) * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "cohenDz": f"{result['effect_size']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "significance": _significance_text(is_significant),
        },
    )
    return PairedResultsResponse(
        test_type="paired_t",
        n_pairs=result["n_pairs"],
        effect=round(effect, 4),
        effect_label=translate("results.paired.effect.mean_difference"),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(1 - request.alpha, 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        effect_size=round(result["effect_size"], 4),
        effect_size_label=translate("results.effect_size.cohens_dz"),
        verdict=_verdict(is_significant, effect, request.alpha),
        interpretation=interpretation,
    )


def _analyze_wilcoxon(request: PairedResultsRequest) -> PairedResultsResponse:
    result = wilcoxon_signed_rank_test(
        request.control_values, request.treatment_values, request.alpha
    )
    if result is None:
        raise ValueError(translate("errors.schemas.wilcoxon_degenerate"))
    is_significant = result["is_significant"]
    effect = result["pseudomedian"]
    interpretation = translate(
        "results.interpretation.wilcoxon",
        {
            "pseudomedian": f"{effect:+.4f}",
            "wStat": f"{result['test_statistic']:.1f}",
            "nNonzero": str(result["n_nonzero"]),
            "nZero": str(result["n_zero_differences"]),
            "ciLevel": f"{(1 - request.alpha) * 100:.1f}",
            "ciLower": f"{result['ci_lower']:.4f}",
            "ciUpper": f"{result['ci_upper']:.4f}",
            "rankBiserial": f"{result['effect_size']:.4f}",
            "pValue": f"{result['p_value']:.6f}",
            "significance": _significance_text(is_significant),
        },
    )
    return PairedResultsResponse(
        test_type="wilcoxon",
        n_pairs=result["n_pairs"],
        effect=round(effect, 4),
        effect_label=translate("results.paired.effect.pseudomedian"),
        ci_lower=round(result["ci_lower"], 4),
        ci_upper=round(result["ci_upper"], 4),
        ci_level=round(1 - request.alpha, 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        effect_size=round(result["effect_size"], 4),
        effect_size_label=translate("results.effect_size.rank_biserial"),
        n_zero_differences=result["n_zero_differences"],
        verdict=_verdict(is_significant, effect, request.alpha),
        interpretation=interpretation,
    )


def _analyze_mcnemar(request: PairedResultsRequest) -> PairedResultsResponse:
    result = mcnemar_test(request.control_values, request.treatment_values, request.alpha)
    is_significant = result["is_significant"]
    effect = result["proportion_difference"]
    odds_ratio = result["odds_ratio"]
    method_text = translate(
        "results.mcnemar.method_exact"
        if result["method"] == "exact"
        else "results.mcnemar.method_chi_square"
    )
    odds_ratio_text = (
        f"{odds_ratio:.4f}"
        if odds_ratio is not None
        else translate("results.mcnemar.odds_ratio_undefined")
    )
    interpretation = translate(
        "results.interpretation.mcnemar",
        {
            "b": str(result["discordant_positive"]),
            "c": str(result["discordant_negative"]),
            "nDiscordant": str(result["n_discordant"]),
            "proportionDiff": f"{effect * 100:+.4f}",
            "oddsRatio": odds_ratio_text,
            "method": method_text,
            "pValue": f"{result['p_value']:.6f}",
            "significance": _significance_text(is_significant),
        },
    )
    return PairedResultsResponse(
        test_type="mcnemar",
        n_pairs=result["n_pairs"],
        effect=round(effect, 6),
        effect_label=translate("results.paired.effect.proportion_difference"),
        ci_lower=round(result["ci_lower"], 6),
        ci_upper=round(result["ci_upper"], 6),
        ci_level=round(1 - request.alpha, 4),
        p_value=round(result["p_value"], 6),
        test_statistic=round(result["test_statistic"], 4),
        is_significant=is_significant,
        effect_size=round(odds_ratio, 4) if odds_ratio is not None else None,
        effect_size_label=translate("results.effect_size.odds_ratio"),
        method=result["method"],
        n_discordant=result["n_discordant"],
        discordant_positive=result["discordant_positive"],
        discordant_negative=result["discordant_negative"],
        verdict=_verdict(is_significant, effect, request.alpha),
        interpretation=interpretation,
    )


def _significance_text(is_significant: bool) -> str:
    return translate(
        "results.significance.significant"
        if is_significant
        else "results.significance.not_significant"
    )


def analyze_omnibus_results(request: OmnibusResultsRequest) -> OmnibusResultsResponse:
    """Dispatch an omnibus test (Welch's ANOVA / Kruskal–Wallis) across more than two groups.

    Separate from ``analyze_results`` because the outcome is omnibus — a single F/H statistic over all
    groups, not the scalar effect + confidence interval that ``ResultsResponse`` carries. A degenerate
    input (a group with no within-group variance for Welch, or no rank variation at all for
    Kruskal–Wallis) raises ``ValueError`` from the stats layer, which the global handler maps to HTTP
    400 rather than inventing a statistic.
    """
    if request.test_type == "welch_anova":
        return _analyze_welch_anova(request)
    return _analyze_kruskal_wallis(request)


def _analyze_welch_anova(request: OmnibusResultsRequest) -> OmnibusResultsResponse:
    result = welch_anova_test(request.groups, request.alpha)
    if result is None:
        raise ValueError(translate("errors.schemas.welch_anova_degenerate"))
    is_significant = result["is_significant"]
    interpretation = translate(
        "results.interpretation.welch_anova",
        {
            "fStatistic": f"{result['test_statistic']:.4f}",
            "dfNum": f"{result['df_numerator']:.0f}",
            "dfDen": f"{result['df_denominator']:.4f}",
            "groups": str(result["num_groups"]),
            "n": str(result["n_total"]),
            "pValue": f"{result['p_value']:.6f}",
            "etaSquared": f"{result['effect_size']:.4f}",
            "significance": _significance_text(is_significant),
        },
    )
    return OmnibusResultsResponse(
        test_type="welch_anova",
        test_statistic=round(result["test_statistic"], 4),
        df_numerator=result["df_numerator"],
        df_denominator=round(result["df_denominator"], 4),
        p_value=round(result["p_value"], 6),
        is_significant=is_significant,
        effect_size=round(result["effect_size"], 4),
        effect_size_label=translate("results.effect_size.eta_squared"),
        num_groups=result["num_groups"],
        n_total=result["n_total"],
        group_summaries=[
            OmnibusGroupSummary(
                n=summary["n"],
                mean=round(summary["mean"], 4),
                std=round(summary["std"], 4),
            )
            for summary in result["group_summaries"]
        ],
        verdict=_omnibus_verdict(is_significant, request.alpha),
        interpretation=interpretation,
    )


def _analyze_kruskal_wallis(request: OmnibusResultsRequest) -> OmnibusResultsResponse:
    result = kruskal_wallis_test(request.groups, request.alpha)
    if result is None:
        raise ValueError(translate("errors.schemas.kruskal_wallis_degenerate"))
    is_significant = result["is_significant"]
    interpretation = translate(
        "results.interpretation.kruskal_wallis",
        {
            "hStatistic": f"{result['test_statistic']:.4f}",
            "df": f"{result['df_numerator']:.0f}",
            "groups": str(result["num_groups"]),
            "n": str(result["n_total"]),
            "pValue": f"{result['p_value']:.6f}",
            "epsilonSquared": f"{result['effect_size']:.4f}",
            "significance": _significance_text(is_significant),
        },
    )
    return OmnibusResultsResponse(
        test_type="kruskal_wallis",
        test_statistic=round(result["test_statistic"], 4),
        df_numerator=result["df_numerator"],
        df_denominator=None,
        p_value=round(result["p_value"], 6),
        is_significant=is_significant,
        effect_size=round(result["effect_size"], 4),
        effect_size_label=translate("results.effect_size.epsilon_squared"),
        num_groups=result["num_groups"],
        n_total=result["n_total"],
        group_summaries=[
            OmnibusGroupSummary(
                n=summary["n"],
                median=round(summary["median"], 4),
                mean_rank=round(summary["mean_rank"], 4),
            )
            for summary in result["group_summaries"]
        ],
        verdict=_omnibus_verdict(is_significant, request.alpha),
        interpretation=interpretation,
    )


def _omnibus_verdict(is_significant: bool, alpha: float) -> str:
    # Omnibus tests report only whether *some* group differs (no signed direction over >2 groups), so
    # the verdict is a two-state association/no-association call, mirroring the categorical analyzer.
    return translate(
        "results.omnibus.verdict_difference"
        if is_significant
        else "results.omnibus.verdict_no_difference",
        {"alpha": f"{alpha:.3f}"},
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
