"""
Multi-covariate CUPED (variance reduction with several pre-experiment covariates).

CUPED (Deng, Xu, Kohavi & Walker, "Improving the Sensitivity of Online Controlled Experiments by
Utilizing Pre-Experiment Data", WSDM 2013) reduces the variance of a treatment-effect estimate by
subtracting a pre-experiment covariate ``X`` that is correlated with the outcome ``Y`` but, being
measured *before* assignment, is independent of the treatment. The single-covariate adjustment is
``Y_adj = Y - theta * (X - mean X)`` with ``theta = cov(X, Y) / var(X)``.

This module generalizes that to a **covariate vector** ``X = (X_1, ..., X_k)`` — the regression
(ANCOVA) form of CUPED that Deng et al. (2013, §3.2) note as the multi-covariate extension, and the
stdlib analogue of DoorDash's CUPAC (where the covariate is an ML prediction). The optimal
coefficient vector solves the **normal equations** of the least-squares regression of ``Y`` on the
centered covariates (verified against ordinary-least-squares theory at implementation time, not from
memory):

    Sigma_xx · theta = Sigma_xy            (theta = Sigma_xx^{-1} · Sigma_xy)
    Y_adj = Y - theta^T (X - mean X)

where ``Sigma_xx`` is the k×k covariate covariance matrix and ``Sigma_xy`` the length-k vector of
covariances between each covariate and ``Y``. Because the covariates are pre-treatment,
``E[Y_adj] = E[Y]`` so the effect estimate is unbiased, while

    Var(Y_adj) = Var(Y) - 2·theta^T Sigma_xy + theta^T Sigma_xx theta

(the general quadratic form; at the pooled optimum ``theta^T Sigma_xx theta = theta^T Sigma_xy`` so
it collapses to ``Var(Y)(1 - R^2)``, but per arm the pooled ``theta`` meets arm-specific moments, so
the full form is required). For ``k = 1`` every formula reduces to the single-covariate E5 CUPED.

The module is stdlib-only and holds pure functions; assembling sufficient statistics and the
response shape lives in the service layer. The linear system is small (k is a handful of
covariates), so it is solved with Gaussian elimination + partial pivoting rather than pulling in
numpy — keeping the stats package dependency-free and self-contained.
"""

from collections.abc import Sequence

# A pivot at or below this fraction of the matrix's largest magnitude is treated as zero: the
# covariates are (numerically) collinear and the normal equations have no stable unique solution.
_SINGULAR_RELATIVE_TOLERANCE = 1e-12


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    """Inner product of two equal-length vectors."""
    return sum(a * b for a, b in zip(left, right))


def quadratic_form(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> float:
    """``vector^T · matrix · vector`` for a square ``matrix``."""
    size = len(vector)
    return sum(
        vector[i] * matrix[i][j] * vector[j] for i in range(size) for j in range(size)
    )


def solve_linear_system(
    matrix: Sequence[Sequence[float]], vector: Sequence[float]
) -> list[float] | None:
    """Solve ``matrix · x = vector`` via Gaussian elimination with partial pivoting.

    Returns the solution vector, or ``None`` when the matrix is singular (e.g. collinear
    covariates) — the caller then falls back to the unadjusted estimate. The singularity test is
    relative to the largest matrix entry so it is scale-invariant.
    """
    size = len(vector)
    if size == 0:
        return []
    if len(matrix) != size or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be square and match the vector length")

    augmented = [[float(matrix[i][j]) for j in range(size)] + [float(vector[i])] for i in range(size)]
    max_abs = max((abs(augmented[i][j]) for i in range(size) for j in range(size)), default=0.0)
    if max_abs == 0.0:
        return None
    tolerance = _SINGULAR_RELATIVE_TOLERANCE * max_abs

    # Forward elimination with partial pivoting -> upper-triangular form.
    for column in range(size):
        pivot_row = column
        best_magnitude = abs(augmented[column][column])
        for row in range(column + 1, size):
            magnitude = abs(augmented[row][column])
            if magnitude > best_magnitude:
                best_magnitude = magnitude
                pivot_row = row
        if best_magnitude <= tolerance:
            return None
        augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        for row in range(column + 1, size):
            factor = augmented[row][column] / pivot
            if factor == 0.0:
                continue
            for col in range(column, size + 1):
                augmented[row][col] -= factor * augmented[column][col]

    # Back substitution.
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        accumulated = augmented[row][size]
        for col in range(row + 1, size):
            accumulated -= augmented[row][col] * solution[col]
        solution[row] = accumulated / augmented[row][row]
    return solution


def cuped_theta(
    sigma_xx: Sequence[Sequence[float]], sigma_xy: Sequence[float]
) -> list[float] | None:
    """CUPED coefficient vector ``theta = Sigma_xx^{-1} · Sigma_xy`` (the normal equations).

    Returns ``None`` when ``Sigma_xx`` is singular (collinear / zero-variance covariates), signalling
    the caller to use the zero vector (the adjustment collapses to the unadjusted estimate).
    """
    return solve_linear_system(sigma_xx, sigma_xy)


def adjusted_variance(
    var_y: float,
    theta: Sequence[float],
    sigma_xy: Sequence[float],
    sigma_xx: Sequence[Sequence[float]],
) -> float:
    """``Var(Y_adj) = Var(Y) - 2·theta^T Sigma_xy + theta^T Sigma_xx theta``.

    The full quadratic form: per arm the pooled ``theta`` is applied to that arm's own covariance
    moments, so the convenient ``Var(Y) - theta^T Sigma_xy`` simplification (valid only at the
    pooled optimum) does not hold.
    """
    return var_y - 2.0 * dot(theta, sigma_xy) + quadratic_form(sigma_xx, theta)
