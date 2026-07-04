from math import ceil, sqrt
from statistics import NormalDist
from typing import Any

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS


def normal_ppf(probability: float) -> float:
    return NormalDist().inv_cdf(probability)


def standard_normal_cdf(value: float) -> float:
    return NormalDist().cdf(value)


def wilson_score_interval(successes: int, n: int, alpha: float) -> tuple[float, float]:
    """Wilson (1927) score interval for a single binomial proportion.

    Unlike the Wald interval ``p̂ ± z·√(p̂(1−p̂)/n)``, the score interval inverts the score test, so it
    is bounded inside ``[0, 1]``, never degenerates to a point at ``p̂ ∈ {0, 1}``, and holds its nominal
    coverage far better at small ``n`` or extreme rates — exactly the regime where the Wald interval
    collapses. Source (verified numerically against ``statsmodels.stats.proportion.proportion_confint(
    method="wilson")`` at implementation time, not from memory): E. B. Wilson, *JASA* 22 (1927), 209–212;
    Agresti & Coull, *The American Statistician* 52 (1998).

    Returns ``(lower, upper)`` on the proportion scale. The endpoints are analytically within ``[0, 1]``
    (at ``successes = 0`` the lower endpoint is exactly 0; at ``successes = n`` the upper is exactly 1).
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    z = NormalDist().inv_cdf(1 - alpha / 2)
    p = successes / n
    z_sq_over_n = z * z / n
    denominator = 1 + z_sq_over_n
    center = (p + z_sq_over_n / 2) / denominator
    half_width = (z / denominator) * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return center - half_width, center + half_width


def newcombe_difference_interval(
    successes1: int,
    n1: int,
    successes2: int,
    n2: int,
    alpha: float,
) -> tuple[float, float]:
    """Newcombe (1998) "Method 10" hybrid-score interval for the difference ``p1 − p2``.

    A MOVER (method of variance estimates recovery) combination of the two single-proportion Wilson
    intervals ``(l_i, u_i)``::

        lower = (p̂1 − p̂2) − √((p̂1 − l1)² + (u2 − p̂2)²)
        upper = (p̂1 − p̂2) + √((u1 − p̂1)² + (p̂2 − l2)²)

    It inherits Wilson's small-sample coverage and boundary behaviour, so it replaces the Wald
    difference interval that mis-covers when a cell count is tiny or a rate is near 0 / 1. Source
    (verified numerically against ``statsmodels.stats.proportion.confint_proportions_2indep(
    method="newcomb", compare="diff")`` to 1e-9 at implementation time, not from memory): R. G.
    Newcombe, *Statistics in Medicine* 17 (1998), 873–890, method 10; the worked example 56/70 vs
    48/80 reproduces his published 95 % interval (0.0524, 0.3339). The construction is antisymmetric:
    swapping the two groups negates and reverses the interval.
    """
    p1 = successes1 / n1
    p2 = successes2 / n2
    lower1, upper1 = wilson_score_interval(successes1, n1, alpha)
    lower2, upper2 = wilson_score_interval(successes2, n2, alpha)
    difference = p1 - p2
    lower = difference - sqrt((p1 - lower1) ** 2 + (upper2 - p2) ** 2)
    upper = difference + sqrt((upper1 - p1) ** 2 + (p2 - lower2) ** 2)
    return lower, upper


def calculate_detectable_mde_binary(
    n: int,
    baseline_rate: float,
    alpha: float,
    power: float,
) -> float:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be between 0 and 1 for binary metrics")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")

    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    low = 0.0
    high = 1 - baseline_rate - 1e-9

    for _ in range(80):
        delta = (low + high) / 2
        variant_rate = baseline_rate + delta
        pooled_rate = (baseline_rate + variant_rate) / 2
        required_n = (
            z_alpha * sqrt(2 * pooled_rate * (1 - pooled_rate))
            + z_power * sqrt(
                baseline_rate * (1 - baseline_rate) + variant_rate * (1 - variant_rate)
            )
        ) ** 2 / (delta**2)

        if required_n <= n:
            high = delta
        else:
            low = delta

    return high


def calculate_binary_sample_size(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_count: int = 2,
) -> dict[str, Any]:
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be between 0 and 1 for binary metrics")
    if mde_pct <= 0:
        raise ValueError("mde_pct must be positive")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")

    mde_absolute = baseline_rate * (mde_pct / 100)
    variant_rate = baseline_rate + mde_absolute
    if variant_rate >= 1:
        raise ValueError("baseline_rate and mde_pct imply an invalid variant rate")

    comparison_count = max(1, variants_count - 1)
    adjusted_alpha = alpha / comparison_count
    z_alpha = NormalDist().inv_cdf(1 - adjusted_alpha / 2)
    z_power = NormalDist().inv_cdf(power)
    pooled_rate = (baseline_rate + variant_rate) / 2

    numerator = (
        z_alpha * sqrt(2 * pooled_rate * (1 - pooled_rate))
        + z_power * sqrt(
            baseline_rate * (1 - baseline_rate) + variant_rate * (1 - variant_rate)
        )
    ) ** 2
    sample_size_per_variant = ceil(numerator / (mde_absolute**2))

    return {
        "metric_type": "binary",
        "baseline_value": baseline_rate,
        "mde_pct": mde_pct,
        "mde_absolute": mde_absolute,
        "alpha": alpha,
        "adjusted_alpha": adjusted_alpha,
        "power": power,
        "sample_size_per_variant": sample_size_per_variant,
        "total_sample_size": sample_size_per_variant * variants_count,
        "assumptions": [
            "Two-sided fixed-horizon test with equal variance approximation.",
            "MDE is interpreted as a relative uplift over the baseline rate.",
            (
                f"Bonferroni-adjusted alpha is {adjusted_alpha:.6g} across {comparison_count} "
                "treatment-vs-control comparisons. This is conservative for multi-variant designs."
                if variants_count > 2
                else "Nominal alpha is used for a single treatment-vs-control comparison."
            ),
        ],
    }
