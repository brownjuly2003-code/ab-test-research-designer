"""Tests for the ratio-metric delta-method estimator (``stats/ratio.py``).

Covers: the closed-form against a hand computation, the property that a denominator of 1 collapses
to the mean of the numerator (so a ratio with den == 1 equals a continuous mean), the delta-method
variance against an empirical bootstrap (the key correctness proof), the within-user correlation
the naive estimator drops, and the degenerate guards.
"""

import math
import random

import pytest

from app.backend.app.stats.ratio import (
    compare_ratios,
    ratio_estimate,
    ratio_sufficient_moments,
)


def _sufficient(xs: list[float], ys: list[float]) -> dict[str, float]:
    """Per-arm sufficient statistics from raw per-user (denominator, numerator) lists."""
    assert len(xs) == len(ys)
    return {
        "n": len(xs),
        "sum_x": sum(xs),
        "sum_x2": sum(x * x for x in xs),
        "sum_y": sum(ys),
        "sum_y2": sum(y * y for y in ys),
        "sum_xy": sum(x * y for x, y in zip(xs, ys)),
    }


# --- closed form vs hand computation -------------------------------------------------------


def test_ratio_estimate_matches_hand_computation() -> None:
    # Users (denominator x, numerator y): (10,1),(20,4),(30,9),(40,16).
    # mean_x=25, mean_y=7.5, var_x=500/3, var_y=43, cov_xy=250/3, R=0.3.
    # linearized = 43 - 2*0.3*(250/3) + 0.09*(500/3) = 43 - 50 + 15 = 8.
    # Var(R) = 8 / (4 * 25^2) = 8 / 2500 = 0.0032.
    stats = _sufficient([10, 20, 30, 40], [1, 4, 9, 16])
    estimate = ratio_estimate(stats)
    assert estimate is not None
    assert estimate["ratio"] == pytest.approx(0.3)
    assert estimate["variance"] == pytest.approx(0.0032)
    assert estimate["mean_x"] == pytest.approx(25.0)
    assert estimate["mean_y"] == pytest.approx(7.5)


def test_sufficient_moments_below_two_users_is_none() -> None:
    assert ratio_sufficient_moments(1, 5.0, 25.0, 2.0, 4.0, 10.0) is None


# --- property: denominator == 1 collapses to a continuous mean -----------------------------


def test_ratio_with_unit_denominator_equals_mean_of_numerator() -> None:
    # With every x_i == 1, R = mean(Y) and Var(R) = var(Y)/n — i.e. the variance of a sample mean,
    # exactly the continuous estimator. A ratio metric with a unit denominator IS a mean metric.
    ys = [2.0, 4.0, 6.0, 8.0]
    n = len(ys)
    stats = _sufficient([1.0] * n, ys)
    estimate = ratio_estimate(stats)
    assert estimate is not None

    mean_y = sum(ys) / n
    var_y = sum((y - mean_y) ** 2 for y in ys) / (n - 1)
    assert estimate["ratio"] == pytest.approx(mean_y)
    assert estimate["variance"] == pytest.approx(var_y / n)


# --- the key correctness proof: delta variance vs an empirical bootstrap -------------------


def test_delta_variance_matches_bootstrap() -> None:
    """The delta-method variance of R̂ must match the empirical sampling variance of R̂ obtained by
    bootstrapping users. Numerator (clicks) is correlated with denominator (impressions), which is
    exactly the regime where the naive variance is wrong and the delta method is needed."""
    rng = random.Random(20260625)
    n_users = 4000
    click_prob = 0.2
    xs: list[float] = []
    ys: list[float] = []
    for _ in range(n_users):
        impressions = rng.randint(40, 160)
        clicks = sum(1 for _ in range(impressions) if rng.random() < click_prob)
        xs.append(float(impressions))
        ys.append(float(clicks))

    estimate = ratio_estimate(_sufficient(xs, ys))
    assert estimate is not None
    delta_variance = estimate["variance"]

    # Bootstrap: resample users with replacement, recompute R̂* = sum(y*)/sum(x*), take the variance.
    bootstrap_ratios: list[float] = []
    for _ in range(400):
        sum_x = 0.0
        sum_y = 0.0
        for _ in range(n_users):
            j = rng.randrange(n_users)
            sum_x += xs[j]
            sum_y += ys[j]
        bootstrap_ratios.append(sum_y / sum_x)
    mean_boot = sum(bootstrap_ratios) / len(bootstrap_ratios)
    bootstrap_variance = sum((r - mean_boot) ** 2 for r in bootstrap_ratios) / (
        len(bootstrap_ratios) - 1
    )

    # Both estimate the sampling variance of the same R̂; agree to within bootstrap noise.
    assert delta_variance == pytest.approx(bootstrap_variance, rel=0.15)


