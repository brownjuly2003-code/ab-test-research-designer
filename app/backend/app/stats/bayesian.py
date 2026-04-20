import math

from app.backend.app.stats.binary import normal_ppf


def bayesian_sample_size_binary(
    baseline_rate: float,
    desired_precision: float,
    credibility: float = 0.95,
) -> int:
    if not 0 < baseline_rate < 1:
        raise ValueError(f"baseline_rate must be in (0,1), got {baseline_rate}")
    if desired_precision <= 0:
        raise ValueError(f"desired_precision must be > 0, got {desired_precision}")
    if not 0.5 < credibility < 1:
        raise ValueError(f"credibility must be in (0.5,1), got {credibility}")

    z_value = normal_ppf(1 - (1 - credibility) / 2)
    sample_size = 2 * baseline_rate * (1 - baseline_rate) * (z_value / desired_precision) ** 2
    return math.ceil(sample_size)


def bayesian_sample_size_continuous(
    std_dev: float,
    desired_precision: float,
    credibility: float = 0.95,
) -> int:
    if std_dev <= 0:
        raise ValueError(f"std_dev must be > 0, got {std_dev}")
    if desired_precision <= 0:
        raise ValueError(f"desired_precision must be > 0, got {desired_precision}")
    if not 0.5 < credibility < 1:
        raise ValueError(f"credibility must be in (0.5,1), got {credibility}")

    z_value = normal_ppf(1 - (1 - credibility) / 2)
    sample_size = 2 * std_dev**2 * (z_value / desired_precision) ** 2
    return math.ceil(sample_size)


def precision_to_mde_equivalent(
    desired_precision: float,
    baseline_rate: float | None = None,
    std_dev: float | None = None,
    metric_type: str = "binary",
) -> float:
    return desired_precision * 2
