"""Holdout, event-timing, identity-resolution, and exclusion quality blocks."""
from __future__ import annotations

from typing import Any, cast

from app.backend.app.i18n import translate
from app.backend.app.schemas.api import (
    ObservedResultsBinary,
    ObservedResultsContinuous,
    ResultsRequest,
)
from app.backend.app.services.monte_carlo_service import (
    simulate_continuous_uplift_distribution,
    simulate_uplift_distribution,
)
from app.backend.app.services.results_service import analyze_results

from .common import _always_valid_block, _continuous_moments
from .constants import (
    _BAYESIAN_PROBABILITY_DECIMALS,
    _BAYESIAN_SEED,
    _BAYESIAN_SIMULATIONS,
)


def _pool_treated_arms(arms: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold the treatment arms (variation_index >= 1) into one pooled treated arm by summing their
    sufficient statistics. The control arm (index 0) is excluded — it is the in-window baseline, not
    part of the rolled-out treatment."""
    pooled = {"exposed_users": 0, "converted_users": 0, "value_sum": 0.0, "value_sq_sum": 0.0}
    for arm in arms[1:]:
        pooled["exposed_users"] += int(arm["exposed_users"])
        pooled["converted_users"] += int(arm["converted_users"])
        pooled["value_sum"] += float(arm["value_sum"])
        pooled["value_sq_sum"] += float(arm["value_sq_sum"])
    return pooled


def _holdout_arm_stat(metric_type: str, arm: dict[str, Any], label: str) -> dict[str, Any]:
    exposed = int(arm["exposed_users"])
    stat: dict[str, Any] = {
        "label": label,
        "exposed_users": exposed,
        "converted_users": int(arm["converted_users"]),
    }
    if metric_type == "binary":
        stat["conversion_rate"] = (
            round(int(arm["converted_users"]) / exposed, 6) if exposed else None
        )
    else:
        mean, std = _continuous_moments(arm)
        stat["mean"] = round(mean, 6) if mean is not None else None
        stat["std"] = round(std, 6) if std is not None else None
    return stat


def _holdout_binary(
    base: dict[str, Any],
    alpha: float,
    holdout: dict[str, Any],
    treated: dict[str, Any],
    mixture_variance: float | None,
) -> dict[str, Any]:
    holdout_rate = int(holdout["converted_users"]) / int(holdout["exposed_users"])
    treated_rate = int(treated["converted_users"]) / int(treated["exposed_users"])
    request = ResultsRequest(
        metric_type="binary",
        binary=ObservedResultsBinary(
            control_conversions=int(holdout["converted_users"]),
            control_users=int(holdout["exposed_users"]),
            treatment_conversions=int(treated["converted_users"]),
            treatment_users=int(treated["exposed_users"]),
            alpha=alpha,
        ),
    )
    analysis = analyze_results(request)
    simulation = simulate_uplift_distribution(
        baseline_conversion=holdout_rate,
        observed_conversion_a=holdout_rate,
        sample_size_a=int(holdout["exposed_users"]),
        observed_conversion_b=treated_rate,
        sample_size_b=int(treated["exposed_users"]),
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    # holdout is the baseline (A), the pooled treated arms the treatment (B): a positive effect means
    # the rollout improved the metric over holding users back. Same unpooled variance as the primary.
    effect = treated_rate - holdout_rate
    variance = holdout_rate * (1 - holdout_rate) / int(holdout["exposed_users"]) + (
        treated_rate * (1 - treated_rate) / int(treated["exposed_users"])
    )
    base["status"] = "ok"
    base["note"] = translate("live_stats.holdout.ok")
    base["analysis"] = analysis.model_dump()
    base["probability_treated_beats_holdout"] = round(
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


def _holdout_continuous(
    base: dict[str, Any],
    alpha: float,
    holdout: dict[str, Any],
    treated: dict[str, Any],
    mixture_variance: float | None,
) -> dict[str, Any]:
    holdout_mean, holdout_std = _continuous_moments(holdout)
    treated_mean, treated_std = _continuous_moments(treated)
    if not holdout_std or not treated_std:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.holdout.zero_variance")
        return base
    holdout_mean = cast("float", holdout_mean)
    treated_mean = cast("float", treated_mean)
    request = ResultsRequest(
        metric_type="continuous",
        continuous=ObservedResultsContinuous(
            control_mean=holdout_mean,
            control_std=holdout_std,
            control_n=int(holdout["exposed_users"]),
            treatment_mean=treated_mean,
            treatment_std=treated_std,
            treatment_n=int(treated["exposed_users"]),
            alpha=alpha,
        ),
    )
    simulation = simulate_continuous_uplift_distribution(
        control_mean=holdout_mean,
        control_std=holdout_std,
        control_n=int(holdout["exposed_users"]),
        treatment_mean=treated_mean,
        treatment_std=treated_std,
        treatment_n=int(treated["exposed_users"]),
        num_simulations=_BAYESIAN_SIMULATIONS,
        seed=_BAYESIAN_SEED,
    )
    effect = treated_mean - holdout_mean
    variance = (
        holdout_std**2 / int(holdout["exposed_users"])
        + treated_std**2 / int(treated["exposed_users"])
    )
    base["status"] = "ok"
    base["note"] = translate("live_stats.holdout.ok")
    base["analysis"] = analyze_results(request).model_dump()
    base["probability_treated_beats_holdout"] = round(
        simulation["probability_uplift_positive"], _BAYESIAN_PROBABILITY_DECIMALS
    )
    base["always_valid"] = _always_valid_block(effect, variance, mixture_variance, alpha)
    return base


def _build_holdout_block(
    *,
    metric_type: str,
    alpha: float,
    arms: list[dict[str, Any]],
    holdout_aggregates: dict[str, Any] | None,
    mixture_variance: float | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "treated": None,
        "holdout": None,
        "analysis": None,
        "probability_treated_beats_holdout": None,
        "always_valid": None,
        "treated_users_total": None,
        "holdout_users_total": None,
    }
    if metric_type not in ("binary", "continuous"):
        return {"status": "unavailable", "note": translate("live_stats.holdout.unavailable_ratio"), **empty}

    holdout = (holdout_aggregates or {}).get("holdout")
    holdout_users = int(holdout["exposed_users"]) if holdout else 0
    if not holdout or holdout_users == 0:
        return {"status": "unavailable", "note": translate("live_stats.holdout.unavailable"), **empty}

    treated = _pool_treated_arms(arms)
    treated_users = int(treated["exposed_users"])
    base: dict[str, Any] = {
        "treated": _holdout_arm_stat(metric_type, treated, "treated"),
        "holdout": _holdout_arm_stat(metric_type, holdout, "holdout"),
        "analysis": None,
        "probability_treated_beats_holdout": None,
        "always_valid": None,
        "treated_users_total": treated_users,
        "holdout_users_total": holdout_users,
    }
    if treated_users < 2 or holdout_users < 2:
        base["status"] = "insufficient_data"
        base["note"] = translate("live_stats.holdout.insufficient_data")
        return base
    if metric_type == "binary":
        return _holdout_binary(base, alpha, holdout, treated, mixture_variance)
    return _holdout_continuous(base, alpha, holdout, treated, mixture_variance)


def _build_event_timing_block(
    event_timing_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Late / out-of-order conversion indicator (P4.2).

    Reports how conversions on the primary metric distribute relative to each user's exposure:
    ``in_window`` (attributed), ``late`` (after the attribution horizon), and ``out_of_order``
    (before the exposure — causally impossible). Purely informational — a data-quality indicator
    that never alters a comparison or the decision verdict. ``unavailable`` when no summary was
    computed (e.g. the experiment has no exposures yet).
    """
    if not event_timing_summary:
        return {
            "status": "unavailable",
            "metric": None,
            "horizon_days": None,
            "in_window": None,
            "late": None,
            "out_of_order": None,
            "total": None,
        }
    return {
        "status": "ok",
        "metric": event_timing_summary.get("metric_name"),
        "horizon_days": event_timing_summary.get("horizon_days"),
        "in_window": int(event_timing_summary.get("in_window", 0)),
        "late": int(event_timing_summary.get("late", 0)),
        "out_of_order": int(event_timing_summary.get("out_of_order", 0)),
        "total": int(event_timing_summary.get("total", 0)),
    }


def _build_identity_resolution_block(
    identity_resolution_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Identity-resolution indicator (P4.3).

    Reports how many anonymous → canonical links are active and how much they touched the rollup
    (``canonicalized_events`` re-attributed, ``merged_users`` whose double-count was prevented). The
    resolution already happened in the primary rollup; this block only surfaces it. ``inactive`` when
    no links exist (the common case) — the frontend hides the block then. Purely informational; it
    never alters a comparison or the decision verdict.
    """
    linked = int((identity_resolution_summary or {}).get("linked_identities", 0) or 0)
    if not identity_resolution_summary or linked <= 0:
        return {
            "status": "inactive",
            "linked_identities": linked,
            "canonicalized_events": None,
            "merged_users": None,
        }
    return {
        "status": "active",
        "linked_identities": linked,
        "canonicalized_events": int(identity_resolution_summary.get("canonicalized_events", 0) or 0),
        "merged_users": int(identity_resolution_summary.get("merged_users", 0) or 0),
    }


def _build_population_block(
    population_diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Canonical analytical population fingerprint (audit F-02).

    Surfaces treated/holdout N and exclusion counts under one shared policy so a
    cohort-definition mismatch is visible before effect estimation. Informational only.
    """
    if not population_diagnostics:
        return {
            "status": "unavailable",
            "policy_version": None,
            "fingerprint": None,
            "treated_users": None,
            "holdout_users": None,
            "excluded_users": None,
            "manual_excluded": None,
            "rate_spike_excluded": None,
            "linked_identities": None,
            "policy_aligned": None,
        }
    return {
        "status": "ok",
        "policy_version": population_diagnostics.get("policy_version"),
        "fingerprint": population_diagnostics.get("fingerprint"),
        "treated_users": int(population_diagnostics.get("treated_users", 0) or 0),
        "holdout_users": int(population_diagnostics.get("holdout_users", 0) or 0),
        "excluded_users": int(population_diagnostics.get("excluded_users", 0) or 0),
        "manual_excluded": int(population_diagnostics.get("manual_excluded", 0) or 0),
        "rate_spike_excluded": int(population_diagnostics.get("rate_spike_excluded", 0) or 0),
        "linked_identities": int(population_diagnostics.get("linked_identities", 0) or 0),
        "policy_aligned": bool(population_diagnostics.get("policy_aligned", True)),
    }


def _build_exclusion_block(
    exclusion_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Bot / fraud filter indicator (P4.4).

    Reports how many exposed users the rollup removed, split into the manual deny-list and the
    rate-spike heuristic. The exclusion already happened in the primary rollup; this block only
    surfaces it so the filter is never silent. ``inactive`` when nothing was filtered (the common
    case) — the frontend hides the block then. Purely informational; the per-reason split is disjoint
    so ``manual_filtered + rate_spike_filtered == total_filtered``.
    """
    total = int((exclusion_summary or {}).get("total_filtered", 0) or 0)
    if not exclusion_summary or total <= 0:
        return {
            "status": "inactive",
            "total_filtered": total,
            "manual_filtered": None,
            "rate_spike_filtered": None,
        }
    return {
        "status": "active",
        "total_filtered": total,
        "manual_filtered": int(exclusion_summary.get("manual_filtered", 0) or 0),
        "rate_spike_filtered": int(exclusion_summary.get("rate_spike_filtered", 0) or 0),
    }
