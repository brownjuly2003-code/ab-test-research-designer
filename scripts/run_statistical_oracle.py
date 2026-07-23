"""Run a differential statistical oracle against optional scientific libraries.

The production runtime remains stdlib-only for the statistics engine. This script is an
optional verification gate: install ``app/backend/requirements-oracle.txt`` after the normal
dev requirements, run this script, and inspect the JSON artifact if a comparison drifts.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

ORACLE_PACKAGES = ("numpy", "pandas", "scipy", "statsmodels", "lifelines")


@dataclass(frozen=True)
class Check:
    case: str
    metric: str
    observed: float
    expected: float
    abs_tolerance: float
    rel_tolerance: float
    abs_diff: float
    rel_diff: float
    passed: bool
    source: str


def _as_float(value: Any) -> float:
    return float(value)


def _add_check(
    checks: list[Check],
    *,
    case: str,
    metric: str,
    observed: Any,
    expected: Any,
    abs_tolerance: float,
    source: str,
    rel_tolerance: float = 0.0,
) -> None:
    observed_float = _as_float(observed)
    expected_float = _as_float(expected)
    if math.isfinite(expected_float):
        abs_diff = abs(observed_float - expected_float)
        denominator = max(1.0, abs(expected_float))
        rel_diff = abs_diff / denominator
        allowed = max(abs_tolerance, rel_tolerance * denominator)
        passed = math.isfinite(observed_float) and abs_diff <= allowed
    else:
        abs_diff = 0.0 if observed_float == expected_float else math.inf
        rel_diff = 0.0 if abs_diff == 0.0 else math.inf
        passed = observed_float == expected_float
    checks.append(
        Check(
            case=case,
            metric=metric,
            observed=observed_float,
            expected=expected_float,
            abs_tolerance=abs_tolerance,
            rel_tolerance=rel_tolerance,
            abs_diff=abs_diff,
            rel_diff=rel_diff,
            passed=passed,
            source=source,
        )
    )


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ORACLE_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def _assert_oracle_dependencies() -> None:
    missing = [name for name, version in _dependency_versions().items() if version == "missing"]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"missing optional oracle dependencies: {joined}; "
            "install app/backend/requirements-oracle.txt"
        )


def _check_student_and_distribution_tails(checks: list[Check]) -> None:
    from scipy import stats as scipy_stats

    from app.backend.app.stats.student_t import f_sf, t_cdf, t_ppf

    for value, df in [(-2.5, 3.0), (-0.25, 5.5), (1.75, 12.0), (4.0, 30.0)]:
        _add_check(
            checks,
            case="student_t_cdf",
            metric=f"value={value},df={df}",
            observed=t_cdf(value, df),
            expected=scipy_stats.t.cdf(value, df),
            abs_tolerance=5e-7,
            source="scipy.stats.t.cdf",
        )
    for probability, df in [(0.025, 8.0), (0.8, 4.5), (0.975, 30.0)]:
        _add_check(
            checks,
            case="student_t_ppf",
            metric=f"p={probability},df={df}",
            observed=t_ppf(probability, df),
            expected=scipy_stats.t.ppf(probability, df),
            abs_tolerance=2e-5,
            source="scipy.stats.t.ppf",
        )
    for value, df1, df2 in [(5.0, 2.0, 10.0), (1.0, 3.0, 3.5), (10.0, 4.0, 20.0)]:
        _add_check(
            checks,
            case="f_survival",
            metric=f"value={value},df1={df1},df2={df2}",
            observed=f_sf(value, df1, df2),
            expected=scipy_stats.f.sf(value, df1, df2),
            abs_tolerance=5e-7,
            source="scipy.stats.f.sf",
        )


def _check_binary_and_exact_family(checks: list[Check]) -> None:
    from scipy import stats as scipy_stats
    from statsmodels.stats.proportion import (
        confint_proportions_2indep,
        proportion_confint,
    )

    from app.backend.app.stats.binary import (
        newcombe_difference_interval,
        wilson_score_interval,
    )
    from app.backend.app.stats.fisher_exact import fisher_exact_test
    from app.backend.app.stats.poisson_rate import poisson_rate_test
    from app.backend.app.stats.unconditional_exact import (
        barnard_exact_test,
        boschloo_exact_test,
    )

    wilson = wilson_score_interval(7, 20, 0.05)
    expected_wilson = proportion_confint(7, 20, alpha=0.05, method="wilson")
    for label, observed, expected in zip(("lower", "upper"), wilson, expected_wilson, strict=True):
        _add_check(
            checks,
            case="wilson_interval",
            metric=label,
            observed=observed,
            expected=expected,
            abs_tolerance=1e-12,
            source="statsmodels.proportion_confint(method='wilson')",
        )

    newcombe = newcombe_difference_interval(56, 70, 48, 80, 0.05)
    expected_newcombe = confint_proportions_2indep(
        56,
        70,
        48,
        80,
        method="newcomb",
        compare="diff",
        alpha=0.05,
    )
    for label, observed, expected in zip(
        ("lower", "upper"), newcombe, expected_newcombe, strict=True
    ):
        _add_check(
            checks,
            case="newcombe_difference_interval",
            metric=label,
            observed=observed,
            expected=expected,
            abs_tolerance=1e-12,
            source="statsmodels.confint_proportions_2indep(method='newcomb')",
        )

    table = [[8, 2], [1, 5]]
    fisher = fisher_exact_test(8, 10, 1, 6)
    fisher_ref = scipy_stats.fisher_exact(table, alternative="two-sided")
    _add_check(
        checks,
        case="fisher_exact",
        metric="p_value",
        observed=fisher["p_value"],
        expected=fisher_ref.pvalue,
        abs_tolerance=1e-10,
        source="scipy.stats.fisher_exact",
    )
    _add_check(
        checks,
        case="fisher_exact",
        metric="odds_ratio",
        observed=fisher["odds_ratio"],
        expected=fisher_ref.statistic,
        abs_tolerance=1e-12,
        source="scipy.stats.fisher_exact",
    )

    # scipy's unconditional exact APIs expect columns to be samples:
    # [[control_success, treatment_success], [control_failure, treatment_failure]].
    unconditional_table = [[3, 8], [7, 2]]
    boschloo = boschloo_exact_test(3, 10, 8, 10)
    boschloo_ref = scipy_stats.boschloo_exact(unconditional_table, alternative="two-sided", n=256)
    _add_check(
        checks,
        case="boschloo_exact",
        metric="p_value",
        observed=boschloo["p_value"],
        expected=boschloo_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.boschloo_exact",
    )
    barnard = barnard_exact_test(3, 10, 8, 10)
    barnard_ref = scipy_stats.barnard_exact(unconditional_table, alternative="two-sided", n=256)
    _add_check(
        checks,
        case="barnard_exact",
        metric="p_value",
        observed=barnard["p_value"],
        expected=barnard_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.barnard_exact",
    )

    poisson = poisson_rate_test(30, 1000.0, 45, 1000.0, alpha=0.05)
    if poisson is None:
        raise AssertionError("poisson oracle case unexpectedly degenerated")
    poisson_ref = scipy_stats.binomtest(45, 75, p=0.5, alternative="two-sided")
    _add_check(
        checks,
        case="poisson_rate",
        metric="p_value",
        observed=poisson["p_value"],
        expected=poisson_ref.pvalue,
        abs_tolerance=1e-12,
        source="scipy.stats.binomtest",
    )


def _check_continuous_and_robust_family(checks: list[Check]) -> None:
    import numpy as np
    from scipy import stats as scipy_stats
    from statsmodels.stats.weightstats import ttost_ind

    from app.backend.app.schemas.api import ObservedResultsContinuous
    from app.backend.app.services.results.continuous import _analyze_continuous
    from app.backend.app.stats.bootstrap_permutation import bootstrap_permutation_test
    from app.backend.app.stats.equivalence import tost_equivalence_test
    from app.backend.app.stats.mann_whitney import mann_whitney_u_test
    from app.backend.app.stats.quantile_te import quantile_treatment_effect_test
    from app.backend.app.stats.trimmed_t import trimmed_means_t_test

    control = [5.1, 4.8, 6.2, 5.5, 4.9, 5.7, 6.0, 5.3]
    treatment = [6.5, 7.1, 6.8, 7.4, 6.9, 7.7, 6.2, 7.0, 7.3]
    obs = ObservedResultsContinuous(
        control_mean=float(np.mean(control)),
        control_std=float(np.std(control, ddof=1)),
        control_n=len(control),
        treatment_mean=float(np.mean(treatment)),
        treatment_std=float(np.std(treatment, ddof=1)),
        treatment_n=len(treatment),
        alpha=0.05,
    )
    continuous = _analyze_continuous(obs)
    welch_ref = scipy_stats.ttest_ind(treatment, control, equal_var=False)
    _add_check(
        checks,
        case="welch_t",
        metric="test_statistic",
        observed=continuous.test_statistic,
        expected=round(float(welch_ref.statistic), 4),
        abs_tolerance=5e-5,
        source="scipy.stats.ttest_ind(equal_var=False)",
    )
    _add_check(
        checks,
        case="welch_t",
        metric="p_value",
        observed=continuous.p_value,
        expected=round(float(welch_ref.pvalue), 6),
        abs_tolerance=5e-7,
        source="scipy.stats.ttest_ind(equal_var=False)",
    )

    margin = 0.5
    equivalence_control = [10.1, 9.8, 10.4, 10.0, 9.9, 10.2, 10.3, 9.7]
    equivalence_treatment = [10.0, 10.1, 10.2, 9.9, 10.1, 10.0, 10.3, 9.8]
    equivalence = tost_equivalence_test(
        control_mean=float(np.mean(equivalence_control)),
        control_std=float(np.std(equivalence_control, ddof=1)),
        control_n=len(equivalence_control),
        treatment_mean=float(np.mean(equivalence_treatment)),
        treatment_std=float(np.std(equivalence_treatment, ddof=1)),
        treatment_n=len(equivalence_treatment),
        margin=margin,
        alpha=0.05,
    )
    if equivalence is None:
        raise AssertionError("equivalence oracle case unexpectedly degenerated")
    tost_ref = ttost_ind(
        equivalence_treatment,
        equivalence_control,
        -margin,
        margin,
        usevar="unequal",
    )
    _add_check(
        checks,
        case="tost_equivalence",
        metric="p_value",
        observed=equivalence["p_value"],
        expected=tost_ref[0],
        abs_tolerance=2e-6,
        source="statsmodels.stats.weightstats.ttost_ind(usevar='unequal')",
    )

    mann = mann_whitney_u_test(control, treatment)
    mann_ref = scipy_stats.mannwhitneyu(
        treatment,
        control,
        alternative="two-sided",
        method="asymptotic",
    )
    if mann is None:
        raise AssertionError("Mann-Whitney oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="mann_whitney",
        metric="u_statistic",
        observed=mann["u_statistic"],
        expected=mann_ref.statistic,
        abs_tolerance=1e-12,
        source="scipy.stats.mannwhitneyu(method='asymptotic')",
    )
    _add_check(
        checks,
        case="mann_whitney",
        metric="p_value",
        observed=mann["p_value"],
        expected=mann_ref.pvalue,
        abs_tolerance=1e-12,
        source="scipy.stats.mannwhitneyu(method='asymptotic')",
    )

    trimmed_control = [1.0, 2.0, 2.2, 2.4, 2.8, 3.0, 3.4, 20.0]
    trimmed_treatment = [1.4, 2.3, 2.5, 2.9, 3.1, 3.6, 3.8, 22.0]
    trimmed = trimmed_means_t_test(trimmed_control, trimmed_treatment, trim=0.2)
    trimmed_ref = scipy_stats.ttest_ind(
        trimmed_treatment,
        trimmed_control,
        equal_var=False,
        trim=0.2,
    )
    if trimmed is None:
        raise AssertionError("trimmed-t oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="trimmed_t",
        metric="test_statistic",
        observed=trimmed["test_statistic"],
        expected=trimmed_ref.statistic,
        abs_tolerance=2e-6,
        source="scipy.stats.ttest_ind(trim=0.2,equal_var=False)",
    )
    _add_check(
        checks,
        case="trimmed_t",
        metric="p_value",
        observed=trimmed["p_value"],
        expected=trimmed_ref.pvalue,
        abs_tolerance=2e-6,
        source="scipy.stats.ttest_ind(trim=0.2,equal_var=False)",
    )

    resample_control = [1.0, 2.0, 3.0, 4.0]
    resample_treatment = [2.5, 3.5, 4.5, 5.5]
    bootstrap_a = bootstrap_permutation_test(
        resample_control, resample_treatment, n_resamples=500, seed=123
    )
    bootstrap_b = bootstrap_permutation_test(
        resample_control, resample_treatment, n_resamples=500, seed=123
    )
    if bootstrap_a is None or bootstrap_b is None:
        raise AssertionError("bootstrap oracle case unexpectedly degenerated")
    for metric in ("observed_diff", "p_value", "ci_lower", "ci_upper"):
        _add_check(
            checks,
            case="bootstrap_permutation_reproducibility",
            metric=metric,
            observed=bootstrap_a[metric],
            expected=bootstrap_b[metric],
            abs_tolerance=0.0,
            source="same fixed seed rerun",
        )

    quantile = quantile_treatment_effect_test(
        resample_control, resample_treatment, quantile=0.5, n_resamples=500, seed=321
    )
    shifted = quantile_treatment_effect_test(
        [value + 10.0 for value in resample_control],
        [value + 10.0 for value in resample_treatment],
        quantile=0.5,
        n_resamples=500,
        seed=321,
    )
    if quantile is None or shifted is None:
        raise AssertionError("quantile oracle case unexpectedly degenerated")
    for metric in ("observed_diff", "p_value", "ci_lower", "ci_upper"):
        _add_check(
            checks,
            case="quantile_translation_invariance",
            metric=metric,
            observed=shifted[metric],
            expected=quantile[metric],
            abs_tolerance=1e-12,
            source="translation-invariance metamorphic oracle",
        )


def _check_paired_family(checks: list[Check]) -> None:
    from scipy import stats as scipy_stats
    from statsmodels.stats.contingency_tables import mcnemar

    from app.backend.app.stats.paired import (
        mcnemar_test,
        paired_t_test,
        wilcoxon_signed_rank_test,
    )

    control = [10.0, 12.0, 9.0, 11.0, 10.5, 9.5, 13.0, 12.5]
    treatment = [11.0, 13.0, 10.5, 11.5, 11.0, 10.0, 14.0, 12.8]
    paired = paired_t_test(control, treatment)
    paired_ref = scipy_stats.ttest_rel(treatment, control)
    if paired is None:
        raise AssertionError("paired-t oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="paired_t",
        metric="test_statistic",
        observed=paired["test_statistic"],
        expected=paired_ref.statistic,
        abs_tolerance=2e-6,
        source="scipy.stats.ttest_rel",
    )
    _add_check(
        checks,
        case="paired_t",
        metric="p_value",
        observed=paired["p_value"],
        expected=paired_ref.pvalue,
        abs_tolerance=2e-6,
        source="scipy.stats.ttest_rel",
    )

    wilcoxon = wilcoxon_signed_rank_test(control, treatment)
    wilcoxon_ref = scipy_stats.wilcoxon(
        treatment,
        control,
        zero_method="wilcox",
        correction=True,
        alternative="two-sided",
        method="approx",
    )
    if wilcoxon is None:
        raise AssertionError("Wilcoxon oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="wilcoxon_signed_rank",
        metric="test_statistic",
        observed=wilcoxon["test_statistic"],
        expected=wilcoxon_ref.statistic,
        abs_tolerance=1e-12,
        source="scipy.stats.wilcoxon(method='approx', correction=True)",
    )
    _add_check(
        checks,
        case="wilcoxon_signed_rank",
        metric="p_value",
        observed=wilcoxon["p_value"],
        expected=wilcoxon_ref.pvalue,
        abs_tolerance=2e-6,
        source="scipy.stats.wilcoxon(method='approx', correction=True)",
    )

    control_binary = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]
    treatment_binary = [0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0]
    mcnemar_result = mcnemar_test(control_binary, treatment_binary)
    # rows = control 0/1, columns = treatment 0/1
    table = [[2, 3], [3, 4]]
    exact = mcnemar(table, exact=True, correction=True)
    _add_check(
        checks,
        case="mcnemar",
        metric="p_value",
        observed=mcnemar_result["p_value"],
        expected=exact.pvalue,
        abs_tolerance=1e-12,
        source="statsmodels.stats.contingency_tables.mcnemar(exact=True)",
    )


def _check_ratio_and_categorical_family(checks: list[Check]) -> None:
    import numpy as np
    from scipy import stats as scipy_stats

    from app.backend.app.stats.chi_square_independence import (
        chi_square_independence_test,
        g_test_independence,
    )
    from app.backend.app.stats.ratio import compare_ratios

    table = [[18, 22, 10], [25, 15, 20], [12, 18, 30]]
    chi_square = chi_square_independence_test(table)
    chi_ref = scipy_stats.chi2_contingency(table, correction=False)
    _add_check(
        checks,
        case="chi_square_independence",
        metric="statistic",
        observed=chi_square["chi_square"],
        expected=chi_ref.statistic,
        abs_tolerance=1e-10,
        source="scipy.stats.chi2_contingency(correction=False)",
    )
    _add_check(
        checks,
        case="chi_square_independence",
        metric="p_value",
        observed=chi_square["p_value"],
        expected=chi_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.chi2_contingency(correction=False)",
    )

    g_test = g_test_independence(table)
    g_ref = scipy_stats.chi2_contingency(table, correction=False, lambda_="log-likelihood")
    _add_check(
        checks,
        case="g_test_independence",
        metric="statistic",
        observed=g_test["chi_square"],
        expected=g_ref.statistic,
        abs_tolerance=1e-10,
        source="scipy.stats.chi2_contingency(lambda_='log-likelihood')",
    )
    _add_check(
        checks,
        case="g_test_independence",
        metric="p_value",
        observed=g_test["p_value"],
        expected=g_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.chi2_contingency(lambda_='log-likelihood')",
    )

    control_x = np.array([100.0, 120.0, 90.0, 110.0, 95.0, 105.0])
    control_y = np.array([42.0, 51.0, 38.0, 49.0, 41.0, 46.0])
    treatment_x = np.array([98.0, 115.0, 102.0, 108.0, 99.0, 111.0])
    treatment_y = np.array([51.0, 63.0, 55.0, 60.0, 52.0, 62.0])
    control_stats = _ratio_stats_from_arrays(control_x, control_y)
    treatment_stats = _ratio_stats_from_arrays(treatment_x, treatment_y)
    ratio = compare_ratios(control_stats, treatment_stats)
    if ratio is None:
        raise AssertionError("ratio oracle case unexpectedly degenerated")
    control_ratio, control_variance = _numpy_ratio_and_variance(control_x, control_y)
    treatment_ratio, treatment_variance = _numpy_ratio_and_variance(treatment_x, treatment_y)
    expected_effect = treatment_ratio - control_ratio
    expected_variance = control_variance + treatment_variance
    _add_check(
        checks,
        case="ratio_delta_method",
        metric="effect",
        observed=ratio["effect"],
        expected=expected_effect,
        abs_tolerance=1e-12,
        source="independent numpy covariance delta-method",
    )
    _add_check(
        checks,
        case="ratio_delta_method",
        metric="standard_error",
        observed=ratio["standard_error"],
        expected=math.sqrt(expected_variance),
        abs_tolerance=1e-12,
        source="independent numpy covariance delta-method",
    )


def _ratio_stats_from_arrays(x: Any, y: Any) -> dict[str, float]:
    import numpy as np

    return {
        "n": float(len(x)),
        "sum_x": float(np.sum(x)),
        "sum_x2": float(np.sum(x * x)),
        "sum_y": float(np.sum(y)),
        "sum_y2": float(np.sum(y * y)),
        "sum_xy": float(np.sum(x * y)),
    }


def _numpy_ratio_and_variance(x: Any, y: Any) -> tuple[float, float]:
    import numpy as np

    mean_x = float(np.mean(x))
    mean_y = float(np.mean(y))
    ratio = mean_y / mean_x
    var_x = float(np.var(x, ddof=1))
    var_y = float(np.var(y, ddof=1))
    cov_xy = float(np.cov(x, y, ddof=1)[0, 1])
    variance = (var_y - 2.0 * ratio * cov_xy + ratio * ratio * var_x) / (
        len(x) * mean_x * mean_x
    )
    return ratio, max(variance, 0.0)


def _check_omnibus_survival_and_cox(checks: list[Check]) -> None:
    import pandas as pd
    from lifelines import CoxPHFitter
    from lifelines.statistics import logrank_test, multivariate_logrank_test
    from scipy import stats as scipy_stats
    from statsmodels.stats.oneway import anova_oneway

    from app.backend.app.stats.cox_ph import cox_ph_treatment_effect
    from app.backend.app.stats.omnibus import kruskal_wallis_test, welch_anova_test
    from app.backend.app.stats.survival import (
        log_rank_test,
        weighted_k_sample_log_rank_test,
    )

    groups = [
        [5.1, 4.8, 6.2, 5.5, 4.9, 5.7, 6.0, 5.3],
        [6.5, 7.1, 6.8, 7.4, 6.9, 7.7, 6.2, 7.0, 7.3],
        [5.9, 6.3, 6.7, 5.5, 6.1, 6.4, 7.2],
    ]
    welch = welch_anova_test(groups)
    welch_ref = anova_oneway(groups, use_var="unequal", welch_correction=True)
    if welch is None:
        raise AssertionError("Welch ANOVA oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="welch_anova",
        metric="statistic",
        observed=welch["test_statistic"],
        expected=welch_ref.statistic,
        abs_tolerance=1e-9,
        source="statsmodels.stats.oneway.anova_oneway(use_var='unequal')",
    )
    _add_check(
        checks,
        case="welch_anova",
        metric="p_value",
        observed=welch["p_value"],
        expected=welch_ref.pvalue,
        abs_tolerance=5e-7,
        source="statsmodels.stats.oneway.anova_oneway(use_var='unequal')",
    )
    _add_check(
        checks,
        case="welch_anova",
        metric="df_denominator",
        observed=welch["df_denominator"],
        expected=welch_ref.df_denom,
        abs_tolerance=1e-7,
        source="statsmodels.stats.oneway.anova_oneway(use_var='unequal')",
    )

    kruskal = kruskal_wallis_test(groups)
    kruskal_ref = scipy_stats.kruskal(*groups)
    if kruskal is None:
        raise AssertionError("Kruskal-Wallis oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="kruskal_wallis",
        metric="statistic",
        observed=kruskal["test_statistic"],
        expected=kruskal_ref.statistic,
        abs_tolerance=1e-9,
        source="scipy.stats.kruskal",
    )
    _add_check(
        checks,
        case="kruskal_wallis",
        metric="p_value",
        observed=kruskal["p_value"],
        expected=kruskal_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.kruskal",
    )

    placebo_durations, placebo_events, mp6_durations, mp6_events, third_durations, third_events = (
        _survival_fixture()
    )
    logrank = log_rank_test(mp6_durations, mp6_events, placebo_durations, placebo_events)
    logrank_ref = logrank_test(
        mp6_durations,
        placebo_durations,
        event_observed_A=mp6_events,
        event_observed_B=placebo_events,
    )
    if logrank is None:
        raise AssertionError("log-rank oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="log_rank",
        metric="chi_square",
        observed=logrank["chi_square"],
        expected=logrank_ref.test_statistic,
        abs_tolerance=1e-9,
        source="lifelines.statistics.logrank_test",
    )
    _add_check(
        checks,
        case="log_rank",
        metric="p_value",
        observed=logrank["p_value"],
        expected=logrank_ref.p_value,
        abs_tolerance=5e-7,
        source="lifelines.statistics.logrank_test",
    )

    arms = [
        (mp6_durations, mp6_events),
        (placebo_durations, placebo_events),
        (third_durations, third_events),
    ]
    weighted = weighted_k_sample_log_rank_test(arms, rho=1.0, gamma=0.0)
    durations = mp6_durations + placebo_durations + third_durations
    events = mp6_events + placebo_events + third_events
    labels = ["mp6"] * len(mp6_durations) + ["placebo"] * len(placebo_durations) + [
        "third"
    ] * len(third_durations)
    weighted_ref = multivariate_logrank_test(
        durations,
        labels,
        event_observed=events,
        weightings="fleming-harrington",
        p=1,
        q=0,
    )
    if weighted is None:
        raise AssertionError("weighted log-rank oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="fleming_harrington_log_rank",
        metric="chi_square",
        observed=weighted["chi_square"],
        expected=weighted_ref.test_statistic,
        abs_tolerance=1e-8,
        source="lifelines.statistics.multivariate_logrank_test(weightings='fleming-harrington')",
    )
    _add_check(
        checks,
        case="fleming_harrington_log_rank",
        metric="p_value",
        observed=weighted["p_value"],
        expected=weighted_ref.p_value,
        abs_tolerance=5e-7,
        source="lifelines.statistics.multivariate_logrank_test(weightings='fleming-harrington')",
    )

    cox = cox_ph_treatment_effect(
        placebo_durations,
        placebo_events,
        mp6_durations,
        mp6_events,
    )
    if cox is None:
        raise AssertionError("Cox PH oracle case unexpectedly degenerated")
    cox_df = pd.DataFrame(
        {
            "duration": placebo_durations + mp6_durations,
            "event": placebo_events + mp6_events,
            "treatment": [0] * len(placebo_durations) + [1] * len(mp6_durations),
        }
    )
    cox_ref = CoxPHFitter()
    cox_ref.fit(cox_df, duration_col="duration", event_col="event", formula="treatment")
    _add_check(
        checks,
        case="cox_ph",
        metric="log_hazard_ratio",
        observed=cox["log_hazard_ratio"],
        expected=cox_ref.params_["treatment"],
        abs_tolerance=5e-7,
        source="lifelines.CoxPHFitter",
    )
    _add_check(
        checks,
        case="cox_ph",
        metric="standard_error",
        observed=cox["standard_error"],
        expected=cox_ref.standard_errors_["treatment"],
        abs_tolerance=5e-7,
        source="lifelines.CoxPHFitter",
    )
    _add_check(
        checks,
        case="cox_ph",
        metric="hazard_ratio",
        observed=cox["hazard_ratio"],
        expected=cox_ref.hazard_ratios_["treatment"],
        abs_tolerance=5e-7,
        source="lifelines.CoxPHFitter",
    )


def _survival_fixture() -> tuple[list[float], list[bool], list[float], list[bool], list[float], list[bool]]:
    placebo_durations = [1, 1, 2, 2, 3, 4, 4, 5, 5, 8, 8, 8, 8, 11, 11, 12, 12, 15, 17, 22, 23]
    placebo_events = [True] * len(placebo_durations)
    mp6_raw = [
        (6, True),
        (6, True),
        (6, True),
        (6, False),
        (7, True),
        (9, False),
        (10, True),
        (10, False),
        (11, False),
        (13, True),
        (16, True),
        (17, False),
        (19, False),
        (20, False),
        (22, True),
        (23, True),
        (25, False),
        (32, False),
        (32, False),
        (34, False),
        (35, False),
    ]
    third_raw = [
        (2, True),
        (4, True),
        (5, False),
        (6, True),
        (7, True),
        (9, True),
        (11, False),
        (12, True),
        (14, True),
        (15, False),
        (18, True),
        (21, False),
        (24, True),
        (26, False),
        (30, False),
    ]
    mp6_durations = [float(time) for time, _ in mp6_raw]
    mp6_events = [event for _, event in mp6_raw]
    third_durations = [float(time) for time, _ in third_raw]
    third_events = [event for _, event in third_raw]
    return (
        [float(value) for value in placebo_durations],
        placebo_events,
        mp6_durations,
        mp6_events,
        third_durations,
        third_events,
    )


def _run_oracle() -> dict[str, Any]:
    _assert_oracle_dependencies()
    checks: list[Check] = []
    _check_student_and_distribution_tails(checks)
    _check_binary_and_exact_family(checks)
    _check_continuous_and_robust_family(checks)
    _check_paired_family(checks)
    _check_ratio_and_categorical_family(checks)
    _check_omnibus_survival_and_cox(checks)
    failures = [check for check in checks if not check.passed]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "dependencies": _dependency_versions(),
        "summary": {
            "checks": len(checks),
            "failed": len(failures),
            "cases": sorted({check.case for check in checks}),
        },
        "checks": [check.__dict__ for check in checks],
    }


def _write_artifact(report: dict[str, Any], artifact_path: Path) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _self_test() -> int:
    checks: list[Check] = []
    _add_check(
        checks,
        case="self_test",
        metric="exact",
        observed=1.0,
        expected=1.0,
        abs_tolerance=0.0,
        source="internal",
    )
    _add_check(
        checks,
        case="self_test",
        metric="tolerance",
        observed=1.000001,
        expected=1.0,
        abs_tolerance=2e-6,
        source="internal",
    )
    if not all(check.passed for check in checks):
        print("self-test failed", file=sys.stderr)
        return 1
    print("self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path(".ci-artifacts/statistical-oracle.json"),
        help="JSON artifact path for versions and comparison diffs.",
    )
    parser.add_argument("--self-test", action="store_true", help="Run a fast stdlib-only CLI smoke.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        report = _run_oracle()
    except Exception as exc:
        print(f"[stat-oracle] ERROR: {exc}", file=sys.stderr)
        return 2
    _write_artifact(report, args.artifact)
    failed = int(report["summary"]["failed"])
    check_count = int(report["summary"]["checks"])
    if failed:
        print(f"[stat-oracle] {failed}/{check_count} checks failed; see {args.artifact}", file=sys.stderr)
        return 1
    print(f"[stat-oracle] {check_count} checks passed; artifact: {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
