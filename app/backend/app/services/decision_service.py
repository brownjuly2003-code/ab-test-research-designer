"""Decision Readout — synthesize one ship / no-ship / keep-running verdict.

Every live-experiment signal already exists separately in the live-stats payload
(``services.live_stats_service.build_live_stats``): frequentist effect + CI + significance,
Bayesian P(B>A), SRM, and the group-sequential boundary crossing. The operator still has to
assemble the decision by hand. This module does that assembly — **no new statistics**, only
rules over the fields the live-stats engine already produced.

Output is structured (verdict + confidence codes, and reason/blocker *codes* with numeric
params), not prose: the frontend renders it through the ``results.decision`` i18n namespace so
the readout localizes for free and the rule branches stay byte-stable under test.

Rule summary (thresholds in ``constants.py`` + policy ``practical_v1`` in
``decision_policy.py`` / ADR 0001):

* **SRM mismatch** -> hard blocker; the verdict is forced to ``no_ship`` because a broken
  assignment makes every downstream number untrustworthy.
* **Statistical win**: a treatment is frequentist-significant with a positive effect, its
  Bayesian P(B>A) clears ``DECISION_SHIP_PROBABILITY``, and — for sequential designs — it has
  crossed the O'Brien-Fleming boundary (the peeking guard).
* **Practical win (=> ship)**: a statistical win whose CI lower bound clears the design
  minimum worthwhile effect (default: absolute MDE from ``mde_pct``). Trivial-but-significant
  effects no longer ship (audit F-07).
* **Loss** (=> no_ship): a treatment is significant with a negative effect (boundary-confirmed
  when sequential).
* **Fixed-horizon peeking guard**: a fixed-horizon design promises a single read at the planned
  sample size, so before ``DECISION_FIXED_HORIZON_READ_FRACTION`` of that sample is collected the
  plain z-significance carries no alpha guarantee. On such an early read a win/loss only counts
  when the anytime-valid (mSPRT) view — which stays valid under continuous monitoring — confirms
  it; otherwise the readout is ``keep_running`` with a ``fixed_horizon_before_planned_read``
  reason. Confidence on an early (anytime-valid-confirmed) call is capped at ``medium`` because
  the effect *size* read early is still winner's-curse-inflated even when its sign is certain.
  When the payload carries no planned size (older designs without sizing), the read is treated as
  the planned one — the pre-guard behavior.
* **Inconclusive** CI that still straddles 0: ``keep_running`` while information is still
  accruing, or ``no_ship`` once a sequential design has reached its planned size.

* **Guardrail breach** -> ship veto: when a declared guardrail metric is significantly degraded
  beyond its tolerance margin on live data (``live_stats.guardrail``), the verdict is forced to
  ``no_ship`` even if the primary is a win — the data is trustworthy, but the treatment harms a
  protected metric. The breach is surfaced as a blocker and the vetoed primary win is still reported.
"""

from __future__ import annotations

from typing import Any

from app.backend.app.constants import (
    DECISION_FIXED_HORIZON_READ_FRACTION,
    DECISION_INFO_FRACTION_COMPLETE,
    DECISION_SHIP_PROBABILITY,
    DECISION_STRONG_PROBABILITY,
)
from app.backend.app.services.decision_policy import (
    evaluate_practical_win,
    resolve_decision_policy,
)

Verdict = str  # "ship" | "no_ship" | "keep_running"
Confidence = str  # "high" | "medium" | "low"


def _reason(code: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "params": params}


