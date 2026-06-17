"""Decision Readout — synthesize one ship / no-ship / keep-running verdict.

Every live-experiment signal already exists separately in the live-stats payload
(``services.live_stats_service.build_live_stats``): frequentist effect + CI + significance,
Bayesian P(B>A), SRM, and the group-sequential boundary crossing. The operator still has to
assemble the decision by hand. This module does that assembly — **no new statistics**, only
rules over the fields the live-stats engine already produced.

Output is structured (verdict + confidence codes, and reason/blocker *codes* with numeric
params), not prose: the frontend renders it through the ``results.decision`` i18n namespace so
the readout localizes for free and the rule branches stay byte-stable under test.

Rule summary (thresholds in ``constants.py``):

* **SRM mismatch** -> hard blocker; the verdict is forced to ``no_ship`` because a broken
  assignment makes every downstream number untrustworthy.
* **Win** (=> ship): a treatment is frequentist-significant with a positive effect, its Bayesian
  P(B>A) clears ``DECISION_SHIP_PROBABILITY``, and — for sequential designs — it has crossed the
  O'Brien-Fleming boundary (the peeking guard).
* **Loss** (=> no_ship): a treatment is significant with a negative effect (boundary-confirmed
  when sequential).
* **Inconclusive** CI that still straddles 0: ``keep_running`` while information is still
  accruing, or ``no_ship`` once a sequential design has reached its planned size.

Guardrails are intentionally *not* a rule here: guardrail metrics are design-time declarations
(``report.metrics_plan.guardrail``); the execution-layer MVP does not ingest or measure them on
live data, so there is nothing to breach yet. Wiring guardrail measurement into ingestion would
be the natural place to add a guardrail blocker later.
"""

from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    DECISION_INFO_FRACTION_COMPLETE,
    DECISION_SHIP_PROBABILITY,
    DECISION_STRONG_PROBABILITY,
)

Verdict = str  # "ship" | "no_ship" | "keep_running"
Confidence = str  # "high" | "medium" | "low"


def _reason(code: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "params": params}


