"""
Always-valid inference via a mixture Sequential Probability Ratio Test (mSPRT).

Unlike the fixed-horizon and group-sequential (O'Brien-Fleming) machinery in this package, the
quantities here stay valid under *continuous monitoring*: an analyst may inspect the experiment at
any moment, any number of times, and stop whenever they like, and the type-I error is still bounded
by ``alpha``. This is the property practitioners want from a live dashboard, where looks are not
pre-planned.

Method (Robbins 1970; Johari, Pekelis & Walsh, "Always Valid Inference: Continuous Monitoring of
A/B Tests", arXiv:1512.04922 / Operations Research 2022). For a normal mixing distribution
``H = N(0, tau^2)`` over the unknown effect, the mixture likelihood ratio against the null
``theta = 0`` has the closed form

    Lambda_n = sqrt( V / (V + tau^2) ) * exp( tau^2 * theta_hat^2 / (2 * V * (V + tau^2)) )

where ``theta_hat`` is the observed effect (e.g. difference in means/rates) and ``V = Var(theta_hat)``
is the variance of that estimate. Two consequences:

* **Always-valid p-value** ``p = min(1, 1 / Lambda_n)``. Under the null ``Lambda_n`` is a
  non-negative martingale with ``E[Lambda_n] = 1``, so by Ville's inequality
  ``P(exists n : p_n <= alpha) <= alpha`` — i.e. the running minimum p-value controls type-I error
  uniformly over time, not just at a single fixed sample size.
* **(1 - alpha) confidence sequence** ``theta_hat +/- r`` with

    r = sqrt( (2 * V * (V + tau^2) / tau^2) * ( ln(1 / alpha) + 0.5 * ln((V + tau^2) / V) ) )

  The interval covers the true effect with probability at least ``1 - alpha`` *simultaneously at
  all sample sizes*. By construction it excludes 0 exactly when the always-valid p-value drops
  below ``alpha`` (the test and the confidence sequence are dual).

The mixing variance ``tau^2`` is a tuning parameter. Validity of the type-I bound holds for *any*
fixed ``tau^2 > 0``; ``tau^2`` only trades power across effect sizes. Following Johari et al. it is
best set near the squared scale of the effect the experiment was powered to detect, so the mixture
concentrates mass on plausible alternatives (see :func:`default_mixture_variance`).

Caveats (honest, mirroring the rest of this stdlib-only stats layer):
* This is the normal-approximation form. ``theta_hat`` and ``V`` are treated as if normal, which is
  the standard large-sample regime for A/B metrics (the same approximation the binary/continuous
  estimators here already use). For tiny per-arm counts the asymptotics are weaker.
* ``V`` is a plug-in estimate (it depends on the data). The martingale argument is exact for known
  ``V``; with a plug-in variance the guarantee is asymptotic, which is the accepted industry
  practice for mSPRT on two-sample A/B data. The ``test_always_valid`` suite verifies the resulting
  anytime type-I control empirically by Monte-Carlo.
"""

from math import exp, log, sqrt
from typing import Any


def _validate(effect: float, variance: float, mixture_variance: float) -> None:
    if variance <= 0:
        raise ValueError("variance (Var of the effect estimate) must be positive")
    if mixture_variance <= 0:
        raise ValueError("mixture_variance (tau^2) must be positive")
    # effect is unconstrained (any real difference, including exactly 0).
    _ = effect


def msprt_log_likelihood_ratio(
    effect: float,
    variance: float,
    mixture_variance: float,
) -> float:
    """Natural log of the mixture likelihood ratio ``ln(Lambda_n)`` against the null effect 0.

    Computed in log space for numerical stability. ``effect`` is ``theta_hat``, ``variance`` is
    ``V = Var(theta_hat)``, ``mixture_variance`` is ``tau^2``.
    """
    _validate(effect, variance, mixture_variance)
    v_plus_tau = variance + mixture_variance
    # ln(Lambda) = 0.5*ln(V/(V+tau^2)) + tau^2*effect^2 / (2*V*(V+tau^2))
    return -0.5 * log(v_plus_tau / variance) + (
        mixture_variance * effect**2 / (2.0 * variance * v_plus_tau)
    )


def always_valid_p_value(
    effect: float,
    variance: float,
    mixture_variance: float,
) -> float:
    """Anytime-valid p-value ``min(1, 1 / Lambda_n)``.

    Stays valid under continuous monitoring: rejecting the first time this drops below ``alpha``
    controls type-I error at ``alpha`` regardless of how many times the experiment was inspected.
    A zero observed effect yields ``Lambda_n < 1`` and therefore a p-value of exactly 1.
    """
    log_lr = msprt_log_likelihood_ratio(effect, variance, mixture_variance)
    if log_lr <= 0.0:
        # Lambda_n <= 1  ->  1/Lambda_n >= 1  ->  clamped to 1.
        return 1.0
    return min(1.0, exp(-log_lr))


def confidence_sequence(
    effect: float,
    variance: float,
    mixture_variance: float,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """``(lower, upper)`` of the (1 - ``alpha``) anytime-valid confidence sequence around ``effect``.

    The sequence excludes 0 exactly when :func:`always_valid_p_value` is below ``alpha``.
    """
    _validate(effect, variance, mixture_variance)
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    v_plus_tau = variance + mixture_variance
    radius = sqrt(
        (2.0 * variance * v_plus_tau / mixture_variance)
        * (log(1.0 / alpha) + 0.5 * log(v_plus_tau / variance))
    )
    return effect - radius, effect + radius


def evaluate_always_valid(
    effect: float,
    variance: float,
    mixture_variance: float,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Bundle the always-valid p-value, confidence sequence and significance verdict.

    ``is_significant`` is ``True`` when the always-valid p-value is below ``alpha`` (equivalently,
    when the confidence sequence excludes 0).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    p_value = always_valid_p_value(effect, variance, mixture_variance)
    lower, upper = confidence_sequence(effect, variance, mixture_variance, alpha)
    return {
        "always_valid_p_value": p_value,
        "confidence_level": 1.0 - alpha,
        "ci_sequence_lower": lower,
        "ci_sequence_upper": upper,
        "is_significant": p_value < alpha,
        "mixture_variance": mixture_variance,
    }


def default_mixture_variance(expected_effect: float) -> float:
    """``tau^2`` from the effect the experiment was powered to detect.

    Per Johari, Pekelis & Walsh, setting ``tau`` near the target effect concentrates the mixture
    mass on plausible alternatives and maximizes power there. Validity of the type-I bound holds for
    any ``tau^2 > 0``, so this choice is about power, not correctness.
    """
    if expected_effect <= 0:
        raise ValueError("expected_effect must be positive to derive a mixture variance")
    return float(expected_effect**2)
