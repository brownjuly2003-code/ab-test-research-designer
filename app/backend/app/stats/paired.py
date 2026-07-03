"""Paired (within-subject) two-sample tests — the pre/post-on-the-same-unit family.

Where the binary / continuous / Mann–Whitney estimators compare **two independent arms**, these
three compare **two measurements of the same unit** (before/after, control/treatment on the same
user), so they work on the per-pair difference ``d_i = treatment_i − control_i`` and are far more
powerful when the pairing removes between-unit variance. All three consume one shared input — two
equal-length arrays paired by index — hence a single "paired samples" form feeds the family:

* **Paired t-test** — the one-sample t-test on the differences. Parametric; assumes the differences
  are roughly normal. Statistic ``t = mean(d) / (sd(d)/√n)`` on ``n − 1`` degrees of freedom, the
  two-sided p-value from the Student-t CDF, a t-interval on the mean difference, and Cohen's ``d_z =
  mean(d)/sd(d)`` as the standardized effect size.

* **Wilcoxon signed-rank test** — the distribution-free counterpart. Zero differences are dropped
  (Wilcoxon's original convention), the remaining ``|d|`` are ranked with **midranks on ties**, and
  the signed-rank sums ``W+`` / ``W−`` are formed. The two-sided p-value uses the large-sample normal
  approximation **with a continuity correction and the tie correction to the variance**, matching
  ``scipy.stats.wilcoxon(mode="approx", correction=True, zero_method="wilcox")``. Location is the
  Hodges–Lehmann pseudomedian — the median of the Walsh averages ``(d_i + d_j)/2`` for ``i ≤ j`` —
  with its distribution-free confidence interval (the same normal-approximation rank offset the
  two-sample Hodges–Lehmann interval uses). Effect size is the rank-biserial correlation
  ``r = (W+ − W−) / (W+ + W−) ∈ [−1, 1]``.

* **McNemar's test** — the paired **binary** test (values are 0/1). Only the discordant pairs carry
  information: ``b`` = #(control 0 → treatment 1), ``c`` = #(control 1 → treatment 0). For a small
  number of discordant pairs (``< MCNEMAR_EXACT_MAX_DISCORDANT``) the exact two-sided binomial test
  against ``p = ½`` is used; otherwise the Edwards continuity-corrected chi-square
  ``(|b − c| − 1)² / (b + c)`` on 1 degree of freedom. This matches
  ``statsmodels.stats.contingency_tables.mcnemar(exact=…, correction=True)``. The reported effect is
  the marginal proportion difference ``(b − c) / n_pairs`` and the effect size the discordance odds
  ratio ``b / c`` (undefined, reported as ``None``, when ``c = 0``). With no discordant pairs the
  test is uninformative (``p = 1``).

Sources (checked against the literature at implementation time, not from memory): Student (1908) and
Fisher for the paired t; Wilcoxon, "Individual Comparisons by Ranking Methods" (Biometrics, 1945),
Hollander, Wolfe & Chicken, *Nonparametric Statistical Methods* (3rd ed., ch. 3 — the signed-rank
test, its tie/zero handling and the Hodges–Lehmann one-sample estimate with its distribution-free
interval); McNemar, "Note on the sampling error of the difference between correlated proportions or
percentages" (Psychometrika, 1947), Edwards (1948) for the continuity correction. Stdlib-only, pure
functions; the response shapes are assembled in the service layer.
"""

import math
from statistics import NormalDist, median
from typing import Any

from app.backend.app.stats.srm import chi_square_cdf
from app.backend.app.stats.student_t import t_cdf, t_ppf

_STANDARD_NORMAL = NormalDist()

# McNemar switches from the exact two-sided binomial test to the continuity-corrected chi-square
# approximation once the number of discordant pairs reaches this bound. Below it the exact test is
# cheap and avoids the approximation's inaccuracy on few discordant pairs; at or above it the
# chi-square is accurate, matching statsmodels' default `exact` cutoff choice for this project.
MCNEMAR_EXACT_MAX_DISCORDANT = 25


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _paired_differences(control: list[float], treatment: list[float]) -> list[float]:
    """Per-pair differences ``treatment_i − control_i`` (arrays are equal length by construction)."""
    return [t - c for c, t in zip(control, treatment, strict=True)]


