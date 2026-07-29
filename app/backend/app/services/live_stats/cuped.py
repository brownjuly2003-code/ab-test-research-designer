"""CUPED variance-reduction block over ingested pre-period covariates.

Common theta comes from pooled within-arm centered SSCP rather than global raw covariance.
Adjusted means use grand-mean X, while inference uses common-slope ANCOVA with pooled SSE,
effective-rank degrees of freedom, and the covariate-imbalance term.
"""
from __future__ import annotations

import math
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.services.results.continuous import _continuous_t_response
from app.backend.app.stats import cuped


def _stable_centered_difference(raw: float, correction: float) -> float:
    """Centered product residual ``raw - correction``.

    Does not relative-zero small positive residuals: legitimate within-arm signal at large
    means must survive. Callers clamp one-ULP-negative variance/diagonal/Syy to 0; signed
    covariances are returned as-is (including small negatives).
    """
    return float(raw) - float(correction)


def _arm_stable_centered(
    arm: dict[str, Any],
) -> tuple[float, list[float], list[list[float]]] | None:
    """Return repository two-pass centered SSCP when present; else ``None`` (raw fallback)."""
    if (
        "centered_syy" not in arm
        or "centered_sxy" not in arm
        or "centered_sxx" not in arm
    ):
        return None
    return arm["centered_syy"], arm["centered_sxy"], arm["centered_sxx"]


def _multi_moments(
    n: int,
    sum_y: float,
    sum_y2: float,
    sum_x: list[float],
    sum_xy: list[float],
    sum_xx: list[list[float]],
    *,
    centered_syy: float | None = None,
    centered_sxy: list[float] | None = None,
    centered_sxx: list[list[float]] | None = None,
) -> dict[str, Any] | None:
    """Means, outcome variance, the covariate covariance matrix ``Sigma_xx`` and the
    covariate/outcome covariance vector ``Sigma_xy`` from pooled sufficient statistics, or
    ``None`` when there are fewer than 2 observations (a sample variance is undefined)."""
    if n < 2:
        return None
    k = len(sum_x)
    mean_y = sum_y / n
    mean_x = [value / n for value in sum_x]
    denom = n - 1
    stable: tuple[float, list[float], list[list[float]]] | None = None
    if centered_syy is not None and centered_sxy is not None and centered_sxx is not None:
        stable = centered_syy, centered_sxy, centered_sxx
    if stable is not None:
        var_y = float(stable[0]) / denom
    else:
        var_y = _stable_centered_difference(sum_y2, n * mean_y * mean_y) / denom
    if not math.isfinite(var_y) or var_y < 0.0:
        var_y = 0.0
    sigma_xy: list[float] = []
    for j in range(k):
        if stable is not None:
            cov = float(stable[1][j]) / denom
        else:
            cov = _stable_centered_difference(sum_xy[j], n * mean_x[j] * mean_y) / denom
        sigma_xy.append(0.0 if not math.isfinite(cov) else cov)
    sigma_xx = [[0.0] * k for _ in range(k)]
    for i in range(k):
        if stable is not None:
            diag = float(stable[2][i][i]) / denom
        else:
            diag = _stable_centered_difference(sum_xx[i][i], n * mean_x[i] * mean_x[i]) / denom
        if not math.isfinite(diag) or diag < 0.0:
            diag = 0.0
        sigma_xx[i][i] = diag
        for j in range(i + 1, k):
            if stable is not None:
                cov_ij = float(stable[2][i][j])
                cov_ji = float(stable[2][j][i])
                if math.isfinite(cov_ij) and math.isfinite(cov_ji):
                    cov = 0.5 * (cov_ij + cov_ji) / denom
                elif math.isfinite(cov_ij):
                    cov = cov_ij / denom
                elif math.isfinite(cov_ji):
                    cov = cov_ji / denom
                else:
                    cov = 0.0
            else:
                # Prefer the (i,j) sufficient-stat entry; fall back to (j,i) if needed.
                raw_ij = sum_xx[i][j] if math.isfinite(float(sum_xx[i][j])) else sum_xx[j][i]
                cov = _stable_centered_difference(raw_ij, n * mean_x[i] * mean_x[j]) / denom
                if not math.isfinite(cov):
                    alt = _stable_centered_difference(
                        sum_xx[j][i], n * mean_x[j] * mean_x[i]
                    ) / denom
                    cov = alt if math.isfinite(alt) else 0.0
                # Symmetrize from both triangular entries when both finite.
                cov_ji = _stable_centered_difference(
                    sum_xx[j][i], n * mean_x[j] * mean_x[i]
                ) / denom
                if math.isfinite(cov_ji):
                    cov = 0.5 * (cov + cov_ji)
            sigma_xx[i][j] = cov
            sigma_xx[j][i] = cov
    return {
        "n": n,
        "mean_y": mean_y,
        "mean_x": mean_x,
        "var_y": var_y,
        "sigma_xy": sigma_xy,
        "sigma_xx": sigma_xx,
    }


