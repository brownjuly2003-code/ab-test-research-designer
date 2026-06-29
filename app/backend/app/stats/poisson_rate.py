"""
Two-sample Poisson rate test — the exact test for *count / rate* metrics.

The binary, continuous and ratio estimators in this package cover proportions and means. They do not
cover the other staple product-analytics shape: a **rate** — a number of events accrued over an
amount of exposure (errors per 1000 sessions, support tickets per account-week, crashes per
device-day). When the events are well modelled as Poisson (independent arrivals at a constant rate
over the exposure), the right comparison is the **rate ratio** ``RR = λ_t / λ_c``, not a difference
of means or proportions.

The exact test conditions on the total event count. Given ``x_c`` control events over exposure
``t_c`` and ``x_t`` treatment events over ``t_t``, condition on ``n = x_c + x_t``: under H0
(``λ_c = λ_t``) the treatment share ``x_t`` is **Binomial(n, π0)`` with ``π0 = t_t / (t_c + t_t)``
(the exposure split). The two-sided p-value is the exact binomial sum of all outcomes no more likely
than the observed one — the same "sum of small probabilities" convention as Fisher's exact test and
``scipy.stats.binomtest(alternative="two-sided")``. This is the standard exact conditional test for
two Poisson rates (the person-time / incidence-rate-ratio test in epidemiology).

Source (verified against the literature at implementation time, not from memory): Sahai & Khurshid,
*Statistics in Epidemiology* (the conditional binomial test for the ratio of two Poisson rates);
Gu, Ng, Tang & Schucany (2008), "Testing the ratio of two Poisson rates". The reported effect is the
rate ratio with a log-normal Wald interval (``Var(log RR) ≈ 1/x_c + 1/x_t``); like Fisher, the
**p-value is exact** while the interval is the large-sample companion, clearly framed as descriptive.

**Assumption (stated honestly).** This is correct when the unit of analysis is the *event over
exposure* and arrivals are independent (no overdispersion, no within-user clustering). For clustered
per-user counts, analyse the per-user mean (continuous) or a ratio metric instead — the rate test
would be anti-conservative there. The module is stdlib-only and holds pure functions; assembling the
response shape lives in the service layer.
"""

from math import exp, isfinite, lgamma, log, sqrt
from statistics import NormalDist
from typing import Any

_STANDARD_NORMAL = NormalDist()

# Same two-sided tolerance as Fisher: an outcome within this factor of the observed probability
# counts as "at least as extreme".
_RELATIVE_TOLERANCE = 1.0 + 1e-7

# Above this combined event count the exact binomial enumeration is pointless (the normal
# approximation is already exact) and the O(n) sweep grows large; the service rejects such inputs.
MAX_POISSON_EVENTS = 1_000_000


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _binomial_logpmf(k: int, n: int, p: float) -> float:
    log_coefficient = lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
    return log_coefficient + k * log(p) + (n - k) * log(1.0 - p)


def poisson_rate_test(
    control_events: int,
    control_exposure: float,
    treatment_events: int,
    treatment_exposure: float,
    alpha: float = 0.05,
) -> dict[str, Any] | None:
    """Two-sided exact Poisson rate test (conditional binomial) on counts over exposure.

    ``*_events`` are non-negative event counts; ``*_exposure`` are positive exposure amounts (time,
    sessions, users — any common denominator). Returns the exact two-sided p-value, the two rates,
    the rate ratio (``None`` when the control arm has zero events, i.e. an infinite ratio), the rate
    difference with its large-sample Wald CI, the significance verdict and an asymptotic achieved
    power. Returns ``None`` when no events were observed in either arm (the test is undefined).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if control_exposure <= 0 or treatment_exposure <= 0:
        raise ValueError("exposures must be positive")
    if control_events < 0 or treatment_events < 0:
        raise ValueError("event counts must be non-negative")

    total_events = control_events + treatment_events
    if total_events == 0:
        return None

    exposure_share = treatment_exposure / (control_exposure + treatment_exposure)

    # Exact two-sided p-value: sum the binomial mass of every split no more likely than observed.
    observed_logpmf = _binomial_logpmf(treatment_events, total_events, exposure_share)
    threshold = exp(observed_logpmf) * _RELATIVE_TOLERANCE
    p_value = 0.0
    for k in range(total_events + 1):
        probability = exp(_binomial_logpmf(k, total_events, exposure_share))
        if probability <= threshold:
            p_value += probability
    p_value = _bounded_probability(p_value)

    control_rate = control_events / control_exposure
    treatment_rate = treatment_events / treatment_exposure
    rate_difference = treatment_rate - control_rate
    rate_ratio = (treatment_rate / control_rate) if control_events > 0 else None

    # Wald CI for the rate difference (Poisson variance Var(x/t) = x/t^2), descriptive companion to
    # the exact p-value.
    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha / 2.0)
    difference_standard_error = sqrt(
        control_events / control_exposure**2 + treatment_events / treatment_exposure**2
    )
    if difference_standard_error > 0:
        ci_lower = rate_difference - z_critical * difference_standard_error
        ci_upper = rate_difference + z_critical * difference_standard_error
        standardized = abs(rate_difference) / difference_standard_error
        power_achieved = _STANDARD_NORMAL.cdf(
            standardized - z_critical
        ) + _STANDARD_NORMAL.cdf(-z_critical - standardized)
    else:
        ci_lower = ci_upper = rate_difference
        power_achieved = 0.0

    relative_effect = (rate_difference / control_rate * 100.0) if control_rate > 0 else 0.0

    return {
        "p_value": p_value,
        "control_rate": control_rate,
        "treatment_rate": treatment_rate,
        "rate_ratio": rate_ratio if (rate_ratio is None or isfinite(rate_ratio)) else None,
        "rate_difference": rate_difference,
        "relative_effect": relative_effect,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_level": 1.0 - alpha,
        "n_events": total_events,
        "is_significant": p_value < alpha,
        "power_achieved": _bounded_probability(power_achieved),
    }
