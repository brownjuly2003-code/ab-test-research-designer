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
from typing import Any

from app.backend.app.stats.student_t import t_cdf, t_ppf


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