def paired_t_test(
    control: list[float], treatment: list[float], alpha: float = 0.05
) -> dict[str, Any] | None:
    """Paired t-test — the one-sample t-test on the per-pair differences.

    ``control`` / ``treatment`` are equal-length paired observations. Returns the mean difference,
    the t statistic, degrees of freedom ``n − 1``, the two-sided p-value, the ``(1 − alpha)``
    confidence interval on the mean difference, Cohen's ``d_z`` effect size, the per-arm means and
    the significance verdict. Returns ``None`` when the test is undefined: fewer than two pairs, or a
    zero difference standard deviation (every pair moved by the same amount — a degenerate,
    infinite-t case the caller surfaces rather than the analyzer inventing a p-value).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if any(not math.isfinite(value) for value in control) or any(
        not math.isfinite(value) for value in treatment
    ):
        raise ValueError("paired values must be finite")

    n_pairs = len(control)
    if n_pairs < 2:
        return None

    differences = _paired_differences(control, treatment)
    mean_difference = sum(differences) / n_pairs
    variance = sum((value - mean_difference) ** 2 for value in differences) / (n_pairs - 1)
    std_difference = math.sqrt(variance)
    if std_difference == 0:
        # Every pair moved by an identical amount: se = 0, the t statistic is ±inf / undefined.
        return None

    standard_error = std_difference / math.sqrt(n_pairs)
    degrees_of_freedom = n_pairs - 1
    test_statistic = mean_difference / standard_error
    p_value = 2.0 * (1.0 - t_cdf(abs(test_statistic), degrees_of_freedom))
    t_critical = t_ppf(1 - alpha / 2, degrees_of_freedom)
    margin = t_critical * standard_error
    cohen_dz = mean_difference / std_difference

    return {
        "n_pairs": n_pairs,
        "mean_difference": mean_difference,
        "control_mean": sum(control) / n_pairs,
        "treatment_mean": sum(treatment) / n_pairs,
        "test_statistic": test_statistic,
        "degrees_of_freedom": degrees_of_freedom,
        "p_value": _bounded_probability(p_value),
        "ci_lower": mean_difference - margin,
        "ci_upper": mean_difference + margin,
        "effect_size": cohen_dz,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }


def _ranks_with_ties(values: list[float]) -> tuple[list[float], list[int]]:
    """Midranks of ``values`` (ascending) plus the tie-group sizes.

    Returns a parallel list of average ranks (1-based, midranks within each block of equal values)
    and the list of tie-group sizes ``t_j`` the signed-rank variance tie-correction consumes.
    """
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    tie_sizes: list[int] = []
    position = 0
    while position < len(order):
        end = position
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for slot in range(position, end):
            ranks[order[slot]] = average_rank
        tie_sizes.append(end - position)
        position = end
    return ranks, tie_sizes


def _hodges_lehmann_signed(differences: list[float], half_width_rank_offset: float) -> dict[str, float]:
    """One-sample Hodges–Lehmann pseudomedian (median of Walsh averages) and its CI.

    The Walsh averages are ``(d_i + d_j)/2`` for all ``i ≤ j``; their median estimates the median
    of the difference distribution. ``half_width_rank_offset`` is ``C = z_{α/2}·√(n(n+1)(2n+1)/24)``
    (the no-tie standard deviation of ``W+`` scaled by the critical value); the CI endpoints are the
    order statistics of the ``M = n(n+1)/2`` Walsh averages at the symmetric ranks ``⌊M/2 − C⌋`` and
    ``M + 1 − ⌊M/2 − C⌋`` — the large-sample normal approximation to the exact signed-rank interval,
    mirroring the two-sample ``mann_whitney._hodges_lehmann_shift``.
    """
    count = len(differences)
    walsh = sorted(
        (differences[i] + differences[j]) / 2.0
        for i in range(count)
        for j in range(i, count)
    )
    pair_count = len(walsh)
    lower_rank = math.floor(pair_count / 2.0 - half_width_rank_offset)
    if lower_rank < 1:
        lower_rank = 1
    upper_rank = pair_count + 1 - lower_rank
    if upper_rank > pair_count:
        upper_rank = pair_count
    return {
        "pseudomedian": median(walsh),
        "ci_lower": walsh[lower_rank - 1],
        "ci_upper": walsh[upper_rank - 1],
    }


def wilcoxon_signed_rank_test(
    control: list[float], treatment: list[float], alpha: float = 0.05
) -> dict[str, Any] | None:
    """Wilcoxon signed-rank test on paired observations (tie- and continuity-corrected normal approx).

    ``control`` / ``treatment`` are equal-length paired observations. Zero differences are dropped,
    the remaining ``|d|`` are midranked, and the signed-rank sums ``W+`` / ``W−`` are formed. Returns
    the statistic ``T = min(W+, W−)``, the tie- and continuity-corrected z, the two-sided p-value,
    the rank-biserial effect size, the Hodges–Lehmann pseudomedian with its distribution-free CI, the
    counts of pairs / dropped zeros, and the significance verdict. Returns ``None`` when the test is
    undefined: fewer than two non-zero differences, or a zero rank variance (all non-zero differences
    tied in magnitude — the rank test carries no signal).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if any(not math.isfinite(value) for value in control) or any(
        not math.isfinite(value) for value in treatment
    ):
        raise ValueError("paired values must be finite")

    n_pairs = len(control)
    if n_pairs < 2:
        return None

    differences = _paired_differences(control, treatment)
    nonzero = [value for value in differences if value != 0]
    n_zero_differences = n_pairs - len(nonzero)
    n_nonzero = len(nonzero)
    if n_nonzero < 2:
        # All (or all but one) pairs are ties at zero: no rank signal to test.
        return None

    absolute = [abs(value) for value in nonzero]
    ranks, tie_sizes = _ranks_with_ties(absolute)
    w_plus = sum(rank for value, rank in zip(nonzero, ranks, strict=True) if value > 0)
    w_minus = sum(rank for value, rank in zip(nonzero, ranks, strict=True) if value < 0)

    mean_w = n_nonzero * (n_nonzero + 1) / 4.0
    tie_term = sum(size**3 - size for size in tie_sizes)
    variance_w = n_nonzero * (n_nonzero + 1) * (2 * n_nonzero + 1) / 24.0 - tie_term / 48.0
    if variance_w <= 0:
        return None
    standard_deviation_w = math.sqrt(variance_w)

    statistic = min(w_plus, w_minus)
    # Continuity correction pulls the statistic half a step toward its mean; the standardized value
    # is negative for statistic < mean, and the two-sided p doubles that lower tail.
    z_value = (statistic - mean_w + 0.5) / standard_deviation_w
    p_value = 2.0 * _STANDARD_NORMAL.cdf(z_value) if z_value < 0 else 2.0 * (1.0 - _STANDARD_NORMAL.cdf(z_value))

    rank_total = n_nonzero * (n_nonzero + 1) / 2.0
    rank_biserial = (w_plus - w_minus) / rank_total

    # The Hodges–Lehmann location estimate and its CI use the FULL set of n_pairs differences (zeros
    # are real "no change" observations and belong in a location estimate), so the rank offset uses
    # n_pairs — the textbook Hollander–Wolfe construction, mirroring the two-sample analyzer which
    # also builds its shift estimate from the full data. The p-value above drops zeros (Wilcoxon's
    # convention for the signed-rank statistic); these are two distinct quantities.
    half_width = _STANDARD_NORMAL.inv_cdf(1 - alpha / 2) * math.sqrt(
        n_pairs * (n_pairs + 1) * (2 * n_pairs + 1) / 24.0
    )
    hodges_lehmann = _hodges_lehmann_signed(differences, half_width)

    return {
        "n_pairs": n_pairs,
        "n_zero_differences": n_zero_differences,
        "n_nonzero": n_nonzero,
        "w_plus": w_plus,
        "w_minus": w_minus,
        "test_statistic": statistic,
        "z_value": z_value,
        "p_value": _bounded_probability(p_value),
        "effect_size": rank_biserial,
        "pseudomedian": hodges_lehmann["pseudomedian"],
        "ci_lower": hodges_lehmann["ci_lower"],
        "ci_upper": hodges_lehmann["ci_upper"],
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }


def _mcnemar_exact_two_sided_p(n_discordant: int, minority: int) -> float:
    """Exact two-sided McNemar p: twice the lower binomial tail of ``Binom(n_discordant, ½)``.

    Under the null the discordant pairs split 50/50, so the smaller discordant count ``minority``
    is the lower tail of a symmetric binomial; the two-sided p doubles it, clipped at 1 — matching
    ``scipy.stats.binomtest(minority, n_discordant, 0.5)`` (symmetric ``p = ½``).
    """
    lower_tail = sum(math.comb(n_discordant, k) for k in range(minority + 1)) * (0.5**n_discordant)
    return _bounded_probability(2.0 * lower_tail)


def mcnemar_test(
    control: list[float], treatment: list[float], alpha: float = 0.05
) -> dict[str, Any]:
    """McNemar's test on paired **binary** observations (0/1).

    ``control`` / ``treatment`` are equal-length paired 0/1 values (the caller validates the binary
    domain). Only the discordant pairs matter: ``b`` = #(0 → 1), ``c`` = #(1 → 0). Uses the exact
    two-sided binomial test when the discordant total is below ``MCNEMAR_EXACT_MAX_DISCORDANT`` and
    the Edwards continuity-corrected chi-square otherwise. Returns the discordant counts, the test
    statistic (``min(b, c)`` for the exact path, the chi-square for the asymptotic path), the
    two-sided p-value, the ``method`` used, the marginal proportion difference ``(b − c)/n_pairs``,
    the discordance odds ratio ``b/c`` (``None`` when ``c = 0``) and the significance verdict.
    Never returns ``None``: with no discordant pairs the test is uninformative but well-defined
    (``p = 1``, not significant).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")

    n_pairs = len(control)
    b = sum(1 for c, t in zip(control, treatment, strict=True) if c == 0 and t == 1)
    c = sum(1 for cv, t in zip(control, treatment, strict=True) if cv == 1 and t == 0)
    n_discordant = b + c

    if n_discordant == 0:
        method = "exact"
        statistic = 0.0
        p_value = 1.0
    elif n_discordant < MCNEMAR_EXACT_MAX_DISCORDANT:
        method = "exact"
        statistic = float(min(b, c))
        p_value = _mcnemar_exact_two_sided_p(n_discordant, min(b, c))
    else:
        method = "chi_square"
        statistic = (abs(b - c) - 1) ** 2 / n_discordant
        p_value = _bounded_probability(1.0 - chi_square_cdf(statistic, 1))

    proportion_difference = (b - c) / n_pairs if n_pairs > 0 else 0.0
    odds_ratio = b / c if c > 0 else None

    # Large-sample Wald CI for the difference of the two correlated (marginal) proportions,
    # Var[(b − c)/n] = (b + c − (b − c)²/n)/n² (Fleiss, *Statistical Methods for Rates and
    # Proportions*). Collapses to a point when there are no discordant pairs.
    if n_pairs > 0 and n_discordant > 0:
        variance = (n_discordant - (b - c) ** 2 / n_pairs) / (n_pairs**2)
        standard_error = math.sqrt(variance) if variance > 0 else 0.0
        z_critical = _STANDARD_NORMAL.inv_cdf(1 - alpha / 2)
        ci_lower = proportion_difference - z_critical * standard_error
        ci_upper = proportion_difference + z_critical * standard_error
    else:
        ci_lower = ci_upper = proportion_difference

    return {
        "n_pairs": n_pairs,
        "discordant_positive": b,
        "discordant_negative": c,
        "n_discordant": n_discordant,
        "test_statistic": statistic,
        "p_value": p_value,
        "method": method,
        "proportion_difference": proportion_difference,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "odds_ratio": odds_ratio,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }
