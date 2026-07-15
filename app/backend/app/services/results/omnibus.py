"""Omnibus multi-group analyzers (Welch ANOVA / Kruskal–Wallis)."""
from __future__ import annotations

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    OmnibusGroupSummary,
    OmnibusResultsRequest,
    OmnibusResultsResponse,
)
from app.backend.app.stats.omnibus import kruskal_wallis_test, welch_anova_test

from .common import _significance_text


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

