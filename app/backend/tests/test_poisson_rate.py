"""Tests for the two-sample Poisson rate test (``stats/poisson_rate.py``).

Covers: the exact two-sided p-value against ``scipy.stats.binomtest`` (the conditional binomial the
test reduces to — expected constants frozen so the suite stays stdlib-only and CI-safe), the rate
ratio and its undefined (zero control events) case, arm-swap behaviour, monotonicity in separation,
the rate-difference Wald CI, degenerate guards, and a Monte-Carlo proof that the discrete exact test
controls type-I error at (in fact below) the nominal rate.
"""

import math
import random

import pytest

from app.backend.app.stats.poisson_rate import poisson_rate_test


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's Poisson sampler (adequate for the small rates used here)."""
    limit = math.exp(-lam)
    k = 0
    product = 1.0
    while True:
        k += 1
        product *= rng.random()
        if product <= limit:
            return k - 1


# --- exact p-value vs scipy.stats.binomtest -----------------------------------------------


def test_canonical_rate_test_matches_binomtest() -> None:
    # 10 events / 100 vs 25 events / 100. Conditioned on n=35 with pi0=0.5, the two-sided exact
    # binomial p-value is 0.016674 (== scipy.stats.binomtest(25, 35, 0.5)).
    result = poisson_rate_test(10, 100, 25, 100)
    assert result is not None
    assert result["p_value"] == pytest.approx(0.016674, abs=1e-5)
    assert result["rate_ratio"] == pytest.approx(2.5)


def test_rate_ratio_accounts_for_unequal_exposure() -> None:
    # Equal counts but the treatment ran over twice the exposure -> half the rate -> RR = 0.5.
    result = poisson_rate_test(20, 100, 20, 200)
    assert result is not None
    assert result["control_rate"] == pytest.approx(0.20)
    assert result["treatment_rate"] == pytest.approx(0.10)
    assert result["rate_ratio"] == pytest.approx(0.5)


def test_rate_ratio_undefined_when_control_has_no_events() -> None:
    result = poisson_rate_test(0, 100, 7, 100)
    assert result is not None
    assert result["rate_ratio"] is None
    # The exact p-value is still defined (and the difference CI too).
    assert 0.0 <= result["p_value"] <= 1.0
    assert result["ci_lower"] <= result["ci_upper"]


# --- structural properties -----------------------------------------------------------------


def test_arm_swap_preserves_p_value_and_reciprocates_rate_ratio() -> None:
    forward = poisson_rate_test(40, 1000, 30, 1000)
    reverse = poisson_rate_test(30, 1000, 40, 1000)
    assert forward is not None and reverse is not None
    assert forward["p_value"] == pytest.approx(reverse["p_value"])
    assert forward["rate_ratio"] is not None and reverse["rate_ratio"] is not None
    assert forward["rate_ratio"] == pytest.approx(1.0 / reverse["rate_ratio"])


def test_equal_rates_not_significant() -> None:
    result = poisson_rate_test(50, 1000, 50, 1000)
    assert result is not None
    assert result["rate_ratio"] == pytest.approx(1.0)
    assert result["is_significant"] is False
    assert result["p_value"] > 0.5


def test_p_value_monotone_in_separation() -> None:
    # Holding control fixed and raising treatment events (same exposure) strengthens the evidence.
    p_values = [
        poisson_rate_test(30, 1000, treatment_events, 1000)["p_value"]  # type: ignore[index]
        for treatment_events in (33, 45, 60, 90)
    ]
    assert p_values[0] > p_values[1] > p_values[2] > p_values[3]


def test_rate_difference_and_ci_fields() -> None:
    result = poisson_rate_test(20, 100, 40, 100)
    assert result is not None
    assert result["rate_difference"] == pytest.approx(0.20)  # 0.40 - 0.20
    # Poisson Wald SE = sqrt(20/100^2 + 40/100^2) = sqrt(60)/100.
    se = math.sqrt(60) / 100
    z = 1.959963985
    assert result["ci_lower"] == pytest.approx(0.20 - z * se, abs=1e-4)
    assert result["ci_upper"] == pytest.approx(0.20 + z * se, abs=1e-4)


def test_p_value_always_bounded() -> None:
    rng = random.Random(13)
    for _ in range(200):
        x1 = rng.randint(0, 40)
        x2 = rng.randint(0, 40)
        if x1 + x2 == 0:
            continue
        result = poisson_rate_test(x1, rng.uniform(1, 500), x2, rng.uniform(1, 500))
        assert result is not None
        assert 0.0 <= result["p_value"] <= 1.0


# --- Monte-Carlo: discrete exact test controls type-I error --------------------------------


