"""Freeze reference numbers for the two-arm log-rank test + Kaplan-Meier estimator (task P5.4).

This is the *verification oracle*, run BEFORE the production code in ``app/backend/app/stats/
survival.py`` is written. It contains a fully independent, from-scratch implementation of

  * the Kaplan-Meier product-limit estimator with Greenwood's-formula pointwise variance, and
  * the Mantel-Cox (log-rank) two-sample test with the hypergeometric risk-set expectation/variance,

and pins them against:

  1. the **Freireich et al. (1963) leukemia remission dataset** (6-MP vs placebo, 21 patients per
     arm) — the canonical log-rank textbook example (Klein & Moeschberger, "Survival Analysis";
     Collett, "Modelling Survival Data"). Published log-rank chi-square ~= 16.79, p ~= 4.2e-5, and
     the 6-MP Kaplan-Meier survival estimates appear in essentially every survival text.
  2. a **tiny hand-computable example** with one censored observation per arm, so the censoring /
     risk-set-exit logic is pinned rather than only the headline number.
  3. **scipy.stats.chi2.sf(x, 1)** for the log-rank p-value (independent chi-square tail), and
     **lifelines** (``logrank_test`` / ``KaplanMeierFitter``) if it can be imported.

The production module is stdlib-only; scipy/lifelines are used here purely as external oracles and
are NOT runtime dependencies. The numbers printed here are copied into ``tests/test_survival.py``.
"""

from __future__ import annotations

import math

# --- independent reference implementation (NOT the production code) -----------------------------


def km_estimate(times: list[float], events: list[bool]) -> list[dict[str, float]]:
    """Kaplan-Meier product-limit estimate with Greenwood variance, at each distinct event time.

    Returns step points (time, survival, at_risk, n_events, greenwood_var, se). ``at_risk`` at time
    t is the number of subjects with observed time >= t (censoring at exactly t is treated as
    occurring just after any events at t, the standard convention).
    """
    order = sorted(range(len(times)), key=lambda i: times[i])
    stimes = [times[i] for i in order]
    sevents = [events[i] for i in order]
    n = len(stimes)

    distinct_event_times = sorted({stimes[i] for i in range(n) if sevents[i]})
    survival = 1.0
    greenwood_sum = 0.0  # running Sum d_i / (n_i (n_i - d_i))
    points: list[dict[str, float]] = []
    for t in distinct_event_times:
        at_risk = sum(1 for x in stimes if x >= t)
        d = sum(1 for i in range(n) if stimes[i] == t and sevents[i])
        survival *= 1.0 - d / at_risk
        if at_risk - d > 0:
            greenwood_sum += d / (at_risk * (at_risk - d))
            variance = survival * survival * greenwood_sum
            se = math.sqrt(variance)
        else:
            # survival hit 0 (everyone still at risk had the event): Greenwood variance undefined.
            variance = math.nan
            se = math.nan
        points.append(
            {
                "time": float(t),
                "survival": survival,
                "at_risk": float(at_risk),
                "n_events": float(d),
                "greenwood_var": variance,
                "se": se,
            }
        )
    return points


