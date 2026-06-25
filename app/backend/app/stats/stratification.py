"""
Post-stratification variance reduction.

Post-stratification adjusts a treatment-effect estimate by splitting the sample into strata of a
categorical attribute known at assignment time (platform, country, new-vs-returning, …), estimating
the effect *within* each stratum, and recombining the per-stratum effects weighted by stratum size.
When the stratifying variable explains variation in the outcome, the between-strata variation is
removed from the estimator's error and the effect estimate gets more precise — the same goal as
CUPED, but using a concurrent categorical attribute rather than a pre-period covariate.

Source (verified against the literature at implementation time, not from memory): Miratrix, Sekhon &
Yu, "Adjusting treatment effect estimates by post-stratification in randomized experiments" (JRSS-B,
2013); Kohavi, Tang & Xu, *Trustworthy Online Controlled Experiments* (stratified sampling /
post-stratification). The principle (per the Miratrix et al. abstract): divide the sample into
strata, compute the difference-in-means per stratum, and average the per-stratum estimands weighted
by stratum size. For a control/treatment pair over strata ``s`` with per-stratum effect ``Δ_s`` and
per-stratum effect variance ``Var(Δ_s)``:

    w_s = N_s / N            (N_s = stratum size across both arms, N = total)
    Δ   = Σ_s w_s · Δ_s
    Var(Δ) = Σ_s w_s² · Var(Δ_s)

This is the **conditional** variance (conditioning on the observed stratum sizes) — the standard,
closed-form post-stratification estimator, not the finite-sample Neyman form. ``Δ / sqrt(Var(Δ))`` is
a large-sample standard-normal z-statistic, the same normal approximation the binary / continuous /
ratio estimators in this package already use. Each ``Var(Δ_s)`` is the unpooled sum of the two arms'
estimate variances (rate variance ``p(1−p)/n`` for binary; ``s²/n`` for continuous), matching the
variance behind the displayed frequentist intervals. Post-stratification can *increase* variance when
strata are many and poorly chosen (Miratrix et al.), so the reported reduction is shown honestly and
may be negative. This module is stdlib-only and holds pure functions; assembling the sufficient
statistics and the response shape lives in the service layer.
"""

from math import isfinite, sqrt
from statistics import NormalDist
from typing import Any

_STANDARD_NORMAL = NormalDist()


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def binary_point_variance(conversions: int, n: int) -> tuple[float, float] | None:
    """Conversion rate ``p`` and the variance of that rate estimate ``p(1−p)/n``.

    Returns ``None`` when ``n < 1`` (no rate). A zero-variance arm (``p`` is 0 or 1) is allowed; it
    contributes 0 to the stratum effect variance, just like the unpooled binary comparison.
    """
    if n < 1:
        return None
    rate = conversions / n
    return rate, rate * (1.0 - rate) / n


def continuous_point_variance(
    value_sum: float, value_sq_sum: float, n: int
) -> tuple[float, float] | None:
    """Per-user mean and the variance of that mean estimate ``s²/n`` (``s²`` = sample variance).

    Returns ``None`` when ``n < 2`` (a sample variance is undefined). Round-off below zero in the
    sample variance is clamped to 0.
    """
    if n < 2:
        return None
    mean = value_sum / n
    sample_variance = (value_sq_sum - n * mean * mean) / (n - 1)
    if sample_variance < 0.0:
        sample_variance = 0.0
    return mean, sample_variance / n


def stratum_difference(
    control: tuple[float, float], treatment: tuple[float, float]
) -> dict[str, float]:
    """Per-stratum effect ``Δ_s = point_t − point_c`` and its unpooled variance ``var_c + var_t``.

    Each operand is a ``(point_estimate, variance_of_estimate)`` pair from
    :func:`binary_point_variance` or :func:`continuous_point_variance`.
    """
    control_point, control_variance = control
    treatment_point, treatment_variance = treatment
    return {
        "delta": treatment_point - control_point,
        "variance": control_variance + treatment_variance,
    }


def combine_strata(strata: list[dict[str, Any]], alpha: float = 0.05) -> dict[str, Any] | None:
    """Size-weighted combine of per-stratum effects into one post-stratified estimate + z-test.

    ``strata`` is a list of ``{"n": int, "delta": float, "variance": float}`` — each stratum's size
    (across both arms), per-stratum effect and per-stratum effect variance. Strata with ``n <= 0`` or
    a non-finite delta/variance are dropped. Returns the post-stratified effect, its confidence
    interval, z-statistic, p-value, significance verdict and achieved power; ``None`` when no stratum
    survives or the total weight is zero or the combined variance is not positive (no usable signal).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    usable = [
        stratum
        for stratum in strata
        if int(stratum["n"]) > 0
        and isfinite(float(stratum["delta"]))
        and isfinite(float(stratum["variance"]))
        and float(stratum["variance"]) >= 0.0
    ]
    total = sum(int(stratum["n"]) for stratum in usable)
    if not usable or total <= 0:
        return None

    effect = 0.0
    variance = 0.0
    for stratum in usable:
        weight = int(stratum["n"]) / total
        effect += weight * float(stratum["delta"])
        variance += weight * weight * float(stratum["variance"])
    if variance <= 0:
        return None

    standard_error = sqrt(variance)
    test_statistic = effect / standard_error
    p_value = 2.0 * (1.0 - _STANDARD_NORMAL.cdf(abs(test_statistic)))
    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha / 2.0)
    # Achieved power of the two-sided z-test at the observed effect (same form as the binary /
    # continuous / ratio estimators): P(reject | observed |z|) = Φ(|z|−z_crit) + Φ(−z_crit−|z|).
    power_achieved = _STANDARD_NORMAL.cdf(abs(test_statistic) - z_critical) + _STANDARD_NORMAL.cdf(
        -z_critical - abs(test_statistic)
    )
    return {
        "effect": effect,
        "variance": variance,
        "standard_error": standard_error,
        "test_statistic": test_statistic,
        "p_value": _bounded_probability(p_value),
        "ci_lower": effect - z_critical * standard_error,
        "ci_upper": effect + z_critical * standard_error,
        "ci_level": 1.0 - alpha,
        "is_significant": p_value < alpha,
        "power_achieved": _bounded_probability(power_achieved),
        "num_strata": len(usable),
        "total_users": total,
    }


def variance_reduction_pct(pooled_variance: float, stratified_variance: float) -> float | None:
    """Percent variance reduction of the post-stratified estimate vs the naive pooled estimate.

    ``(1 − stratified/pooled) · 100``. Returns ``None`` when the pooled variance is not positive
    (nothing to compare against). May be **negative** when stratification hurts (few, poorly chosen
    strata) — reported honestly rather than clamped, per Miratrix et al.
    """
    if pooled_variance <= 0 or not isfinite(pooled_variance) or not isfinite(stratified_variance):
        return None
    return (1.0 - stratified_variance / pooled_variance) * 100.0