def synthesize_decision(live_stats: dict[str, Any]) -> dict[str, Any]:
    """Collapse a live-stats payload into a single decision readout.

    Returns ``{experiment_id, verdict, confidence, reasons[], blockers[]}`` where each reason /
    blocker is ``{code, params}`` for the frontend to localize and format."""
    experiment_id = live_stats.get("experiment_id", "")
    srm = live_stats.get("srm", {})
    comparisons = live_stats.get("comparisons", [])
    sequential = live_stats.get("sequential", {})
    exposures_total = int(live_stats.get("exposures_total", 0))

    blockers: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []

    # --- Hard blocker: sample-ratio mismatch invalidates everything downstream ----------------
    if srm.get("is_srm"):
        blockers.append(_reason("srm_mismatch", p_value=srm.get("p_value")))

    sequential_active = sequential.get("status") == "active"
    info_fraction = sequential.get("information_fraction") if sequential_active else None
    sequential_complete = (
        sequential_active
        and info_fraction is not None
        and info_fraction >= DECISION_INFO_FRACTION_COMPLETE
    )

    wins, losses, inconclusive, evaluable = _classify(comparisons, sequential_active)

    # --- No usable data yet -------------------------------------------------------------------
    if not evaluable:
        if exposures_total == 0:
            reasons.append(_reason("no_exposures"))
        else:
            reasons.append(_reason("insufficient_per_arm"))
        # A blocker can technically co-exist (SRM needs exposures, so in practice it will not),
        # but if one is present it still dominates the verdict.
        verdict = "no_ship" if blockers else "keep_running"
        return _result(experiment_id, verdict, "low", reasons, blockers)

    # --- SRM blocker dominates a data-bearing readout too -------------------------------------
    if blockers:
        reasons.append(_reason("blocked_untrustworthy"))
        return _result(experiment_id, "no_ship", "low", reasons, blockers)

    # --- Ship: at least one boundary-confirmed positive win -----------------------------------
    if wins:
        strong = sequential_complete or any(
            win["prob"] is not None and win["prob"] >= DECISION_STRONG_PROBABILITY for win in wins
        )
        for win in wins:
            reasons.append(
                _reason(
                    "significant_win",
                    arm=win["arm"],
                    effect_relative=win["effect_relative"],
                    p_value=win["p_value"],
                )
            )
            if win["prob"] is not None:
                reasons.append(_reason("bayesian_win", arm=win["arm"], probability=win["prob"]))
            if sequential_active:
                reasons.append(_reason("sequential_crossed", arm=win["arm"]))
        # A losing arm alongside a winner is still worth surfacing.
        for loss in losses:
            reasons.append(
                _reason("significant_loss", arm=loss["arm"], effect_relative=loss["effect_relative"])
            )
        return _result(experiment_id, "ship", "high" if strong else "medium", reasons, blockers)

    # --- No ship: every evaluable arm is a confirmed loss -------------------------------------
    if losses and not inconclusive:
        strong = sequential_complete or any(
            loss["prob"] is not None and loss["prob"] <= 1 - DECISION_STRONG_PROBABILITY
            for loss in losses
        )
        for loss in losses:
            reasons.append(
                _reason("significant_loss", arm=loss["arm"], effect_relative=loss["effect_relative"])
            )
        return _result(experiment_id, "no_ship", "high" if strong else "medium", reasons, blockers)

    # --- Mixed losses + inconclusive, or purely inconclusive ----------------------------------
    for loss in losses:
        reasons.append(
            _reason("significant_loss", arm=loss["arm"], effect_relative=loss["effect_relative"])
        )
    for item in inconclusive:
        if item["frequentist_significant"] and sequential_active and not item["sequential_significant"]:
            # Frequentist-significant but the sequential boundary is not crossed yet: the classic
            # "do not peek" case — keep running rather than acting on an unconfirmed crossing.
            reasons.append(_reason("sequential_not_crossed", arm=item["arm"]))
        else:
            reasons.append(_reason("inconclusive_ci", arm=item["arm"]))

    if sequential_complete:
        # Ran the full planned course and still no detectable effect -> stop, do not ship.
        reasons.append(_reason("info_fraction_complete_no_effect"))
        return _result(experiment_id, "no_ship", "medium", reasons, blockers)

    if sequential_active and info_fraction is not None:
        reasons.append(_reason("info_fraction_incomplete", information_fraction=info_fraction))
    return _result(experiment_id, "keep_running", "low", reasons, blockers)


def _classify(
    comparisons: list[dict[str, Any]], sequential_active: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Bucket each control-vs-treatment comparison into win / loss / inconclusive.

    ``evaluable`` is False when no comparison carries a usable frequentist analysis yet."""
    wins: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    inconclusive: list[dict[str, Any]] = []
    evaluable = False

    for comparison in comparisons:
        analysis = comparison.get("analysis")
        if comparison.get("status") != "ok" or not analysis:
            continue
        evaluable = True
        arm = comparison.get("treatment_index")
        effect = analysis.get("observed_effect", 0.0)
        significant = bool(analysis.get("is_significant"))
        prob = comparison.get("probability_treatment_beats_control")
        sequential_significant = comparison.get("sequential_significant")

        # Sequential designs only "confirm" a result once the boundary is crossed; fixed-horizon
        # designs have no such gate (read once at the planned size).
        boundary_ok = (sequential_significant is True) if sequential_active else True
        bayesian_ok = prob is None or prob >= DECISION_SHIP_PROBABILITY

        record = {
            "arm": arm,
            "effect_relative": analysis.get("observed_effect_relative"),
            "p_value": analysis.get("p_value"),
            "prob": prob,
            "frequentist_significant": significant,
            "sequential_significant": sequential_significant,
        }

        if significant and effect > 0 and boundary_ok and bayesian_ok:
            wins.append(record)
        elif significant and effect < 0 and boundary_ok:
            losses.append(record)
        else:
            inconclusive.append(record)

    return wins, losses, inconclusive, evaluable


def _result(
    experiment_id: str,
    verdict: Verdict,
    confidence: Confidence,
    reasons: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "verdict": verdict,
        "confidence": confidence,
        "reasons": reasons,
        "blockers": blockers,
    }
