"""Guardrail metric monitoring block."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.stats import stratification
from app.backend.app.stats.guardrail import (
    INCREASE_IS_BAD,
    STATUS_BREACHED,
    STATUS_OK,
    STATUS_WARNING,
    evaluate_guardrail,
    worst_status,
)


def _guardrail_baseline(metric: dict[str, Any]) -> float | None:
    """Design baseline of a guardrail in natural units: the rate (``baseline_rate`` is a percent) for
    a binary guardrail, the mean for a continuous one. ``None`` when the design omits it (then no
    relative margin can be scaled and the margin falls back to 0)."""
    if metric.get("metric_type") == "binary":
        baseline_rate = metric.get("baseline_rate")
        return float(baseline_rate) / 100.0 if baseline_rate is not None else None
    baseline_mean = metric.get("baseline_mean")
    return float(baseline_mean) if baseline_mean is not None else None


def _guardrail_margin_abs(metric: dict[str, Any]) -> float:
    """Tolerated degradation in natural units = baseline · margin_pct/100; 0 when no margin (any
    significant degradation breaches) or no usable baseline to scale a relative margin against."""
    margin_pct = metric.get("non_inferiority_margin_pct")
    if margin_pct is None:
        return 0.0
    baseline = _guardrail_baseline(metric)
    if baseline is None:
        return 0.0
    return abs(baseline) * float(margin_pct) / 100.0


def _guardrail_point(metric_type: str, arm: dict[str, Any]) -> tuple[float, float] | None:
    """``(point estimate, variance of that estimate)`` for one guardrail arm, or ``None`` when the
    arm has fewer than 2 exposed users. Reuses the same unpooled binary / continuous moments as
    post-stratification — no new statistic."""
    n = int(arm["exposed_users"])
    if n < 2:
        return None
    if metric_type == "binary":
        return stratification.binary_point_variance(int(arm["converted_users"]), n)
    return stratification.continuous_point_variance(
        float(arm["value_sum"]), float(arm["value_sq_sum"]), n
    )


def _guardrail_arm_stat(metric_type: str, arm: dict[str, Any]) -> dict[str, Any]:
    point = _guardrail_point(metric_type, arm)
    return {
        "variation_index": int(arm["variation_index"]),
        "exposed_users": int(arm["exposed_users"]),
        "point_estimate": round(point[0], 6) if point is not None else None,
    }


def _guardrail_comparison(
    *,
    metric_type: str,
    direction: str,
    margin_abs: float,
    alpha: float,
    control: dict[str, Any],
    treatment: dict[str, Any],
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "treatment_index": int(treatment["variation_index"]),
        "control": _guardrail_arm_stat(metric_type, control),
        "treatment": _guardrail_arm_stat(metric_type, treatment),
        "effect": None,
        "harm": None,
        "harm_lower_bound": None,
        "margin": round(margin_abs, 8),
        "p_value": None,
        "is_breached": None,
        "note": None,
    }
    control_point = _guardrail_point(metric_type, control)
    treatment_point = _guardrail_point(metric_type, treatment)
    if control_point is None or treatment_point is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.guardrail.insufficient_data")
        return base
    effect = treatment_point[0] - control_point[0]
    variance = control_point[1] + treatment_point[1]
    result = evaluate_guardrail(
        effect, variance, direction=direction, margin=margin_abs, alpha=alpha
    )
    if result is None:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.guardrail.zero_variance")
        return base
    base["status"] = result["status"]
    base["effect"] = round(effect, 6)
    base["harm"] = round(result["harm"], 6)
    base["harm_lower_bound"] = round(result["harm_lower_bound"], 6)
    base["p_value"] = round(result["p_value"], 6)
    base["is_breached"] = result["is_breached"]
    return base


def _guardrail_metric_result(
    *,
    metric: dict[str, Any],
    aggregates: dict[str, Any] | None,
    variants_count: int,
    alpha: float,
) -> dict[str, Any]:
    metric_type = str(metric.get("metric_type", "binary"))
    direction = str(metric.get("direction", INCREASE_IS_BAD))
    margin_abs = _guardrail_margin_abs(metric)
    by_index = {
        int(item["variation_index"]): item
        for item in (aggregates or {}).get("variations", [])
    }
    arms = [
        by_index.get(
            index,
            {
                "variation_index": index,
                "exposed_users": 0,
                "converted_users": 0,
                "value_sum": 0.0,
                "value_sq_sum": 0.0,
            },
        )
        for index in range(variants_count)
    ]
    comparisons = [
        _guardrail_comparison(
            metric_type=metric_type,
            direction=direction,
            margin_abs=margin_abs,
            alpha=alpha,
            control=arms[0],
            treatment=arms[treatment_index],
        )
        for treatment_index in range(1, variants_count)
    ]
    evaluated = [c["status"] for c in comparisons if c["status"] != "insufficient_data"]
    status = worst_status(evaluated) if evaluated else "insufficient_data"
    margin_pct = metric.get("non_inferiority_margin_pct")
    return {
        "name": str(metric.get("name", "")),
        "metric_type": metric_type,
        "direction": direction,
        "margin_pct": float(margin_pct) if margin_pct is not None else None,
        "status": status,
        "comparisons": comparisons,
    }


def _build_guardrail_block(
    *,
    guardrail_metrics: list[dict[str, Any]],
    guardrail_aggregates: dict[str, Any] | None,
    variants_count: int,
    alpha: float,
) -> dict[str, Any]:
    if not guardrail_metrics:
        return {
            "status": "unavailable",
            "note": translate("live_stats.guardrail.none"),
            "any_breached": False,
            "metrics": [],
        }

    aggregates_by_name = guardrail_aggregates or {}
    metrics = [
        _guardrail_metric_result(
            metric=metric,
            aggregates=aggregates_by_name.get(str(metric.get("name", ""))),
            variants_count=variants_count,
            alpha=alpha,
        )
        for metric in guardrail_metrics
    ]
    evaluated = [m["status"] for m in metrics if m["status"] != "insufficient_data"]
    any_breached = any(m["status"] == STATUS_BREACHED for m in metrics)
    if not evaluated:
        return {
            "status": "unavailable",
            "note": translate("live_stats.guardrail.unavailable"),
            "any_breached": False,
            "metrics": metrics,
        }
    block_status = worst_status(evaluated)
    note = {
        STATUS_BREACHED: translate("live_stats.guardrail.breached"),
        STATUS_WARNING: translate("live_stats.guardrail.warning"),
        STATUS_OK: translate("live_stats.guardrail.ok"),
    }[block_status]
    return {
        "status": block_status,
        "note": note,
        "any_breached": any_breached,
        "metrics": metrics,
    }


# --- Holdout groups on live data (F5) --------------------------------------------------------
#
# A holdout is a long-lived group held back from the rollout (variation_index = -1). The cumulative
# read compares the *pooled treated arms* (variation_index >= 1) against the holdout on the primary
# metric: it answers "what is the standing effect of everything we rolled out, vs users who got
# nothing" — distinct from the per-variant primary test, and a check on the winner's-curse tendency
# of summed individual wins to overstate reality. Pooling the treatment arms is a sum of sufficient
# statistics; the treated-vs-holdout effect then reuses the same two-proportion / Welch test
# (``analyze_results``), Bayesian P(B>A) (``simulate_uplift_distribution``) and anytime-valid view the
# primary path uses — no new statistic. The control arm (variation_index = 0) stays out of the treated
# pool: it is the in-window baseline, whereas the holdout is the long-lived held-back group. Supported
# for binary and continuous metrics; a ratio metric has no single per-user outcome the pool reads.
