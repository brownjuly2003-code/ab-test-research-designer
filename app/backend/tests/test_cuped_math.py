"""Tests for the multi-covariate CUPED math (``stats/cuped.py``).

Covers: the stdlib linear solver against an independent Cramer's-rule reference and against
singular / empty inputs; the coefficient vector satisfying the normal equations; the k=1 reduction
to the single-covariate E5 closed form; the full quadratic-form adjusted variance; and the key
property that adding a second informative covariate reduces variance strictly more than one alone.
"""

import math

import pytest

from app.backend.app.services.live_stats.cuped import _multi_moments, _within_arm_sscp
from app.backend.app.stats.cuped import (
    adjusted_variance,
    cuped_theta,
    dot,
    quadratic_form,
    solve_linear_system,
)


def _sample_moments(
    ys: list[float], xs: list[list[float]]
) -> tuple[float, list[list[float]], list[float]]:
    """Sample outcome variance, covariate covariance matrix and covariate/outcome covariance
    vector from raw per-user data (xs is a list of k covariate value-lists)."""
    n = len(ys)
    k = len(xs)
    mean_y = sum(ys) / n
    mean_x = [sum(xs[j]) / n for j in range(k)]
    var_y = sum((y - mean_y) ** 2 for y in ys) / (n - 1)
    sigma_xy = [
        sum((xs[j][i] - mean_x[j]) * (ys[i] - mean_y) for i in range(n)) / (n - 1)
        for j in range(k)
    ]
    sigma_xx = [
        [
            sum((xs[i][m] - mean_x[i]) * (xs[j][m] - mean_x[j]) for m in range(n)) / (n - 1)
            for j in range(k)
        ]
        for i in range(k)
    ]
    return var_y, sigma_xx, sigma_xy


# --- linear solver ---------------------------------------------------------------------------


def test_solve_linear_system_diagonal() -> None:
    assert solve_linear_system([[2.0, 0.0], [0.0, 4.0]], [2.0, 8.0]) == [1.0, 2.0]


def test_solve_linear_system_matches_cramer_2x2() -> None:
    # Independent reference: Cramer's rule for [[a,b],[b,c]] x = [d,e].
    for a, b, c, d, e in [(4.0, 2.0, 3.0, 1.0, 2.0), (5.0, -1.0, 2.0, 3.0, -4.0)]:
        det = a * c - b * b
        expected = [(d * c - b * e) / det, (a * e - d * b) / det]
        solved = solve_linear_system([[a, b], [b, c]], [d, e])
        assert solved is not None
        assert abs(solved[0] - expected[0]) < 1e-12
        assert abs(solved[1] - expected[1]) < 1e-12


def test_solve_linear_system_singular_returns_none() -> None:
    # Second row is twice the first -> singular.
    assert solve_linear_system([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]) is None


def test_solve_linear_system_zero_matrix_returns_none() -> None:
    assert solve_linear_system([[0.0, 0.0], [0.0, 0.0]], [1.0, 2.0]) is None


def test_solve_linear_system_empty() -> None:
    assert solve_linear_system([], []) == []