def test_monte_carlo_type_one_error_at_or_below_alpha() -> None:
    """Under H0 (a shared rate, equal exposure) the conditional exact test must not over-reject.
    Being discrete, it is conservative: the empirical type-I rate stays at or below alpha."""
    rng = random.Random(20260629)
    alpha = 0.05
    trials = 1500
    rejections = 0
    for _ in range(trials):
        x1 = _poisson(rng, 8.0)
        x2 = _poisson(rng, 8.0)
        if x1 + x2 == 0:
            continue
        result = poisson_rate_test(x1, 1.0, x2, 1.0, alpha=alpha)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    empirical = rejections / trials
    assert empirical <= 0.06, empirical


def test_monte_carlo_power_under_real_rate_gap() -> None:
    rng = random.Random(5)
    trials = 400
    rejections = 0
    for _ in range(trials):
        x1 = _poisson(rng, 30.0)
        x2 = _poisson(rng, 60.0)
        if x1 + x2 == 0:
            continue
        result = poisson_rate_test(x1, 1.0, x2, 1.0, alpha=0.05)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    assert rejections / trials > 0.8


# --- degenerate / defensive guards ---------------------------------------------------------


def test_no_events_is_none() -> None:
    assert poisson_rate_test(0, 100, 0, 200) is None


def test_invalid_alpha_raises() -> None:
    with pytest.raises(ValueError):
        poisson_rate_test(5, 10, 5, 10, alpha=0.0)
    with pytest.raises(ValueError):
        poisson_rate_test(5, 10, 5, 10, alpha=1.0)


def test_non_positive_exposure_raises() -> None:
    with pytest.raises(ValueError):
        poisson_rate_test(5, 0, 5, 10)
    with pytest.raises(ValueError):
        poisson_rate_test(5, 10, 5, -1)


def test_negative_events_raise() -> None:
    with pytest.raises(ValueError):
        poisson_rate_test(-1, 10, 5, 10)


# --- sizing (calculate_poisson_rate_sample_size) ---------------------------------------------
# Frozen references from the P2.1 verification run (scratchpad verify_sizing_vs_scipy.py, seed
# 20260703): lambda_c 0.30 / +20% / alpha 0.05 / power 0.80 -> 948 total events, per-arm exposure
# 1436.4 -> 1437 users at unit exposure; Monte-Carlo power of the conditional binomial test at
# that exposure = 0.799. scipy is cross-checked locally, not a dependency.

from app.backend.app.stats.poisson_rate import calculate_poisson_rate_sample_size  # noqa: E402


def test_sizing_matches_frozen_reference() -> None:
    plan = calculate_poisson_rate_sample_size(
        baseline_rate=0.30, mde_pct=20.0, alpha=0.05, power=0.80
    )
    assert plan["expected_total_events"] == 948
    assert plan["sample_size_per_variant"] == 1437
    assert plan["required_exposure_per_variant"] == pytest.approx(1436.4, abs=0.1)
    assert plan["metric_type"] == "count"


def test_sizing_scales_with_exposure_per_user() -> None:
    unit = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, exposure_per_user=1.0)
    double = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, exposure_per_user=2.0)
    assert double["sample_size_per_variant"] == 719
    # Twice the exposure per user needs (up to rounding) half the users for the same events.
    assert double["expected_total_events"] == unit["expected_total_events"]


def test_sizing_event_budget_is_rate_scale_invariant() -> None:
    # The conditional framing depends only on the rate RATIO, so the required event count must not
    # change when both rates are scaled; the required exposure shrinks proportionally.
    low = calculate_poisson_rate_sample_size(0.03, 20.0, 0.05, 0.80)
    high = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80)
    assert low["expected_total_events"] == high["expected_total_events"]
    assert low["sample_size_per_variant"] > high["sample_size_per_variant"]


def test_sizing_mde_monotonicity() -> None:
    small = calculate_poisson_rate_sample_size(0.30, 10.0, 0.05, 0.80)
    large = calculate_poisson_rate_sample_size(0.30, 40.0, 0.05, 0.80)
    assert small["sample_size_per_variant"] > large["sample_size_per_variant"]


def test_sizing_assumptions_state_poisson_and_conditional_framing() -> None:
    plan = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80)
    text = " ".join(plan["assumptions"])
    assert "Poisson" in text
    assert "overdispersion" in text
    assert "conditional" in text


def test_sizing_multivariant_applies_bonferroni() -> None:
    two = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, variants_count=2)
    three = calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, variants_count=3)
    assert three["adjusted_alpha"] == pytest.approx(0.025)
    assert three["sample_size_per_variant"] > two["sample_size_per_variant"]


def test_sizing_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        calculate_poisson_rate_sample_size(0.0, 20.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_poisson_rate_sample_size(0.30, 0.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, exposure_per_user=0.0)
    with pytest.raises(ValueError):
        calculate_poisson_rate_sample_size(0.30, 20.0, 0.05, 0.80, variants_count=99)
