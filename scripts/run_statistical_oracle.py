"""Run a differential statistical oracle against optional scientific libraries.

The production runtime remains stdlib-only for the statistics engine. This script is an
optional verification gate: install ``app/backend/requirements-oracle.txt`` after the normal
dev requirements, run this script, and inspect the JSON artifact if a comparison drifts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
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
SCIENTIFIC_THREAD_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


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
        expected_magnitude = abs(expected_float)
        rel_diff = (
            abs_diff / expected_magnitude
            if expected_magnitude > 0.0
            else abs_diff
        )
        allowed = max(abs_tolerance, rel_tolerance * expected_magnitude)
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


def _bound_scientific_library_threads() -> None:
    for variable in SCIENTIFIC_THREAD_ENV_VARS:
        os.environ[variable] = "1"


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


def _check_supporting_statistical_utilities(checks: list[Check]) -> None:
    import numpy as np
    from scipy import stats as scipy_stats
    from statsmodels.stats.multitest import multipletests

    from app.backend.app.stats.cuped import adjusted_variance, cuped_theta
    from app.backend.app.stats.guardrail import (
        DECREASE_IS_BAD,
        INCREASE_IS_BAD,
        STATUS_BREACHED,
        STATUS_OK,
        evaluate_guardrail,
        harm_in_direction,
    )
    from app.backend.app.stats.multiple_testing import (
        benjamini_hochberg,
        holm_bonferroni,
    )
    from app.backend.app.stats.sequential import obrien_fleming_boundaries
    from app.backend.app.stats.srm import chi_square_srm

    srm = chi_square_srm([530, 470], [0.5, 0.5])
    srm_ref = scipy_stats.chisquare([530, 470], f_exp=[500, 500])
    _add_check(
        checks,
        case="srm_chi_square",
        metric="statistic",
        observed=srm[0],
        expected=srm_ref.statistic,
        abs_tolerance=1e-12,
        source="scipy.stats.chisquare",
    )
    _add_check(
        checks,
        case="srm_chi_square",
        metric="p_value",
        observed=srm[1],
        expected=srm_ref.pvalue,
        abs_tolerance=5e-7,
        source="scipy.stats.chisquare",
    )

    pvalues = [0.001, 0.02, 0.04, 0.2, 0.8]
    bh = benjamini_hochberg(pvalues, q=0.05)
    bh_reject, bh_adjusted, _, _ = multipletests(pvalues, alpha=0.05, method="fdr_bh")
    holm = holm_bonferroni(pvalues, alpha=0.05)
    holm_reject, holm_adjusted, _, _ = multipletests(pvalues, alpha=0.05, method="holm")
    for index, (observed, expected) in enumerate(
        zip(bh["adjusted_pvalues"], bh_adjusted, strict=True)
    ):
        _add_check(
            checks,
            case="benjamini_hochberg",
            metric=f"adjusted_pvalue[{index}]",
            observed=observed,
            expected=expected,
            abs_tolerance=1e-12,
            source="statsmodels.stats.multitest.multipletests(method='fdr_bh')",
        )
    for index, (observed, expected) in enumerate(zip(bh["rejected"], bh_reject, strict=True)):
        _add_check(
            checks,
            case="benjamini_hochberg",
            metric=f"rejected[{index}]",
            observed=float(observed),
            expected=float(expected),
            abs_tolerance=0.0,
            source="statsmodels.stats.multitest.multipletests(method='fdr_bh')",
        )
    for index, (observed, expected) in enumerate(
        zip(holm["adjusted_pvalues"], holm_adjusted, strict=True)
    ):
        _add_check(
            checks,
            case="holm_bonferroni",
            metric=f"adjusted_pvalue[{index}]",
            observed=observed,
            expected=expected,
            abs_tolerance=1e-12,
            source="statsmodels.stats.multitest.multipletests(method='holm')",
        )
    for index, (observed, expected) in enumerate(zip(holm["rejected"], holm_reject, strict=True)):
        _add_check(
            checks,
            case="holm_bonferroni",
            metric=f"rejected[{index}]",
            observed=float(observed),
            expected=float(expected),
            abs_tolerance=0.0,
            source="statsmodels.stats.multitest.multipletests(method='holm')",
        )

    sigma_xx = [[4.0, 1.0], [1.0, 9.0]]
    sigma_xy = [2.0, 3.0]
    theta = cuped_theta(sigma_xx, sigma_xy)
    if theta is None:
        raise AssertionError("CUPED oracle case unexpectedly degenerated")
    theta_ref = np.linalg.solve(np.array(sigma_xx), np.array(sigma_xy))
    for index, (observed, expected) in enumerate(zip(theta, theta_ref, strict=True)):
        _add_check(
            checks,
            case="cuped_theta",
            metric=f"theta[{index}]",
            observed=observed,
            expected=expected,
            abs_tolerance=1e-12,
            source="numpy.linalg.solve",
        )
    variance = adjusted_variance(25.0, theta, sigma_xy, sigma_xx)
    variance_ref = 25.0 - 2.0 * float(np.dot(theta_ref, sigma_xy)) + float(
        theta_ref.T @ np.array(sigma_xx) @ theta_ref
    )
    _add_check(
        checks,
        case="cuped_adjusted_variance",
        metric="variance",
        observed=variance,
        expected=variance_ref,
        abs_tolerance=1e-12,
        source="numpy quadratic form",
    )

    for n_looks in range(2, 6):
        boundaries = obrien_fleming_boundaries(n_looks, alpha=0.05)
        information = np.arange(1, n_looks + 1, dtype=float) / n_looks
        correlation = np.sqrt(
            np.minimum.outer(information, information)
            / np.maximum.outer(information, information)
        )
        z_boundaries = np.array([look["z_boundary"] for look in boundaries])
        survival_probability = scipy_stats.multivariate_normal.cdf(
            z_boundaries,
            mean=np.zeros(n_looks),
            cov=correlation,
            lower_limit=-z_boundaries,
            maxpts=1_000_000,
            abseps=1e-7,
            releps=1e-7,
            rng=np.random.default_rng(20260902 + n_looks),
        )
        _add_check(
            checks,
            case="obrien_fleming_boundaries",
            metric=f"scipy_type_i_k={n_looks}",
            observed=1.0 - survival_probability,
            expected=0.05,
            abs_tolerance=2e-4,
            source="scipy.stats.multivariate_normal rectangular crossing probability",
        )

    guardrail = evaluate_guardrail(0.12, 0.0004, direction=INCREASE_IS_BAD, margin=0.05)
    if guardrail is None:
        raise AssertionError("guardrail oracle case unexpectedly degenerated")
    guardrail_z = (0.12 - 0.05) / math.sqrt(0.0004)
    _add_check(
        checks,
        case="guardrail_noninferiority",
        metric="p_value",
        observed=guardrail["p_value"],
        expected=1.0 - scipy_stats.norm.cdf(guardrail_z),
        abs_tolerance=1e-12,
        source="scipy.stats.norm.cdf one-sided reference",
    )
    _add_check(
        checks,
        case="guardrail_noninferiority",
        metric="breached_status",
        observed=float(guardrail["status"] == STATUS_BREACHED),
        expected=1.0,
        abs_tolerance=0.0,
        source="one-sided lower-bound duality",
    )
    _add_check(
        checks,
        case="guardrail_noninferiority",
        metric="decrease_is_bad_harm_sign",
        observed=harm_in_direction(0.12, DECREASE_IS_BAD),
        expected=-0.12,
        abs_tolerance=0.0,
        source="directed harm sign contract",
    )
    ok_guardrail = evaluate_guardrail(0.12, 0.0004, direction=DECREASE_IS_BAD, margin=0.0)
    if ok_guardrail is None:
        raise AssertionError("guardrail OK oracle case unexpectedly degenerated")
    _add_check(
        checks,
        case="guardrail_noninferiority",
        metric="improvement_status_ok",
        observed=float(ok_guardrail["status"] == STATUS_OK),
        expected=1.0,
        abs_tolerance=0.0,
        source="directed harm sign contract",
    )


def _check_c05_independent_oracles(checks: list[Check]) -> None:
    import numpy as np
    import statsmodels.api as sm
    from scipy import integrate as scipy_integrate
    from scipy import stats as scipy_stats
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    from app.backend.app.services.live_stats.cuped import _build_cuped_block
    from app.backend.app.services.monte_carlo_service import (
        beta_probability_treatment_beats_control,
    )
    from app.backend.app.stats.always_valid import always_valid_p_value
    from app.backend.app.stats.binary import calculate_binary_sample_size
    from app.backend.app.stats.continuous import calculate_continuous_sample_size
    from app.backend.app.stats.stratification import (
        combine_strata,
        continuous_point_variance,
        stratum_difference,
    )

    power_solver = NormalIndPower()
    allocations = (("50/50", (0.5, 0.5)), ("90/10", (0.9, 0.1)))
    binary_effect_size = abs(proportion_effectsize(0.1, 0.11))
    for label, allocation in allocations:
        ratio = allocation[1] / allocation[0]
        binary = calculate_binary_sample_size(
            baseline_rate=0.1,
            mde_pct=10.0,
            alpha=0.05,
            power=0.8,
            traffic_split=allocation,
        )
        binary_control_reference = power_solver.solve_power(
            effect_size=binary_effect_size,
            alpha=0.05,
            power=0.8,
            ratio=ratio,
            alternative="two-sided",
        )
        _add_check(
            checks,
            case="binary_sample_size",
            metric=f"total_n_{label}",
            observed=binary["total_sample_size"],
            expected=binary_control_reference * (1.0 + ratio),
            abs_tolerance=2.0,
            rel_tolerance=0.02,
            source="statsmodels.stats.power.NormalIndPower with proportion_effectsize",
        )

        continuous = calculate_continuous_sample_size(
            baseline_mean=100.0,
            std_dev=20.0,
            mde_pct=5.0,
            alpha=0.05,
            power=0.8,
            traffic_split=allocation,
        )
        continuous_control_reference = power_solver.solve_power(
            effect_size=0.25,
            alpha=0.05,
            power=0.8,
            ratio=ratio,
            alternative="two-sided",
        )
        _add_check(
            checks,
            case="continuous_sample_size",
            metric=f"total_n_{label}",
            observed=continuous["total_sample_size"],
            expected=continuous_control_reference * (1.0 + ratio),
            abs_tolerance=2.0,
            rel_tolerance=0.003,
            source="statsmodels.stats.power.NormalIndPower",
        )

    raw_strata = (
        (
            np.array([9.0, 10.0, 11.0, 12.0]),
            np.array([11.0, 12.0, 12.0, 13.0, 14.0]),
        ),
        (
            np.array([18.0, 19.0, 20.0, 20.0, 21.0, 22.0]),
            np.array([20.0, 21.0, 22.0, 23.0, 24.0]),
        ),
    )
    production_strata: list[dict[str, Any]] = []
    stratum_references: list[tuple[int, float, float]] = []
    for control_values, treatment_values in raw_strata:
        control = continuous_point_variance(
            float(control_values.sum()),
            float(np.dot(control_values, control_values)),
            len(control_values),
        )
        treatment = continuous_point_variance(
            float(treatment_values.sum()),
            float(np.dot(treatment_values, treatment_values)),
            len(treatment_values),
        )
        if control is None or treatment is None:
            raise AssertionError("post-stratification oracle fixture unexpectedly degenerated")
        difference = stratum_difference(control, treatment)
        stratum_size = len(control_values) + len(treatment_values)
        production_strata.append({"n": stratum_size, **difference})
        reference_delta = float(treatment_values.mean() - control_values.mean())
        reference_variance = float(
            treatment_values.var(ddof=1) / len(treatment_values)
            + control_values.var(ddof=1) / len(control_values)
        )
        stratum_references.append((stratum_size, reference_delta, reference_variance))

    post_stratified = combine_strata(production_strata, alpha=0.05)
    if post_stratified is None:
        raise AssertionError("post-stratification oracle case unexpectedly degenerated")
    total_stratum_size = sum(item[0] for item in stratum_references)
    reference_effect = sum(
        size / total_stratum_size * delta
        for size, delta, _variance in stratum_references
    )
    reference_variance = sum(
        (size / total_stratum_size) ** 2 * variance
        for size, _delta, variance in stratum_references
    )
    reference_standard_error = math.sqrt(reference_variance)
    reference_p_value = 2.0 * scipy_stats.norm.sf(
        abs(reference_effect / reference_standard_error)
    )
    for metric, expected in (
        ("effect", reference_effect),
        ("variance", reference_variance),
        ("standard_error", reference_standard_error),
        ("p_value", reference_p_value),
    ):
        _add_check(
            checks,
            case="post_stratification",
            metric=metric,
            observed=post_stratified[metric],
            expected=expected,
            abs_tolerance=1e-12,
            source="NumPy sample moments and scipy.stats.norm reference",
        )

    control_x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    control_y = np.array([10.0, 13.0, 13.0, 16.0, 18.0, 19.0])
    treatment_x = np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    treatment_y = np.array([14.0, 15.0, 18.0, 20.0, 21.0, 24.0])

    def cuped_arm(index: int, x_values: Any, y_values: Any) -> dict[str, Any]:
        centered_x = x_values - x_values.mean()
        centered_y = y_values - y_values.mean()
        return {
            "variation_index": index,
            "n": len(x_values),
            "sum_y": float(y_values.sum()),
            "sum_y2": float(np.dot(y_values, y_values)),
            "sum_x": [float(x_values.sum())],
            "sum_xy": [float(np.dot(x_values, y_values))],
            "sum_xx": [[float(np.dot(x_values, x_values))]],
            "centered_syy": float(np.dot(centered_y, centered_y)),
            "centered_sxy": [float(np.dot(centered_x, centered_y))],
            "centered_sxx": [[float(np.dot(centered_x, centered_x))]],
        }

    control_n = len(control_x)
    treatment_n = len(treatment_x)
    cuped_block = _build_cuped_block(
        metric_type="continuous",
        alpha=0.05,
        variants_count=2,
        exposed_total=control_n + treatment_n,
        exposed_by_index={0: control_n, 1: treatment_n},
        cuped_aggregates={
            "covariate_names": ["pre_period"],
            "variations": [
                cuped_arm(0, control_x, control_y),
                cuped_arm(1, treatment_x, treatment_y),
            ],
        },
    )
    cuped_comparison = cuped_block["comparisons"][0]
    cuped_analysis = cuped_comparison["analysis"]
    if cuped_comparison["status"] != "ok" or cuped_analysis is None:
        raise AssertionError("live CUPED oracle case unexpectedly degenerated")

    outcomes = np.concatenate((control_y, treatment_y))
    covariate = np.concatenate((control_x, treatment_x))
    treatment_indicator = np.concatenate(
        (np.zeros(control_n), np.ones(treatment_n))
    )
    design_matrix = sm.add_constant(
        np.column_stack((treatment_indicator, covariate))
    )
    ancova_reference = sm.OLS(outcomes, design_matrix).fit()
    for metric, observed, expected, tolerance in (
        ("theta", cuped_block["theta"], ancova_reference.params[2], 5e-7),
        (
            "observed_effect",
            cuped_analysis["observed_effect"],
            ancova_reference.params[1],
            5e-5,
        ),
        (
            "test_statistic",
            cuped_analysis["test_statistic"],
            ancova_reference.tvalues[1],
            5e-5,
        ),
        ("p_value", cuped_analysis["p_value"], ancova_reference.pvalues[1], 5e-7),
    ):
        _add_check(
            checks,
            case="live_cuped_ancova",
            metric=metric,
            observed=observed,
            expected=expected,
            abs_tolerance=tolerance,
            source="statsmodels.api.OLS treatment-plus-covariate ANCOVA",
        )

    alpha = 0.05
    path_count = 20_000
    final_sample_size = 100
    null_generator = np.random.Generator(np.random.PCG64(20260902))
    null_paths = null_generator.standard_normal((path_count, final_sample_size))
    running_sums = np.cumsum(null_paths, axis=1)
    rejected = np.zeros(path_count, dtype=bool)
    for sample_size in range(10, final_sample_size + 1, 10):
        variance = 1.0 / sample_size
        effects = running_sums[:, sample_size - 1] / sample_size
        p_values = np.fromiter(
            (
                always_valid_p_value(float(effect), variance, mixture_variance=0.04)
                for effect in effects
            ),
            dtype=float,
            count=path_count,
        )
        rejected |= p_values < alpha
    empirical_type_i = float(np.mean(rejected))
    _add_check(
        checks,
        case="always_valid_msprt_type_i",
        metric="ten_looks_null_rejection_rate",
        observed=empirical_type_i,
        expected=0.0,
        abs_tolerance=0.055,
        source="20,000-path N(0,1) null simulation at ten sequential looks",
    )

    beta_cases = (
        (100, 10, 100, 12),
        (250, 40, 120, 25),
        (40, 3, 60, 12),
    )
    for control_users, control_conversions, treatment_users, treatment_conversions in beta_cases:
        observed_probability = beta_probability_treatment_beats_control(
            control_users=control_users,
            control_conversions=control_conversions,
            treatment_users=treatment_users,
            treatment_conversions=treatment_conversions,
        )
        control_alpha = control_conversions + 1
        control_beta = control_users - control_conversions + 1
        treatment_alpha = treatment_conversions + 1
        treatment_beta = treatment_users - treatment_conversions + 1
        reference_probability, _error = scipy_integrate.quad(
            lambda probability,
            ta=treatment_alpha,
            tb=treatment_beta,
            ca=control_alpha,
            cb=control_beta: scipy_stats.beta.pdf(probability, ta, tb)
            * scipy_stats.beta.cdf(probability, ca, cb),
            0.0,
            1.0,
            epsabs=1e-12,
            epsrel=1e-12,
            limit=200,
        )
        _add_check(
            checks,
            case="beta_probability_treatment_beats_control",
            metric=(
                f"control={control_conversions}/{control_users},"
                f"treatment={treatment_conversions}/{treatment_users}"
            ),
            observed=observed_probability,
            expected=reference_probability,
            abs_tolerance=1e-10,
            source="scipy.integrate.quad of independent Beta PDF/CDF product",
        )


def _check_supported_method(checks: list[Check]) -> None:
    from statsmodels.stats.proportion import (
        confint_proportions_2indep,
        proportions_ztest,
    )

    from app.backend.app.evidence.stats_kernel import (
        AnalysisPlan,
        BinaryArmStatistics,
        BinarySufficientStatistics,
        LegacyStatsKernelAdapter,
        StatsKernelBuild,
        StatsKernelInputLineage,
        StatsKernelRequest,
    )

    alpha = 0.05
    control_conversions, control_users = 100, 1000
    treatment_conversions, treatment_users = 130, 1000
    digest = "sha256:" + "0" * 64
    result = LegacyStatsKernelAdapter(
        StatsKernelBuild(
            git_commit="0" * 40,
            build_digest=digest,
            dependency_lock_digest=digest,
        )
    ).analyze(
        StatsKernelRequest(
            plan=AnalysisPlan(alpha=alpha),
            aggregates=BinarySufficientStatistics(
                control=BinaryArmStatistics(
                    intervention_id="control",
                    conversions=control_conversions,
                    users=control_users,
                ),
                treatment=BinaryArmStatistics(
                    intervention_id="treatment",
                    conversions=treatment_conversions,
                    users=treatment_users,
                ),
            ),
            lineage=StatsKernelInputLineage(
                protocol_revision_id=digest,
                metric_id="oracle_binary_metric",
                metric_version="v1",
                metric_digest=digest,
                query_ids=(digest,),
                source_snapshot_ids=("oracle_snapshot",),
            ),
        )
    )
    expected_statistic, expected_p_value = proportions_ztest(
        (treatment_conversions, control_conversions),
        (treatment_users, control_users),
        alternative="two-sided",
        prop_var=False,
    )
    expected_lower, expected_upper = confint_proportions_2indep(
        treatment_conversions,
        treatment_users,
        control_conversions,
        control_users,
        method="newcomb",
        compare="diff",
        alpha=alpha,
    )
    comparisons = (
        (
            "test_statistic",
            result.diagnostics.test_statistic,
            expected_statistic,
            1e-4,
            "statsmodels.stats.proportion.proportions_ztest",
        ),
        (
            "p_value",
            result.estimate.uncertainty.p_value,
            expected_p_value,
            1e-6,
            "statsmodels.stats.proportion.proportions_ztest",
        ),
        (
            "interval_lower",
            result.estimate.uncertainty.lower,
            expected_lower,
            1e-6,
            "statsmodels.stats.proportion.confint_proportions_2indep(method='newcomb')",
        ),
        (
            "interval_upper",
            result.estimate.uncertainty.upper,
            expected_upper,
            1e-6,
            "statsmodels.stats.proportion.confint_proportions_2indep(method='newcomb')",
        ),
    )
    for metric, observed, expected, tolerance, source in comparisons:
        _add_check(
            checks,
            case="binary_pooled_z_newcombe",
            metric=metric,
            observed=observed,
            expected=expected,
            abs_tolerance=tolerance,
            source=source,
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
    _bound_scientific_library_threads()
    _assert_oracle_dependencies()
    checks: list[Check] = []
    _check_student_and_distribution_tails(checks)
    _check_binary_and_exact_family(checks)
    _check_continuous_and_robust_family(checks)
    _check_paired_family(checks)
    _check_ratio_and_categorical_family(checks)
    _check_omnibus_survival_and_cox(checks)
    _check_supporting_statistical_utilities(checks)
    _check_c05_independent_oracles(checks)
    _check_supported_method(checks)
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
