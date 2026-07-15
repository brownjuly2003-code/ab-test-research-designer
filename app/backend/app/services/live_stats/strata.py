"""Post-stratification block over per-stratum sufficient statistics."""
from __future__ import annotations

from typing import Any

from app.backend.app.i18n import translate
from app.backend.app.stats import stratification


def _stratum_arm_estimate(metric_type: str, arm: dict[str, Any]) -> tuple[float, float] | None:
    """``(point estimate, variance of that estimate)`` for one stratum arm, or ``None`` when the arm
    has fewer than 2 users (too small to contribute a per-stratum effect variance)."""
    n = int(arm["exposed_users"])
    if n < 2:
        return None
    if metric_type == "binary":
        return stratification.binary_point_variance(int(arm["converted_users"]), n)
    return stratification.continuous_point_variance(
        float(arm["value_sum"]), float(arm["value_sq_sum"]), n
    )


def _empty_stratum_arm() -> dict[str, Any]:
    return {"exposed_users": 0, "converted_users": 0, "value_sum": 0.0, "value_sq_sum": 0.0}


def _accumulate_stratum_arm(target: dict[str, Any], arm: dict[str, Any]) -> None:
    target["exposed_users"] += int(arm["exposed_users"])
    target["converted_users"] += int(arm["converted_users"])
    target["value_sum"] += float(arm["value_sum"])
    target["value_sq_sum"] += float(arm["value_sq_sum"])


def _stratified_comparison(
    metric_type: str,
    strata: list[dict[str, Any]],
    treatment_index: int,
    alpha: float,
) -> dict[str, Any]:
    strata_effects: list[dict[str, Any]] = []
    combine_input: list[dict[str, Any]] = []
    pooled_control = _empty_stratum_arm()
    pooled_treatment = _empty_stratum_arm()
    for stratum in strata:
        by_index = {int(arm["variation_index"]): arm for arm in stratum.get("variations", [])}
        control = by_index.get(0)
        treatment = by_index.get(treatment_index)
        control_n = int(control["exposed_users"]) if control else 0
        treatment_n = int(treatment["exposed_users"]) if treatment else 0
        if control is not None:
            _accumulate_stratum_arm(pooled_control, control)
        if treatment is not None:
            _accumulate_stratum_arm(pooled_treatment, treatment)
        delta: float | None = None
        if control is not None and treatment is not None:
            control_estimate = _stratum_arm_estimate(metric_type, control)
            treatment_estimate = _stratum_arm_estimate(metric_type, treatment)
            if control_estimate is not None and treatment_estimate is not None:
                difference = stratification.stratum_difference(control_estimate, treatment_estimate)
                delta = difference["delta"]
                combine_input.append(
                    {
                        "n": control_n + treatment_n,
                        "delta": difference["delta"],
                        "variance": difference["variance"],
                    }
                )
        strata_effects.append(
            {
                "stratum": str(stratum["stratum"]),
                "users": control_n + treatment_n,
                "control_users": control_n,
                "treatment_users": treatment_n,
                "effect": round(delta, 6) if delta is not None else None,
            }
        )

    base: dict[str, Any] = {
        "treatment_index": treatment_index,
        "status": "insufficient_data",
        "effect": None,
        "standard_error": None,
        "test_statistic": None,
        "p_value": None,
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": None,
        "is_significant": None,
        "variance_reduction_pct": None,
        "num_strata": None,
        "strata": strata_effects,
        "note": translate("live_stats.stratified.insufficient_data"),
    }
    combined = stratification.combine_strata(combine_input, alpha) if combine_input else None
    if combined is None:
        return base

    # Variance reduction vs the naive estimate that ignores strata, over the *same* covered users
    # (pool every stratum into one control/treatment arm) — an apples-to-apples comparison.
    variance_reduction: float | None = None
    pooled_control_estimate = _stratum_arm_estimate(metric_type, pooled_control)
    pooled_treatment_estimate = _stratum_arm_estimate(metric_type, pooled_treatment)
    if pooled_control_estimate is not None and pooled_treatment_estimate is not None:
        pooled_variance = pooled_control_estimate[1] + pooled_treatment_estimate[1]
        variance_reduction = stratification.variance_reduction_pct(
            pooled_variance, combined["variance"]
        )

    return {
        "treatment_index": treatment_index,
        "status": "ok",
        "effect": round(combined["effect"], 6),
        "standard_error": round(combined["standard_error"], 6),
        "test_statistic": round(combined["test_statistic"], 6),
        "p_value": round(combined["p_value"], 6),
        "ci_lower": round(combined["ci_lower"], 6),
        "ci_upper": round(combined["ci_upper"], 6),
        "ci_level": round(combined["ci_level"], 6),
        "is_significant": combined["is_significant"],
        "variance_reduction_pct": (
            round(variance_reduction, 4) if variance_reduction is not None else None
        ),
        "num_strata": combined["num_strata"],
        "strata": strata_effects,
        "note": None,
    }


def _build_stratified_block(
    *,
    metric_type: str,
    alpha: float,
    variants_count: int,
    exposed_total: int,
    stratified_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "num_strata": None,
        "stratified_users_total": None,
        "exposed_users_total": None,
        "comparisons": [],
    }
    if metric_type not in ("binary", "continuous"):
        return {"status": "unavailable", "note": translate("live_stats.stratified.not_applicable"), **empty}

    aggregates = stratified_aggregates or {}
    if aggregates.get("too_many_strata"):
        return {
            "status": "too_many_strata",
            "note": translate("live_stats.stratified.too_many"),
            **empty,
            "num_strata": aggregates.get("num_strata"),
            "exposed_users_total": exposed_total,
        }

    strata = list(aggregates.get("strata", []))
    covered_total = sum(
        int(arm["exposed_users"]) for stratum in strata for arm in stratum.get("variations", [])
    )
    if not strata or covered_total == 0:
        return {
            "status": "unavailable",
            "note": translate("live_stats.stratified.unavailable"),
            **empty,
            "num_strata": len(strata) or None,
            "stratified_users_total": 0,
            "exposed_users_total": exposed_total,
        }

    comparisons = [
        _stratified_comparison(metric_type, strata, treatment_index, alpha)
        for treatment_index in range(1, variants_count)
    ]
    return {
        "status": "available",
        "note": translate("live_stats.stratified.available"),
        "num_strata": len(strata),
        "stratified_users_total": covered_total,
        "exposed_users_total": exposed_total,
        "comparisons": comparisons,
    }


# --- Guardrail metrics on live data (F4) -----------------------------------------------------
#
# A guardrail metric must not be harmed by the treatment. Unlike the two-sided primary test, each
# guardrail is checked with a *directed* one-sided breach test (``stats.guardrail``): the harm is the
# treatment−control difference signed by the guardrail's harm direction, its variance is the same
# unpooled (binary p(1−p)/n) / Welch (continuous s²/n) variance the primary comparison uses, and a
# breach is a statistically significant degradation beyond an optional tolerance margin. Guardrail
# outcomes are ingested through the ordinary conversion stream (one conversion metric per guardrail
# name) and rolled up by ``repository.get_experiment_analysis_aggregates`` per guardrail — no new
# store and no new test statistic. A breach feeds the decision readout as a ship blocker.
