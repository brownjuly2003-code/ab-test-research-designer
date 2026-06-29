"""Yuen–Welch trimmed-means t-test on raw continuous samples: a robust two-sample location test that
compares γ-trimmed means with a Winsorized-variance standard error and Welch–Satterthwaite degrees of
freedom, paired with a Student-t confidence interval for the trimmed-mean difference.

Where the Student / Welch t-test compares the *arithmetic* means, a single heavy tail — the usual
shape of revenue, order value, session length — inflates the variance and drags the mean, so the
ordinary t-test loses power and its interval balloons. Trimming a fixed fraction γ from each tail
before estimating the location (Yuen 1974) keeps the efficiency of a mean-based test under a clean
Gaussian centre while staying robust to the tails: the estimand is the population trimmed mean, the
standard error uses the Winsorized variance (the trimmed observations are pulled in to the trimming
cutoffs rather than discarded, which is what makes the variance of the trimmed mean estimable), and
the reference law is a Student-t with Welch degrees of freedom on the effective (untrimmed) counts.

  * γ-trimmed mean — sort each arm, drop the lowest and highest ``g = floor(γ·n)`` observations, and
    average the remaining ``h = n − 2g`` (the "effective" sample size). γ = 0 recovers Welch's t-test
    on the raw means exactly.
  * Winsorized variance — replace the g lowest values with the (g+1)-th smallest and the g highest
    with the (g+1)-th largest, then take the sample sum of squares around the Winsorized mean. The
    squared standard error of the trimmed mean is ``SSD_win / (h·(h−1))``.
  * Welch–Satterthwaite df on the per-arm variance terms ``d_j = SSD_win,j / (h_j·(h_j−1))``:
    ``ν = (d_c + d_t)² / (d_c²/(h_c−1) + d_t²/(h_t−1))``; the statistic is ``(m_t − m_c)/√(d_c + d_t)``
    referred to Student-t(ν), and the interval is ``(m_t − m_c) ± t_{ν,1−α/2}·√(d_c + d_t)``.

The test is the robust complement to the rank-based Mann–Whitney (which tests stochastic dominance,
not a location difference) and to the bootstrap/permutation mean test (which keeps the non-robust mean
as its estimand): it answers "did the robust central location move?" with a parametric, deterministic
calculation — no resampling, so identical inputs always yield identical output.

Sources (checked against the literature at implementation time, not from memory): Yuen, "The two-sample
trimmed t for unequal population variances" (Biometrika 61, 1974); Wilcox, *Introduction to Robust
Estimation and Hypothesis Testing* (4th ed., 2017, §5.3 — the trimmed-mean t and Winsorized variance);
Tukey & McLaughlin (1963 — Winsorization). Cross-checked against ``scipy.stats.ttest_ind(a, b,
trim=γ, equal_var=False)`` and its ``confidence_interval`` at authoring time. The module is
stdlib-only (the Student-t CDF / quantile come from ``stats.student_t``) and holds pure functions;
assembling the response shape lives in the service layer.
"""

from math import isfinite, sqrt
from statistics import fmean
from typing import Any

from app.backend.app.stats.student_t import t_cdf, t_ppf

# Conventional default trimming fraction for Yuen's test (20% from each tail — Wilcox's default).
DEFAULT_TRIM = 0.2


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _winsorized_ssd_and_trimmed_mean(sorted_values: list[float], g: int) -> tuple[float, float]:
    """Return ``(SSD_win, trimmed_mean)`` for one already-sorted arm.

    The g lowest values are pulled up to ``sorted_values[g]`` and the g highest down to
    ``sorted_values[n−g−1]`` (Winsorization); ``SSD_win`` is the sum of squared deviations of that
    Winsorized sample about its own mean, and the trimmed mean averages the middle ``n − 2g`` values.
    With ``g = 0`` this collapses to the ordinary sum of squares and arithmetic mean, so the γ = 0
    path reduces to Welch's t-test.
    """
    n = len(sorted_values)
    low = sorted_values[g]
    high = sorted_values[n - g - 1]
    middle = sorted_values[g : n - g]
    trimmed_mean = fmean(middle)
    winsorized = [low] * g + middle + [high] * g
    winsorized_mean = fmean(winsorized)
    ssd = sum((value - winsorized_mean) ** 2 for value in winsorized)
    return ssd, trimmed_mean


