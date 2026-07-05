"""Freeze P5.3 formulas against scipy BEFORE writing production code (p3.2/p3.3 pattern).

Boschloo's & Barnard's unconditional exact tests (2x2) and the G-test (likelihood-ratio chi-square,
r x c) are alternatives to Fisher's exact test and Pearson's chi-square respectively. This script
holds a *stdlib-only* reference implementation of each and checks it against scipy 1.17.1
(cross-checked locally, never a runtime dependency). The numbers it prints are frozen into the unit
tests; the production modules reproduce this exact algorithm.

Run:  python scratchpad/verify_barnard_boschloo_gtest.py
"""

import math
import time

import numpy as np
from scipy.stats import barnard_exact, boschloo_exact, chi2_contingency, fisher_exact

GRID_POINTS = 64  # uniform interior nuisance grid; + golden-section refine. scipy is stable from n=16.


# --------------------------------------------------------------------------------------------------
# Shared unconditional-exact machinery (mirrors app/stats/unconditional_exact.py)
# --------------------------------------------------------------------------------------------------
def _binomial_row(n: int, p: float) -> list[float]:
    """Binomial(k; n, p) for k = 0..n."""
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
    """sup over pi in (0,1) of the product-binomial mass over an extreme set of (x1, x2) tables."""
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


def _pooled_wald_z(x1: int, n1: int, x2: int, n2: int) -> float:
    p1 = x1 / n1
    p2 = x2 / n2
    p_hat = (x1 + x2) / (n1 + n2)
    if p_hat <= 0.0 or p_hat >= 1.0:
        return 0.0
    se = math.sqrt(p_hat * (1.0 - p_hat) * (1.0 / n1 + 1.0 / n2))
    return (p1 - p2) / se if se > 0.0 else 0.0


def barnard(a: int, n1: int, c: int, n2: int) -> float:
    """Two-sided Barnard unconditional exact test (pooled-Wald ordering, scipy default)."""
    t_obs = abs(_pooled_wald_z(a, n1, c, n2))
    pairs = [
        (x1, x2)
        for x1 in range(n1 + 1)
        for x2 in range(n2 + 1)
        if abs(_pooled_wald_z(x1, n1, x2, n2)) >= t_obs - 1e-12
    ]
    return _sup_product_binomial(pairs, n1, n2)


def _fisher_one_sided_matrices(n1: int, n2: int) -> tuple[list[list[float]], list[list[float]]]:
    """One-sided Fisher exact p (less = P(A<=x1), greater = P(A>=x1)) for every (x1, x2).

    Organized by total-success count m = x1 + x2: given m, x1 is hypergeometric, so a single cumulative
    sweep fills a whole diagonal. O(n1*n2) overall (vs O(n1*n2*support) recomputing per table).
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


def boschloo(a: int, n1: int, c: int, n2: int) -> float:
    """Two-sided Boschloo unconditional exact test = min(1, 2*min(one-sided))."""
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


# --------------------------------------------------------------------------------------------------
# G-test (mirrors app/stats/chi_square_independence.g_test_independence)
# --------------------------------------------------------------------------------------------------
def _regularized_gamma_p(s: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x < s + 1:
        ap = s
        total = 1.0 / s
        delta = total
        for _ in range(300):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-12:
                break
        return total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    tiny = 1e-30
    b = x + 1.0 - s
    cc = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 300):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        cc = b + an / cc
        if abs(cc) < tiny:
            cc = tiny
        d = 1.0 / d
        delta = d * cc
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return 1.0 - math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def g_test(table: list[list[int]]) -> tuple[float, int, float]:
    num_rows = len(table)
    num_cols = len(table[0])
    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[i][j] for i in range(num_rows)) for j in range(num_cols)]
    total = sum(row_totals)
    g = 0.0
    for i in range(num_rows):
        for j in range(num_cols):
            observed = table[i][j]
            if observed == 0:
                continue  # lim x->0 x*ln x = 0
            expected = row_totals[i] * col_totals[j] / total
            g += observed * math.log(observed / expected)
    g *= 2.0
    df = (num_rows - 1) * (num_cols - 1)
    p_value = max(0.0, min(1.0, 1.0 - _regularized_gamma_p(df / 2.0, g / 2.0)))
    return g, df, p_value


# --------------------------------------------------------------------------------------------------
def col(a: int, n1: int, c: int, n2: int) -> list[list[int]]:
    """App (a/n1 control, c/n2 treatment) -> scipy column-sample orientation."""
    return [[a, c], [n1 - a, n2 - c]]


def main() -> None:
    print("=== Boschloo / Barnard vs scipy (two-sided) ===")
    tables = [
        ("beats-Fisher 3/10 vs 8/10", 3, 10, 8, 10),
        ("2/20 vs 9/20", 2, 20, 9, 20),
        ("asymmetric 2/8 vs 11/25", 2, 8, 11, 25),
        ("zero cell 0/10 vs 7/10", 0, 10, 7, 10),
        ("empty margin 0/10 vs 0/10", 0, 10, 0, 10),
        ("all-success control 10/10 vs 4/10", 10, 10, 4, 10),
    ]
    max_bo = max_ba = 0.0
    for name, a, n1, c, n2 in tables:
        t = col(a, n1, c, n2)
        s_bo = float(boschloo_exact(t, alternative="two-sided", n=256).pvalue)
        s_ba = float(barnard_exact(t, alternative="two-sided", n=256).pvalue)
        s_f = float(fisher_exact(t, alternative="two-sided")[1])
        m_bo = boschloo(a, n1, c, n2)
        m_ba = barnard(a, n1, c, n2)
        max_bo = max(max_bo, abs(s_bo - m_bo))
        max_ba = max(max_ba, abs(s_ba - m_ba))
        print(f"  {name}")
        print(f"    boschloo scipy={s_bo:.8f} mine={m_bo:.8f} (fisher={s_f:.8f})")
        print(f"    barnard  scipy={s_ba:.8f} mine={m_ba:.8f}")
    print(f"  MAX ABS DIFF: boschloo={max_bo:.2e} barnard={max_ba:.2e}")
    assert max_bo < 1e-6, max_bo
    assert max_ba < 1e-6, max_ba

    print("\n=== G-test vs scipy (log-likelihood, correction=False) ===")
    g_tables = [
        ("3x3", [[10, 20, 30], [15, 25, 20], [12, 18, 25]]),
        ("2x3", [[30, 10, 15], [20, 25, 18]]),
        ("2x2 zero cell", [[0, 10], [8, 6]]),
    ]
    max_g = 0.0
    for name, obs in g_tables:
        s_g, s_p, s_df, _ = chi2_contingency(np.array(obs), lambda_="log-likelihood", correction=False)
        m_g, m_df, m_p = g_test(obs)
        max_g = max(max_g, abs(float(s_g) - m_g), abs(float(s_p) - m_p))
        print(f"  {name}: scipy G={float(s_g):.8f} p={float(s_p):.8f} df={s_df} | mine G={m_g:.8f} p={m_p:.8f} df={m_df}")
    print(f"  MAX ABS DIFF (G, p): {max_g:.2e}")
    assert max_g < 1e-8, max_g

    print("\n=== worst-case timing at cap (total N = 200, balanced) ===")
    t0 = time.time()
    boschloo(50, 100, 60, 100)
    t_bo = time.time() - t0
    t0 = time.time()
    barnard(50, 100, 60, 100)
    t_ba = time.time() - t0
    print(f"  boschloo={t_bo:.2f}s barnard={t_ba:.2f}s")

    print("\nALL FROZEN ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
