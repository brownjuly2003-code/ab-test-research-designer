"""Versioned practical-significance decision policy (ADR 0001 / audit F-07).

Separates *statistical evidence* (frequentist CI, Bayesian P(B>A), sequential
boundaries) from the *business ship rule*. Default policy ``practical_v1`` requires
the lower CI bound of a positive win to clear the design minimum worthwhile effect
(MWE), derived from ``mde_pct`` the same way live-stats sizes the mSPRT mixture.
"""

from __future__ import annotations

from typing import Any, Literal

from app.backend.app.services.live_stats.common import _expected_absolute_effect

DECISION_POLICY_VERSION = "practical_v1"
PracticalRule = Literal["ci_lower_above"]
MweScale = Literal["absolute_analysis_units"]


def resolve_decision_policy(
    live_stats: dict[str, Any],
    *,
    project_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the active policy dict from design inputs.

    Preference order for design fields:
    1. ``project_payload.metrics`` when the caller still has the experiment;
    2. ``live_stats["decision_policy_inputs"]`` embedded by the live-stats builder;
    3. empty → practical gate disabled (statistical-only, documented).
    """
    inputs = _policy_inputs(live_stats, project_payload)
    metric_type = str(inputs.get("metric_type") or live_stats.get("metric_type") or "binary")
    baseline = _as_float(inputs.get("baseline_value"))
    mde_pct = _as_float(inputs.get("mde_pct"))
    planned_power = _as_float(inputs.get("power"))
    # Explicit override (future API field); absent → derive from mde_pct.
    explicit_mwe = _as_float(inputs.get("minimum_worthwhile_effect"))

    absolute_mwe = explicit_mwe
    mwe_source = "explicit"
    if absolute_mwe is None and baseline is not None and mde_pct is not None:
        absolute_mwe = _expected_absolute_effect(baseline, {"mde_pct": mde_pct})
        mwe_source = "design_mde_pct"

    mwe_analysis = (
        _to_analysis_units(metric_type, absolute_mwe) if absolute_mwe is not None else None
    )
    if mwe_analysis is not None:
        mwe_analysis = round(mwe_analysis, 6)
    require_practical = mwe_analysis is not None and mwe_analysis > 0

    return {
        "version": DECISION_POLICY_VERSION,
        "require_practical_evidence": require_practical,
        "practical_rule": "ci_lower_above",
        "mwe_scale": "absolute_analysis_units",
        "minimum_worthwhile_effect": mwe_analysis,
        "minimum_worthwhile_effect_relative_pct": mde_pct,
        "mwe_source": mwe_source if require_practical else "unavailable",
        "metric_type": metric_type,
        "baseline_value": baseline,
        "planned_power": planned_power,
        "evidence_fields": [
            "analysis.is_significant",
            "analysis.observed_effect",
            "analysis.ci_lower",
            "analysis.ci_upper",
            "probability_treatment_beats_control",
            "sequential_significant",
            "always_valid.is_significant",
        ],
    }


def evaluate_practical_win(
    *,
    policy: dict[str, Any],
    analysis: dict[str, Any],
    sample_complete: bool,
) -> dict[str, Any]:
    """Classify a statistical win against the practical threshold.

    Returns ``status``:
    - ``met`` — CI lower ≥ MWE; eligible for ship (subject to other rules)
    - ``uncertain`` — significant positive but CI still crosses MWE
    - ``proven_below`` — entire CI below MWE
    - ``unavailable`` — no practical gate / missing CI
    """
    if not policy.get("require_practical_evidence"):
        return {
            "status": "unavailable",
            "mwe": None,
            "ci_lower": analysis.get("ci_lower"),
            "ci_upper": analysis.get("ci_upper"),
            "sample_complete": sample_complete,
        }

    mwe = float(policy["minimum_worthwhile_effect"])
    ci_lower = analysis.get("ci_lower")
    ci_upper = analysis.get("ci_upper")
    if ci_lower is None or ci_upper is None:
        return {
            "status": "unavailable",
            "mwe": mwe,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "sample_complete": sample_complete,
        }

    ci_lo = float(ci_lower)
    ci_hi = float(ci_upper)
    if ci_lo >= mwe:
        status: str = "met"
    elif ci_hi < mwe:
        status = "proven_below"
    else:
        status = "uncertain"

    return {
        "status": status,
        "mwe": mwe,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "sample_complete": sample_complete,
    }


def _policy_inputs(
    live_stats: dict[str, Any],
    project_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if project_payload and isinstance(project_payload.get("metrics"), dict):
        metrics = project_payload["metrics"]
        decision = project_payload.get("decision_policy") or {}
        return {
            "metric_type": metrics.get("metric_type"),
            "baseline_value": metrics.get("baseline_value"),
            "mde_pct": metrics.get("mde_pct"),
            "power": metrics.get("power"),
            "minimum_worthwhile_effect": decision.get("minimum_worthwhile_effect"),
        }
    embedded = live_stats.get("decision_policy_inputs")
    if isinstance(embedded, dict):
        return embedded
    return {}


def _to_analysis_units(metric_type: str, absolute_effect: float) -> float:
    """Map design absolute effect (proportion for binary rates) onto analyzer units.

    Binary live results report rates and effects in percentage points (e.g. +0.20 pp),
    while design ``baseline_value`` is a proportion (0.10). Continuous / count / ratio
    effects stay in natural units equal to ``baseline * mde_pct/100``.
    """
    if metric_type == "binary":
        return absolute_effect * 100.0
    return absolute_effect


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
