"""Precision-based sample sizing for the Bayesian planning mode.

These size an experiment so the posterior credible interval reaches a target half-width
(``desired_precision``). With the flat/weakly-informative priors this tool assumes, the posterior
is well approximated by a normal centred on the observed effect, so the required N coincides with
the frequentist normal-approximation precision formula ``N = 2 * var * (z / precision)**2`` — the
prior does not enter beyond that approximation. They are *not* a full Bayesian design over an
informative prior; the "Bayesian" label denotes the planning mode (size-to-precision rather than
size-to-power), not prior-dependent math.
"""

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
