"""Guardrail breach math (F4): the directed one-sided regression test that flags a treatment
which significantly degrades a protected metric beyond a tolerated margin.

Verified against the one-sided non-inferiority framing (ICH E10; Kohavi et al. guardrail metrics):
the harm is signed by direction, the breach decision and the one-sided p-value never disagree
(``harm_lower_bound > margin`` ⇔ ``p < α``), a tolerance margin suppresses small degradations, and
a Monte-Carlo run under the null keeps the breach rate at the one-sided α (no false alarms).
"""

from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats import guardrail


# --- direction + status helpers -------------------------------------------------------


def test_harm_in_direction_signs_by_direction() -> None:
    assert guardrail.harm_in_direction(0.1, guardrail.INCREASE_IS_BAD) == pytest.approx(0.1)
    assert guardrail.harm_in_direction(0.1, guardrail.DECREASE_IS_BAD) == pytest.approx(-0.1)
    assert guardrail.harm_in_direction(-0.2, guardrail.DECREASE_IS_BAD) == pytest.approx(0.2)


def test_harm_in_direction_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError, match="direction"):
        guardrail.harm_in_direction(0.1, "sideways")


def test_worst_status_picks_most_severe() -> None:
    assert guardrail.worst_status([]) == guardrail.STATUS_OK
    assert guardrail.worst_status(["ok", "ok"]) == guardrail.STATUS_OK
    assert guardrail.worst_status(["ok", "warning"]) == guardrail.STATUS_WARNING
    assert guardrail.worst_status(["ok", "breached", "warning"]) == guardrail.STATUS_BREACHED


# --- evaluate_guardrail: the three statuses -------------------------------------------