def synthesize_decision(
    live_stats: dict[str, Any],
    *,
    project_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collapse a live-stats payload into a single decision readout.

    Returns ``{experiment_id, verdict, confidence, reasons[], blockers[], policy, evidence}``
    where each reason / blocker is ``{code, params}`` for the frontend to localize and format.
    """
    experiment_id = live_stats.get("experiment_id", "")
    srm = live_stats.get("srm", {})
    comparisons = live_stats.get("comparisons", [])
    sequential = live_stats.get("sequential", {})
    exposures_total = int(live_stats.get("exposures_total", 0))
    guardrail = live_stats.get("guardrail", {})
    guardrail_breaches = [
        metric for metric in guardrail.get("metrics", []) if metric.get("status") == "breached"
    ]
    policy = resolve_decision_policy(live_stats, project_payload=project_payload)

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
    # Fixed-horizon peeking guard: before the planned single read, z-significance alone confirms
    # nothing — only the anytime-valid view may. An unknown planned size (fraction None) is treated
    # as the planned read, matching designs stored before sizing carried through to live stats.
    fixed_horizon_fraction = (
        sequential.get("information_fraction")
        if sequential.get("status") == "fixed_horizon"
        else None
    )
    early_fixed_horizon_read = (
        fixed_horizon_fraction is not None
        and fixed_horizon_fraction < DECISION_FIXED_HORIZON_READ_FRACTION
    )
    sample_complete = sequential_complete or (
        sequential.get("status") == "fixed_horizon"
        and fixed_horizon_fraction is not None
        and fixed_horizon_fraction >= DECISION_FIXED_HORIZON_READ_FRACTION
    )

    statistical_wins, losses, inconclusive, evaluable = _classify(
        comparisons, sequential_active, early_fixed_horizon_read
    )
    practical_wins, practical_hold, practical_reject = _split_practical_wins(
        statistical_wins, policy, sample_complete
    )

    # --- No usable data yet -------------------------------------------------------------------
    if not evaluable:
        if exposures_total == 0:
            reasons.append(_reason("no_exposures"))
        else:
            reasons.append(_reason("insufficient_per_arm"))
        if not policy.get("require_practical_evidence"):
            reasons.append(_reason("practical_threshold_unavailable"))
        # A blocker can technically co-exist (SRM needs exposures, so in practice it will not),
        # but if one is present it still dominates the verdict.
        verdict = "no_ship" if blockers else "keep_running"
        return _result(
            experiment_id, verdict, "low", reasons, blockers, policy, practical_wins + practical_hold
        )

    # --- SRM blocker dominates a data-bearing readout too -------------------------------------
    if blockers and srm.get("is_srm"):
        reasons.append(_reason("blocked_untrustworthy"))
        return _result(experiment_id, "no_ship", "low", reasons, blockers, policy, statistical_wins)

    # --- Guardrail breach vetoes a ship: the data is trustworthy, but the treatment significantly
    #     degrades a protected metric, so no positive primary result justifies shipping ----------
    if guardrail_breaches:
        for breach in guardrail_breaches:
            blockers.append(_reason("guardrail_breach", metric=breach.get("name", "")))
        # A vetoed win is still worth surfacing so the operator sees what the guardrail overrode.
        for win in statistical_wins:
            reasons.append(
                _reason(
                    "significant_win",
                    arm=win["arm"],
                    effect_relative=win["effect_relative"],
                    p_value=win["p_value"],
                )
            )
            _append_practical_reason(reasons, win)
        reasons.append(_reason("guardrail_vetoed"))
        return _result(experiment_id, "no_ship", "high", reasons, blockers, policy, statistical_wins)

    # --- Ship: at least one boundary-confirmed positive win that clears practical MWE ---------
    if practical_wins:
        strong = sequential_complete or any(
            win["prob"] is not None and win["prob"] >= DECISION_STRONG_PROBABILITY
            for win in practical_wins
        )
        for win in practical_wins:
            reasons.append(
                _reason(
                    "significant_win",
                    arm=win["arm"],
                    effect_relative=win["effect_relative"],
                    p_value=win["p_value"],
                )
            )
            _append_practical_reason(reasons, win)
            if win["prob"] is not None:
                reasons.append(_reason("bayesian_win", arm=win["arm"], probability=win["prob"]))
            if sequential_active:
                reasons.append(_reason("sequential_crossed", arm=win["arm"]))
            elif early_fixed_horizon_read:
                reasons.append(_reason("anytime_valid_confirmed", arm=win["arm"]))
        # A losing arm alongside a winner is still worth surfacing.
        for loss in losses:
            reasons.append(
                _reason("significant_loss", arm=loss["arm"], effect_relative=loss["effect_relative"])
            )
        # Surface statistical wins held back only by practical threshold for transparency.
        for held in practical_hold + practical_reject:
            reasons.append(
                _reason(
                    "significant_win",
                    arm=held["arm"],
                    effect_relative=held["effect_relative"],
                    p_value=held["p_value"],
                )
            )
            _append_practical_reason(reasons, held)
        confidence = "high" if strong else "medium"
        if early_fixed_horizon_read:
            # Anytime-valid confirms the sign, but an effect size read this early is still
            # winner's-curse-inflated — never report an early ship as "high" confidence.
            confidence = "medium"
        return _result(
            experiment_id, "ship", confidence, reasons, blockers, policy, practical_wins
        )

    # --- Statistical wins present but none clear practical MWE --------------------------------
    if practical_hold or practical_reject:
        for win in practical_hold + practical_reject:
            reasons.append(
                _reason(
                    "significant_win",
                    arm=win["arm"],
                    effect_relative=win["effect_relative"],
                    p_value=win["p_value"],
                )
            )
            _append_practical_reason(reasons, win)
        for loss in losses:
            reasons.append(
                _reason("significant_loss", arm=loss["arm"], effect_relative=loss["effect_relative"])
            )
        if practical_reject and not practical_hold:
            return _result(
                experiment_id,
                "no_ship",
                "medium",
                reasons,
                blockers,
                policy,
                practical_reject,
            )
        # Uncertain practical (CI crosses MWE): keep running while sample is incomplete;
        # if sample is complete, treat as no_ship (cannot claim practical value).
        if sample_complete:
            reasons.append(_reason("statistically_positive_but_below_practical_threshold"))
            return _result(
                experiment_id,
                "no_ship",
                "medium",
                reasons,
                blockers,
                policy,
                practical_hold + practical_reject,
            )
        if sequential_active and info_fraction is not None:
            reasons.append(_reason("info_fraction_incomplete", information_fraction=info_fraction))
        elif early_fixed_horizon_read:
            reasons.append(
                _reason("info_fraction_incomplete", information_fraction=fixed_horizon_fraction)
            )
        return _result(
            experiment_id,
            "keep_running",
            "low",
            reasons,
            blockers,
            policy,
            practical_hold,
        )

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
            if early_fixed_horizon_read:
                reasons.append(_reason("anytime_valid_confirmed", arm=loss["arm"]))
        confidence = "high" if strong else "medium"
        if early_fixed_horizon_read:
            confidence = "medium"
        return _result(experiment_id, "no_ship", confidence, reasons, blockers, policy, [])

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
        elif (
            item["frequentist_significant"]
            and early_fixed_horizon_read
            and item["always_valid_significant"] is not True
        ):
            # The fixed-horizon twin of the case above: the z-test looks significant, but this is
            # an early read of a single-look design and the anytime-valid view does not back it —
            # acting now would be exactly the peeking the design warns about.
            reasons.append(
                _reason(
                    "fixed_horizon_before_planned_read",
                    arm=item["arm"],
                    information_fraction=fixed_horizon_fraction,
                )
            )
        else:
            reasons.append(_reason("inconclusive_ci", arm=item["arm"]))

    if sequential_complete:
        # Ran the full planned course and still no detectable effect -> stop, do not ship.
        reasons.append(_reason("info_fraction_complete_no_effect"))
        return _result(experiment_id, "no_ship", "medium", reasons, blockers, policy, [])

    if sequential_active and info_fraction is not None:
        reasons.append(_reason("info_fraction_incomplete", information_fraction=info_fraction))
    elif early_fixed_horizon_read:
        reasons.append(
            _reason("info_fraction_incomplete", information_fraction=fixed_horizon_fraction)
        )
    return _result(experiment_id, "keep_running", "low", reasons, blockers, policy, [])


def _split_practical_wins(
    statistical_wins: list[dict[str, Any]],
    policy: dict[str, Any],
    sample_complete: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition statistical wins into practical / uncertain / proven-below-MWE."""
    practical: list[dict[str, Any]] = []
    hold: list[dict[str, Any]] = []
    reject: list[dict[str, Any]] = []
    for win in statistical_wins:
        analysis = win.get("analysis") or {}
        evaluation = evaluate_practical_win(
            policy=policy, analysis=analysis, sample_complete=sample_complete
        )
        enriched = {**win, "practical": evaluation}
        status = evaluation["status"]
        if status in {"met", "unavailable"}:
            # unavailable = no MWE configured → statistical win ships (compat path).
            practical.append(enriched)
        elif status == "proven_below":
            reject.append(enriched)
        else:
            hold.append(enriched)
    return practical, hold, reject


def _append_practical_reason(reasons: list[dict[str, Any]], win: dict[str, Any]) -> None:
    practical = win.get("practical") or {}
    status = practical.get("status")
    if status == "met":
        reasons.append(
            _reason(
                "practical_threshold_met",
                arm=win["arm"],
                mwe=practical.get("mwe"),
                ci_lower=practical.get("ci_lower"),
            )
        )
    elif status == "uncertain":
        reasons.append(
            _reason(
                "practical_threshold_uncertain",
                arm=win["arm"],
                mwe=practical.get("mwe"),
                ci_lower=practical.get("ci_lower"),
                ci_upper=practical.get("ci_upper"),
            )
        )
    elif status == "proven_below":
        reasons.append(
            _reason(
                "below_practical_threshold_proven",
                arm=win["arm"],
                mwe=practical.get("mwe"),
                ci_upper=practical.get("ci_upper"),
            )
        )
    elif status == "unavailable" and win.get("practical") is not None:
        # Only when policy itself has no MWE (compat); omit noise if never evaluated.
        pass


def _classify(
    comparisons: list[dict[str, Any]],
    sequential_active: bool,
    early_fixed_horizon_read: bool,
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
        always_valid_significant = (comparison.get("always_valid") or {}).get("is_significant")

        # Sequential designs only "confirm" a result once the boundary is crossed. A fixed-horizon
        # design confirms at its planned single read; *before* that point the z-test carries no
        # alpha guarantee, so only the anytime-valid (mSPRT) view — valid under continuous
        # monitoring — may confirm an early result.
        if sequential_active:
            boundary_ok = sequential_significant is True
        elif early_fixed_horizon_read:
            boundary_ok = always_valid_significant is True
        else:
            boundary_ok = True
        bayesian_ok = prob is None or prob >= DECISION_SHIP_PROBABILITY

        record = {
            "arm": arm,
            "effect_relative": analysis.get("observed_effect_relative"),
            "p_value": analysis.get("p_value"),
            "prob": prob,
            "frequentist_significant": significant,
            "sequential_significant": sequential_significant,
            "always_valid_significant": always_valid_significant,
            "analysis": analysis,
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
    policy: dict[str, Any],
    winning_arms: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = {
        "policy_version": policy.get("version"),
        "minimum_worthwhile_effect": policy.get("minimum_worthwhile_effect"),
        "mwe_source": policy.get("mwe_source"),
        "planned_power": policy.get("planned_power"),
        "require_practical_evidence": policy.get("require_practical_evidence"),
        "winning_arms": [
            {
                "arm": win.get("arm"),
                "effect_relative": win.get("effect_relative"),
                "p_value": win.get("p_value"),
                "practical": win.get("practical"),
            }
            for win in winning_arms
        ],
        # Explicitly not used for the verdict (audit F-07): post-hoc observed power.
        "power_achieved_not_used": True,
    }
    return {
        "experiment_id": experiment_id,
        "verdict": verdict,
        "confidence": confidence,
        "reasons": reasons,
        "blockers": blockers,
        "policy": policy,
        "evidence": evidence,
    }
