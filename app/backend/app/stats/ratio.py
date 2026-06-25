"""
Ratio metrics via the delta method.

A ratio metric ``R = sum(Y) / sum(X)`` is randomized on the *user*, where ``X`` and ``Y`` are
per-user totals of a denominator and a numerator (e.g. click-through rate, where ``X`` = impressions
and ``Y`` = clicks, or revenue-per-session). Because the analysis unit (the denominator events)
differs from the randomization unit (the user), the naive two-sample variance is **wrong**: it
ignores the within-user correlation between numerator and denominator. The delta method linearizes
``R̂ = Ȳ / X̄`` with a first-order Taylor expansion and recovers the correct variance from the
per-user (co)variances.

Source (verified against the literature at implementation time, not from memory): Deng, Knoblich &
Lu, "Applying the Delta Method in Metric Analytics: A Practical Guide with Novel Ideas" (KDD 2018);
Kohavi, Tang & Xu, *Trustworthy Online Controlled Experiments* (ch. on ratio metrics and the delta
method). For per-user pairs ``(X_i, Y_i)`` over ``n`` users with means ``μ_X, μ_Y``, per-user
sample variances ``σ_X², σ_Y²`` and covariance ``σ_XY``,

    R̂ = μ_Y / μ_X
    Var(R̂) = ( σ_Y² − 2·R̂·σ_XY + R̂²·σ_X² ) / ( n · μ_X² )

The ``−2·R̂·σ_XY`` term is exactly the within-user numerator/denominator correlation the naive
estimator drops. For two independent arms the variance of the difference is the sum,

    Δ = R̂_t − R̂_c,   Var(Δ) = Var(R̂_t) + Var(R̂_c),

and ``Δ / sqrt(Var(Δ))`` is a large-sample standard-normal z-statistic — the same normal
approximation the binary/continuous estimators in this package already rely on. This module is
stdlib-only and holds pure functions; assembling the response shape lives in the service layer.
"""

from math import sqrt
from statistics import NormalDist
from typing import Any

_STANDARD_NORMAL = NormalDist()


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def ratio_sufficient_moments(
    n: int,
    sum_x: float,
    sum_x2: float,
    sum_y: float,
    sum_y2: float,
    sum_xy: float,
) -> dict[str, float] | None:
    """Per-user means and *sample* (co)variances from sufficient statistics.

    ``x`` is the ratio denominator, ``y`` the numerator. Returns ``None`` when ``n < 2`` (a sample
    variance is undefined), which the caller treats as insufficient data.
    """
    if n < 2:
        return None
    mean_x = sum_x / n
    mean_y = sum_y / n
    return {
        "n": float(n),
        "mean_x": mean_x,
        "mean_y": mean_y,
        "var_x": (sum_x2 - n * mean_x * mean_x) / (n - 1),
        "var_y": (sum_y2 - n * mean_y * mean_y) / (n - 1),
        "cov_xy": (sum_xy - n * mean_x * mean_y) / (n - 1),
    }


def ratio_estimate(stats: dict[str, Any]) -> dict[str, float] | None:
    """Ratio estimate ``R̂ = μ_Y/μ_X`` and its delta-method variance ``Var(R̂)``.

    ``stats`` carries the per-arm sufficient statistics ``n, sum_x, sum_x2, sum_y, sum_y2, sum_xy``
    (``x`` = denominator, ``y`` = numerator); any extra keys are ignored. Returns ``None`` when the
    estimate is undefined: fewer than 2 users (no sample variance) or a zero denominator mean ``μ_X``
    (the ratio and its linearization blow up).
    """
    moments = ratio_sufficient_moments(
        int(stats["n"]),
        float(stats["sum_x"]),
        float(stats["sum_x2"]),
        float(stats["sum_y"]),
        float(stats["sum_y2"]),
        float(stats["sum_xy"]),
    )
    if moments is None:
        return None
    mean_x = moments["mean_x"]
    if mean_x == 0:
        return None
    n = moments["n"]
    ratio = moments["mean_y"] / mean_x
    # Var(Y − R·X) = σ_Y² − 2R·σ_XY + R²·σ_X² is the variance of a real random variable, hence
    # non-negative in exact arithmetic; clamp tiny negative round-off to 0.
    linearized_variance = (
        moments["var_y"] - 2.0 * ratio * moments["cov_xy"] + ratio * ratio * moments["var_x"]
    )
    variance = max(linearized_variance, 0.0) / (n * mean_x * mean_x)
    return {
        "ratio": ratio,
        "variance": variance,
        "n": n,
        "mean_x": mean_x,
        "mean_y": moments["mean_y"],
    }


def compare_ratios(
    control: dict[str, Any],
    treatment: dict[str, Any],
    alpha: float = 0.05,
) -> dict[str, Any] | None:
    """Two-sample delta-method z-test on the ratio difference ``Δ = R̂_t − R̂_c``.

    ``control`` / ``treatment`` are per-arm sufficient-statistic dicts (see :func:`ratio_estimate`).
    Returns the effect, its confidence interval, z-statistic, p-value, significance verdict and
    achieved power; ``None`` when either arm is degenerate (``n < 2`` or a zero denominator) or the
    pooled variance is zero (no usable signal yet).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    control_estimate = ratio_estimate(control)
    treatment_estimate = ratio_estimate(treatment)
    if control_estimate is None or treatment_estimate is None:
        return None
    variance = control_estimate["variance"] + treatment_estimate["variance"]
    if variance <= 0:
        return None

    control_ratio = control_estimate["ratio"]
    treatment_ratio = treatment_estimate["ratio"]
    effect = treatment_ratio - control_ratio
    standard_error = sqrt(variance)
    test_statistic = effect / standard_error
    p_value = 2.0 * (1.0 - _STANDARD_NORMAL.cdf(abs(test_statistic)))
    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha / 2.0)
    ci_lower = effect - z_critical * standard_error
    ci_upper = effect + z_critical * standard_error
    relative_effect = (effect / control_ratio * 100.0) if control_ratio != 0 else 0.0
    # Achieved power of the two-sided z-test at the observed effect (same form as the binary /
    # continuous estimators): P(reject | observed |z|) = Φ(|z|−z_crit) + Φ(−z_crit−|z|).
    power_achieved = _STANDARD_NORMAL.cdf(abs(test_statistic) - z_critical) + _STANDARD_NORMAL.cdf(
        -z_critical - abs(test_statistic)
    )
    return {
        "control_ratio": control_ratio,
        "treatment_ratio": treatment_ratio,
        "effect": effect,
        "variance": variance,
        "standard_error": standard_error,
        "test_statistic": test_statistic,
        "p_value": _bounded_probability(p_value),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": 1.0 - alpha,
        "relative_effect": relative_effect,
        "is_significant": p_value < alpha,
        "power_achieved": _bounded_probability(power_achieved),
    }
