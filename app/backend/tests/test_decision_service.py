"""Decision Readout — rule coverage for the ship / no-ship / keep-running synthesis.

The synthesizer adds no statistics; it classifies the *existing* live-stats signals. Most cases
drive ``build_live_stats`` over realistic aggregates so the decision is exercised over genuine
frequentist/Bayesian/SRM output; the sequential-crossing and information-fraction branches use a
hand-built live-stats dict where engineering a crossing through the real planner is awkward.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.services.decision_service import synthesize_decision
from app.backend.app.services.live_stats_service import build_live_stats


# --- builders -------------------------------------------------------------------------


def _binary_design(*, n_looks: int = 1, variants_count: int = 2, traffic_split=None) -> dict:
    return {
        "metrics": {
            "primary_metric_name": "purchase",
            "metric_type": "binary",
            "baseline_value": 0.10,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
        },
        "setup": {
            "traffic_split": traffic_split or [50, 50],
            "variants_count": variants_count,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
        },
        "constraints": {
            "n_looks": n_looks,
            "analysis_mode": "frequentist",
            "seasonality_present": False,
            "active_campaigns_present": False,
            "long_test_possible": True,
            "credibility": 0.95,
        },
    }


def _arm(index: int, exposed: int, converted: int) -> dict:
    return {
        "variation_index": index,
        "exposed_users": exposed,
        "converted_users": converted,
        "value_sum": 0.0,
        "value_sq_sum": 0.0,
    }


def _aggregates(*arms: dict) -> dict:
    return {"experiment_id": "e", "metric_name": "purchase", "variations": list(arms)}


def _decide(design: dict, *arms: dict) -> dict:
    return synthesize_decision(build_live_stats("e", design, _aggregates(*arms)))


def _codes(items: list[dict]) -> list[str]:
    return [item["code"] for item in items]


# --- no usable data -------------------------------------------------------------------


def test_no_exposures_keeps_running() -> None:
    decision = _decide(_binary_design(), _arm(0, 0, 0), _arm(1, 0, 0))
    assert decision["verdict"] == "keep_running"
    assert decision["confidence"] == "low"
    assert "no_exposures" in _codes(decision["reasons"])
    assert decision["blockers"] == []


def test_insufficient_per_arm_keeps_running() -> None:
    decision = _decide(_binary_design(), _arm(0, 1, 0), _arm(1, 1, 1))
    assert decision["verdict"] == "keep_running"
    assert "insufficient_per_arm" in _codes(decision["reasons"])


# --- blockers -------------------------------------------------------------------------


def test_srm_mismatch_is_a_blocker_forcing_no_ship() -> None:
    # 5000 vs 3000 against a planned 50/50 split is a hard sample-ratio mismatch.
    decision = _decide(_binary_design(), _arm(0, 5000, 500), _arm(1, 3000, 360))
    assert decision["verdict"] == "no_ship"
    assert decision["confidence"] == "low"
    assert "srm_mismatch" in _codes(decision["blockers"])
    assert "blocked_untrustworthy" in _codes(decision["reasons"])


# --- ship -----------------------------------------------------------------------------


def test_clear_positive_result_ships_with_high_confidence() -> None:
    # 10% control vs 12% treatment at n=5000/arm: significant, P(B>A) ~ 1.0, balanced split.
    decision = _decide(_binary_design(), _arm(0, 5000, 500), _arm(1, 5000, 600))
    assert decision["verdict"] == "ship"
    assert decision["confidence"] == "high"
    codes = _codes(decision["reasons"])
    assert "significant_win" in codes
    assert "bayesian_win" in codes
    assert decision["blockers"] == []
    win = next(r for r in decision["reasons"] if r["code"] == "significant_win")
    assert win["params"]["arm"] == 1
    assert win["params"]["effect_relative"] is not None


def test_ship_reports_a_losing_arm_alongside_the_winner() -> None:
    design = _binary_design(variants_count=3, traffic_split=[34, 33, 33])
    decision = _decide(
        design,
        _arm(0, 5000, 500),  # control 10%
        _arm(1, 5000, 650),  # treatment 13% -> win
        _arm(2, 5000, 350),  # treatment 7% -> loss
    )
    assert decision["verdict"] == "ship"
    reasons = decision["reasons"]
    win_arms = [r["params"]["arm"] for r in reasons if r["code"] == "significant_win"]
    loss_arms = [r["params"]["arm"] for r in reasons if r["code"] == "significant_loss"]
    assert win_arms == [1]
    assert loss_arms == [2]


# --- no ship --------------------------------------------------------------------------


def test_significant_negative_result_does_not_ship() -> None:
    # Treatment 8% is significantly worse than control 12% at n=5000/arm.
    decision = _decide(_binary_design(), _arm(0, 5000, 600), _arm(1, 5000, 400))
    assert decision["verdict"] == "no_ship"
    assert decision["confidence"] == "high"
    assert "significant_loss" in _codes(decision["reasons"])
    assert decision["blockers"] == []


# --- keep running ---------------------------------------------------------------------


def test_inconclusive_ci_keeps_running_under_fixed_horizon() -> None:
    # 50/500 vs 52/500: tiny, non-significant difference -> CI straddles zero.
    decision = _decide(_binary_design(), _arm(0, 500, 50), _arm(1, 500, 52))
    assert decision["verdict"] == "keep_running"
    assert decision["confidence"] == "low"
    assert "inconclusive_ci" in _codes(decision["reasons"])


def test_sequential_significant_but_boundary_not_crossed_keeps_running() -> None:
    # n_looks=3: the fixed-horizon test is significant, but the O'Brien-Fleming boundary is not
    # crossed at this early information fraction -> do not act on the unconfirmed crossing.
    decision = _decide(_binary_design(n_looks=3), _arm(0, 5000, 500), _arm(1, 5000, 600))
    assert decision["verdict"] == "keep_running"
    assert "sequential_not_crossed" in _codes(decision["reasons"])


# --- sequential branches via a hand-built live-stats payload --------------------------


def _live_stats(*, comparisons: list[dict], sequential: dict, exposures_total: int = 1000, srm=None) -> dict:
    return {
        "experiment_id": "e",
        "metric_type": "binary",
        "primary_metric_name": "purchase",
        "exposures_total": exposures_total,
        "conversions_total": 100,
        "disclaimer": "",
        "srm": srm or {"status": "ok", "is_srm": False, "p_value": 0.9},
        "comparisons": comparisons,
        "sequential": sequential,
        "cuped": {"status": "not_applicable"},
    }


def _ok_comparison(*, arm: int, effect: float, significant: bool, prob, seq_sig, effect_relative=0.2, p_value=0.01) -> dict:
    return {
        "treatment_index": arm,
        "status": "ok",
        "control": {},
        "treatment": {},
        "analysis": {
            "observed_effect": effect,
            "observed_effect_relative": effect_relative,
            "p_value": p_value,
            "is_significant": significant,
        },
        "probability_treatment_beats_control": prob,
        "sequential_significant": seq_sig,
        "note": None,
    }


def test_sequential_crossing_with_strong_probability_ships() -> None:
    decision = synthesize_decision(
        _live_stats(
            comparisons=[_ok_comparison(arm=1, effect=0.02, significant=True, prob=0.999, seq_sig=True)],
            sequential={"status": "active", "information_fraction": 1.0},
        )
    )
    assert decision["verdict"] == "ship"
    assert decision["confidence"] == "high"
    assert "sequential_crossed" in _codes(decision["reasons"])


def test_sequential_complete_without_effect_is_no_ship() -> None:
    decision = synthesize_decision(
        _live_stats(
            comparisons=[_ok_comparison(arm=1, effect=0.001, significant=False, prob=0.6, seq_sig=False)],
            sequential={"status": "active", "information_fraction": 1.0},
        )
    )
    assert decision["verdict"] == "no_ship"
    assert decision["confidence"] == "medium"
    assert "info_fraction_complete_no_effect" in _codes(decision["reasons"])


def test_sequential_incomplete_inconclusive_keeps_running_with_fraction_note() -> None:
    decision = synthesize_decision(
        _live_stats(
            comparisons=[_ok_comparison(arm=1, effect=0.001, significant=False, prob=0.6, seq_sig=False)],
            sequential={"status": "active", "information_fraction": 0.4},
        )
    )
    assert decision["verdict"] == "keep_running"
    fraction_reason = next(r for r in decision["reasons"] if r["code"] == "info_fraction_incomplete")
    assert fraction_reason["params"]["information_fraction"] == 0.4


def test_positive_but_weak_probability_does_not_ship() -> None:
    # Frequentist-significant positive effect, but P(B>A) below the ship threshold (0.95) ->
    # not a win; it stays inconclusive and keeps running under a fixed horizon.
    decision = synthesize_decision(
        _live_stats(
            comparisons=[_ok_comparison(arm=1, effect=0.02, significant=True, prob=0.80, seq_sig=None)],
            sequential={"status": "fixed_horizon", "n_looks": 1},
        )
    )
    assert decision["verdict"] == "keep_running"
    assert "ship" not in decision["verdict"]
