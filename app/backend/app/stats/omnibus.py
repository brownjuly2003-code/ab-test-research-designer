"""Omnibus tests for more than two groups — the multi-variant (A/B/C/…) post-hoc family.

Where the binary / continuous / Mann–Whitney estimators compare **two** arms, an experiment with
three or more variants needs a single omnibus test of "do the groups differ at all?" before drilling
into pairwise contrasts — exactly as the chi-square test of independence is the omnibus for an r×c
categorical table. Two analyzers cover the continuous case, one parametric and one rank-based, both
consuming the same input (a list of per-group value arrays, one array per variant):

* **Welch's one-way ANOVA** — the heteroscedastic omnibus for group *means*. Classic Fisher ANOVA
  assumes every arm shares one variance; that assumption is routinely false across experiment arms
  (a winning variant often shifts spread as well as level), and violating it inflates the Type-I
  error. Welch (1951) reweights each group by ``w_i = n_i / s_i²`` and adjusts the denominator and
  the (fractional) denominator degrees of freedom, giving a test that holds its nominal level under
  unequal variances. Statistic
  ``F* = [Σ w_i (x̄_i − x̄*)² / (k − 1)] / [1 + 2(k − 2)/(k² − 1) · S]`` where ``x̄* = Σ w_i x̄_i / W``,
  ``W = Σ w_i`` and ``S = Σ (1 − w_i/W)² / (n_i − 1)``; reference distribution ``F(k − 1, df₂)`` with
  ``df₂ = (k² − 1) / (3S)``. The reported effect size is the descriptive
  ``η² = SS_between / SS_total`` on the raw (unweighted) data — the proportion of variance explained
  by group membership, ∈ [0, 1] — kept separate from the Welch weighting so it reads as a plain
  descriptive magnitude rather than a quantity derived from the heteroscedastic statistic.

* **Kruskal–Wallis H test** — the distribution-free omnibus (the k-sample generalization of the
  Mann–Whitney U). All observations are pooled and midranked (average ranks on ties); the statistic
  ``H = 12 / (N(N + 1)) · Σ R_i²/n_i − 3(N + 1)`` is divided by the tie correction
  ``1 − Σ(t_j³ − t_j)/(N³ − N)`` and referred to ``χ²`` on ``k − 1`` degrees of freedom (the
  large-sample approximation). Effect size is ``ε² = H / (N − 1)`` (Tomczak & Tomczak 2014),
  the rank analogue of η² ∈ [0, 1].

Both return per-group summaries (means/SDs for Welch, medians/mean-ranks for Kruskal–Wallis) so the
omnibus verdict is actionable — a single p-value over ≥ 3 arms otherwise says "something differs"
without saying which arm. A degenerate input (fewer than two groups with usable within-group spread,
or no rank variation at all) yields ``None`` so the service layer can surface a 400 rather than the
analyzer inventing a statistic.

Sources (checked against the literature at implementation time, not from memory): Welch, "On the
comparison of several mean values: an alternative approach" (Biometrika, 1951); Kruskal & Wallis,
"Use of ranks in one-criterion variance analysis" (JASA, 1952); Tomczak & Tomczak (2014, ε²). The
Welch statistic and denominator df are cross-checked against ``statsmodels.stats.oneway.anova_oneway
(use_var="unequal")`` and the Kruskal–Wallis H / p against ``scipy.stats.kruskal`` (frozen in
``tests/test_omnibus.py``). Stdlib-only, pure functions reusing ``student_t.f_sf`` and
``srm.chi_square_cdf``; the response shapes are assembled in the service layer.
"""

import math
from statistics import mean, median
from typing import Any

from app.backend.app.stats.srm import chi_square_cdf
from app.backend.app.stats.student_t import f_sf

# Cap on total observations across all groups. The statistics are O(N log N) (ranking) / O(N)
# (means), and the group dimensions are bounded by the request schema, so this only guards against
# absurd magnitudes, mirroring the Fisher / Poisson / contingency caps.
MAX_OMNIBUS_TOTAL = 5_000_000


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _validate_groups(groups: list[list[float]]) -> None:
    """Shared structural guards: at least two groups, finite values, total within the cap."""
    if len(groups) < 2:
        raise ValueError("omnibus tests need at least two groups")
    total = sum(len(group) for group in groups)
    if total == 0:
        raise ValueError("omnibus groups must contain at least one value")
    if total > MAX_OMNIBUS_TOTAL:
        raise ValueError(f"omnibus total observations exceed the {MAX_OMNIBUS_TOTAL} cap")
    if any(not math.isfinite(value) for group in groups for value in group):
        raise ValueError("omnibus values must be finite")


