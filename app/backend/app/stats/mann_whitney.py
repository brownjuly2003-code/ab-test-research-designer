"""
Mann–Whitney U test (Wilcoxon rank-sum) — the distribution-free two-sample test.

Where the binary / continuous / ratio estimators in this package compare *means* under a normal
approximation, the Mann–Whitney U test compares the *whole distributions*: it asks whether one arm
is stochastically larger than the other (``P(treatment > control) > 1/2``), using only the ranks of
the pooled observations. That makes it robust to heavy tails and outliers — the regime where the
mean-based t/z test misbehaves and exactly where real product metrics (revenue, time-on-site, AOV)
live. Because it is rank-based, it needs the **raw per-unit values**, not the (mean, std, n) summary
the parametric path accepts.

Source (verified against the literature at implementation time, not from memory): Mann & Whitney,
"On a Test of Whether one of Two Random Variables is Stochastically Larger than the Other" (Ann.
Math. Stat., 1947); Hollander, Wolfe & Chicken, *Nonparametric Statistical Methods* (3rd ed.,
ch. 4 — the rank-sum test, the tie correction, and the Hodges–Lehmann shift estimate with its
distribution-free confidence interval); Hodges & Lehmann (1963). Definitions used:

    Pool the ``N = n_c + n_t`` observations, rank them 1..N with **midranks** on ties. With ``R_t``
    the rank sum of the treatment arm,
        U_t = R_t − n_t(n_t+1)/2 = #{(t, c) : t > c}   (ties count ½),   U_c = n_c·n_t − U_t.
    Under H0 (equal distributions), U_t has mean ``μ_U = n_c·n_t/2`` and, with tie groups of sizes
    ``τ_j`` (Σ τ_j = N),
        σ²_U = (n_c·n_t / 12) · [ (N + 1) − Σ(τ_j³ − τ_j) / (N(N−1)) ].
    The standardized statistic with a continuity correction toward the mean is
        z = (U_t − μ_U ∓ ½) / σ_U,   two-sided p = 2·(1 − Φ(|z|)).
    Effect size: common-language ``CLES = U_t / (n_c·n_t) = P(treatment > control)`` and the
    rank-biserial correlation ``r = 2·CLES − 1 = (U_t − U_c)/(n_c·n_t) ∈ [−1, 1]``.
    Location shift: the Hodges–Lehmann estimate is the median of the ``n_c·n_t`` pairwise differences
    ``t_j − c_i``; its distribution-free CI takes the order statistics of those differences at ranks
    derived from the same normal approximation (``K = ⌊M/2 − z_{α/2}·σ_U⌋``, symmetric upper rank).

This is the large-sample (asymptotic) test, matching ``scipy.stats.mannwhitneyu(method="asymptotic")``;
the exact small-sample permutation distribution is a future refinement. The module is stdlib-only and
holds pure functions; assembling the response shape lives in the service layer.
"""

from math import floor, isfinite, sqrt
from statistics import NormalDist, median
from typing import Any

_STANDARD_NORMAL = NormalDist()


def _bounded_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _pooled_rank_sum_and_ties(
    control: list[float], treatment: list[float]
) -> tuple[float, list[int]]:
    """Treatment rank sum (midranks) over the pooled sample, plus the tie-group sizes.

    Both arms are pooled, sorted ascending, and assigned average (mid) ranks within each block of
    equal values. Returns the sum of the treatment arm's ranks and the list of tie-group sizes
    ``τ_j`` (a singleton is a group of size 1), which the variance tie-correction consumes.
    """
    pooled: list[tuple[float, int]] = [(value, 0) for value in control]
    pooled += [(value, 1) for value in treatment]
    pooled.sort(key=lambda item: item[0])

    total = len(pooled)
    treatment_rank_sum = 0.0
    tie_sizes: list[int] = []
    index = 0
    while index < total:
        end = index
        while end < total and pooled[end][0] == pooled[index][0]:
            end += 1
        # Positions index..end-1 (0-based) are tied; their 1-based ranks are index+1..end, whose
        # average is ((index + 1) + end) / 2.
        average_rank = (index + 1 + end) / 2.0
        for position in range(index, end):
            if pooled[position][1] == 1:
                treatment_rank_sum += average_rank
        tie_sizes.append(end - index)
        index = end
    return treatment_rank_sum, tie_sizes


