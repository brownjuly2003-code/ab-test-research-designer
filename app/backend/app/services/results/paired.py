"""Paired-sample analyzers (paired t / Wilcoxon / McNemar)."""
from __future__ import annotations

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import PairedResultsRequest, PairedResultsResponse
from app.backend.app.stats.paired import (
    mcnemar_test,
    paired_t_test,
    wilcoxon_signed_rank_test,
)

from .common import _significance_text, _verdict


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