def test_dot_and_quadratic_form() -> None:
    assert dot([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == 32.0
    # v^T M v for M = [[2,1],[1,3]], v = [1,2] -> 2*1 + 1*2 + 1*2 + 3*4 = 18
    assert quadratic_form([[2.0, 1.0], [1.0, 3.0]], [1.0, 2.0]) == 18.0


# --- CUPED coefficients ----------------------------------------------------------------------


def test_cuped_theta_satisfies_normal_equations() -> None:
    sigma_xx = [[4.0, 2.0], [2.0, 3.0]]
    sigma_xy = [3.0, 2.0]
    theta = cuped_theta(sigma_xx, sigma_xy)
    assert theta is not None
    # Sigma_xx @ theta == Sigma_xy
    for i in range(2):
        assert abs(dot(sigma_xx[i], theta) - sigma_xy[i]) < 1e-12


def test_cuped_theta_single_covariate_equals_cov_over_var() -> None:
    # k = 1: theta = cov(X, Y) / var(X) — the E5 single-covariate coefficient.
    theta = cuped_theta([[4.0]], [3.0])
    assert theta == [0.75]


def test_cuped_theta_rank_deficient_preserves_fitted_direction() -> None:
    # Rank-1 Sxx with a consistent RHS: the normal equations have a line of solutions.
    # Require a finite solution that preserves the fitted direction, not a unique coefficient vector.
    sigma_xx = [[1.0, 2.0], [2.0, 4.0]]
    sigma_xy = [3.0, 6.0]
    theta = cuped_theta(sigma_xx, sigma_xy)
    assert theta is not None
    assert all(math.isfinite(component) for component in theta)
    # Single independent equation of Sxx @ theta = sigma_xy: theta0 + 2*theta1 = 3.
    assert theta[0] + 2.0 * theta[1] == pytest.approx(3.0)


def test_cuped_theta_handles_independent_covariates_with_disparate_scales() -> None:
    # Diagonal PSD with extreme scale separation. Global-max pivot tolerance currently
    # rejects the small pivot even though the system is independent and exactly solvable.
    sigma_xx = [[1e-16, 0.0], [0.0, 1e16]]
    expected = [2.0, 3.0]
    sigma_xy = [sigma_xx[0][0] * expected[0], sigma_xx[1][1] * expected[1]]
    theta = cuped_theta(sigma_xx, sigma_xy)
    assert theta is not None
    assert all(math.isfinite(component) for component in theta)
    assert theta[0] == pytest.approx(expected[0])
    assert theta[1] == pytest.approx(expected[1])


# --- adjusted variance -----------------------------------------------------------------------


def test_adjusted_variance_k1_matches_e5_closed_form() -> None:
    var_y, theta, cov_xy, var_x = 5.0, [0.75], [3.0], [[4.0]]
    expected = 5.0 - 2 * 0.75 * 3.0 + 0.75 * 0.75 * 4.0  # var_y - 2*theta*cov + theta^2*var_x
    assert abs(adjusted_variance(var_y, theta, cov_xy, var_x) - expected) < 1e-12


def test_adjusted_variance_at_pooled_optimum_equals_var_minus_linear_term() -> None:
    # At the least-squares optimum theta^T Sigma_xx theta == theta^T Sigma_xy, so the adjusted
    # variance collapses to var_y - theta^T Sigma_xy = var_y * (1 - R^2).
    sigma_xx = [[4.0, 2.0], [2.0, 3.0]]
    sigma_xy = [3.0, 2.0]
    var_y = 5.0
    theta = cuped_theta(sigma_xx, sigma_xy)
    assert theta is not None
    adjusted = adjusted_variance(var_y, theta, sigma_xy, sigma_xx)
    assert abs(adjusted - (var_y - dot(theta, sigma_xy))) < 1e-12
    assert 0.0 <= adjusted < var_y  # variance can only drop


def test_two_informative_covariates_reduce_variance_more_than_one() -> None:
    # Y is an exact linear function of X1 and X2, so the two-covariate adjustment removes nearly all
    # variance, strictly more than the single best covariate alone.
    x1 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    x2 = [2.0, 1.0, 5.0, 3.0, 6.0, 4.0]
    ys = [3.0 * a + 2.0 * b for a, b in zip(x1, x2)]

    var_y, sx_single, sxy_single = _sample_moments(ys, [x1])
    theta_single = cuped_theta(sx_single, sxy_single)
    assert theta_single is not None
    reduction_single = 1 - adjusted_variance(var_y, theta_single, sxy_single, sx_single) / var_y

    _, sx_multi, sxy_multi = _sample_moments(ys, [x1, x2])
    theta_multi = cuped_theta(sx_multi, sxy_multi)
    assert theta_multi is not None
    reduction_multi = 1 - adjusted_variance(var_y, theta_multi, sxy_multi, sx_multi) / var_y

    assert 0.0 < reduction_single < reduction_multi
    assert reduction_multi > 0.99  # exact linear fit -> near-total variance removal


def test_multi_moments_clamps_one_ulp_cancellation_to_nonnegative() -> None:
    # Large equal values: n*mean^2 cancels with sum_y2 / sum_xx, but one-ULP-low
    # second moments make the centered numerators slightly negative under float eval.
    n = 2
    mean = 1e16
    exact_second = n * mean * mean
    sum_y = n * mean
    sum_y2 = math.nextafter(exact_second, -math.inf)
    sum_x = [n * mean]
    # Physically neutral cross-moment (exact product of means) — avoid unrelated cov paths.
    sum_xy = [exact_second]
    sum_xx = [[math.nextafter(exact_second, -math.inf)]]

    moments = _multi_moments(n, sum_y, sum_y2, sum_x, sum_xy, sum_xx)
    assert moments is not None
    assert math.isfinite(moments["var_y"])
    assert math.isfinite(moments["sigma_xx"][0][0])
    assert moments["var_y"] == 0.0
    assert moments["sigma_xx"][0][0] == 0.0
    assert all(math.isfinite(value) for value in moments["sigma_xy"])
    assert all(
        math.isfinite(moments["sigma_xx"][i][j])
        for i in range(len(moments["sigma_xx"]))
        for j in range(len(moments["sigma_xx"]))
    )
    assert moments["sigma_xx"][0][0] == moments["sigma_xx"][0][0]  # 1x1 symmetry


def test_multi_moments_preserves_modest_spread_at_large_mean() -> None:
    # Legitimate modest within-arm spread must survive large means. At mean=1e7,
    # sum((y-mean)^2)=10 is exact float signal but << 1e-12 * |n*mean^2|, so a
    # raw-second-moment relative clamp incorrectly zeros var_y / Sxx / Syy.
    n = 5
    mean = 1e7
    offsets = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ys = [mean + d for d in offsets]
    xs = [mean + d for d in offsets]
    sum_y = float(sum(ys))
    sum_y2 = float(sum(y * y for y in ys))
    sum_x = [float(sum(xs))]
    sum_xy = [float(sum(x * y for x, y in zip(xs, ys, strict=True)))]
    sum_xx = [[float(sum(x * x for x in xs))]]

    moments = _multi_moments(n, sum_y, sum_y2, sum_x, sum_xy, sum_xx)
    assert moments is not None
    # Sample variance of offsets: 10 / 4 = 2.5.
    assert moments["var_y"] == pytest.approx(2.5)
    assert moments["sigma_xx"][0][0] == pytest.approx(2.5)
    assert moments["var_y"] > 0.0
    assert moments["sigma_xx"][0][0] > 0.0

    arm = {
        "n": n,
        "sum_y": sum_y,
        "sum_y2": sum_y2,
        "sum_x": sum_x,
        "sum_xy": sum_xy,
        "sum_xx": sum_xx,
    }
    within = _within_arm_sscp([arm], 1)
    assert within is not None
    sxx, _sxy, syy = within
    assert syy == pytest.approx(10.0)
    assert sxx[0][0] == pytest.approx(10.0)


def test_within_arm_sscp_one_ulp_negative_arm_does_not_wipe_other_arm() -> None:
    # Arm 0: pure one-ULP cancellation at huge mean (physically zero within-arm spread).
    # Arm 1: modest positive Syy/Sxx. Post-pool clamp of total would wipe arm 1.
    mean0 = 1e16
    n0 = 2
    exact0 = n0 * mean0 * mean0
    arm0 = {
        "n": n0,
        "sum_y": n0 * mean0,
        "sum_y2": math.nextafter(exact0, -math.inf),
        "sum_x": [n0 * mean0],
        "sum_xy": [exact0],
        "sum_xx": [[math.nextafter(exact0, -math.inf)]],
    }
    n1 = 5
    mean1 = 1e7
    offsets = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ys = [mean1 + d for d in offsets]
    xs = [mean1 + d for d in offsets]
    arm1 = {
        "n": n1,
        "sum_y": float(sum(ys)),
        "sum_y2": float(sum(y * y for y in ys)),
        "sum_x": [float(sum(xs))],
        "sum_xy": [float(sum(x * y for x, y in zip(xs, ys, strict=True)))],
        "sum_xx": [[float(sum(x * x for x in xs))]],
    }
    within = _within_arm_sscp([arm0, arm1], 1)
    assert within is not None
    sxx, sxy, syy = within
    assert syy == pytest.approx(10.0)
    assert sxx[0][0] == pytest.approx(10.0)
    assert sxy[0] == pytest.approx(10.0)  # signed cov preserved (=Syy for y=x offsets)


def test_within_arm_sscp_preserves_signed_sxy_and_off_diagonal() -> None:
    # Negative within-arm cov must not be zeroed; off-diagonal sign preserved.
    arm = {
        "n": 4,
        "sum_y": 10.0,  # means: y=2.5
        "sum_y2": 30.0,  # Syy = 30 - 4*2.5^2 = 5
        "sum_x": [0.0, 4.0],  # means: x0=0, x1=1
        "sum_xy": [-2.0, 12.0],  # Sxy0 = -2 - 0, Sxy1 = 12 - 4*1*2.5 = 2
        "sum_xx": [
            [2.0, -1.0],  # Sxx00=2, Sxx01=-1
            [-1.0, 6.0],  # Sxx11 = 6 - 4*1 = 2
        ],
    }
    within = _within_arm_sscp([arm], 2)
    assert within is not None
    sxx, sxy, syy = within
    assert syy == pytest.approx(5.0)
    assert sxy[0] == pytest.approx(-2.0)
    assert sxy[1] == pytest.approx(2.0)
    assert sxx[0][1] == pytest.approx(-1.0)
    assert sxx[1][0] == pytest.approx(-1.0)


def test_adjusted_variance_clamps_roundoff_below_zero() -> None:
    # Mathematically Var(Y_adj) = 0 when theta=1, var_y=1, sigma_xy=1, sigma_xx=1, but a
    # slightly inflated sigma_xy makes the quadratic form evaluate slightly negative.
    result = adjusted_variance(
        1.0,
        [1.0],
        [1.0000000000000007],
        [[1.0]],
    )
    assert math.isfinite(result)
    assert result == 0.0
