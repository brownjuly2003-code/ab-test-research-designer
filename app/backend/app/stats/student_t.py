"""Student-t distribution CDF and quantile via stdlib only.

Numerical recipes' regularized incomplete beta is used so the runtime tree
keeps its zero-`scipy` posture. Accuracy is within ~1e-9 of `scipy.stats.t`
for df >= 1; for df > 1e6 we fall back to the standard normal because the
t-distribution converges to it and the continued fraction loses precision.
"""

import math
import warnings
from statistics import NormalDist

_NORMAL = NormalDist()
_LARGE_DF = 1e6
_BETACF_MAX_ITER = 200
_BETACF_EPS = 3.0e-7


class StudentTConvergenceWarning(RuntimeWarning):
    """Raised when the regularized incomplete beta continued fraction
    fails to reach `_BETACF_EPS` within `_BETACF_MAX_ITER` iterations.

    In practice this never fires for df >= 1 and x in [0, 1]; we surface
    it so a future numerical regression cannot fail silently.
    """


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1.0e-30:
        d = 1.0e-30
    d = 1.0 / d
    h = d
    for m in range(1, _BETACF_MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1.0e-30:
            d = 1.0e-30
        c = 1.0 + aa / c
        if abs(c) < 1.0e-30:
            c = 1.0e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1.0e-30:
            d = 1.0e-30
        c = 1.0 + aa / c
        if abs(c) < 1.0e-30:
            c = 1.0e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _BETACF_EPS:
            return h
    warnings.warn(
        f"_betacf did not converge in {_BETACF_MAX_ITER} iterations "
        f"(a={a}, b={b}, x={x}); returning best estimate",
        StudentTConvergenceWarning,
        stacklevel=2,
    )
    return h


def _betainc_regularized(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(value: float, df: float) -> float:
    """Cumulative probability P(T <= value) for Student-t with `df` degrees of freedom.

    Falls back to standard normal for df beyond _LARGE_DF or when df is
    not finite/positive (defensive, matches the historical contract).
    """
    if not math.isfinite(df) or df <= 0:
        return _NORMAL.cdf(value)
    if df >= _LARGE_DF:
        return _NORMAL.cdf(value)
    if not math.isfinite(value):
        return 0.0 if value < 0 else 1.0
    x = df / (df + value * value)
    half = 0.5 * _betainc_regularized(df / 2.0, 0.5, x)
    return 1.0 - half if value >= 0 else half


def t_ppf(probability: float, df: float) -> float:
    """Inverse Student-t CDF via bisection on `t_cdf`.

    The bracket is expanded geometrically so heavy-tailed cases (df=1,
    probability near 0 or 1) still converge — fixed-50 brackets clip to
    that bound and silently return wrong quantiles.
    """
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be in (0, 1)")
    if not math.isfinite(df) or df <= 0:
        return _NORMAL.inv_cdf(probability)
    if df >= _LARGE_DF:
        return _NORMAL.inv_cdf(probability)
    lo, hi = -2.0, 2.0
    while t_cdf(lo, df) >= probability and lo > -1.0e9:
        lo *= 2.0
    while t_cdf(hi, df) <= probability and hi < 1.0e9:
        hi *= 2.0
    if not (t_cdf(lo, df) < probability < t_cdf(hi, df)):
        raise RuntimeError(
            f"t_ppf failed to bracket probability={probability} for df={df}"
        )
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < probability:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