def trimmed_means_t_test(
    control: list[float],
    treatment: list[float],
    trim: float = DEFAULT_TRIM,
    alpha: float = 0.05,
) -> dict[str, Any] | None:
    """Yuen–Welch trimmed-means t-test for the difference ``treatment − control``.

    ``control`` / ``treatment`` are the raw observed values per arm. Returns the per-arm trimmed means
    and effective (untrimmed) sizes, the trimmed-mean difference, its Student-t confidence interval at
    level ``1 − alpha``, the two-sided p-value, the t-statistic and Welch degrees of freedom, an
    asymptotic achieved power (descriptive — the inference is the p-value), and the significance
    verdict. Returns ``None`` when the test is not evaluable: an effective per-arm size
    ``h = n − 2g`` below 2, or a zero pooled Winsorized variance (constant arms after Winsorization —
    a parametric location test has no standard error there; use the permutation or rank test instead).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 <= trim < 0.5:
        raise ValueError("trim must be in [0, 0.5)")
    if any(not isfinite(value) for value in control) or any(
        not isfinite(value) for value in treatment
    ):
        raise ValueError("sample values must be finite")

    n_control = len(control)
    n_treatment = len(treatment)
    if n_control < 2 or n_treatment < 2:
        return None

    g_control = int(n_control * trim)
    g_treatment = int(n_treatment * trim)
    h_control = n_control - 2 * g_control
    h_treatment = n_treatment - 2 * g_treatment
    if h_control < 2 or h_treatment < 2:
        # Too few untrimmed observations to estimate the variance of a trimmed mean.
        return None

    ssd_control, mean_control = _winsorized_ssd_and_trimmed_mean(sorted(control), g_control)
    ssd_treatment, mean_treatment = _winsorized_ssd_and_trimmed_mean(sorted(treatment), g_treatment)

    # Squared standard error of each trimmed mean (Yuen 1974): SSD_win / (h·(h−1)).
    d_control = ssd_control / (h_control * (h_control - 1))
    d_treatment = ssd_treatment / (h_treatment * (h_treatment - 1))
    se_squared = d_control + d_treatment

    effect = mean_treatment - mean_control
    if se_squared <= 0:
        # Both arms have zero Winsorized variance: a parametric location test is not evaluable.
        return None

    standard_error = sqrt(se_squared)
    test_statistic = effect / standard_error

    # Welch–Satterthwaite degrees of freedom on the per-arm trimmed variance terms.
    degrees_of_freedom = (se_squared**2) / (
        (d_control**2) / (h_control - 1) + (d_treatment**2) / (h_treatment - 1)
    )

    p_value = _bounded_probability(2.0 * (1.0 - t_cdf(abs(test_statistic), degrees_of_freedom)))

    t_critical = t_ppf(1.0 - alpha / 2.0, degrees_of_freedom)
    margin = t_critical * standard_error
    ci_lower = effect - margin
    ci_upper = effect + margin

    # Asymptotic achieved power (descriptive): probability the two-sided test rejects given a
    # non-centrality equal to the observed |t|, approximating the non-central t by a shifted central t
    # — the same shape the other distribution-free analyzers report.
    standardized = abs(test_statistic)
    power_achieved = (1.0 - t_cdf(t_critical - standardized, degrees_of_freedom)) + t_cdf(
        -t_critical - standardized, degrees_of_freedom
    )

    return {
        "trim": trim,
        "control_trimmed_mean": mean_control,
        "treatment_trimmed_mean": mean_treatment,
        "control_effective_n": h_control,
        "treatment_effective_n": h_treatment,
        "observed_diff": effect,
        "p_value": p_value,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": 1.0 - alpha,
        "test_statistic": test_statistic,
        "degrees_of_freedom": degrees_of_freedom,
        "is_significant": p_value < alpha,
        "power_achieved": _bounded_probability(power_achieved),
    }