def test_delta_variance_differs_from_naive_when_correlated() -> None:
    """When numerator and denominator are positively correlated, the delta variance is strictly
    smaller than the naive "treat the ratio as one number per user" variance that ignores the
    covariance — demonstrating the correction the −2R·cov term provides."""
    rng = random.Random(7)
    xs: list[float] = []
    ys: list[float] = []
    for _ in range(2000):
        impressions = rng.randint(50, 150)
        clicks = sum(1 for _ in range(impressions) if rng.random() < 0.3)
        xs.append(float(impressions))
        ys.append(float(clicks))

    estimate = ratio_estimate(_sufficient(xs, ys))
    assert estimate is not None
    delta_variance = estimate["variance"]

    # Naive per-user ratio r_i = y_i / x_i, variance of its mean = var(r)/n. This treats each user's
    # ratio as one observation and ignores that the denominator is itself random/correlated.
    per_user = [y / x for x, y in zip(xs, ys)]
    n = len(per_user)
    mean_r = sum(per_user) / n
    naive_variance = (sum((r - mean_r) ** 2 for r in per_user) / (n - 1)) / n
    assert delta_variance < naive_variance


# --- two-sample comparison -----------------------------------------------------------------


def test_ratio_point_estimate_is_sum_ratio() -> None:
    # R̂ = sum(Y)/sum(X): 500 users each (x=100, y=20) -> 0.20; each (x=100, y=30) -> 0.30.
    # Identical users carry zero sampling variance (the comparison itself is degenerate here — see
    # test_compare_ratios_degenerate_arm_is_none — but the point estimate is still well defined).
    control = ratio_estimate(_sufficient([100.0] * 500, [20.0] * 500))
    treatment = ratio_estimate(_sufficient([100.0] * 500, [30.0] * 500))
    assert control is not None and treatment is not None
    assert control["ratio"] == pytest.approx(0.20)
    assert treatment["ratio"] == pytest.approx(0.30)
    assert control["variance"] == 0.0


def test_compare_ratios_significance_and_ci() -> None:
    rng = random.Random(99)

    def arm(prob: float) -> dict[str, float]:
        xs: list[float] = []
        ys: list[float] = []
        for _ in range(3000):
            impressions = rng.randint(80, 120)
            clicks = sum(1 for _ in range(impressions) if rng.random() < prob)
            xs.append(float(impressions))
            ys.append(float(clicks))
        return _sufficient(xs, ys)

    control = arm(0.20)
    treatment = arm(0.24)
    result = compare_ratios(control, treatment, alpha=0.05)
    assert result is not None
    assert result["effect"] > 0
    assert result["is_significant"] is True
    # A significant positive effect -> confidence interval excludes 0 and lies above it.
    assert result["ci_lower"] > 0
    assert result["ci_lower"] < result["effect"] < result["ci_upper"]
    # z and p are consistent: |z| above the 1.96 two-sided 5% critical value.
    assert abs(result["test_statistic"]) > 1.96
    assert result["p_value"] < 0.05


def test_compare_ratios_null_effect_not_significant() -> None:
    rng = random.Random(2024)

    def arm() -> dict[str, float]:
        xs: list[float] = []
        ys: list[float] = []
        for _ in range(2500):
            impressions = rng.randint(80, 120)
            clicks = sum(1 for _ in range(impressions) if rng.random() < 0.25)
            xs.append(float(impressions))
            ys.append(float(clicks))
        return _sufficient(xs, ys)

    result = compare_ratios(arm(), arm(), alpha=0.05)
    assert result is not None
    assert result["is_significant"] is False
    assert result["ci_lower"] < 0 < result["ci_upper"]


# --- degenerate guards ---------------------------------------------------------------------


def test_ratio_estimate_zero_denominator_is_none() -> None:
    # All denominators zero -> mean_x == 0 -> ratio undefined.
    stats = _sufficient([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])
    assert ratio_estimate(stats) is None


def test_ratio_estimate_single_user_is_none() -> None:
    stats = _sufficient([10.0], [3.0])
    assert ratio_estimate(stats) is None


def test_compare_ratios_degenerate_arm_is_none() -> None:
    # Control has zero variance in both x and y (identical users) AND treatment too -> pooled
    # variance 0 -> None. Identical constant arms carry no sampling variance.
    control = _sufficient([100.0] * 10, [20.0] * 10)
    treatment = _sufficient([100.0] * 10, [25.0] * 10)
    assert compare_ratios(control, treatment, alpha=0.05) is None


def test_compare_ratios_invalid_alpha_raises() -> None:
    control = _sufficient([10.0, 20.0], [2.0, 5.0])
    treatment = _sufficient([10.0, 20.0], [3.0, 6.0])
    with pytest.raises(ValueError):
        compare_ratios(control, treatment, alpha=0.0)
    with pytest.raises(ValueError):
        compare_ratios(control, treatment, alpha=1.0)


def test_ratio_variance_is_non_negative_and_finite() -> None:
    rng = random.Random(5)
    xs = [float(rng.randint(1, 100)) for _ in range(200)]
    ys = [float(rng.randint(0, 50)) for _ in range(200)]
    estimate = ratio_estimate(_sufficient(xs, ys))
    assert estimate is not None
    assert estimate["variance"] >= 0
    assert math.isfinite(estimate["variance"])