def logrank_test(
    times1: list[float],
    events1: list[bool],
    times2: list[float],
    events2: list[bool],
) -> dict[str, float]:
    """Two-sample Mantel-Cox log-rank test. Arm 1 is the reference for O1 - E1.

    At each pooled distinct event time t_j: n1, n2 at risk (>= t_j); d1, d2 events; d = d1 + d2;
    n = n1 + n2. Expected arm-1 events e1 = d * n1 / n; hypergeometric variance
    v = d * (n1/n) * (n2/n) * (n - d) / (n - 1)  (v = 0 when n == 1). Statistic
    chi2 = (O1 - E1)^2 / V ~ chi-square with 1 df.
    """
    pooled_event_times = sorted(
        {times1[i] for i in range(len(times1)) if events1[i]}
        | {times2[i] for i in range(len(times2)) if events2[i]}
    )
    o1 = 0.0
    e1 = 0.0
    o2 = 0.0
    e2 = 0.0
    v = 0.0
    for t in pooled_event_times:
        n1 = sum(1 for x in times1 if x >= t)
        n2 = sum(1 for x in times2 if x >= t)
        n = n1 + n2
        d1 = sum(1 for i in range(len(times1)) if times1[i] == t and events1[i])
        d2 = sum(1 for i in range(len(times2)) if times2[i] == t and events2[i])
        d = d1 + d2
        if n == 0:
            continue
        e1t = d * n1 / n
        e2t = d * n2 / n
        o1 += d1
        o2 += d2
        e1 += e1t
        e2 += e2t
        if n > 1:
            v += d * (n1 / n) * (n2 / n) * (n - d) / (n - 1)
    chi2 = (o1 - e1) ** 2 / v if v > 0 else math.nan
    return {"o1": o1, "e1": e1, "o2": o2, "e2": e2, "var": v, "chi2": chi2}


def chi2_sf_df1(x: float) -> float:
    """Chi-square(1) survival = 2 * (1 - Phi(sqrt(x))) via the standard normal (self-check only)."""
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(math.sqrt(x) / math.sqrt(2.0))))


# --- Freireich et al. (1963) leukemia remission data --------------------------------------------
# 6-MP (treatment): '+' == censored (still in remission at last follow-up)
PLACEBO_TIMES = [1, 1, 2, 2, 3, 4, 4, 5, 5, 8, 8, 8, 8, 11, 11, 12, 12, 15, 17, 22, 23]
PLACEBO_EVENTS = [True] * 21  # every placebo patient relapsed (no censoring)

MP6_RAW = [
    (6, True), (6, True), (6, True), (6, False), (7, True), (9, False), (10, True), (10, False),
    (11, False), (13, True), (16, True), (17, False), (19, False), (20, False), (22, True),
    (23, True), (25, False), (32, False), (32, False), (34, False), (35, False),
]
MP6_TIMES = [t for t, _ in MP6_RAW]
MP6_EVENTS = [e for _, e in MP6_RAW]


def main() -> None:
    print("=" * 90)
    print("FREIREICH log-rank (arm 1 = 6-MP treatment, arm 2 = placebo control)")
    print("=" * 90)
    lr = logrank_test(MP6_TIMES, MP6_EVENTS, PLACEBO_TIMES, PLACEBO_EVENTS)
    print(f"  O1 (6-MP observed events)   = {lr['o1']:.10f}  (expect 9)")
    print(f"  E1 (6-MP expected events)   = {lr['e1']:.10f}")
    print(f"  O2 (placebo observed)       = {lr['o2']:.10f}  (expect 21)")
    print(f"  E2 (placebo expected)       = {lr['e2']:.10f}")
    print(f"  V  (log-rank variance)      = {lr['var']:.10f}")
    print(f"  chi-square (1 df)           = {lr['chi2']:.10f}   (published ~= 16.79)")
    print(f"  p (erf normal self-check)   = {chi2_sf_df1(lr['chi2']):.3e}")
    try:
        from scipy.stats import chi2 as scipy_chi2  # type: ignore

        print(f"  p (scipy.stats.chi2.sf,1df) = {scipy_chi2.sf(lr['chi2'], 1):.6e}   (published ~= 4.2e-5)")
    except Exception as exc:  # pragma: no cover - oracle only
        print(f"  scipy unavailable: {exc}")

    print()
    print("FREIREICH Kaplan-Meier — 6-MP (treatment) arm, step points:")
    for p in km_estimate(MP6_TIMES, MP6_EVENTS):
        ci_lo = max(0.0, p["survival"] - 1.959963985 * p["se"]) if not math.isnan(p["se"]) else float("nan")
        ci_hi = min(1.0, p["survival"] + 1.959963985 * p["se"]) if not math.isnan(p["se"]) else float("nan")
        print(
            f"    t={p['time']:5.1f}  n={int(p['at_risk']):2d}  d={int(p['n_events'])}  "
            f"S={p['survival']:.6f}  SE={p['se']:.6f}  CI=[{ci_lo:.4f},{ci_hi:.4f}]"
        )
    print()
    print("FREIREICH Kaplan-Meier — placebo (control) arm, step points:")
    for p in km_estimate(PLACEBO_TIMES, PLACEBO_EVENTS):
        print(
            f"    t={p['time']:5.1f}  n={int(p['at_risk']):2d}  d={int(p['n_events'])}  "
            f"S={p['survival']:.6f}  SE={p['se']:.6f}"
        )

    print()
    print("=" * 90)
    print("SMALL hand-computable example (one censored obs per arm)")
    print("=" * 90)
    # Arm1 (treatment): (1,event),(3,censored),(5,event)   Arm2 (control): (2,event),(4,censored),(6,event)
    a1t, a1e = [1, 3, 5], [True, False, True]
    a2t, a2e = [2, 4, 6], [True, False, True]
    slr = logrank_test(a1t, a1e, a2t, a2e)
    print("  pooled event times: 1,2,5,6")
    print(f"  O1={slr['o1']:.4f}  E1={slr['e1']:.6f} (expect 1.4)  V={slr['var']:.6f} (expect 0.74)")
    print(f"  chi-square={slr['chi2']:.10f}  (expect 0.36/0.74 = 0.4864864865)")
    try:
        from scipy.stats import chi2 as scipy_chi2  # type: ignore

        print(f"  p (scipy) = {scipy_chi2.sf(slr['chi2'], 1):.10f}")
    except Exception:
        print(f"  p (erf)   = {chi2_sf_df1(slr['chi2']):.10f}")
    print("  KM arm1 (treatment):")
    for p in km_estimate(a1t, a1e):
        print(
            f"    t={p['time']:.1f}  n={int(p['at_risk'])}  d={int(p['n_events'])}  "
            f"S={p['survival']:.6f}  var={p['greenwood_var']:.6f}  SE={p['se']:.6f}"
        )

    print()
    print("=" * 90)
    print("DEGENERATE: both arms fully censored -> no events -> V = 0 (log-rank undefined)")
    print("=" * 90)
    dlr = logrank_test([1, 2], [False, False], [1, 2], [False, False])
    print(f"  V={dlr['var']}  chi2={dlr['chi2']} (nan expected -> service returns 400)")

    # --- lifelines cross-check (optional third oracle) ------------------------------------------
    print()
    print("=" * 90)
    print("lifelines cross-check (optional)")
    print("=" * 90)
    try:
        import sys

        sys.path.insert(
            0,
            r"C:/Users/uedom/AppData/Local/Temp/claude/D--/3be8f8d9-4015-4fd5-94a5-22aaac53101d/scratchpad/lifelines_lib",
        )
        from lifelines import KaplanMeierFitter  # type: ignore
        from lifelines.statistics import logrank_test as ll_logrank  # type: ignore

        res = ll_logrank(MP6_TIMES, PLACEBO_TIMES, event_observed_A=MP6_EVENTS, event_observed_B=PLACEBO_EVENTS)
        print(f"  lifelines chi2 = {res.test_statistic:.10f}   p = {res.p_value:.6e}")
        kmf = KaplanMeierFitter().fit(MP6_TIMES, MP6_EVENTS)
        print(f"  lifelines KM 6-MP S(6) = {float(kmf.survival_function_at_times(6).iloc[0]):.6f}")
        print(f"  lifelines KM 6-MP S(23) = {float(kmf.survival_function_at_times(23).iloc[0]):.6f}")
    except Exception as exc:  # pragma: no cover - oracle only
        print(f"  lifelines unavailable ({type(exc).__name__}); relying on published number + scipy.")


if __name__ == "__main__":
    main()
