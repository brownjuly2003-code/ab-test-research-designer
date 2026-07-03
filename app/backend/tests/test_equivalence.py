"""Tests for the TOST equivalence estimator (``stats/equivalence.py``): two one-sided Welch t-tests
that conclude the two arms are equivalent within ``±margin``.

The expected p-values / CIs below are frozen ``scipy.stats.t`` values (computed at authoring time:
``max(sf((d+m)/se, df), cdf((d-m)/se, df))`` for the TOST p-value and ``d ± t.ppf(1-alpha, df)*se``
for the (1-2*alpha) decision interval), so the test stays stdlib-only and CI-safe. Covers the
p-value against those constants, the CI ⇔ equivalence duality, arm-swap symmetry, margin monotonicity,
the degenerate guard, the positive-margin guard, Cohen's d and a Monte-Carlo type-I check.
"""

import math
import random

import pytest

from app.backend.app.stats.equivalence import tost_equivalence_test


def _run(cm, cs, cn, tm, ts, tn, margin, alpha=0.05):
    return tost_equivalence_test(
        control_mean=cm,
        control_std=cs,
        control_n=cn,
        treatment_mean=tm,
        treatment_std=ts,
        treatment_n=tn,
        margin=margin,
        alpha=alpha,
    )


# --- p-value and CI vs frozen scipy constants ----------------------------------------------


def test_symmetric_arms_match_scipy() -> None:
    # control ~ (0, sd 1, n 100), treatment ~ (0.1, sd 1, n 100): SE = sqrt(0.02), Welch df = 198.
    result = _run(0.0, 1.0, 100, 0.1, 1.0, 100, 0.5)
    assert result is not None
    assert result["effect"] == pytest.approx(0.1, abs=1e-12)
    assert result["degrees_of_freedom"] == pytest.approx(198.0, abs=1e-9)
    assert result["p_value"] == pytest.approx(0.0025794245, abs=1e-6)
    assert result["is_equivalent"] is True
    # The reported interval is the (1 - 2*alpha) = 90% TOST decision interval.
    assert result["ci_level"] == pytest.approx(0.90, abs=1e-12)
    assert result["ci_lower"] == pytest.approx(-0.1337109228, abs=1e-6)
    assert result["ci_upper"] == pytest.approx(0.3337109228, abs=1e-6)


def test_effect_beyond_margin_is_not_equivalent() -> None:
    # Effect of 2.0 against a margin of 1.0: the difference exceeds the tolerance, so equivalence is
    # firmly rejected and the binding (upper) one-sided p-value is close to 1.
    result = _run(10.0, 2.0, 50, 12.0, 2.1, 50, 1.0)
    assert result is not None
    assert result["effect"] == pytest.approx(2.0, abs=1e-12)
    assert result["p_value"] == pytest.approx(0.9917192121, abs=1e-6)
    assert result["is_equivalent"] is False


def test_ci_equivalence_duality() -> None:
    # TOST concludes equivalence at alpha iff the (1 - 2*alpha) CI lies entirely inside (-m, +m).
    result = _run(5.0, 1.5, 40, 5.05, 1.4, 40, 0.6)
    assert result is not None
    margin = result["margin"]
    inside = -margin < result["ci_lower"] and result["ci_upper"] < margin
    assert result["is_equivalent"] == inside
    assert result["p_value"] == pytest.approx(0.0470111818, abs=1e-6)
    assert result["ci_lower"] == pytest.approx(-0.4900725976, abs=1e-6)
    assert result["ci_upper"] == pytest.approx(0.5900725976, abs=1e-6)


# --- structural properties ------------------------------------------------------------------


def test_arm_swap_symmetry() -> None:
    # Swapping the arms negates the effect and the CI but leaves the TOST p-value and the equivalence
    # decision unchanged (the margin is symmetric).
    forward = _run(0.0, 1.0, 80, 0.2, 1.1, 90, 0.5)
    swapped = _run(0.2, 1.1, 90, 0.0, 1.0, 80, 0.5)
    assert forward is not None and swapped is not None
    assert forward["effect"] == pytest.approx(-swapped["effect"], abs=1e-12)
    assert forward["p_value"] == pytest.approx(swapped["p_value"], abs=1e-12)
    assert forward["is_equivalent"] == swapped["is_equivalent"]
    assert forward["ci_lower"] == pytest.approx(-swapped["ci_upper"], abs=1e-12)
    assert forward["ci_upper"] == pytest.approx(-swapped["ci_lower"], abs=1e-12)


def test_p_value_decreases_as_margin_widens() -> None:
    # A wider equivalence margin makes equivalence easier to demonstrate, so the TOST p-value falls
    # monotonically as the margin grows.
    base = (0.0, 1.0, 60, 0.15, 1.0, 60)
    p_small = _run(*base, 0.3)["p_value"]
    p_mid = _run(*base, 0.6)["p_value"]
    p_large = _run(*base, 1.0)["p_value"]
    assert p_small > p_mid > p_large


def test_cohens_d_pooled() -> None:
    # Equal-variance arms (sd 2, n 50 each): pooled SD = 2, so Cohen's d = effect / 2.
    result = _run(0.0, 2.0, 50, 1.0, 2.0, 50, 1.5)
    assert result is not None
    assert result["cohens_d"] == pytest.approx(1.0 / 2.0, abs=1e-9)


def test_power_achieved_bounds() -> None:
    result = _run(0.0, 1.0, 200, 0.0, 1.0, 200, 0.5)
    assert result is not None
    assert 0.0 <= result["power_achieved"] <= 1.0
    # A precise sample with a generous margin and a zero observed effect should have high power.
    assert result["power_achieved"] > 0.9


