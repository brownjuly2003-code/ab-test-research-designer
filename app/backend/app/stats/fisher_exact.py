"""
Fisher's exact test — the exact conditional test for a 2x2 table.

The binary path in this package compares two proportions with the normal-approximation z-test
(``stats.binary`` / the ``_analyze_binary`` service branch). That approximation leans on the central
limit theorem and degrades exactly where experiments are smallest and decisions are riskiest: few
users per arm, or a rare event (a handful of conversions). Fisher's exact test instead conditions on
both margins of the 2x2 table and enumerates the hypergeometric distribution of the cell count, so
its p-value is exact for *any* sample size — no large-sample assumption. It is the textbook companion
to the z-test for proportions and the honest choice when ``n`` is small or a cell count is tiny.

Source (verified against the literature at implementation time, not from memory): R. A. Fisher,
*Statistical Methods for Research Workers* (1925) and *The Design of Experiments* (1935, the
"lady tasting tea"); Agresti, *Categorical Data Analysis* (3rd ed., 3.5 — exact inference for 2x2
tables, the two-sided "sum of small probabilities" p-value, and the sample odds ratio). Layout::

                 success   failure   row total
    control         a         b         a + b = r1
    treatment       c         d         c + d = r2
    col total     a + c     b + d         N

With every margin held fixed, the control-success cell ``a`` follows a hypergeometric law,
    P(A = k) = C(c1, k) * C(c2, r1 - k) / C(N, r1),   k in [max(0, r1 - c2), min(r1, c1)],
where ``c1 = a + c`` (total successes), ``c2 = b + d`` (total failures), ``r1 = a + b``. The
**two-sided** p-value is the sum of all table probabilities no larger than the observed one
(``P(A = k) <= P(A = a)`` up to a small relative tolerance) — the convention used by
``scipy.stats.fisher_exact(alternative="two-sided")``. The reported effect size is the sample odds
ratio ``OR = (a*d) / (b*c)`` (``None`` when ``b*c = 0`` — an empty off-diagonal makes it infinite /
undefined; the exact p-value is still defined).

Probabilities are accumulated in log-space via :func:`math.lgamma` so the test stays fast and stable
for any table the caller permits (the service caps the total to keep the support enumeration bounded;
beyond that the normal-approximation z-test is appropriate anyway). The module is stdlib-only and
holds pure functions; assembling the response shape lives in the service layer.
"""

from math import exp, isfinite, lgamma
from typing import Any

# Sum-of-small-probabilities relative tolerance, matching scipy's two-sided convention: a table whose
# probability is within this factor of the observed one is counted as "at least as extreme".
_RELATIVE_TOLERANCE = 1.0 + 1e-7

# Above this combined table total the exact enumeration is pointless (the normal-approximation
# z-test is already accurate) and the support sweep grows large; the service rejects such tables
# with a clear message rather than enumerating silently.
MAX_FISHER_EXACT_TOTAL = 500_000


def _log_binomial(n: int, k: int) -> float:
    """Natural log of the binomial coefficient C(n, k) via log-gamma (0 outside the valid range)."""
    if k < 0 or k > n:
        return float("-inf")
    return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)


def _hypergeometric_pmf(k: int, successes: int, failures: int, draws: int) -> float:
    """P(A = k) for A ~ Hypergeometric, drawing ``draws`` from ``successes + failures`` items.

    ``successes = c1`` (column total of the success column), ``failures = c2``, ``draws = r1`` (the
    control row total). Computed in log-space and exponentiated.
    """
    total = successes + failures
    log_pmf = (
        _log_binomial(successes, k)
        + _log_binomial(failures, draws - k)
        - _log_binomial(total, draws)
    )
    if not isfinite(log_pmf):
        return 0.0
    return exp(log_pmf)


def fisher_exact_test(
    control_conversions: int,
    control_users: int,
    treatment_conversions: int,
    treatment_users: int,
) -> dict[str, Any]:
    """Two-sided Fisher's exact test on a 2x2 conversion table.

    Returns the exact two-sided p-value, the sample odds ratio (``None`` when undefined because an
    off-diagonal cell is zero), the two observed rates, and the absolute / relative risk difference.
    Raises ``ValueError`` only on structurally invalid counts (negative, or conversions exceeding
    users); the schema already enforces these, so this is a defensive backstop. A degenerate table
    where one arm is empty cannot occur (the schema requires at least two users per arm).
    """
    a = control_conversions
    b = control_users - control_conversions
    c = treatment_conversions
    d = treatment_users - treatment_conversions
    if a < 0 or b < 0 or c < 0 or d < 0:
        raise ValueError("conversion counts must be non-negative and not exceed users")

    row1 = a + b  # control users
    successes = a + c  # column total: total conversions
    failures = b + d  # column total: total non-conversions
    total = a + b + c + d

    # Hypergeometric support for the control-success cell, with both margins fixed.
    low = max(0, row1 - failures)
    high = min(row1, successes)

    observed_probability = _hypergeometric_pmf(a, successes, failures, row1)
    threshold = observed_probability * _RELATIVE_TOLERANCE
    p_value = 0.0
    for k in range(low, high + 1):
        probability = _hypergeometric_pmf(k, successes, failures, row1)
        if probability <= threshold:
            p_value += probability
    p_value = min(1.0, max(0.0, p_value))

    control_rate = a / control_users
    treatment_rate = c / treatment_users
    odds_ratio = (a * d) / (b * c) if (b * c) != 0 else None

    return {
        "p_value": p_value,
        "odds_ratio": odds_ratio,
        "control_rate": control_rate,
        "treatment_rate": treatment_rate,
        "risk_difference": treatment_rate - control_rate,
        "relative_risk_difference": (
            (treatment_rate - control_rate) / control_rate if control_rate > 0 else 0.0
        ),
        "table_total": total,
    }
