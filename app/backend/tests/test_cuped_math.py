"""Tests for the multi-covariate CUPED math (``stats/cuped.py``).

Covers: the stdlib linear solver against an independent Cramer's-rule reference and against
singular / empty inputs; the coefficient vector satisfying the normal equations; the k=1 reduction
to the single-covariate E5 closed form; the full quadratic-form adjusted variance; and the key
property that adding a second informative covariate reduces variance strictly more than one alone.
"""

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


def test_cuped_theta_collinear_covariates_returns_none() -> None:
    # visits == 2 * spend exactly -> the covariance matrix is singular.
    var_y, sigma_xx, sigma_xy = _sample_moments(
        [5.0, 9.0, 14.0, 20.0],
        [[1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0]],
    )
    assert cuped_theta(sigma_xx, sigma_xy) is None


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