def _pool_sufficient(arms: list[dict[str, Any]], k: int) -> dict[str, Any]:
    """Sum raw totals for grand-mean X and diagnostics.

    Slope ``theta`` is not fitted from these raw pooled moments; see ``_within_arm_sscp``.
    When every arm carries repository ``centered_*`` fields, also form grand-pooled centered
    SSCP via the parallel-axis theorem (stable at large means; preserves between-arm gaps).
    """
    total_n = 0
    sum_y = 0.0
    sum_y2 = 0.0
    sum_x = [0.0] * k
    sum_xy = [0.0] * k
    sum_xx = [[0.0] * k for _ in range(k)]
    for arm in arms:
        total_n += int(arm["n"])
        sum_y += float(arm["sum_y"])
        sum_y2 += float(arm["sum_y2"])
        for i in range(k):
            sum_x[i] += float(arm["sum_x"][i])
            sum_xy[i] += float(arm["sum_xy"][i])
            for j in range(k):
                sum_xx[i][j] += float(arm["sum_xx"][i][j])
    result: dict[str, Any] = {
        "n": total_n,
        "sum_y": sum_y,
        "sum_y2": sum_y2,
        "sum_x": sum_x,
        "sum_xy": sum_xy,
        "sum_xx": sum_xx,
    }
    if arms and all(_arm_stable_centered(arm) is not None for arm in arms):
        if total_n <= 0:
            result["centered_syy"] = 0.0
            result["centered_sxy"] = [0.0] * k
            result["centered_sxx"] = [[0.0] * k for _ in range(k)]
        else:
            grand_mean_y = sum_y / total_n
            grand_mean_x = [sum_x[j] / total_n for j in range(k)]
            c_syy = 0.0
            c_sxy = [0.0] * k
            c_sxx = [[0.0] * k for _ in range(k)]
            for arm in arms:
                n_a = int(arm["n"])
                if n_a <= 0:
                    continue
                mean_y_a = float(arm["sum_y"]) / n_a
                mean_x_a = [float(arm["sum_x"][j]) / n_a for j in range(k)]
                dy = mean_y_a - grand_mean_y
                dx = [mean_x_a[j] - grand_mean_x[j] for j in range(k)]
                c_syy += float(arm["centered_syy"]) + n_a * dy * dy
                for i in range(k):
                    c_sxy[i] += float(arm["centered_sxy"][i]) + n_a * dx[i] * dy
                    for j in range(k):
                        c_sxx[i][j] += (
                            float(arm["centered_sxx"][i][j]) + n_a * dx[i] * dx[j]
                        )
            result["centered_syy"] = c_syy
            result["centered_sxy"] = c_sxy
            result["centered_sxx"] = c_sxx
    return result


def _within_arm_sscp(
    arms: list[dict[str, Any]], k: int
) -> tuple[list[list[float]], list[float], float] | None:
    """Common-slope SSCP from within-arm centered moments (arm fixed effects).

    Excludes between-arm mean gaps so chance X imbalance cannot leak into ``theta``.
    For each arm with ``n >= 2``:
        prefer repository ``centered_sxx/sxy/syy`` when present; else
        Sxx += sum_xx_a - n_a * mean_x_a * mean_x_a^T (raw fallback)
    Returns ``None`` when no arm contributes usable within-arm degrees of freedom.
    The common df divisor cancels in ``Sxx * theta = Sxy``, so raw SSCP is enough.
    ``Syy`` supports residual SSE = Syy - theta^T Sxy for common-slope ANCOVA inference.
    """
    sxx = [[0.0] * k for _ in range(k)]
    sxy = [0.0] * k
    syy = 0.0
    usable = False
    for arm in arms:
        n = int(arm["n"])
        if n < 2:
            continue
        usable = True
        stable = _arm_stable_centered(arm)
        if stable is not None:
            arm_syy = float(stable[0])
            arm_sxy_vec = [float(stable[1][j]) for j in range(k)]
            arm_sxx_mat = [
                [float(stable[2][i][j]) for j in range(k)] for i in range(k)
            ]
        else:
            mean_x = [float(arm["sum_x"][j]) / n for j in range(k)]
            mean_y = float(arm["sum_y"]) / n
            arm_syy = _stable_centered_difference(float(arm["sum_y2"]), n * mean_y * mean_y)
            arm_sxy_vec = [
                _stable_centered_difference(
                    float(arm["sum_xy"][i]), n * mean_x[i] * mean_y
                )
                for i in range(k)
            ]
            arm_sxx_mat = [
                [
                    _stable_centered_difference(
                        float(arm["sum_xx"][i][j]), n * mean_x[i] * mean_x[j]
                    )
                    for j in range(k)
                ]
                for i in range(k)
            ]
        # Per-arm: one-ULP-negative residual is zero, not a debt against other arms.
        if math.isfinite(arm_syy) and arm_syy > 0.0:
            syy += arm_syy
        for i in range(k):
            arm_sxy = arm_sxy_vec[i]
            if math.isfinite(arm_sxy):
                sxy[i] += arm_sxy  # signed (including small negatives)
            for j in range(k):
                arm_sxx = arm_sxx_mat[i][j]
                if not math.isfinite(arm_sxx):
                    continue
                if i == j:
                    if arm_sxx > 0.0:
                        sxx[i][j] += arm_sxx
                else:
                    sxx[i][j] += arm_sxx  # signed off-diagonal
    if not usable:
        return None
    if not math.isfinite(syy) or syy < 0.0:
        syy = 0.0
    for i in range(k):
        if not math.isfinite(sxy[i]):
            sxy[i] = 0.0
        diag = sxx[i][i]
        if not math.isfinite(diag) or diag < 0.0:
            sxx[i][i] = 0.0
        for j in range(i + 1, k):
            a, b = sxx[i][j], sxx[j][i]
            if math.isfinite(a) and math.isfinite(b):
                mid = 0.5 * (a + b)
            else:
                mid = a if math.isfinite(a) else (b if math.isfinite(b) else 0.0)
            sxx[i][j] = mid
            sxx[j][i] = mid
    return sxx, sxy, syy


def _cuped_arm_stat(
    arm: dict[str, Any] | None,
    index: int,
    theta: list[float],
    global_mean_x: list[float],
    exposed_users: int,
) -> dict[str, Any]:
    n = int(arm["n"]) if arm else 0
    coverage = round(n / exposed_users, 4) if exposed_users > 0 else None
    if n == 0 or arm is None:
        return {
            "variation_index": index,
            "covariate_users": 0,
            "exposed_users": exposed_users,
            "coverage": coverage,
            "unadjusted_mean": None,
            "adjusted_mean": None,
            "adjusted_std": None,
            "_mean_x": None,
            "_adjusted_mean": None,
            "_adjusted_std": None,
            "_var_y": None,
            "_adjusted_var": None,
        }
    k = len(theta)
    mean_x = [arm["sum_x"][j] / n for j in range(k)]
    mean_y = arm["sum_y"] / n
    adjusted_mean = mean_y - cuped.dot(theta, [mean_x[j] - global_mean_x[j] for j in range(k)])
    adjusted_std: float | None = None
    var_y: float | None = None
    adjusted_var: float | None = None
    stable = _arm_stable_centered(arm)
    arm_moments = _multi_moments(
        n,
        arm["sum_y"],
        arm["sum_y2"],
        arm["sum_x"],
        arm["sum_xy"],
        arm["sum_xx"],
        centered_syy=float(stable[0]) if stable is not None else None,
        centered_sxy=list(stable[1]) if stable is not None else None,
        centered_sxx=[list(row) for row in stable[2]] if stable is not None else None,
    )
    if arm_moments is not None:
        var_y = float(arm_moments["var_y"])
        adjusted_var = float(
            cuped.adjusted_variance(
                arm_moments["var_y"],
                theta,
                arm_moments["sigma_xy"],
                arm_moments["sigma_xx"],
            )
        )
        adjusted_std = math.sqrt(adjusted_var) if adjusted_var > 0 else 0.0
    return {
        "variation_index": index,
        "covariate_users": n,
        "exposed_users": exposed_users,
        "coverage": coverage,
        "unadjusted_mean": round(mean_y, 6),
        "adjusted_mean": round(adjusted_mean, 6),
        "adjusted_std": round(adjusted_std, 6) if adjusted_std is not None else None,
        # Full-precision internals for ANCOVA inference; stripped before public response.
        "_mean_x": mean_x,
        "_adjusted_mean": adjusted_mean,
        "_adjusted_std": adjusted_std,
        "_var_y": var_y,
        "_adjusted_var": adjusted_var,
    }


def _public_cuped_arm(arm: dict[str, Any]) -> dict[str, Any]:
    """Public per-arm CUPED fields (display-rounded means/std; no internal vars)."""
    return {
        "variation_index": arm["variation_index"],
        "covariate_users": arm["covariate_users"],
        "exposed_users": arm["exposed_users"],
        "coverage": arm["coverage"],
        "unadjusted_mean": arm["unadjusted_mean"],
        "adjusted_mean": arm["adjusted_mean"],
        "adjusted_std": arm["adjusted_std"],
    }


def _cuped_estimator_variance_reduction_pct(
    control: dict[str, Any], treatment: dict[str, Any], se2: float
) -> float | None:
    """Per-comparison VR: ``100 * (1 - se2 / raw_est)`` for the active analysis se2."""
    var_y_c = control.get("_var_y")
    var_y_t = treatment.get("_var_y")
    if var_y_c is None or var_y_t is None:
        return None
    n_c = int(control["covariate_users"])
    n_t = int(treatment["covariate_users"])
    if n_c <= 0 or n_t <= 0:
        return None
    raw_est = float(var_y_c) / n_c + float(var_y_t) / n_t
    if not (raw_est > 0.0 and math.isfinite(raw_est) and math.isfinite(se2)):
        return None
    pct = 100.0 * (1.0 - float(se2) / raw_est)
    if not math.isfinite(pct):
        return None
    # Negatives are legitimate when CUPED does not help; clamp only tiny FP overshoot >100.
    if pct > 100.0 and pct <= 100.0 + 1e-6:
        pct = 100.0
    return round(pct, 4)


def _welch_df_from_std(std_c: float, n_c: int, std_t: float, n_t: int) -> float:
    control_term = (std_c * std_c) / n_c
    treatment_term = (std_t * std_t) / n_t
    denominator = 0.0
    if n_c > 1:
        denominator += (control_term * control_term) / (n_c - 1)
    if n_t > 1:
        denominator += (treatment_term * treatment_term) / (n_t - 1)
    if denominator == 0.0:
        return math.inf
    return ((control_term + treatment_term) ** 2) / denominator


def _clamp_nonnegative_sse(sse: float, syy: float) -> float | None:
    """Tolerance-aware SSE: tiny negative roundoff -> 0; nonfinite/material negative -> None."""
    if not math.isfinite(sse):
        return None
    if sse >= 0.0:
        return sse
    scale = max(abs(syy), 1.0)
    if sse >= -1e-12 * scale:
        return 0.0
    return None


def _cuped_welch_fallback(
    control: dict[str, Any], treatment: dict[str, Any], alpha: float
) -> tuple[dict[str, Any], float]:
    """Safe unadjusted Welch path when ANCOVA contrast variance is unusable."""
    std_c = float(control["_adjusted_std"] or 0.0)
    std_t = float(treatment["_adjusted_std"] or 0.0)
    n_c = int(control["covariate_users"])
    n_t = int(treatment["covariate_users"])
    se2 = max((std_c * std_c) / n_c + (std_t * std_t) / n_t, 0.0)
    analysis = _continuous_t_response(
        control_mean=float(control["_adjusted_mean"]),
        treatment_mean=float(treatment["_adjusted_mean"]),
        standard_error=math.sqrt(se2),
        degrees_of_freedom=_welch_df_from_std(std_c, n_c, std_t, n_t),
        alpha=alpha,
    ).model_dump()
    return analysis, se2