def welch_anova_test(groups: list[list[float]], alpha: float = 0.05) -> dict[str, Any] | None:
    """Welch's heteroscedastic one-way ANOVA across ``k >= 2`` groups.

    ``groups`` is a list of per-group value arrays. Returns the Welch F statistic, the numerator
    (``k − 1``) and fractional denominator degrees of freedom, the upper-tail p-value, the descriptive
    η² effect size, the total N, the group count, per-group summaries (n, mean, sample SD) and the
    significance verdict. Returns ``None`` when the test is undefined: any group with fewer than two
    observations, or any group with zero within-group variance (its weight ``n_i/s_i²`` is infinite),
    which the caller surfaces rather than the analyzer inventing an F.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    _validate_groups(groups)

    k = len(groups)
    sizes = [len(group) for group in groups]
    if any(size < 2 for size in sizes):
        # A group of one has no within-group variance estimate: Welch's weights are undefined.
        return None

    means = [mean(group) for group in groups]
    variances = [
        sum((value - means[i]) ** 2 for value in groups[i]) / (sizes[i] - 1) for i in range(k)
    ]
    if any(variance == 0 for variance in variances):
        # Zero within-group variance ⇒ weight n_i/s_i² is infinite; the Welch statistic is undefined.
        return None

    weights = [sizes[i] / variances[i] for i in range(k)]
    weight_total = sum(weights)
    weighted_grand_mean = sum(weights[i] * means[i] for i in range(k)) / weight_total
    numerator = sum(weights[i] * (means[i] - weighted_grand_mean) ** 2 for i in range(k)) / (k - 1)
    # S = Σ (1 − w_i/W)² / (n_i − 1) is strictly positive for k >= 2 (each (1 − w_i/W)² > 0), so the
    # denominator adjustment and df₂ never divide by zero.
    spread = sum((1 - weights[i] / weight_total) ** 2 / (sizes[i] - 1) for i in range(k))
    f_statistic = numerator / (1 + (2 * (k - 2) / (k**2 - 1)) * spread)
    df_numerator = k - 1
    df_denominator = (k**2 - 1) / (3 * spread)
    p_value = _bounded_probability(f_sf(f_statistic, df_numerator, df_denominator))

    # Descriptive η² = SS_between / SS_total on the raw (unweighted) data: the share of total variance
    # explained by group membership. Independent of the Welch weighting, so it reads as a plain
    # effect-size magnitude. SS_total > 0 here: zero total variance would require every within-group
    # variance to be zero, already returned None above.
    all_values = [value for group in groups for value in group]
    total_n = len(all_values)
    grand_mean = mean(all_values)
    ss_between = sum(sizes[i] * (means[i] - grand_mean) ** 2 for i in range(k))
    ss_total = sum((value - grand_mean) ** 2 for value in all_values)
    eta_squared = ss_between / ss_total if ss_total > 0 else 0.0

    group_summaries = [
        {"n": sizes[i], "mean": means[i], "std": math.sqrt(variances[i])} for i in range(k)
    ]

    return {
        "test_statistic": f_statistic,
        "df_numerator": float(df_numerator),
        "df_denominator": df_denominator,
        "p_value": p_value,
        "effect_size": eta_squared,
        "num_groups": k,
        "n_total": total_n,
        "group_summaries": group_summaries,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }


def _midranks(values: list[float]) -> tuple[list[float], float]:
    """Average (mid)ranks of ``values`` plus the tie term ``Σ(t_j³ − t_j)`` used by the H correction."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    tie_term = 0.0
    position = 0
    while position < len(order):
        end = position
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1
        average_rank = (position + 1 + end) / 2.0
        for slot in range(position, end):
            ranks[order[slot]] = average_rank
        block = end - position
        tie_term += block**3 - block
        position = end
    return ranks, tie_term


def kruskal_wallis_test(groups: list[list[float]], alpha: float = 0.05) -> dict[str, Any] | None:
    """Kruskal–Wallis H test — the distribution-free omnibus across ``k >= 2`` groups.

    ``groups`` is a list of per-group value arrays. Returns the tie-corrected H statistic, its degrees
    of freedom ``k − 1``, the chi-square upper-tail p-value, the ε² effect size, the total N, the group
    count, per-group summaries (n, median, mean rank) and the significance verdict. Returns ``None``
    when there is no rank variation at all (every observation tied): the tie correction collapses to
    zero and H is undefined, which the caller surfaces rather than dividing by zero.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    _validate_groups(groups)

    k = len(groups)
    sizes = [len(group) for group in groups]
    all_values = [value for group in groups for value in group]
    total_n = len(all_values)
    if total_n < 2 or total_n**3 - total_n == 0:
        return None

    ranks, tie_term = _midranks(all_values)
    correction = 1 - tie_term / (total_n**3 - total_n)
    if correction <= 0:
        # Every value is tied: no rank information, H is undefined.
        return None

    rank_sums: list[float] = []
    mean_ranks: list[float] = []
    offset = 0
    for size in sizes:
        rank_sum = sum(ranks[offset + j] for j in range(size))
        rank_sums.append(rank_sum)
        mean_ranks.append(rank_sum / size)
        offset += size

    h_raw = 12.0 / (total_n * (total_n + 1)) * sum(
        rank_sums[i] ** 2 / sizes[i] for i in range(k)
    ) - 3 * (total_n + 1)
    h_statistic = h_raw / correction
    df = k - 1
    p_value = _bounded_probability(1.0 - chi_square_cdf(h_statistic, df))
    # ε² = H / (N − 1) ∈ [0, 1] — the rank analogue of η² (Tomczak & Tomczak 2014).
    epsilon_squared = h_statistic / (total_n - 1)

    group_summaries = [
        {"n": sizes[i], "median": median(groups[i]), "mean_rank": mean_ranks[i]} for i in range(k)
    ]

    return {
        "test_statistic": h_statistic,
        "df_numerator": float(df),
        "p_value": p_value,
        "effect_size": epsilon_squared,
        "num_groups": k,
        "n_total": total_n,
        "group_summaries": group_summaries,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }
