"""Pearson's chi-square test of independence for an r×c contingency table.

This is the omnibus categorical test: given counts of a categorical outcome (the columns) across two
or more groups (the rows), it asks whether the outcome distribution depends on the group — i.e.
whether the row and column classifications are associated. Unlike the two-proportion / Fisher tests
(which compare a single binary outcome across two arms) this handles an arbitrary r×c table: three
plan tiers chosen across four variants, a five-point satisfaction rating across two arms, and so on.

The statistic is the uncorrected Pearson chi-square ``Σ (O − E)² / E`` with expected counts
``E_ij = rowtotal_i · coltotal_j / N`` under the independence null, on ``(r − 1)(c − 1)`` degrees of
freedom. The p-value is the upper tail of the chi-square distribution, computed with the same
regularized-gamma routine the SRM check uses (``stats.srm.chi_square_cdf``), so no new special
function is introduced. No continuity correction is applied: Yates' correction is a 2×2-only device,
and for the 2×2 case this project already offers Fisher's exact test (preferred for small samples).
Surfacing the uncorrected statistic keeps the r×c result consistent with the textbook definition and
with ``scipy.stats.chi2_contingency(correction=False)``.

Effect size is Cramér's V = ``sqrt(chi² / (N · min(r−1, c−1)))`` ∈ [0, 1], the standard
association-strength measure for contingency tables (0 = independent, 1 = perfect association).

The test is asymptotic: the chi-square reference distribution is an approximation that needs
adequately large expected counts. Cochran's rule of thumb (expected counts ≥ 5) is surfaced as a
warning via the minimum expected count, so the caller can fall back to an exact test on a sparse
table rather than trusting an unreliable p-value.

Sources (checked against the literature at implementation time, not from memory): Pearson (1900);
Agresti, *Categorical Data Analysis* (2013, §3 — the chi-square test of independence and its
expected-count conditions); Cramér, *Mathematical Methods of Statistics* (1946 — V); Cochran (1954 —
the minimum-expected-count guidance). Stdlib-only, pure function; the response shape is assembled in
the service layer.
"""

import math
from typing import Any

from app.backend.app.stats.srm import chi_square_cdf

# Cap on total observations. The statistic is O(r·c) and the table dimensions are bounded by the
# request schema, so this only guards against absurd magnitudes, mirroring the Fisher / Poisson caps.
MAX_CONTINGENCY_TOTAL = 5_000_000

# Cochran's rule of thumb: the chi-square approximation grows unreliable once an expected cell count
# falls below this threshold.
MIN_RELIABLE_EXPECTED_COUNT = 5.0