def test_clear_breach_when_harm_dominates_variance() -> None:
    # +10pp degradation with a tiny SE: harm is many SEs past the (zero) margin.
    result = guardrail.evaluate_guardrail(
        0.10, 0.02**2, direction=guardrail.INCREASE_IS_BAD, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_BREACHED
    assert result["is_breached"] is True
    assert result["harm"] == pytest.approx(0.10)
    # one-sided lower bound = harm - z_{0.95}*SE, z_{0.95} ≈ 1.6449
    assert result["harm_lower_bound"] == pytest.approx(0.10 - 1.6448536 * 0.02, abs=1e-6)
    assert result["harm_lower_bound"] > result["margin"]
    assert result["p_value"] < 0.05


def test_warning_when_point_degrades_but_not_significant() -> None:
    # +3pp point degradation but a wide SE: harm > margin yet the lower bound does not clear it.
    result = guardrail.evaluate_guardrail(
        0.03, 0.05**2, direction=guardrail.INCREASE_IS_BAD, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_WARNING
    assert result["is_breached"] is False
    assert result["harm"] > result["margin"]
    assert result["harm_lower_bound"] < result["margin"]
    assert result["p_value"] >= 0.05


def test_ok_when_treatment_improves_the_metric() -> None:
    # A −5pp move on an increase-is-bad metric is an improvement: harm is negative, never a breach.
    result = guardrail.evaluate_guardrail(
        -0.05, 0.01**2, direction=guardrail.INCREASE_IS_BAD, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_OK
    assert result["is_breached"] is False
    assert result["harm"] == pytest.approx(-0.05)
    assert result["p_value"] > 0.5


def test_decrease_is_bad_flips_the_harmful_direction() -> None:
    # Revenue (decrease_is_bad) drops by 0.10: that is +0.10 of harm -> breach with a small SE.
    result = guardrail.evaluate_guardrail(
        -0.10, 0.02**2, direction=guardrail.DECREASE_IS_BAD, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_BREACHED
    assert result["harm"] == pytest.approx(0.10)


def test_decrease_is_bad_increase_is_safe() -> None:
    # Revenue rises by 0.10 on a decrease_is_bad metric: harm is negative -> ok.
    result = guardrail.evaluate_guardrail(
        0.10, 0.02**2, direction=guardrail.DECREASE_IS_BAD, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_OK
    assert result["harm"] == pytest.approx(-0.10)


# --- the tolerance margin -------------------------------------------------------------


def test_margin_absorbs_degradation_within_tolerance() -> None:
    # +3pp degradation, but a 5pp margin tolerates it even with a tiny SE: not even a warning.
    result = guardrail.evaluate_guardrail(
        0.03, 0.005**2, direction=guardrail.INCREASE_IS_BAD, margin=0.05, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_OK
    assert result["is_breached"] is False


def test_margin_still_breaches_when_harm_exceeds_it_significantly() -> None:
    # +10pp degradation against a 5pp margin with a small SE: the excess (5pp) is significant.
    result = guardrail.evaluate_guardrail(
        0.10, 0.01**2, direction=guardrail.INCREASE_IS_BAD, margin=0.05, alpha=0.05
    )
    assert result is not None
    assert result["status"] == guardrail.STATUS_BREACHED
    # z is computed on the excess over the margin, not the raw harm.
    assert result["test_statistic"] == pytest.approx((0.10 - 0.05) / 0.01, abs=1e-6)


# --- internal duality + edge cases ----------------------------------------------------


@pytest.mark.parametrize(
    ("effect", "variance", "margin"),
    [
        (0.08, 0.03**2, 0.0),
        (0.02, 0.04**2, 0.0),
        (0.12, 0.02**2, 0.05),
        (-0.03, 0.01**2, 0.0),
        (0.05, 0.05**2, 0.02),
    ],
)
def test_breach_flag_matches_pvalue_and_bound(effect: float, variance: float, margin: float) -> None:
    # The three breach signals are one decision: bound clears margin <=> p < alpha <=> is_breached.
    alpha = 0.05
    result = guardrail.evaluate_guardrail(
        effect, variance, direction=guardrail.INCREASE_IS_BAD, margin=margin, alpha=alpha
    )
    assert result is not None
    assert result["is_breached"] == (result["p_value"] < alpha)
    assert result["is_breached"] == (result["harm_lower_bound"] > margin)


def test_non_positive_variance_is_unevaluable() -> None:
    assert (
        guardrail.evaluate_guardrail(0.1, 0.0, direction=guardrail.INCREASE_IS_BAD) is None
    )
    assert (
        guardrail.evaluate_guardrail(0.1, -1.0, direction=guardrail.INCREASE_IS_BAD) is None
    )


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError, match="direction"):
        guardrail.evaluate_guardrail(0.1, 0.01, direction="up")
    with pytest.raises(ValueError, match="margin"):
        guardrail.evaluate_guardrail(0.1, 0.01, direction=guardrail.INCREASE_IS_BAD, margin=-0.1)
    with pytest.raises(ValueError, match="alpha"):
        guardrail.evaluate_guardrail(0.1, 0.01, direction=guardrail.INCREASE_IS_BAD, alpha=1.0)


# --- Monte-Carlo calibration: no false alarms under the null --------------------------


def test_breach_rate_under_null_stays_at_one_sided_alpha() -> None:
    """Under H0 (control and treatment share the same rate, zero true harm, zero margin) the breach
    rate of the one-sided α-level test should sit at α, not above it — the guardrail does not cry
    wolf on noise. This is the directed analogue of the always-valid / FDR calibration proofs."""
    rng = random.Random(20260626)
    alpha = 0.05
    trials = 3000
    n = 800
    rate = 0.2
    breaches = 0
    for _ in range(trials):
        c_conv = sum(1 for _ in range(n) if rng.random() < rate)
        t_conv = sum(1 for _ in range(n) if rng.random() < rate)
        p_c = c_conv / n
        p_t = t_conv / n
        effect = p_t - p_c
        variance = p_c * (1 - p_c) / n + p_t * (1 - p_t) / n
        result = guardrail.evaluate_guardrail(
            effect, variance, direction=guardrail.INCREASE_IS_BAD, alpha=alpha
        )
        if result is not None and result["is_breached"]:
            breaches += 1
    breach_rate = breaches / trials
    # One-sided test at α=0.05 under H0 -> ~0.05; allow Monte-Carlo slack (SE ≈ 0.004).
    assert breach_rate < 0.075


def test_detects_a_real_regression() -> None:
    # Contrast to the null test: a true +5pp regression is caught almost every time at this size.
    rng = random.Random(11)
    n = 4000
    c_rate, t_rate = 0.20, 0.25
    detections = 0
    trials = 200
    for _ in range(trials):
        c_conv = sum(1 for _ in range(n) if rng.random() < c_rate)
        t_conv = sum(1 for _ in range(n) if rng.random() < t_rate)
        p_c = c_conv / n
        p_t = t_conv / n
        variance = p_c * (1 - p_c) / n + p_t * (1 - p_t) / n
        result = guardrail.evaluate_guardrail(
            p_t - p_c, variance, direction=guardrail.INCREASE_IS_BAD, alpha=0.05
        )
        if result is not None and result["is_breached"]:
            detections += 1
    assert detections / trials > 0.95