# --- guards ---------------------------------------------------------------------------------


def test_near_degenerate_arms_are_robust() -> None:
    # The schema enforces std > 0, so the standard error is always strictly positive and the
    # defensive None guard (parity with the continuous analyzer) is unreachable through the API.
    # Vanishing dispersion with a zero observed effect collapses the CI onto 0 → equivalent.
    result = _run(5.0, 1e-9, 5, 5.0, 1e-9, 5, 1.0)
    assert result is not None
    assert result["is_equivalent"] is True
    assert result["ci_lower"] == pytest.approx(0.0, abs=1e-7)
    assert result["ci_upper"] == pytest.approx(0.0, abs=1e-7)


def test_non_positive_margin_raises() -> None:
    with pytest.raises(ValueError):
        _run(0.0, 1.0, 30, 0.1, 1.0, 30, 0.0)
    with pytest.raises(ValueError):
        _run(0.0, 1.0, 30, 0.1, 1.0, 30, -0.5)


# --- Monte-Carlo type-I control -------------------------------------------------------------


def test_type_one_error_under_boundary_truth() -> None:
    # When the true difference sits exactly on the equivalence boundary (delta = margin), the TOST
    # falsely declaring equivalence should happen at most ~alpha of the time. Sampling normal arms,
    # the empirical rate must stay well under a loose 2*alpha ceiling.
    rng = random.Random(20260629)
    margin = 1.0
    alpha = 0.05
    n = 40
    trials = 400
    false_equivalent = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(n)]
        treatment = [rng.gauss(margin, 1.0) for _ in range(n)]  # true effect == margin (boundary)
        cm = sum(control) / n
        tm = sum(treatment) / n
        cs = math.sqrt(sum((x - cm) ** 2 for x in control) / (n - 1))
        ts = math.sqrt(sum((x - tm) ** 2 for x in treatment) / (n - 1))
        result = _run(cm, cs, n, tm, ts, n, margin, alpha)
        if result is not None and result["is_equivalent"]:
            false_equivalent += 1
    assert false_equivalent / trials <= 2 * alpha


# --- sizing (calculate_tost_sample_size) -----------------------------------------------------
# Frozen references from the P2.1 verification run (scratchpad verify_sizing_vs_scipy.py):
# the classic Chow-Shao-Wang equivalence-of-means example sigma 0.10 / margin 0.05 / alpha 0.05 /
# power 0.80 gives n = 69 (closed form 68.51; Monte-Carlo Welch-TOST power 0.802); the second case
# sigma 20 / margin 2.0 gives n = 1713 (analytic power 0.8001, n-1 -> 0.7998).

from app.backend.app.stats.equivalence import calculate_tost_sample_size, tost_power  # noqa: E402


def test_sizing_matches_chow_shao_wang_example() -> None:
    plan = calculate_tost_sample_size(
        baseline_mean=1.0, std_dev=0.10, equivalence_margin_pct=5.0, alpha=0.05, power=0.80
    )
    assert plan["sample_size_per_variant"] == 69
    assert plan["equivalence_margin_absolute"] == pytest.approx(0.05)


def test_sizing_second_frozen_case() -> None:
    plan = calculate_tost_sample_size(
        baseline_mean=100.0, std_dev=20.0, equivalence_margin_pct=2.0, alpha=0.05, power=0.80
    )
    assert plan["sample_size_per_variant"] == 1713


def test_sizing_returns_minimal_n() -> None:
    plan = calculate_tost_sample_size(
        baseline_mean=1.0, std_dev=0.10, equivalence_margin_pct=5.0, alpha=0.05, power=0.80
    )
    n = plan["sample_size_per_variant"]
    assert tost_power(n, 0.10, 0.05, 0.05) >= 0.80
    assert tost_power(n - 1, 0.10, 0.05, 0.05) < 0.80


def test_sizing_power_uses_level_alpha_not_half() -> None:
    # TOST is a level-alpha procedure: each one-sided test runs at alpha (Berger & Hsu 1996).
    # If the implementation wrongly split alpha/2 the required n would be visibly larger.
    at_alpha = calculate_tost_sample_size(1.0, 0.10, 5.0, 0.05, 0.80)
    at_half = calculate_tost_sample_size(1.0, 0.10, 5.0, 0.025, 0.80)
    assert at_alpha["sample_size_per_variant"] < at_half["sample_size_per_variant"]


def test_sizing_margin_monotonicity() -> None:
    wide = calculate_tost_sample_size(1.0, 0.10, 10.0, 0.05, 0.80)
    narrow = calculate_tost_sample_size(1.0, 0.10, 2.5, 0.05, 0.80)
    assert narrow["sample_size_per_variant"] > wide["sample_size_per_variant"]


def test_sizing_assumptions_state_margin_drive_and_zero_difference() -> None:
    plan = calculate_tost_sample_size(1.0, 0.10, 5.0, 0.05, 0.80)
    text = " ".join(plan["assumptions"])
    assert "margin" in text
    assert "MDE" in text
    assert "ZERO" in text


def test_sizing_multivariant_applies_bonferroni() -> None:
    three = calculate_tost_sample_size(1.0, 0.10, 5.0, 0.05, 0.80, variants_count=3)
    assert three["adjusted_alpha"] == pytest.approx(0.025)
    assert three["sample_size_per_variant"] > 69


def test_sizing_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        calculate_tost_sample_size(0.0, 0.10, 5.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_tost_sample_size(1.0, 0.0, 5.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_tost_sample_size(1.0, 0.10, 0.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_tost_sample_size(1.0, 0.10, 5.0, 1.5, 0.80)
