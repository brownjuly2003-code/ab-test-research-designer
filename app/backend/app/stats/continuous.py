from math import ceil
from statistics import NormalDist

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS


def calculate_continuous_sample_size(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_count: int = 2,
) -> dict:
    if baseline_mean <= 0:
        raise ValueError("baseline_mean must be positive for relative MDE calculations")
    if std_dev <= 0:
        raise ValueError("std_dev must be positive for continuous metrics")
    if mde_pct <= 0:
        raise ValueError("mde_pct must be positive")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")

    mde_absolute = baseline_mean * (mde_pct / 100)
    comparison_count = max(1, variants_count - 1)
    adjusted_alpha = alpha / comparison_count
    z_alpha = NormalDist().inv_cdf(1 - adjusted_alpha / 2)
    z_power = NormalDist().inv_cdf(power)

    sample_size_per_variant = ceil(
        2 * (((z_alpha + z_power) * std_dev) / mde_absolute) ** 2
    )

    return {
        "metric_type": "continuous",
        "baseline_value": baseline_mean,
        "std_dev": std_dev,
        "mde_pct": mde_pct,
        "mde_absolute": mde_absolute,
        "alpha": alpha,
        "adjusted_alpha": adjusted_alpha,
        "power": power,
        "sample_size_per_variant": sample_size_per_variant,
        "total_sample_size": sample_size_per_variant * variants_count,
        "assumptions": [
            "Two-sample comparison of means with equal-sized variants.",
            "MDE is interpreted as a relative uplift over the baseline mean.",
            (
                f"Bonferroni-adjusted alpha is {adjusted_alpha:.6g} across {comparison_count} "
                "treatment-vs-control comparisons. This is conservative for multi-variant designs."
                if variants_count > 2
                else "Nominal alpha is used for a single treatment-vs-control comparison."
            ),
        ],
    }