def _hodges_lehmann_shift(
    control: list[float], treatment: list[float], half_width_rank_offset: float
) -> dict[str, float]:
    """Hodges–Lehmann location shift (median of pairwise ``t − c``) and its distribution-free CI.

    ``half_width_rank_offset`` is ``C = z_{α/2}·sqrt(n_c·n_t·(N+1)/12)`` (the nominal, no-tie
    standard deviation of U scaled by the critical value). The CI endpoints are the order statistics
    of the ``M = n_c·n_t`` pairwise differences at the symmetric ranks ``⌊M/2 − C⌋`` and
    ``M + 1 − ⌊M/2 − C⌋`` — the large-sample normal approximation to the exact rank interval.
    Materializes all ``M`` differences; callers bound ``M`` via the input length cap.
    """
    differences = sorted(
        treatment_value - control_value
        for treatment_value in treatment
        for control_value in control
    )
    pair_count = len(differences)
    shift = median(differences)

    lower_rank = floor(pair_count / 2.0 - half_width_rank_offset)
    if lower_rank < 1:
        lower_rank = 1
    upper_rank = pair_count + 1 - lower_rank
    if upper_rank > pair_count:
        upper_rank = pair_count
    return {
        "shift": shift,
        "ci_lower": differences[lower_rank - 1],
        "ci_upper": differences[upper_rank - 1],
    }


def mann_whitney_u_test(
    control: list[float], treatment: list[float], alpha: float = 0.05
) -> dict[str, Any] | None:
    """Two-sided Mann–Whitney U test on raw per-unit samples (asymptotic, tie-corrected).

    ``control`` / ``treatment`` are the raw observed values per arm. Returns the U statistic, the
    tie- and continuity-corrected z, the two-sided p-value, the common-language effect size
    (``P(treatment > control)``) and rank-biserial correlation, the Hodges–Lehmann shift with its
    distribution-free CI, the per-arm medians, the significance verdict and an asymptotic achieved
    power. Returns ``None`` when the test is undefined: an empty arm, or a degenerate pooled sample
    where every observation is tied (the rank variance collapses to zero — no usable signal).
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if any(not isfinite(value) for value in control) or any(
        not isfinite(value) for value in treatment
    ):
        raise ValueError("sample values must be finite")

    n_control = len(control)
    n_treatment = len(treatment)
    if n_control < 1 or n_treatment < 1:
        return None

    pair_count = n_control * n_treatment
    total = n_control + n_treatment
    treatment_rank_sum, tie_sizes = _pooled_rank_sum_and_ties(control, treatment)

    u_treatment = treatment_rank_sum - n_treatment * (n_treatment + 1) / 2.0
    u_control = pair_count - u_treatment
    mean_u = pair_count / 2.0

    # Tie-corrected variance of U. With no ties this reduces to n_c·n_t·(N+1)/12.
    tie_term = sum(size**3 - size for size in tie_sizes)
    variance_u = (pair_count / 12.0) * ((total + 1) - tie_term / (total * (total - 1)))
    if variance_u <= 0:
        # Every value tied across both arms: the rank test carries no information.
        return None
    standard_deviation_u = sqrt(variance_u)

    # Continuity correction shrinks |U − μ_U| toward the mean by ½, never past it (no sign flip).
    deviation = u_treatment - mean_u
    if deviation > 0:
        corrected = max(0.0, deviation - 0.5)
    elif deviation < 0:
        corrected = min(0.0, deviation + 0.5)
    else:
        corrected = 0.0
    test_statistic = corrected / standard_deviation_u
    p_value = 2.0 * (1.0 - _STANDARD_NORMAL.cdf(abs(test_statistic)))

    common_language_effect = u_treatment / pair_count
    rank_biserial = 2.0 * common_language_effect - 1.0

    z_critical = _STANDARD_NORMAL.inv_cdf(1.0 - alpha / 2.0)
    nominal_std = sqrt(pair_count * (total + 1) / 12.0)
    hodges_lehmann = _hodges_lehmann_shift(control, treatment, z_critical * nominal_std)

    # Asymptotic achieved power of the two-sided rank test at the observed standardized effect, in
    # the same form the binary / continuous / ratio / stratification estimators report.
    power_achieved = _STANDARD_NORMAL.cdf(
        abs(test_statistic) - z_critical
    ) + _STANDARD_NORMAL.cdf(-z_critical - abs(test_statistic))

    return {
        "u_statistic": u_treatment,
        "u_control": u_control,
        "n_control": n_control,
        "n_treatment": n_treatment,
        "test_statistic": test_statistic,
        "p_value": _bounded_probability(p_value),
        "common_language_effect": common_language_effect,
        "rank_biserial": rank_biserial,
        "hodges_lehmann_shift": hodges_lehmann["shift"],
        "ci_lower": hodges_lehmann["ci_lower"],
        "ci_upper": hodges_lehmann["ci_upper"],
        "ci_level": 1.0 - alpha,
        "control_median": median(control),
        "treatment_median": median(treatment),
        "is_significant": p_value < alpha,
        "power_achieved": _bounded_probability(power_achieved),
        "ties_present": any(size > 1 for size in tie_sizes),
    }
