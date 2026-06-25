"""
Multiple-testing corrections for experiments that track several metrics at once.

When an experiment reports many metrics (a primary plus a battery of secondary and guardrail
metrics), testing each at the same nominal ``alpha`` inflates the chance of *some* false positive.
Two different error rates can be controlled, and they answer different questions:

* **FWER** (family-wise error rate) — the probability of *one or more* false positives across the
  whole family. Bonferroni and Holm bound this. Conservative; loses power as the family grows.
* **FDR** (false discovery rate) — the *expected fraction* of false positives among the metrics
  that were declared significant. Benjamini & Hochberg (1995) bound this. Much more powerful when
  many metrics are tested and a controlled share of false discoveries is acceptable.

This module is deliberately distinct from the Bonferroni correction already applied across the
number of *variants* (``stats/binary``, ``stats/continuous``, the live-stats path): that controls
FWER over arms of one metric. Here we control error across the number of *metrics*.

Pure stdlib, no NumPy. Formulae verified against Benjamini & Hochberg, "Controlling the False
Discovery Rate", JRSS-B 57(1):289-300, 1995 (the step-up procedure and the (i/m)q critical line),
and Holm, "A Simple Sequentially Rejective Multiple Test Procedure", Scand. J. Statist. 6:65-70,
1979 (the step-down procedure).

Both public functions return the same dict shape so the API endpoint can dispatch on ``method``:

    {
        "method":            "bh" | "holm",
        "level":             float,        # q (FDR) for BH, alpha (FWER) for Holm
        "num_tests":         int,
        "num_rejected":      int,
        "threshold_rank":    int,          # k* — number of ordered p-values rejected (0 if none)
        "critical_value":    float,        # largest raw p-value that is rejected (0.0 if none)
        "rejected":          list[bool],   # per metric, in the input order
        "adjusted_pvalues":  list[float],  # per metric, in the input order
    }
"""

from typing import Any


def _validate(pvalues: list[float], level: float) -> None:
    if not pvalues:
        raise ValueError("pvalues must be a non-empty list")
    if any(not 0.0 <= p <= 1.0 for p in pvalues):
        raise ValueError("every p-value must lie in [0, 1]")
    if not 0.0 < level < 1.0:
        raise ValueError("the significance level must lie in (0, 1)")


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> dict[str, Any]:
    """Benjamini-Hochberg step-up procedure controlling the FDR at level ``q``.

    Procedure (BH 1995): order the p-values ``p(1) <= ... <= p(m)``; find
    ``k* = max{ k : p(k) <= (k / m) * q }`` and reject the hypotheses with ranks ``1..k*`` (none if
    no such ``k`` exists). Equivalently, reject every metric whose raw p-value is ``<= p(k*)``.

    BH-adjusted p-values use the step-up monotonisation
    ``p_adj(i) = min_{j >= i} min(1, (m / j) * p(j))`` (cumulative minimum taken from the largest
    rank down to the smallest), so a metric is rejected exactly when its adjusted p-value ``<= q``.
    """
    _validate(pvalues, q)
    m = len(pvalues)
    # Ascending order of p-values; ``order[r]`` is the original index of rank r+1. sorted() is
    # stable, so ties keep their input order.
    order = sorted(range(m), key=lambda i: pvalues[i])
    sorted_p = [pvalues[i] for i in order]

    # Step-up: the largest rank k (1-based) whose p-value clears the (k/m)q critical line.
    threshold_rank = 0
    for k in range(m, 0, -1):
        if sorted_p[k - 1] <= (k / m) * q:
            threshold_rank = k
            break
    critical_value = sorted_p[threshold_rank - 1] if threshold_rank > 0 else 0.0

    # Adjusted p-values: running minimum of (m/k)*p(k) from the tail toward the head, clamped to 1.
    adjusted_sorted = [0.0] * m
    running_min = 1.0
    for k in range(m, 0, -1):
        running_min = min(running_min, min(1.0, sorted_p[k - 1] * m / k))
        adjusted_sorted[k - 1] = running_min

    rejected_sorted = [rank <= threshold_rank for rank in range(1, m + 1)]

    rejected = [False] * m
    adjusted = [0.0] * m
    for rank_idx, original_idx in enumerate(order):
        rejected[original_idx] = rejected_sorted[rank_idx]
        adjusted[original_idx] = adjusted_sorted[rank_idx]

    return {
        "method": "bh",
        "level": q,
        "num_tests": m,
        "num_rejected": threshold_rank,
        "threshold_rank": threshold_rank,
        "critical_value": critical_value,
        "rejected": rejected,
        "adjusted_pvalues": adjusted,
    }


def holm_bonferroni(pvalues: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Holm step-down procedure controlling the FWER at level ``alpha``.

    Procedure (Holm 1979): order the p-values ``p(1) <= ... <= p(m)``; step down from the smallest,
    rejecting while ``p(k) <= alpha / (m - k + 1)`` and stopping at the first failure. Provided for
    contrast with BH — uniformly more powerful than plain Bonferroni while still bounding the
    probability of *any* false positive.

    Holm-adjusted p-values use the step-down monotonisation
    ``p_adj(i) = max_{j <= i} min(1, (m - j + 1) * p(j))`` (cumulative maximum from the smallest
    rank up), so a metric is rejected exactly when its adjusted p-value ``<= alpha``.
    """
    _validate(pvalues, alpha)
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    sorted_p = [pvalues[i] for i in order]

    # Adjusted p-values: running maximum of (m-k+1)*p(k) from the head toward the tail, clamped to 1.
    adjusted_sorted = [0.0] * m
    running_max = 0.0
    for k in range(1, m + 1):
        running_max = max(running_max, min(1.0, sorted_p[k - 1] * (m - k + 1)))
        adjusted_sorted[k - 1] = running_max

    # Step-down: reject the leading run that clears alpha/(m-k+1); the first failure stops the run.
    threshold_rank = 0
    for k in range(1, m + 1):
        if sorted_p[k - 1] <= alpha / (m - k + 1):
            threshold_rank = k
        else:
            break
    critical_value = sorted_p[threshold_rank - 1] if threshold_rank > 0 else 0.0

    rejected_sorted = [rank <= threshold_rank for rank in range(1, m + 1)]

    rejected = [False] * m
    adjusted = [0.0] * m
    for rank_idx, original_idx in enumerate(order):
        rejected[original_idx] = rejected_sorted[rank_idx]
        adjusted[original_idx] = adjusted_sorted[rank_idx]

    return {
        "method": "holm",
        "level": alpha,
        "num_tests": m,
        "num_rejected": threshold_rank,
        "threshold_rank": threshold_rank,
        "critical_value": critical_value,
        "rejected": rejected,
        "adjusted_pvalues": adjusted,
    }