def _validate_contingency_table(
    table: list[list[int]], alpha: float
) -> tuple[int, int, list[int], list[int], int]:
    """Shared validation + margin totals for the contingency-table tests (Pearson chi-square, G-test).

    Both tests take the same r×c integer count table and are undefined on the same degenerate inputs,
    so the guards live here once. Returns ``(num_rows, num_cols, row_totals, col_totals, total)``.
    Raises ``ValueError`` for a degenerate table — fewer than two rows or columns, a non-rectangular
    shape, negative counts, a zero grand total, a total above the cap, or a wholly empty row/column
    (which makes the test of independence undefined). These map to HTTP 400 at the service layer.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    num_rows = len(table)
    if num_rows < 2:
        raise ValueError("contingency table needs at least two rows")
    num_cols = len(table[0])
    if num_cols < 2:
        raise ValueError("contingency table needs at least two columns")
    if any(len(row) != num_cols for row in table):
        raise ValueError("contingency table must be rectangular")
    if any(count < 0 for row in table for count in row):
        raise ValueError("contingency table counts must be non-negative")

    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[i][j] for i in range(num_rows)) for j in range(num_cols)]
    total = sum(row_totals)

    if total == 0:
        raise ValueError("contingency table total must be greater than zero")
    if total > MAX_CONTINGENCY_TOTAL:
        raise ValueError(f"contingency table total exceeds the {MAX_CONTINGENCY_TOTAL} cap")
    if any(rt == 0 for rt in row_totals) or any(ct == 0 for ct in col_totals):
        # A wholly empty row or column means a category never occurs; its expected counts are zero
        # and the test of independence is undefined. The caller should drop the empty category.
        raise ValueError("every row and column total must be greater than zero")

    return num_rows, num_cols, row_totals, col_totals, total


def chi_square_independence_test(table: list[list[int]], alpha: float = 0.05) -> dict[str, Any]:
    """Chi-square test of independence on an r×c contingency table.

    ``table`` is a list of rows, each a list of non-negative integer cell counts; rows are the groups
    (e.g. experiment arms), columns the categorical outcome levels. Returns the chi-square statistic,
    degrees of freedom ``(r − 1)(c − 1)``, the upper-tail p-value, Cramér's V effect size, the total
    N, the table shape, the minimum expected cell count with a Cochran low-expected-count warning, and
    the significance verdict at ``alpha``.

    Raises ``ValueError`` for a degenerate table — see :func:`_validate_contingency_table`.
    """
    num_rows, num_cols, row_totals, col_totals, total = _validate_contingency_table(table, alpha)

    chi_square = 0.0
    min_expected = math.inf
    for i in range(num_rows):
        for j in range(num_cols):
            expected = row_totals[i] * col_totals[j] / total
            min_expected = min(min_expected, expected)
            # expected > 0 is guaranteed here: both marginal totals are > 0 (checked above).
            diff = table[i][j] - expected
            chi_square += diff * diff / expected

    degrees_of_freedom = (num_rows - 1) * (num_cols - 1)
    p_value = max(0.0, min(1.0, 1.0 - chi_square_cdf(chi_square, degrees_of_freedom)))

    # Cramér's V (association strength in [0, 1]). min_dim >= 1 since both dimensions are >= 2, and
    # chi_square <= total * min_dim mathematically, so V is bounded by 1.
    min_dim = min(num_rows - 1, num_cols - 1)
    cramers_v = math.sqrt(chi_square / (total * min_dim))

    return {
        "chi_square": chi_square,
        "degrees_of_freedom": degrees_of_freedom,
        "p_value": p_value,
        "cramers_v": cramers_v,
        "n_total": total,
        "num_rows": num_rows,
        "num_cols": num_cols,
        "min_expected_count": min_expected,
        "low_expected_warning": min_expected < MIN_RELIABLE_EXPECTED_COUNT,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }


def g_test_independence(table: list[list[int]], alpha: float = 0.05) -> dict[str, Any]:
    """G-test (likelihood-ratio chi-square) of independence on an r×c contingency table.

    The G-test is the likelihood-ratio counterpart of Pearson's chi-square: instead of the Pearson
    discrepancy ``Σ (O − E)² / E`` it uses ``G = 2·Σ O·ln(O/E)``, with the same independence-null
    expected counts ``E_ij = rowtotal_i · coltotal_j / N`` and the same ``(r − 1)(c − 1)`` degrees of
    freedom referred to the chi-square distribution. Both are members of the power-divergence family
    (Cressie–Read); they are asymptotically equivalent and usually numerically close, but the G-test is
    additive (log-likelihoods decompose cleanly for nested/partitioned tables) and is often preferred in
    that setting. This returns the *same dict shape* as :func:`chi_square_independence_test` with the
    ``chi_square`` key carrying ``G`` (both statistics reference the χ² distribution), so the service
    can present either test through one response, disambiguated by the caller's ``test_type``.

    A cell with ``O = 0`` contributes 0 to the sum (``lim_{x→0} x·ln x = 0``), so an empty *cell* is
    fine; only an empty row/column total is degenerate — the same guards as Pearson, via
    :func:`_validate_contingency_table`. Cramér's V is computed from ``G`` (≈ the Pearson V). Reference:
    ``scipy.stats.chi2_contingency(lambda_="log-likelihood", correction=False)``; Sokal & Rohlf,
    *Biometry* (1981, the G-test); Cressie & Read, *JRSS-B* 46 (1984, the power-divergence family).
    Cross-checked against scipy in ``scratchpad/verify_barnard_boschloo_gtest.py``; stdlib-only.
    """
    num_rows, num_cols, row_totals, col_totals, total = _validate_contingency_table(table, alpha)

    g_statistic = 0.0
    min_expected = math.inf
    for i in range(num_rows):
        for j in range(num_cols):
            expected = row_totals[i] * col_totals[j] / total
            min_expected = min(min_expected, expected)
            observed = table[i][j]
            if observed == 0:
                continue  # lim_{x->0} x*ln(x) = 0, so an empty cell contributes nothing to G
            # expected > 0 is guaranteed here: both marginal totals are > 0 (checked above).
            g_statistic += observed * math.log(observed / expected)
    g_statistic *= 2.0

    degrees_of_freedom = (num_rows - 1) * (num_cols - 1)
    p_value = max(0.0, min(1.0, 1.0 - chi_square_cdf(g_statistic, degrees_of_freedom)))

    # Cramér's V from G (both are power-divergence statistics bounded by total * min_dim).
    min_dim = min(num_rows - 1, num_cols - 1)
    cramers_v = math.sqrt(max(g_statistic, 0.0) / (total * min_dim))

    return {
        "chi_square": g_statistic,
        "degrees_of_freedom": degrees_of_freedom,
        "p_value": p_value,
        "cramers_v": cramers_v,
        "n_total": total,
        "num_rows": num_rows,
        "num_cols": num_cols,
        "min_expected_count": min_expected,
        "low_expected_warning": min_expected < MIN_RELIABLE_EXPECTED_COUNT,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }
