"""CUPED variance-reduction block over ingested pre-period covariates."""
from __future__ import annotations

import math
from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import ObservedResultsContinuous, ResultsRequest
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats import cuped


def _multi_moments(
    n: int,
    sum_y: float,
    sum_y2: float,
    sum_x: list[float],
    sum_xy: list[float],
    sum_xx: list[list[float]],
) -> dict[str, Any] | None:
    """Means, outcome variance, the covariate covariance matrix ``Sigma_xx`` and the
    covariate/outcome covariance vector ``Sigma_xy`` from pooled sufficient statistics, or
    ``None`` when there are fewer than 2 observations (a sample variance is undefined)."""
    if n < 2:
        return None
    k = len(sum_x)
    mean_y = sum_y / n
    mean_x = [value / n for value in sum_x]
    var_y = (sum_y2 - n * mean_y * mean_y) / (n - 1)
    sigma_xy = [(sum_xy[j] - n * mean_x[j] * mean_y) / (n - 1) for j in range(k)]
    sigma_xx = [
        [(sum_xx[i][j] - n * mean_x[i] * mean_x[j]) / (n - 1) for j in range(k)]
        for i in range(k)
    ]
    return {
        "n": n,
        "mean_y": mean_y,
        "mean_x": mean_x,
        "var_y": var_y,
        "sigma_xy": sigma_xy,
        "sigma_xx": sigma_xx,
    }


def _pool_sufficient(arms: list[dict[str, Any]], k: int) -> dict[str, Any]:
    """Sum per-arm sufficient statistics into pooled totals (X is pre-treatment, so pooling
    across arms is unbiased)."""
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
    return {
        "n": total_n,
        "sum_y": sum_y,
        "sum_y2": sum_y2,
        "sum_x": sum_x,
        "sum_xy": sum_xy,
        "sum_xx": sum_xx,
    }


def _cuped_arm_stat(
    arm: dict[str, Any] | None,
    index: int,
    theta: list[float],
    global_mean_x: list[float],
) -> dict[str, Any]:
    n = int(arm["n"]) if arm else 0
    if n == 0 or arm is None:
        return {
            "variation_index": index,
            "covariate_users": 0,
            "unadjusted_mean": None,
            "adjusted_mean": None,
            "adjusted_std": None,
        }
    k = len(theta)
    mean_x = [arm["sum_x"][j] / n for j in range(k)]
    mean_y = arm["sum_y"] / n
    adjusted_mean = mean_y - cuped.dot(theta, [mean_x[j] - global_mean_x[j] for j in range(k)])
    adjusted_std: float | None = None
    arm_moments = _multi_moments(
        n, arm["sum_y"], arm["sum_y2"], arm["sum_x"], arm["sum_xy"], arm["sum_xx"]
    )
    if arm_moments is not None:
        adjusted_var = cuped.adjusted_variance(
            arm_moments["var_y"], theta, arm_moments["sigma_xy"], arm_moments["sigma_xx"]
        )
        adjusted_std = math.sqrt(adjusted_var) if adjusted_var > 0 else 0.0
    return {
        "variation_index": index,
        "covariate_users": n,
        "unadjusted_mean": round(mean_y, 6),
        "adjusted_mean": round(adjusted_mean, 6),
        "adjusted_std": round(adjusted_std, 6) if adjusted_std is not None else None,
    }


def _cuped_comparison(
    control: dict[str, Any], treatment: dict[str, Any], alpha: float
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "treatment_index": treatment["variation_index"],
        "control": control,
        "treatment": treatment,
        "analysis": None,
        "note": None,
    }
    if control["covariate_users"] < 2 or treatment["covariate_users"] < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.insufficient_data")
        return base
    if not control["adjusted_std"] or not treatment["adjusted_std"]:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.cuped.zero_variance")
        return base
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=control["adjusted_mean"],
            control_std=control["adjusted_std"],
            control_n=control["covariate_users"],
            treatment_mean=treatment["adjusted_mean"],
            treatment_std=treatment["adjusted_std"],
            treatment_n=treatment["covariate_users"],
            alpha=alpha,
        ),
    )
    base["status"] = "ok"
    base["analysis"] = analyze_results(request).model_dump()
    return base


def _build_cuped_block(
    *,
    metric_type: str,
    alpha: float,
    variants_count: int,
    exposed_total: int,
    cuped_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "theta": None,
        "num_covariates": None,
        "covariates": [],
        "variance_reduction_pct": None,
        "covariate_users_total": None,
        "exposed_users_total": None,
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
        }

    sums = _pool_sufficient(list(by_index.values()), k)
    pooled = _multi_moments(
        sums["n"], sums["sum_y"], sums["sum_y2"], sums["sum_x"], sums["sum_xy"], sums["sum_xx"]
    )
    # theta needs an invertible Sigma_xx; collinear / constant covariates carry no usable signal
    # -> theta = 0 vector (CUPED collapses to the unadjusted estimate).
    if pooled is None:
        theta = [0.0] * k
        global_mean_x = [0.0] * k
    else:
        global_mean_x = pooled["mean_x"]
        solved = cuped.cuped_theta(pooled["sigma_xx"], pooled["sigma_xy"])
        theta = solved if solved is not None else [0.0] * k

    arm_stats = [
        _cuped_arm_stat(by_index.get(index), index, theta, global_mean_x)
        for index in range(variants_count)
    ]
    comparisons = [
        _cuped_comparison(arm_stats[0], arm_stats[treatment_index], alpha)
        for treatment_index in range(1, variants_count)
    ]

    variance_reduction_pct = None
    if pooled is not None and pooled["var_y"] > 0:
        adjusted_var = cuped.adjusted_variance(
            pooled["var_y"], theta, pooled["sigma_xy"], pooled["sigma_xx"]
        )
        variance_reduction_pct = round((1 - adjusted_var / pooled["var_y"]) * 100, 4)

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
