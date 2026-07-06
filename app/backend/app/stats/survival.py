"""Two-arm survival analysis — the Kaplan-Meier estimator and the log-rank (Mantel-Cox) test.

Where the binary / continuous analyzers compare a *scalar* outcome measured once per subject, a
time-to-event experiment measures, per subject, a **duration** and whether the event was actually
observed or the subject was **censored** (still event-free at last follow-up). That censored
observation carries real information — the subject survived at least that long — which a naive
"mean time" comparison throws away. Two analyzers cover the two-arm case, sharing the same input
(two arms, each a parallel pair of durations + observed-event flags):

* **Kaplan-Meier product-limit estimator** — the non-parametric survival curve per arm.
  ``S(t) = Π_{t_i <= t} (1 - d_i / n_i)`` over the distinct event times ``t_i``, where ``d_i`` is the
  number of events at ``t_i`` and ``n_i`` the number still at risk (observed time ``>= t_i``; a
  censoring tie at ``t_i`` is treated as occurring just after any events there, the standard
  convention). Pointwise variance is **Greenwood's formula**
  ``Var(S(t)) = S(t)^2 · Σ_{t_i <= t} d_i / (n_i (n_i - d_i))`` giving a normal-approximation
  confidence interval ``S(t) ± z · sqrt(Var)`` clamped to ``[0, 1]``. The step points (time,
  survival, at-risk n, events, CI) are returned so the frontend can draw the survival curve.

* **Log-rank (Mantel-Cox) test** — the two-sample test of "do the survival curves differ?". Over the
  pooled ordered event times, at each event time the risk set is a 2×2 table (arm × event/no-event);
  under the null the arm-1 event count is hypergeometric with expectation ``e_1 = d · n_1 / n`` and
  variance ``v = d · (n_1/n) · (n_2/n) · (n - d) / (n - 1)`` (``v = 0`` when ``n = 1``). Summing gives
  ``O_1 - E_1`` and ``V``; the statistic ``χ² = (O_1 - E_1)² / V`` is referred to a chi-square with
  one degree of freedom. It weights every event time equally (the unweighted log-rank), which is most
  powerful under proportional hazards.

Sources (checked against the literature at implementation time, not from memory): Kaplan & Meier,
"Nonparametric estimation from incomplete observations" (JASA, 1958); Greenwood (1926); Mantel (1966)
/ Cox (1972). Both the log-rank χ² and the Kaplan-Meier estimates are frozen against the canonical
**Freireich et al. (1963)** 6-MP-vs-placebo leukemia dataset (published log-rank χ² ≈ 16.79,
p ≈ 4.2e-5) and cross-checked with ``scipy.stats.chi2.sf`` in the scratchpad verification
(``scratchpad/verify_logrank_km.py``); scipy is not a runtime dependency. Stdlib-only, pure
functions reusing ``srm.chi_square_cdf`` for the χ²(1) tail (no second chi-square implementation);
the response shapes are assembled in the service layer.

Explicitly OUT OF SCOPE for this module (documented deferrals, not implemented): Cox
proportional-hazards regression, parametric survival (Weibull / exponential), >2-arm / trend
log-rank, weighted log-rank (Gehan-Wilcoxon / Fleming-Harrington), competing risks, survival
sample-size / power, hazard-ratio and median-survival estimation.
"""

import math
from statistics import NormalDist
from typing import Any

from app.backend.app.stats.srm import chi_square_cdf

# Cap on total observations across both arms. Kaplan-Meier is O(N log N) (sorting) and the log-rank is
# O(U · 1) over the U distinct event times, so this only guards against absurd magnitudes; the per-arm
# counts are bounded by the request schema, mirroring the omnibus / Fisher caps.
MAX_SURVIVAL_TOTAL = 200_000

_STANDARD_NORMAL = NormalDist()


def _validate_arm(durations: list[float], events: list[bool]) -> None:
    if len(durations) != len(events):
        raise ValueError("durations and events must have the same length")
    if len(durations) == 0:
        raise ValueError("each arm needs at least one observation")
    if any(not math.isfinite(value) for value in durations):
        raise ValueError("survival durations must be finite")
    if any(value < 0 for value in durations):
        raise ValueError("survival durations must be non-negative")


