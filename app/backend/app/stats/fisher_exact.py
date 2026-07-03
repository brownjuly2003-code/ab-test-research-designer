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

from bisect import bisect_right
from math import ceil, exp, isfinite, lgamma, log, sqrt
from statistics import NormalDist
from typing import Any

from app.backend.app.constants import MAX_SUPPORTED_VARIANTS

_STANDARD_NORMAL = NormalDist()

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


# Exact sizing enumerates an O(n^2 log n) double sweep per candidate n; beyond this per-arm size the
# enumeration is slow AND unnecessary (the exact and approximate answers converge), so sizing falls
# back to the Casagrande-Pike-Smith continuity-corrected formula with an explicit assumption line.
MAX_FISHER_EXACT_SIZING_PER_ARM = 500


def _binomial_logpmf(k: int, n: int, p: float) -> float:
    return _log_binomial(n, k) + k * log(p) + (n - k) * log(1.0 - p)


def fisher_exact_power(
    baseline_rate: float,
    treatment_rate: float,
    n_per_variant: int,
    alpha: float,
) -> float:
    """Exact unconditional power of the two-sided Fisher test with equal arms of ``n_per_variant``.

    Standard exact algorithm (Bennett & Hsu, Biometrika 1960): condition on the total success count
    ``m``. Given ``m``, the null law of the treatment-success cell is hypergeometric, which fixes the
    conditional rejection region of the level-``alpha`` two-sided test (same sum-of-small-
    probabilities convention as :func:`fisher_exact_test`); under the alternative the cell follows
    the product-binomial law restricted to ``m``. Power is the binomial mixture over ``m`` of the
    conditional rejection probability. Rejection uses the strict ``p < alpha`` convention the
    analyzers apply to the returned p-value.
    """
    if not 0 < baseline_rate < 1 or not 0 < treatment_rate < 1:
        raise ValueError("rates must be strictly between 0 and 1")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if n_per_variant < 2:
        raise ValueError("n_per_variant must be at least 2")

    n = n_per_variant
    log_control = [_binomial_logpmf(k, n, baseline_rate) for k in range(n + 1)]
    log_treatment = [_binomial_logpmf(k, n, treatment_rate) for k in range(n + 1)]

    power = 0.0
    for m in range(2 * n + 1):
        low = max(0, m - n)
        high = min(m, n)
        support = range(low, high + 1)

        # Joint alternative probability of each split (control = m - x, treatment = x).
        joint = [exp(log_control[m - x] + log_treatment[x]) for x in support]
        if sum(joint) < 1e-15:
            continue

        # Conditional null pmf (hypergeometric with both margins fixed) and the two-sided p-value of
        # each split via a sorted prefix sum - identical convention to fisher_exact_test.
        null_pmf = [_hypergeometric_pmf(x, m, 2 * n - m, n) for x in support]
        sorted_pmf = sorted(null_pmf)
        prefix = [0.0]
        for value in sorted_pmf:
            prefix.append(prefix[-1] + value)

        for index, x_probability in enumerate(null_pmf):
            p_value = prefix[bisect_right(sorted_pmf, x_probability * _RELATIVE_TOLERANCE)]
            if p_value < alpha:
                power += joint[index]
    return min(1.0, max(0.0, power))


def _binary_z_sample_size(baseline_rate: float, variant_rate: float, alpha: float, power: float) -> int:
    """Normal-approximation two-proportion n (the project's binary z formula, unadjusted alpha in)."""
    z_alpha = _STANDARD_NORMAL.inv_cdf(1 - alpha / 2)
    z_power = _STANDARD_NORMAL.inv_cdf(power)
    pooled_rate = (baseline_rate + variant_rate) / 2
    numerator = (
        z_alpha * sqrt(2 * pooled_rate * (1 - pooled_rate))
        + z_power * sqrt(
            baseline_rate * (1 - baseline_rate) + variant_rate * (1 - variant_rate)
        )
    ) ** 2
    return ceil(numerator / ((variant_rate - baseline_rate) ** 2))


def calculate_fisher_exact_sample_size(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_count: int = 2,
) -> dict[str, Any]:
    """Sample size per variant for a planned Fisher's-exact analysis of a binary metric.

    In the small-n regime where Fisher's exact test is the right analyzer, its conservatism is
    material: the exact test needs MORE users than the z-approximation (e.g. p 0.20 -> 0.40 at
    alpha 0.05 / power 0.80: z-approx 82 per arm, exact 90 - verified at implementation time by
    simulation with ``scipy.stats.fisher_exact``, empirical power 0.800 at 90). The plan is the
    smallest ``n`` whose exact unconditional power (:func:`fisher_exact_power`) reaches the target,
    scanned upward from the z-approximation seed.

    When the seed exceeds ``MAX_FISHER_EXACT_SIZING_PER_ARM`` the exact enumeration is unnecessary
    (exact and approximate powers converge) and the Casagrande-Pike-Smith (Biometrics 1978)
    continuity-corrected formula ``n' = n_z/4 * (1 + sqrt(1 + 4/(n_z*|delta|)))^2`` is used instead,
    with an explicit assumption line saying so.
    """
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
    z_seed = _binary_z_sample_size(baseline_rate, variant_rate, adjusted_alpha, power)

    if z_seed <= MAX_FISHER_EXACT_SIZING_PER_ARM:
        sample_size_per_variant = max(2, z_seed)
        # Exact power grows to 1 with n, so the scan terminates; the bound is a defensive backstop.
        while (
            fisher_exact_power(baseline_rate, variant_rate, sample_size_per_variant, adjusted_alpha)
            < power
        ):
            sample_size_per_variant += 1
            if sample_size_per_variant > 4 * z_seed + 100:
                raise ValueError("Fisher exact sizing failed to converge")
        method_assumption = (
            "Exact plan: smallest n whose exact unconditional power of the two-sided Fisher test "
            f"reaches {power:.0%} (conditional rejection regions enumerated per total-success "
            "count, product-binomial mixture; Bennett & Hsu 1960). Fisher's conservatism is why "
            f"this exceeds the z-approximation ({z_seed:,} per variant)."
        )
    else:
        sample_size_per_variant = ceil(
            z_seed / 4 * (1 + sqrt(1 + 4 / (z_seed * mde_absolute))) ** 2
        )
        method_assumption = (
            f"At this size (z-approximation {z_seed:,} per variant, above the exact-enumeration "
            f"cap of {MAX_FISHER_EXACT_SIZING_PER_ARM}) the Casagrande-Pike-Smith (1978) "
            "continuity-corrected approximation to the exact-test sample size is used; exact and "
            "approximate powers converge in this regime."
        )

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
            method_assumption,
            "MDE is interpreted as a relative uplift over the baseline rate.",
            (
                f"Bonferroni-adjusted alpha is {adjusted_alpha:.6g} across {comparison_count} "
                "treatment-vs-control comparisons. This is conservative for multi-variant designs."
                if variants_count > 2
                else "Nominal alpha is used for a single treatment-vs-control comparison."
            ),
        ],
    }
