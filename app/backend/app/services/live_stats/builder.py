"""Orchestrator: assemble the full live-stats payload."""
from __future__ import annotations

from typing import Any

from app.backend.app.execution.experiment_assignment import normalize_weights
from app.backend.app.i18n import translate
from app.backend.app.stats.always_valid import default_mixture_variance

from .common import _annotate_multiple_comparison, _expected_absolute_effect
from .cuped import _build_cuped_block
from .guardrails import _build_guardrail_block
from .primary import (
    _build_comparison,
    _build_ratio_comparisons,
    _build_sequential_block,
    _build_srm_block,
)
from .quality import (
    _build_event_timing_block,
    _build_exclusion_block,
    _build_holdout_block,
    _build_identity_resolution_block,
)
from .strata import _build_stratified_block


def build_live_stats(
    experiment_id: str,
    project_payload: dict[str, Any],
    aggregates: dict[str, Any],
    cuped_aggregates: dict[str, Any] | None = None,
    ratio_aggregates: dict[str, Any] | None = None,
    stratified_aggregates: dict[str, Any] | None = None,
    guardrail_aggregates: dict[str, Any] | None = None,
    holdout_aggregates: dict[str, Any] | None = None,
    event_timing_summary: dict[str, Any] | None = None,
    identity_resolution_summary: dict[str, Any] | None = None,
    exclusion_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the live-stats payload from a stored experiment design and the current
    per-variation analysis aggregates (``repository.get_experiment_analysis_aggregates``).

    ``cuped_aggregates`` (``repository.get_cuped_aggregates``) carries the per-variation CUPED
    sufficient statistics over users with a pre-period covariate; ``None`` / empty keeps the
    CUPED block ``unavailable``.

    ``ratio_aggregates`` (``repository.get_ratio_aggregates``) carries the per-variation ratio
    sufficient statistics (numerator/denominator per user); it drives the comparisons when the
    design's ``metric_type`` is ``ratio`` (delta method) and is ignored otherwise.

    ``guardrail_aggregates`` maps each declared guardrail metric name to its per-variation analysis
    aggregates (same shape as ``aggregates``, one entry per guardrail); ``None`` / empty keeps the
    guardrail block ``unavailable``.

    ``holdout_aggregates`` (``repository.get_holdout_aggregates``) carries the held-back
    (``variation_index = -1``) group's rollup for the cumulative treated-vs-holdout read; ``None`` /
    no holdout users keeps the holdout block ``unavailable``.

    ``event_timing_summary`` (``repository.get_event_timing_summary``) carries the late /
    out-of-order conversion counts on the primary metric (P4.2); ``None`` keeps the event-timing
    block ``unavailable``. It is informational only — it does not change any comparison or verdict.

    ``identity_resolution_summary`` (``repository.get_identity_resolution_summary``) carries the
    anonymous → canonical link counts (P4.3); ``None`` / no links keeps the block ``inactive``. The
    resolution itself already happened inside the primary rollup — this block only reports it.

    ``exclusion_summary`` (``repository.get_exclusion_summary``) carries the bot / fraud filter counts
    (P4.4 — manual deny-list + rate-spike); ``None`` / nothing filtered keeps the block ``inactive``.
    The exclusion already happened inside the primary rollup — this block only reports it."""
    metrics = project_payload.get("metrics", {})
    setup = project_payload.get("setup", {})
    constraints = project_payload.get("constraints", {})

    metric_type = metrics.get("metric_type", "binary")
    primary_metric_name = metrics.get("primary_metric_name", "")
    baseline_value = float(metrics.get("baseline_value", 0.0))
    alpha = float(metrics.get("alpha", 0.05))
    variants_count = int(setup.get("variants_count", 2))
    traffic_split = setup.get("traffic_split", [])
    n_looks = int(constraints.get("n_looks", 1))

    # Build a dense per-variation view (0..variants_count-1), filling arms with no exposures.
    by_index = {int(item["variation_index"]): item for item in aggregates.get("variations", [])}
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

    exposures_total = sum(arm["exposed_users"] for arm in arms)
    conversions_total = sum(arm["converted_users"] for arm in arms)

    expected_fractions = normalize_weights(traffic_split) if traffic_split else []

    # Family-wise error control at analysis time, mirroring the planning side (stats.binary /
    # stats.continuous Bonferroni): every control-vs-treatment test runs at alpha / (#treatments),
    # so the live readout's false-positive rate matches the alpha the sample size was planned for.
    # One treatment -> adjusted == nominal, so two-variant experiments are unchanged.
    comparison_count = max(1, variants_count - 1)
    adjusted_alpha = alpha / comparison_count

    # Mixing variance tau^2 for the anytime-valid (mSPRT) view, derived from the design's MDE so it
    # is fixed *before* any data is seen (a precondition for the anytime-valid guarantee) and
    # concentrates power around the effect the experiment was sized for. None -> per-comparison
    # fallback to the observed variance scale (only when the design carries no usable MDE).
    expected_effect = _expected_absolute_effect(baseline_value, metrics)
    design_mixture_variance = (
        default_mixture_variance(expected_effect) if expected_effect else None
    )

    srm = _build_srm_block(arms, expected_fractions)
    if metric_type == "ratio":
        comparisons = _build_ratio_comparisons(
            ratio_aggregates=ratio_aggregates,
            variants_count=variants_count,
            alpha=adjusted_alpha,
            mixture_variance=design_mixture_variance,
        )
    else:
        comparisons = [
            _build_comparison(
                metric_type=metric_type,
                baseline_value=baseline_value,
                alpha=adjusted_alpha,
                control=arms[0],
                treatment=arms[treatment_index],
                mixture_variance=design_mixture_variance,
            )
            for treatment_index in range(1, variants_count)
        ]
    if comparison_count > 1:
        _annotate_multiple_comparison(comparisons, alpha, adjusted_alpha, comparison_count)
    sequential = _build_sequential_block(
        project_payload=project_payload,
        n_looks=n_looks,
        variants_count=variants_count,
        total_exposed=exposures_total,
        comparisons=comparisons,
    )
    cuped = _build_cuped_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        variants_count=variants_count,
        exposed_total=exposures_total,
        cuped_aggregates=cuped_aggregates,
    )
    if comparison_count > 1:
        _annotate_multiple_comparison(
            cuped.get("comparisons", []), alpha, adjusted_alpha, comparison_count
        )
    stratified = _build_stratified_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        variants_count=variants_count,
        exposed_total=exposures_total,
        stratified_aggregates=stratified_aggregates,
    )
    guardrail = _build_guardrail_block(
        guardrail_metrics=metrics.get("guardrail_metrics", []),
        guardrail_aggregates=guardrail_aggregates,
        variants_count=variants_count,
        alpha=adjusted_alpha,
    )
    holdout = _build_holdout_block(
        metric_type=metric_type,
        alpha=adjusted_alpha,
        arms=arms,
        holdout_aggregates=holdout_aggregates,
        mixture_variance=design_mixture_variance,
    )
    event_timing = _build_event_timing_block(event_timing_summary)
    identity_resolution = _build_identity_resolution_block(identity_resolution_summary)
    exclusions = _build_exclusion_block(exclusion_summary)

    return {
        "experiment_id": experiment_id,
        "metric_type": metric_type,
        "primary_metric_name": primary_metric_name,
        "exposures_total": exposures_total,
        "conversions_total": conversions_total,
        "disclaimer": translate("live_stats.disclaimer"),
        "srm": srm,
        "comparisons": comparisons,
        "sequential": sequential,
        "cuped": cuped,
        "stratified": stratified,
        "guardrail": guardrail,
        "holdout": holdout,
        "event_timing": event_timing,
        "identity_resolution": identity_resolution,
        "exclusions": exclusions,
    }
