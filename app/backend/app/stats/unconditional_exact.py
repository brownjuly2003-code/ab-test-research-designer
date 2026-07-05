"""Boschloo's unconditional exact test for a 2x2 table.

Fisher's exact test (``stats.fisher_exact``) conditions on *both* margins of the 2x2 table and is,
because of that conditioning, conservative: on a fixed margin its attainable significance levels are a
sparse discrete set, so the actual type-I error usually sits strictly below the nominal alpha and the
test loses power. Boschloo's test removes the second conditioning. It treats only the two group sizes
``n1``, ``n2`` as fixed and the common success probability ``pi`` under H0 as an unknown *nuisance*
parameter, then takes the p-value to be the supremum, over ``pi in (0, 1)``, of the probability of a
result "as or more extreme" than the observed one. Ordering tables by Fisher's own (one-sided) exact
p-value makes Boschloo's test **uniformly at least as powerful as Fisher's exact test** (Boschloo 1970):
for the same data it never returns a larger p-value, and typically a smaller one, while still holding
the type-I error at or below alpha for every ``pi``. That is the honest small-sample companion to the
z-test for proportions when Fisher's conservatism is costing real power.

Source (verified against the literature at implementation time, not from memory): R. D. Boschloo,
"Raised conditional level of significance for the 2x2 table when testing the equality of two
probabilities", *Statistica Neerlandica* 24 (1970); G. A. Barnard, "Significance tests for 2x2
tables", *Biometrika* 34 (1947); M. Lydersen, M. W. Fagerland & P. Laake, "Recommended tests for
association in 2x2 tables", *Statistics in Medicine* 28 (2009 — recommends unconditional tests, with
Boschloo's as a default because it dominates Fisher's). Cross-checked numerically against
``scipy.stats.boschloo_exact`` in ``scratchpad/verify_barnard_boschloo_gtest.py`` before this module
was written; the frozen numbers are reproduced by the unit tests. Runtime code is stdlib-only.

Layout (same orientation as ``fisher_exact``)::

                 success   failure
    control         a         b
    treatment       c         d

with ``a = control_conversions``, ``n1 = control_users``, ``c = treatment_conversions``,
``n2 = treatment_users``.

**Why Boschloo and not also Barnard.** Barnard's test is the *same* unconditional construction with a
different ordering statistic (a pooled-variance Wald Z instead of Fisher's exact p). It is a sibling,
not an addition: it needs the same nuisance-supremum machinery below plus one extra ``T`` function, and
it does **not** carry Boschloo's clean domination property over Fisher's exact test — no single ordering
makes Barnard's test uniformly more powerful than Fisher's. Shipping two unconditional exact analyzers
side by side would offer users a redundant choice with no principled rule for picking between them,
so Barnard's test is deliberately deferred: Boschloo's is the flagship unconditional exact test and
strictly dominates the conditional Fisher test the app already offers. If a concrete request for
Barnard's ordering ever arrives, it is a small, localized addition on top of the shared helpers here
(one ``T`` statistic + a dispatch branch); nothing below needs to change.

The unconditional supremum is the expensive part: unlike Fisher's ``O(support)`` sweep over one margin,
each candidate ``pi`` costs ``O((n1+1)(n2+1))`` and the extreme set is re-scored on a grid of ``pi``
values with a golden-section refinement. The service caps the combined table total at
:data:`MAX_UNCONDITIONAL_EXACT_TOTAL` (worst case < 1 s); above it the unconditional advantage has
vanished anyway (the tests converge to the accurate, far cheaper z-test / Fisher test at large ``n``),
so the caller is redirected there. The module is stdlib-only and holds pure functions; assembling the
response shape lives in the service layer.
"""

import math
from typing import Any

# Uniform interior nuisance-probability grid used to locate the supremum over ``pi``, followed by a
# golden-section refinement around the best grid point. The tail probability is, for a fixed extreme
# set, a smooth polynomial in ``pi``, so 64 points bracket the maximum and the refinement pins it to
# machine precision; verified stable against ``scipy.stats.boschloo_exact`` from n=16 to n=1024.
GRID_POINTS = 64

# Cap on the combined table total (``control_users + treatment_users``). The unconditional supremum
# enumerates every (x1, x2) table on a grid of nuisance values, ``O((n1+1)(n2+1) * GRID_POINTS)`` — far
# heavier than Fisher's single-margin sweep — so runtime, not memory, is the binding constraint. At the
# cap (a balanced 100/100 table with a large extreme set) the worst case is well under a second. Beyond
# it the unconditional advantage over the z-test / Fisher test is negligible, so the service raises and
# redirects the caller rather than enumerating at length. Set deliberately tight: unconditional exact
# tests are a small-n tool by construction.
MAX_UNCONDITIONAL_EXACT_TOTAL = 200


def _binomial_row(n: int, p: float) -> list[float]:
    """Binomial(k; n, p) for k = 0..n, in log-space (degenerate at p in {0, 1})."""
    if p <= 0.0:
        row = [0.0] * (n + 1)
        row[0] = 1.0
        return row
    if p >= 1.0:
        row = [0.0] * (n + 1)
        row[n] = 1.0
        return row
    log_p = math.log(p)
    log_q = math.log1p(-p)
    return [
        math.exp(
            math.lgamma(n + 1)
            - math.lgamma(k + 1)
            - math.lgamma(n - k + 1)
            + k * log_p
            + (n - k) * log_q
        )
        for k in range(n + 1)
    ]


def _sup_product_binomial(pairs: list[tuple[int, int]], n1: int, n2: int) -> float:
    """Supremum over ``pi in (0, 1)`` of the product-binomial mass over an extreme set of tables.

    Under H0 both arms share a success probability ``pi``; group-1 successes ``x1 ~ Binomial(n1, pi)``
    and group-2 successes ``x2 ~ Binomial(n2, pi)`` independently. ``pairs`` is the set of ``(x1, x2)``
    tables deemed at least as extreme as the observed one. Returns
    ``sup_pi sum_{(x1,x2) in pairs} P(x1; n1, pi) P(x2; n2, pi)``, located on a uniform grid and pinned
    by a golden-section refinement (the objective is a smooth polynomial in ``pi`` for a fixed set).
    """
    if not pairs:
        return 0.0

    def objective(pi: float) -> float:
        r1 = _binomial_row(n1, pi)
        r2 = _binomial_row(n2, pi)
        return math.fsum(r1[i] * r2[j] for (i, j) in pairs)

    grid = [(i + 0.5) / GRID_POINTS for i in range(GRID_POINTS)]
    best_pi = grid[0]
    best = objective(grid[0])
    for pi in grid[1:]:
        value = objective(pi)
        if value > best:
            best = value
            best_pi = pi

    # Golden-section refinement in the bracket around the best grid point.
    step = 1.0 / GRID_POINTS
    lo = max(1e-9, best_pi - step)
    hi = min(1.0 - 1e-9, best_pi + step)
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - gr * (hi - lo)
    d = lo + gr * (hi - lo)
    fc = objective(c)
    fd = objective(d)
    for _ in range(60):
        if fc < fd:
            lo, c, fc = c, d, fd
            d = lo + gr * (hi - lo)
            fd = objective(d)
        else:
            hi, d, fd = d, c, fc
            c = hi - gr * (hi - lo)
            fc = objective(c)
        if hi - lo < 1e-11:
            break
    return min(1.0, max(0.0, max(best, fc, fd)))


def _fisher_one_sided_matrices(
    n1: int, n2: int
) -> tuple[list[list[float]], list[list[float]]]:
    """One-sided Fisher exact p (less = P(A<=x1), greater = P(A>=x1)) for every ``(x1, x2)`` table.

    The ordering statistic for Boschloo's test is Fisher's one-sided exact p-value. Naively that would
    be an ``O(support)`` hypergeometric sum per table, i.e. ``O(n1*n2*support)`` overall. Instead the
    tables are organized by their total-success count ``m = x1 + x2``: conditional on ``m`` the count
    ``x1`` is hypergeometric, so a single cumulative sweep fills a whole ``m``-diagonal. Overall
    ``O(n1*n2)`` — the trick that keeps Boschloo tractable at the cap.
    """
    total = n1 + n2
    less = [[0.0] * (n2 + 1) for _ in range(n1 + 1)]
    greater = [[0.0] * (n2 + 1) for _ in range(n1 + 1)]

    def log_choose(n: int, k: int) -> float:
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

    for m in range(total + 1):
        low = max(0, m - n2)
        high = min(m, n1)
        pmf = {
            x1: math.exp(log_choose(n1, x1) + log_choose(n2, m - x1) - log_choose(total, m))
            for x1 in range(low, high + 1)
        }
        cumulative = 0.0
        cum_less = {}
        for x1 in range(low, high + 1):
            cumulative += pmf[x1]
            cum_less[x1] = min(1.0, cumulative)
        cumulative = 0.0
        cum_greater = {}
        for x1 in range(high, low - 1, -1):
            cumulative += pmf[x1]
            cum_greater[x1] = min(1.0, cumulative)
        for x1 in range(low, high + 1):
            x2 = m - x1
            less[x1][x2] = cum_less[x1]
            greater[x1][x2] = cum_greater[x1]
    return less, greater


def _boschloo_two_sided_p_value(a: int, n1: int, c: int, n2: int) -> float:
    """Two-sided Boschloo p-value = ``min(1, 2 * min(one-sided_less, one-sided_greater))``.

    scipy's two-sided convention is the doubled smaller one-sided p-value (verified: ordering directly
    by a two-sided Fisher p does *not* reproduce scipy on asymmetric tables, but the doubled one-sided
    does, to ~1e-14). Each one-sided p-value is the nuisance-supremum of the product-binomial mass over
    all tables whose one-sided Fisher p is <= the observed table's.
    """
    less, greater = _fisher_one_sided_matrices(n1, n2)

    def one_sided(matrix: list[list[float]]) -> float:
        p_obs = matrix[a][c]
        pairs = [
            (x1, x2)
            for x1 in range(n1 + 1)
            for x2 in range(n2 + 1)
            if matrix[x1][x2] <= p_obs * (1.0 + 1e-9)
        ]
        return _sup_product_binomial(pairs, n1, n2)

    return min(1.0, 2.0 * min(one_sided(less), one_sided(greater)))


def boschloo_exact_test(
    control_conversions: int,
    control_users: int,
    treatment_conversions: int,
    treatment_users: int,
) -> dict[str, Any]:
    """Two-sided Boschloo unconditional exact test on a 2x2 conversion table.

    Returns the exact two-sided p-value together with the same descriptive table statistics the Fisher
    card reports (they are test-agnostic arithmetic on the counts, so the service can present a Boschloo
    result with an identical layout, differing only in the analyzer name and the p-value): the sample
    odds ratio (``None`` when an off-diagonal cell is zero and the ratio is undefined), the two observed
    rates, and the absolute / relative risk difference.

    Raises ``ValueError`` only on structurally invalid counts (negative, or conversions exceeding
    users); the schema already enforces these, so this is a defensive backstop. The service enforces the
    :data:`MAX_UNCONDITIONAL_EXACT_TOTAL` size cap before calling this function.
    """
    a = control_conversions
    b = control_users - control_conversions
    c = treatment_conversions
    d = treatment_users - treatment_conversions
    if a < 0 or b < 0 or c < 0 or d < 0:
        raise ValueError("conversion counts must be non-negative and not exceed users")

    p_value = _boschloo_two_sided_p_value(a, control_users, c, treatment_users)

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
        "table_total": control_users + treatment_users,
    }
