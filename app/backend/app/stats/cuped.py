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

where ``Sigma_xx`` / ``Sigma_xy`` are the Gram and cross moments supplied by the caller. The live
service passes pooled within-arm centered SSCP, so chance between-arm X imbalance does not enter
the slope. Adjusted means still center on grand-mean X. Because covariates are pre-treatment,
``E[Y_adj] = E[Y]`` in expectation, while

    Var(Y_adj) = Var(Y) - 2·theta^T Sigma_xy + theta^T Sigma_xx theta

(the general quadratic form; at the pooled optimum ``theta^T Sigma_xx theta = theta^T Sigma_xy`` so
it collapses to ``Var(Y)(1 - R^2)``, but per arm the pooled ``theta`` meets arm-specific moments, so
the full form is required). For ``k = 1`` every formula reduces to the single-covariate E5 CUPED.

The module is stdlib-only. Full-rank blocks use Gaussian elimination; rank-deficient or ill-scaled
PSD systems use correlation scaling and a rank-aware principal-subspace solve, with dropped
directions set to zero.
"""

import math
from collections.abc import Sequence

# A residual direction at or below this relative threshold is numerically dependent.
_SINGULAR_RELATIVE_TOLERANCE = 1e-12


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    """Inner product of two equal-length vectors."""
    return sum(a * b for a, b in zip(left, right, strict=True))


def quadratic_form(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> float:
    """``vector^T · matrix · vector`` for a square ``matrix``."""
    size = len(vector)
    return sum(
        vector[i] * matrix[i][j] * vector[j] for i in range(size) for j in range(size)
    )


def solve_linear_system(
    matrix: Sequence[Sequence[float]], vector: Sequence[float]
) -> list[float] | None:
    """Solve a full-rank ``matrix · x = vector`` via Gaussian elimination with partial pivoting.

    Returns ``None`` when this block is singular. CUPED covariance systems first use
    :func:`solve_psd_system` to drop dependent directions rather than failing the full system.
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


def _pivoted_cholesky_indices(corr: list[list[float]]) -> list[int]:
    """Select a numerically independent PSD principal subspace (pivoted Cholesky).

    Operates on a correlation-scale Gram matrix. Remaining residual diagonals at or
    below ``_SINGULAR_RELATIVE_TOLERANCE`` times the initial max diagonal are dropped.
    """
    dim = len(corr)
    if dim == 0:
        return []
    residual_diag = [corr[i][i] for i in range(dim)]
    max_diag = max(residual_diag)
    if max_diag <= 0.0:
        return []
    tolerance = _SINGULAR_RELATIVE_TOLERANCE * max_diag
    remaining = set(range(dim))
    selected: list[int] = []
    factors: list[list[float]] = []

    while remaining:
        pivot = max(remaining, key=lambda index: residual_diag[index])
        if residual_diag[pivot] <= tolerance:
            break
        inv_sqrt = 1.0 / math.sqrt(residual_diag[pivot])
        row = [0.0] * dim
        for index in remaining:
            cross = corr[pivot][index]
            for prev in factors:
                cross -= prev[pivot] * prev[index]
            row[index] = cross * inv_sqrt
        for index in remaining:
            if index == pivot:
                continue
            residual_diag[index] -= row[index] * row[index]
            if residual_diag[index] < 0.0:
                residual_diag[index] = 0.0
        residual_diag[pivot] = 0.0
        remaining.remove(pivot)
        selected.append(pivot)
        factors.append(row)

    return selected


def solve_psd_system(
    matrix: Sequence[Sequence[float]], vector: Sequence[float]
) -> tuple[list[float], int] | None:
    """Solve ``matrix · x = vector`` for symmetric PSD ``matrix`` on a stable principal subspace.

    Covariance normal equations are symmetric PSD, often rank-deficient (collinear covariates)
    or badly scaled (disparate variances). This routine:

    1. Validates square shape and finite entries, then symmetrizes.
    2. Keeps directions with a **strictly positive diagonal** (scale-local: ``1e-16`` is not
       discarded merely because another diagonal is ``1e16``).
    3. Rescales to correlation form ``S = D R D`` with ``D = sqrt(diag)`` and solves on ``R``.
    4. Rank-reveals an independent principal subset via pivoted Cholesky (relative tolerance),
       solves that block with :func:`solve_linear_system`, zeros dropped coefficients, maps
       back to the original scale, and returns the effective rank.

    Returns ``(solution, effective_rank)``, or ``None`` when no usable positive-diagonal
    direction exists.
    """
    size = len(vector)
    if size == 0:
        return [], 0
    if len(matrix) != size or any(len(row) != size for row in matrix):
        raise ValueError("matrix must be square and match the vector length")

    symmetric = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for i in range(size):
        rhs_i = float(vector[i])
        if not math.isfinite(rhs_i):
            raise ValueError("vector entries must be finite")
        rhs[i] = rhs_i
        for j in range(i, size):
            upper = float(matrix[i][j])
            lower = float(matrix[j][i])
            if not math.isfinite(upper) or not math.isfinite(lower):
                raise ValueError("matrix entries must be finite")
            value = 0.5 * (upper + lower)
            symmetric[i][j] = value
            symmetric[j][i] = value

    # Scale-local: keep every strictly positive diagonal, independent of other scales.
    active = [i for i in range(size) if symmetric[i][i] > 0.0]
    if not active:
        return None

    scales = [math.sqrt(symmetric[i][i]) for i in active]
    dim = len(active)
    # S = D R D  =>  R y = D^{-1} b  with  y = D x  =>  x = D^{-1} y.
    corr = [[0.0] * dim for _ in range(dim)]
    corr_rhs = [0.0] * dim
    for row, i in enumerate(active):
        corr_rhs[row] = rhs[i] / scales[row]
        for col, j in enumerate(active):
            corr[row][col] = symmetric[i][j] / (scales[row] * scales[col])

    selected = _pivoted_cholesky_indices(corr)
    if not selected:
        return None

    principal = [[corr[i][j] for j in selected] for i in selected]
    principal_rhs = [corr_rhs[i] for i in selected]
    reduced = solve_linear_system(principal, principal_rhs)
    if reduced is None:
        return None

    corr_solution = [0.0] * dim
    for position, index in enumerate(selected):
        corr_solution[index] = reduced[position]

    solution = [0.0] * size
    for local, global_index in enumerate(active):
        solution[global_index] = corr_solution[local] / scales[local]
    return solution, len(selected)


def cuped_theta(
    sigma_xx: Sequence[Sequence[float]], sigma_xy: Sequence[float]
) -> list[float] | None:
    """CUPED coefficient vector ``theta = Sigma_xx^{-1} · Sigma_xy`` (the normal equations).

    Returns ``None`` when ``Sigma_xx`` has no usable positive-variance direction, signalling
    the caller to use the zero vector (the adjustment collapses to the unadjusted estimate).
    Rank-deficient but consistent systems return a finite solution on the identifiable subspace
    (dropped directions are zero); badly scaled independent diagonals keep each coefficient.
    """
    solved = solve_psd_system(sigma_xx, sigma_xy)
    if solved is None:
        return None
    theta, _rank = solved
    return theta


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
    result = var_y - 2.0 * dot(theta, sigma_xy) + quadratic_form(sigma_xx, theta)
    if not math.isfinite(result):
        return result
    if result < 0.0:
        return 0.0
    return result
