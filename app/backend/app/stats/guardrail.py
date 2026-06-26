"""Guardrail metrics — directed regression (breach) detection.

A *guardrail* metric is one the experiment must **not** harm: latency, crash/error rate,
unsubscribe rate, revenue-per-user, … A treatment can win on the primary metric and still be a
no-ship if it significantly degrades a guardrail. Unlike the two-sided primary test (which asks
"did anything change?"), a guardrail asks a one-sided, *directed* question: "did the treatment move
this metric in the harmful direction by more than we are willing to tolerate?"

Each guardrail carries a harm direction — ``increase_is_bad`` (latency, errors) or
``decrease_is_bad`` (revenue, retention) — and an optional **non-inferiority margin** M ≥ 0, the
largest degradation considered practically acceptable (M = 0 means *any* significant degradation is
a breach). Writing the signed degradation in the harmful direction as

    harm = +Δ   (increase_is_bad)        harm = −Δ   (decrease_is_bad)

with Δ = treatment − control and Var(Δ) the same unpooled (binary ``p(1−p)/n``) / Welch
(continuous ``s²/n``) variance behind the displayed confidence interval, the breach test is a
one-sided z-test of

    H₀: harm ≤ M   (no intolerable harm)     vs     H₁: harm > M   (guardrail breached)

    z = (harm − M) / sqrt(Var(Δ)),     p = 1 − Φ(z)   (one-sided)

A breach is declared when the one-sided (1−α) **lower** confidence bound on the harm clears the
margin, ``harm − z_{1−α}·SE > M``, which is exactly ``z > z_{1−α}`` ⇔ ``p < α`` — the same internal
duality the ratio / post-stratification estimators in this package use, so the bound and the p-value
never disagree. Between "ok" and "breached" sits "warning": the point estimate degrades past the
margin (``harm > M``) but not significantly, so the operator is alerted without a hard veto.

Source (verified against the literature at implementation time, not from memory): Kohavi, Tang & Xu,
*Trustworthy Online Controlled Experiments* (2020), ch. on guardrail / organizational metrics and on
practical vs statistical significance; the non-inferiority margin and one-sided framing follow the
standard non-inferiority test (ICH E10; Wellek, *Testing Statistical Hypotheses of Equivalence and
Noninferiority*, 2010). No new test statistic enters the package — the harm and its variance are the
same difference-in-means the binary / continuous live comparisons already compute; this module only
adds the directed, margined one-sided decision. It is stdlib-only and holds pure functions;
assembling the per-arm sufficient statistics and the response shape lives in the service layer.
"""

from math import sqrt
from statistics import NormalDist
from typing import Any

_STANDARD_NORMAL = NormalDist()

# Harm-direction codes shared with the schema layer.
INCREASE_IS_BAD = "increase_is_bad"
DECREASE_IS_BAD = "decrease_is_bad"
_DIRECTIONS = (INCREASE_IS_BAD, DECREASE_IS_BAD)

# Breach-status codes, ordered from safe to harmful so a metric can report its worst comparison.
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_BREACHED = "breached"
_STATUS_SEVERITY = {STATUS_OK: 0, STATUS_WARNING: 1, STATUS_BREACHED: 2}


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def harm_in_direction(effect: float, direction: str) -> float:
    """Signed degradation in the harmful direction: ``+effect`` when an increase is bad, ``−effect``
    when a decrease is bad. Positive harm means the treatment moved the metric the wrong way."""
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction must be one of {_DIRECTIONS}")
    return effect if direction == INCREASE_IS_BAD else -effect


def worst_status(statuses: list[str]) -> str:
    """The most severe breach status in ``statuses`` (``breached`` > ``warning`` > ``ok``); ``ok``
    for an empty list. Lets a guardrail metric summarize several treatment comparisons."""
    worst = STATUS_OK
    for status in statuses:
        if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY[worst]:
            worst = status
    return worst


def evaluate_guardrail(
    effect: float,
    variance: float,
    *,
    direction: str,
    margin: float = 0.0,
    alpha: float = 0.05,
) -> dict[str, Any] | None:
    """One-sided directed breach test for a guardrail metric.

    ``effect`` is Δ = treatment − control in the metric's natural units; ``variance`` is Var(Δ), the
    same unpooled / Welch variance behind the displayed confidence interval. ``direction`` is the
    harm direction (:data:`INCREASE_IS_BAD` / :data:`DECREASE_IS_BAD`) and ``margin`` ≥ 0 the largest
    degradation tolerated before a breach (0 ⇒ any significant degradation breaches). Returns the
    harm, its standard error, the one-sided (1−α) lower confidence bound on the harm, the z-statistic,
    the one-sided p-value, the breach flag and a ``status`` of ``ok`` / ``warning`` / ``breached``;
    ``None`` when the variance is non-positive (no usable signal yet).
    """
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction must be one of {_DIRECTIONS}")
    if margin < 0:
        raise ValueError("margin must be non-negative")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if variance <= 0:
        return None

    harm = harm_in_direction(effect, direction)
    standard_error = sqrt(variance)
    test_statistic = (harm - margin) / standard_error
    # One-sided p-value for H1: harm > margin. A negative z (the treatment improves the metric, or
    # the harm sits below the margin) yields p -> 1, never a false breach.
    p_value = _bounded_probability(1.0 - _STANDARD_NORMAL.cdf(test_statistic))
    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha)
    harm_lower_bound = harm - z_critical * standard_error
    # Duality: lower bound clears the margin  <=>  z > z_crit  <=>  p < alpha.
    is_breached = harm_lower_bound > margin
    if is_breached:
        status = STATUS_BREACHED
    elif harm > margin:
        status = STATUS_WARNING
    else:
        status = STATUS_OK
    return {
        "harm": harm,
        "standard_error": standard_error,
        "harm_lower_bound": harm_lower_bound,
        "margin": margin,
        "test_statistic": test_statistic,
        "p_value": p_value,
        "alpha": alpha,
        "is_breached": is_breached,
        "status": status,
    }