def _cuped_comparison(
    control: dict[str, Any],
    treatment: dict[str, Any],
    alpha: float,
    *,
    sxx: list[list[float]] | None,
    sxy: list[float] | None,
    syy: float | None,
    theta: list[float],
    n_total: int,
    n_arms: int,
    k: int,  # covariate vector dimension only (not residual df)
    effective_rank: int,
) -> dict[str, Any]:
    # Common-slope ANCOVA inference under homoskedastic normal residuals.
    base: dict[str, Any] = {
        "treatment_index": treatment["variation_index"],
        "control": _public_cuped_arm(control),
        "treatment": _public_cuped_arm(treatment),
        "analysis": None,
        "variance_reduction_pct": None,  # set from actual analysis se2 when status=ok
        "note": None,
    }
    n_c = int(control["covariate_users"])
    n_t = int(treatment["covariate_users"])
    if n_c < 2 or n_t < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base

    # Common-slope ANCOVA residual df: N - A - rank(Sxx), not raw covariate count.
    df = float(n_total - n_arms - effective_rank)
    if df <= 0:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base

    # When within-arm SSCP / contrast variance is unusable, keep a safe unadjusted
    # Welch fallback (theta is already the zero vector in that case).
    if sxx is None or sxy is None or syy is None:
        analysis, se2 = _cuped_welch_fallback(control, treatment, alpha)
        if se2 == 0.0:
            base["status"] = "insufficient_data"
            base["note"] = translate("live_stats.cuped.insufficient_data")
            return base
        base["status"] = "ok"
        base["analysis"] = analysis
        base["variance_reduction_pct"] = _cuped_estimator_variance_reduction_pct(
            control, treatment, se2
        )
        return base

    d = [
        float(treatment["_mean_x"][j]) - float(control["_mean_x"][j])
        for j in range(k)
    ]
    solved_z = cuped.solve_psd_system(sxx, d)
    if solved_z is None:
        analysis, se2 = _cuped_welch_fallback(control, treatment, alpha)
        if se2 == 0.0:
            base["status"] = "insufficient_data"
            base["note"] = translate("live_stats.cuped.insufficient_data")
            return base
        base["status"] = "ok"
        base["analysis"] = analysis
        base["variance_reduction_pct"] = _cuped_estimator_variance_reduction_pct(
            control, treatment, se2
        )
        return base
    z, _z_rank = solved_z

    # SSE = Syy - theta^T Sxy (= sum_a (n_a-1)*adjusted_var_a at the fitted theta).
    sse = _clamp_nonnegative_sse(float(syy) - cuped.dot(theta, sxy), float(syy))
    if sse is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base
    sigma2 = sse / df
    imbalance = cuped.dot(d, z)
    se2 = sigma2 * (1.0 / n_c + 1.0 / n_t + imbalance)
    if not math.isfinite(se2):
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base
    if se2 < 0.0:
        scale = max(
            abs(sigma2) * max(1.0 / n_c + 1.0 / n_t + abs(imbalance), 0.0),
            1.0,
        )
        if se2 >= -1e-12 * scale:
            se2 = 0.0
        else:
            base["status"] = "insufficient_data"
            base["note"] = translate("live_stats.cuped.insufficient_data")
            return base
    # Degenerate ANCOVA contrast variance: do not claim ok/p=1 via continuous helper.
    if se2 == 0.0:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base
    se = math.sqrt(se2)
    base["status"] = "ok"
    base["analysis"] = _continuous_t_response(
        control_mean=float(control["_adjusted_mean"]),
        treatment_mean=float(treatment["_adjusted_mean"]),
        standard_error=se,
        degrees_of_freedom=df,
        alpha=alpha,
    ).model_dump()
    base["variance_reduction_pct"] = _cuped_estimator_variance_reduction_pct(
        control, treatment, se2
    )
    return base


def _build_cuped_block(
    *,
    metric_type: str,
    alpha: float,
    variants_count: int,
    exposed_total: int,
    exposed_by_index: dict[int, int],
    cuped_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "theta": None,
        "num_covariates": None,
        "covariates": [],
        "variance_reduction_pct": None,
        "covariate_users_total": None,
        "exposed_users_total": None,
        "coverage_total": None,
        "selection_caveat": None,
        "comparisons": [],
    }
    if metric_type != "continuous":
        return {"status": "not_applicable", "note": translate("live_stats.cuped.not_applicable"), **empty}

    aggregates = cuped_aggregates or {}
    if aggregates.get("too_many_covariates"):
        return {
            "status": "too_many_covariates",
            "note": translate("live_stats.cuped.too_many"),
            **empty,
            "num_covariates": len(aggregates.get("covariate_names", [])),
            "exposed_users_total": exposed_total,
        }

    covariate_names = list(aggregates.get("covariate_names", []))
    k = len(covariate_names)
    by_index = {int(item["variation_index"]): item for item in aggregates.get("variations", [])}
    covariate_users_total = sum(int(item["n"]) for item in by_index.values())
    if k == 0 or covariate_users_total == 0:
        return {
            "status": "unavailable",
            "note": translate("live_stats.cuped.unavailable"),
            **empty,
            "num_covariates": k or None,
            "covariate_users_total": 0,
            "exposed_users_total": exposed_total,
            "coverage_total": round(0 / exposed_total, 4) if exposed_total > 0 else None,
            "selection_caveat": None,
        }

    arm_list = list(by_index.values())
    sums = _pool_sufficient(arm_list, k)
    pooled = _multi_moments(
        sums["n"],
        sums["sum_y"],
        sums["sum_y2"],
        sums["sum_x"],
        sums["sum_xy"],
        sums["sum_xx"],
        centered_syy=sums.get("centered_syy"),
        centered_sxy=sums.get("centered_sxy"),
        centered_sxx=sums.get("centered_sxx"),
    )
    # Common-slope theta from within-arm SSCP. Grand pooled mean_x still centers adjusted means.
    # Rank-deficient systems keep the identifiable subspace; only no usable direction collapses
    # theta to zero.
    sxx: list[list[float]] | None = None
    sxy: list[float] | None = None
    syy: float | None = None
    effective_rank = 0
    if pooled is None:
        theta = [0.0] * k
        global_mean_x = [0.0] * k
    else:
        global_mean_x = pooled["mean_x"]
        within = _within_arm_sscp(arm_list, k)
        if within is None:
            theta = [0.0] * k
            effective_rank = 0
        else:
            sxx, sxy, syy = within
            solved = cuped.solve_psd_system(sxx, sxy)
            if solved is None:
                theta = [0.0] * k
                effective_rank = 0
            else:
                theta, effective_rank = solved

    nonempty_arms = [arm for arm in arm_list if int(arm["n"]) > 0]
    n_total = sum(int(arm["n"]) for arm in nonempty_arms)
    n_arms = len(nonempty_arms)

    arm_stats = [
        _cuped_arm_stat(
            by_index.get(index),
            index,
            theta,
            global_mean_x,
            int(exposed_by_index.get(index, 0)),
        )
        for index in range(variants_count)
    ]
    comparisons = [
        _cuped_comparison(
            arm_stats[0],
            arm_stats[treatment_index],
            alpha,
            sxx=sxx,
            sxy=sxy,
            syy=syy,
            theta=theta,
            n_total=n_total,
            n_arms=n_arms,
            k=k,
            effective_rank=effective_rank,
        )
        for treatment_index in range(1, variants_count)
    ]

    # Legacy block field: pooled (1 - var_adj/var_y)*100 on grand-pooled moments with
    # current within-arm theta — not a mirror of comparison[0].
    variance_reduction_pct = None
    if pooled is not None and pooled["var_y"] > 0:
        adjusted_var = cuped.adjusted_variance(
            pooled["var_y"], theta, pooled["sigma_xy"], pooled["sigma_xx"]
        )
        variance_reduction_pct = round((1 - adjusted_var / pooled["var_y"]) * 100, 4)
    coverage_total = (
        round(covariate_users_total / exposed_total, 4) if exposed_total > 0 else None
    )

    covariates = [{"name": covariate_names[j], "theta": round(theta[j], 6)} for j in range(k)]
    return {
        "status": "available",
        "note": translate("live_stats.cuped.available"),
        # Single-covariate convenience (backward compatible); the vector lives in `covariates`.
        "theta": round(theta[0], 6) if k == 1 else None,
        "num_covariates": k,
        "covariates": covariates,
        "variance_reduction_pct": variance_reduction_pct,
        "covariate_users_total": covariate_users_total,
        "exposed_users_total": exposed_total,
        "coverage_total": coverage_total,
        # Users missing any covariate are excluded from this complete-case subset estimand.
        "selection_caveat": "complete_case_subset",
        "comparisons": comparisons,
    }


# --- Post-stratification on live data (F3b) --------------------------------------------------
#
# Post-stratification splits the exposed users into strata of a categorical attribute known at
# assignment time (ingested via POST .../strata), estimates the control-vs-treatment effect within
# each stratum, and recombines the per-stratum effects weighted by stratum size:
#
#     w_s = N_s / N,   Δ = Σ_s w_s·Δ_s,   Var(Δ) = Σ_s w_s²·Var(Δ_s)
#
# (the conditional post-stratification estimator — Miratrix, Sekhon & Yu 2013). When the stratum
# explains outcome variation the between-strata variation leaves the estimator's error and the
# effect estimate gets more precise. Each per-stratum effect/variance reuses the same unpooled
# binary (p(1−p)/n) or continuous (s²/n) moments as the main comparison — no new statistic. The
# size-weighted combine + z-test live in ``stats.stratification`` (stdlib). Supported for binary and
# continuous metrics; a ratio metric has no single per-user outcome the combine reads.
