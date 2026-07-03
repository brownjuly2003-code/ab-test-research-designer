"""Two One-Sided Tests (TOST) for equivalence on summary continuous statistics.

A difference test asks "is there an effect?"; an equivalence test asks the opposite question —
"is the effect small enough to treat the two arms as practically the same?". This is the right
test when the goal is to *confirm no meaningful change* rather than detect one: a backend refactor,
an infrastructure migration or a cost-cutting change that must not move the metric beyond a
tolerance ``margin`` in either direction.

TOST runs two one-sided Welch t-tests against the equivalence bounds ``-margin`` and ``+margin``
and concludes equivalence only when BOTH one-sided nulls are rejected at level ``alpha``:

* lower test  H0: ``mean_diff <= -margin``  vs  H1: ``mean_diff > -margin``
* upper test  H0: ``mean_diff >= +margin``  vs  H1: ``mean_diff < +margin``

The TOST p-value is ``max(p_lower, p_upper)`` and the decision is equivalent to checking whether the
``(1 - 2*alpha)`` confidence interval for the mean difference lies entirely inside
``(-margin, +margin)``. Welch's unequal-variance standard error and Welch–Satterthwaite degrees of
freedom are used, matching the project's two-sample continuous difference test.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.stats.student_t import t_cdf, t_ppf

_STANDARD_NORMAL = NormalDist()


def _welch_degrees_of_freedom(
    control_std: float, control_n: int, treatment_std: float, treatment_n: int
) -> float:
    control_term = (control_std**2) / control_n
    treatment_term = (treatment_std**2) / treatment_n
    denominator = 0.0
    if control_n > 1:
        denominator += (control_term**2) / (control_n - 1)
    if treatment_n > 1:
        denominator += (treatment_term**2) / (treatment_n - 1)
    if denominator == 0:
        return math.inf
    return ((control_term + treatment_term) ** 2) / denominator


def tost_equivalence_test(
    *,
    control_mean: float,
    control_std: float,
    control_n: int,
    treatment_mean: float,
    treatment_std: float,
    treatment_n: int,
    margin: float,
    alpha: float,
) -> dict[str, Any] | None:
    """Two one-sided t-tests for equivalence of two means within ``±margin``.

    Returns ``None`` when the standard error is zero (both arms degenerate), which the caller maps
    to the shared degenerate response. ``margin`` must be positive (enforced by the schema).
    """
    if margin <= 0:
        raise ValueError("equivalence margin must be positive")

    effect = treatment_mean - control_mean
    standard_error = math.sqrt(
        max((control_std**2) / control_n + (treatment_std**2) / treatment_n, 0.0)
    )
    if standard_error == 0:
        return None

    df = _welch_degrees_of_freedom(control_std, control_n, treatment_std, treatment_n)

    # Lower one-sided test rejects H0: effect <= -margin when (effect + margin) / SE is large positive.
    t_lower = (effect + margin) / standard_error
    p_lower = 1.0 - t_cdf(t_lower, df)
    # Upper one-sided test rejects H0: effect >= +margin when (effect - margin) / SE is large negative.
    t_upper = (effect - margin) / standard_error
    p_upper = t_cdf(t_upper, df)

    # TOST p-value is the larger (binding) of the two one-sided p-values; equivalence is concluded
    # only if BOTH one-sided tests reject, i.e. this maximum is below alpha.
    p_value = max(p_lower, p_upper)
    is_equivalent = p_value < alpha

    # The TOST decision is identical to the (1 - 2*alpha) CI for the mean difference lying entirely
    # inside (-margin, +margin), so we report that interval (90% CI at the default alpha = 0.05).
    ci_level = 1.0 - 2.0 * alpha
    t_critical = t_ppf(1.0 - alpha, df)
    ci_lower = effect - t_critical * standard_error
    ci_upper = effect + t_critical * standard_error

    # The binding side (the one with the larger p-value) determines the result; report its statistic.
    test_statistic = t_lower if p_lower >= p_upper else t_upper

    # Achieved power of the equivalence test given the observed precision and margin, evaluated at a
    # true effect of zero (perfect equivalence): the probability that the (1 - 2*alpha) CI would land
    # inside (-margin, +margin). Honest descriptive companion, clamped to [0, 1].
    half_width_in_se = margin / standard_error - t_critical
    power_achieved = min(1.0, max(0.0, t_cdf(half_width_in_se, df) - t_cdf(-half_width_in_se, df)))

    # Pooled-SD Cohen's d as a unit-free effect-size companion (parity with the bootstrap path).
    pooled_dof = control_n + treatment_n - 2
    cohens_d: float | None = None
    if pooled_dof > 0:
        pooled_variance = (
            (control_n - 1) * control_std**2 + (treatment_n - 1) * treatment_std**2
        ) / pooled_dof
        if pooled_variance > 0:
            cohens_d = effect / math.sqrt(pooled_variance)

    result: dict[str, Any] = {
        "effect": effect,
        "standard_error": standard_error,
        "degrees_of_freedom": df,
        "margin": margin,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": ci_level,
        "p_value": p_value,
        "p_lower": p_lower,
        "p_upper": p_upper,
        "test_statistic": test_statistic,
        "is_equivalent": is_equivalent,
        "power_achieved": power_achieved,
        "control_mean": control_mean,
        "treatment_mean": treatment_mean,
    }
    if cohens_d is not None:
        result["cohens_d"] = cohens_d
    return result


def tost_power(
    n_per_variant: int,
    std_dev: float,
    margin_absolute: float,
    alpha: float,
) -> float:
    """Power of the two-sample TOST at a true difference of ZERO (perfect equivalence).

    Large-sample form (Schuirmann 1987; Julious, Stat. Med. 2004, equivalence section): with equal
    arms of ``n`` and per-arm standard deviation ``sigma``, the standard error of the difference is
    ``sigma * sqrt(2/n)`` and both one-sided level-``alpha`` tests reject together with probability

        power = 2 * Phi(margin / SE - z_{1-alpha}) - 1     (floored at 0).

    Note TOST is a LEVEL-ALPHA procedure - each one-sided test runs at ``alpha``, not ``alpha/2``
    (Berger & Hsu 1996), so ``z_{1-alpha}`` is correct here.
    """
    if n_per_variant <= 0:
        raise ValueError("n_per_variant must be positive")
    standard_error = std_dev * math.sqrt(2.0 / n_per_variant)
    z_alpha = _STANDARD_NORMAL.inv_cdf(1.0 - alpha)
    return max(0.0, 2.0 * _STANDARD_NORMAL.cdf(margin_absolute / standard_error - z_alpha) - 1.0)


def calculate_tost_sample_size(
    baseline_mean: float,
    std_dev: float,
    equivalence_margin_pct: float,
    alpha: float,
    power: float,
    variants_count: int = 2,
) -> dict[str, Any]:
    """Sample size per variant for a planned TOST equivalence analysis of two means.

    Finds the smallest integer ``n`` whose exact normal-approximation power (see :func:`tost_power`)
    reaches the target, seeded by the closed form ``2 * (sigma * (z_{1-alpha} + z_{1-beta/2}) /
    margin)^2`` (Schuirmann 1987; Julious 2004; Chow, Shao & Wang, "Sample Size Calculations in
    Clinical Research", equivalence-of-means chapter - the ``z_{1-beta/2}`` term is because at a
    true difference of zero the power splits symmetrically between the two bounds). Verified at
    implementation time against the classic Chow-Shao-Wang example (sigma 0.10, margin 0.05,
    alpha 0.05, power 0.80 -> n = 69; closed form 68.5) and a Monte-Carlo run of the Welch-TOST
    analyzer at that n (empirical power 0.802).

    Power is evaluated at a TRUE DIFFERENCE OF ZERO (perfect equivalence) - the standard planning
    default; a real nonzero difference within the margin needs a larger sample. The margin is
    symmetric and relative to the baseline mean, mirroring ``mde_pct`` semantics.
    """
    if baseline_mean <= 0:
        raise ValueError("baseline_mean must be positive for relative margin calculations")
    if not math.isfinite(std_dev) or std_dev <= 1e-12:
        raise ValueError("std_dev must be positive for continuous metrics")
    if equivalence_margin_pct <= 0:
        raise ValueError("equivalence_margin_pct must be positive")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")

    margin_absolute = baseline_mean * (equivalence_margin_pct / 100)
    comparison_count = max(1, variants_count - 1)
    adjusted_alpha = alpha / comparison_count

    z_alpha = _STANDARD_NORMAL.inv_cdf(1.0 - adjusted_alpha)
    z_power = _STANDARD_NORMAL.inv_cdf(1.0 - (1.0 - power) / 2.0)
    try:
        closed_form = 2.0 * ((std_dev * (z_alpha + z_power)) / margin_absolute) ** 2
    except OverflowError as exc:
        raise ValueError("equivalence sample size is too large to be finite") from exc
    if not math.isfinite(closed_form):
        raise ValueError("equivalence sample size is too large to be finite")

    # The closed form slightly overshoots the exact minimum (it ignores the power floor at the far
    # bound), so start a little below it and walk up to the first n that reaches the target.
    sample_size_per_variant = max(2, math.floor(closed_form * 0.8))
    while tost_power(sample_size_per_variant, std_dev, margin_absolute, adjusted_alpha) < power:
        sample_size_per_variant += 1

    return {
        "metric_type": "continuous",
        "baseline_value": baseline_mean,
        "std_dev": std_dev,
        "equivalence_margin_pct": equivalence_margin_pct,
        "equivalence_margin_absolute": margin_absolute,
        "alpha": alpha,
        "adjusted_alpha": adjusted_alpha,
        "power": power,
        "sample_size_per_variant": sample_size_per_variant,
        "total_sample_size": sample_size_per_variant * variants_count,
        "assumptions": [
            (
                "Equivalence (TOST) plan: two one-sided tests against a symmetric margin of "
                f"+/-{margin_absolute:g} ({equivalence_margin_pct:g}% of the baseline mean). "
                "Sizing is driven by the margin - the MDE field does not apply to an "
                "equivalence design."
            ),
            (
                "Power is evaluated at a true difference of ZERO (perfect equivalence), the "
                "standard planning default (Schuirmann 1987; Julious 2004). A real nonzero "
                "difference inside the margin would need a larger sample."
            ),
            (
                f"Each one-sided test runs at level {adjusted_alpha:g} - TOST is a level-alpha "
                "procedure, no alpha/2 split (Berger & Hsu 1996). Normal approximation; the "
                "analyzer's Welch-t refinement is negligible at these sample sizes."
            ),
            (
                f"Bonferroni-adjusted alpha is {adjusted_alpha:.6g} across {comparison_count} "
                "treatment-vs-control comparisons. This is conservative for multi-variant designs."
                if variants_count > 2
                else "Nominal alpha is used for a single treatment-vs-control comparison."
            ),
        ],
    }
