from math import ceil, sqrt
from statistics import NormalDist

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS


def calculate_binary_sample_size(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_count: int = 2,
) -> dict:
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
                "Bonferroni-adjusted alpha is applied across treatment-vs-control comparisons. "
                "This is conservative for multi-variant designs."
                if variants_count > 2
                else "Nominal alpha is used for a single treatment-vs-control comparison."
            ),
        ],
    }