def kaplan_meier_estimate(
    durations: list[float], events: list[bool], alpha: float = 0.05
) -> list[dict[str, Any]]:
    """Kaplan-Meier product-limit survival curve with Greenwood pointwise confidence intervals.

    ``durations[i]`` is subject ``i``'s observed time and ``events[i]`` is ``True`` when the event was
    observed (``False`` when the subject was right-censored). Returns one step point per distinct event
    time, each a dict with ``time``, ``survival`` S(t), ``at_risk`` n (subjects with duration ``>= t``),
    ``n_events`` d, ``variance`` (Greenwood), ``std_error`` and the confidence bounds ``ci_lower`` /
    ``ci_upper`` (normal approximation, clamped to ``[0, 1]``). When S(t) reaches 0 (every remaining
    at-risk subject had the event) Greenwood's variance is undefined and the CI collapses to the point
    estimate 0. A fully censored arm has no event times and yields an empty list.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    _validate_arm(durations, events)

    z = _STANDARD_NORMAL.inv_cdf(1 - alpha / 2)
    distinct_event_times = sorted({durations[i] for i in range(len(durations)) if events[i]})

    survival = 1.0
    greenwood_sum = 0.0  # running Σ d_i / (n_i (n_i - d_i))
    points: list[dict[str, Any]] = []
    for event_time in distinct_event_times:
        at_risk = sum(1 for value in durations if value >= event_time)
        n_events = sum(
            1 for i in range(len(durations)) if durations[i] == event_time and events[i]
        )
        survival *= 1.0 - n_events / at_risk
        if at_risk - n_events > 0:
            greenwood_sum += n_events / (at_risk * (at_risk - n_events))
            variance = survival * survival * greenwood_sum
            std_error = math.sqrt(variance)
            half_width = z * std_error
            ci_lower = max(0.0, survival - half_width)
            ci_upper = min(1.0, survival + half_width)
        else:
            # S(t) hit 0: the last at-risk subjects all had the event, Greenwood's variance is undefined.
            variance = 0.0
            std_error = 0.0
            ci_lower = 0.0
            ci_upper = 0.0
        points.append(
            {
                "time": float(event_time),
                "survival": survival,
                "at_risk": at_risk,
                "n_events": n_events,
                "variance": variance,
                "std_error": std_error,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            }
        )
    return points


def log_rank_test(
    durations1: list[float],
    events1: list[bool],
    durations2: list[float],
    events2: list[bool],
    alpha: float = 0.05,
) -> dict[str, Any] | None:
    """Two-sample log-rank (Mantel-Cox) test comparing two survival curves.

    Arm 1 is the reference for ``O_1 - E_1``; the statistic is symmetric in the arms so the χ² is the
    same either way. Returns the χ² statistic (1 df), its p-value (chi-square upper tail), the observed
    and expected event counts per arm, the pooled variance ``V``, the significance verdict and each
    arm's ``n`` and total events. Returns ``None`` when ``V = 0`` — no events occur in either arm (a
    fully censored comparison), so the statistic is undefined — which the caller surfaces as a 400
    rather than inventing a χ².
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    _validate_arm(durations1, events1)
    _validate_arm(durations2, events2)

    total = len(durations1) + len(durations2)
    if total > MAX_SURVIVAL_TOTAL:
        raise ValueError(f"survival total observations exceed the {MAX_SURVIVAL_TOTAL} cap")

    pooled_event_times = sorted(
        {durations1[i] for i in range(len(durations1)) if events1[i]}
        | {durations2[i] for i in range(len(durations2)) if events2[i]}
    )

    observed1 = 0
    observed2 = 0
    expected1 = 0.0
    expected2 = 0.0
    variance = 0.0
    for event_time in pooled_event_times:
        at_risk1 = sum(1 for value in durations1 if value >= event_time)
        at_risk2 = sum(1 for value in durations2 if value >= event_time)
        at_risk = at_risk1 + at_risk2
        if at_risk == 0:
            continue
        events_here1 = sum(
            1 for i in range(len(durations1)) if durations1[i] == event_time and events1[i]
        )
        events_here2 = sum(
            1 for i in range(len(durations2)) if durations2[i] == event_time and events2[i]
        )
        events_here = events_here1 + events_here2
        observed1 += events_here1
        observed2 += events_here2
        expected1 += events_here * at_risk1 / at_risk
        expected2 += events_here * at_risk2 / at_risk
        if at_risk > 1:
            variance += (
                events_here
                * (at_risk1 / at_risk)
                * (at_risk2 / at_risk)
                * (at_risk - events_here)
                / (at_risk - 1)
            )

    if variance <= 0:
        # No events in either arm (or every event time has a singleton risk set): V is zero and the
        # statistic is undefined. Surfaced by the caller as a 400.
        return None

    chi_square = (observed1 - expected1) ** 2 / variance
    p_value = min(1.0, max(0.0, 1.0 - chi_square_cdf(chi_square, 1)))
    return {
        "chi_square": chi_square,
        "df": 1,
        "p_value": p_value,
        "observed1": observed1,
        "expected1": expected1,
        "observed2": observed2,
        "expected2": expected2,
        "variance": variance,
        "n1": len(durations1),
        "n2": len(durations2),
        "events1": observed1,
        "events2": observed2,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }
