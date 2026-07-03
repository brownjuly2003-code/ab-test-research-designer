"""Tests for Fisher's exact 2x2 test (``stats/fisher_exact.py``).

Covers: the exact two-sided p-value against a by-hand hypergeometric computation (independently
cross-checked against ``scipy.stats.fisher_exact(alternative="two-sided")`` at authoring time — the
expected constants below are those scipy values, frozen so the test stays stdlib-only and CI-safe),
the sample odds ratio and its undefined (zero off-diagonal) case, arm-swap symmetry, monotonicity in
separation, convergence to the normal-approximation z-test on large tables, and a Monte-Carlo proof
that the exact test controls type-I error at (in fact below) the nominal rate on small samples.
"""

import math
import random
from statistics import NormalDist

import pytest

from app.backend.app.stats.fisher_exact import fisher_exact_test

_NORMAL = NormalDist()


def _pooled_two_proportion_z_p(a: int, n1: int, c: int, n2: int) -> float:
    """The pooled two-proportion z-test p-value, matching the ``_analyze_binary`` service formula."""
    p1, p2 = a / n1, c / n2
    pooled = (a + c) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se
    return 2 * (1 - _NORMAL.cdf(abs(z)))


# --- exact p-value vs hand computation (cross-checked against scipy) ------------------------


def test_canonical_table_matches_scipy() -> None:
    # [[8,2],[1,5]]: control 8/10, treatment 1/6. scipy.stats.fisher_exact -> OR=20, p=0.034965035.
    result = fisher_exact_test(8, 10, 1, 6)
    assert result["p_value"] == pytest.approx(0.034965035, abs=1e-7)
    assert result["odds_ratio"] == pytest.approx(20.0)


def test_two_sided_p_value_by_hand() -> None:
    # [[3,0],[0,3]]: margins all 3, N=6, C(6,3)=20. The control-success cell ranges 0..3 with
    # hypergeometric probabilities P(0)=1/20, P(1)=9/20, P(2)=9/20, P(3)=1/20. Observed cell is 3
    # with P=0.05; the only tables as unlikely are k=0 and k=3, so two-sided p = 0.05+0.05 = 0.10.
    result = fisher_exact_test(3, 3, 0, 3)
    assert result["p_value"] == pytest.approx(0.10)


def test_odds_ratio_is_sample_cross_ratio() -> None:
    # [[10,10],[15,5]] -> OR = (a*d)/(b*c) = (10*5)/(10*15) = 1/3.
    result = fisher_exact_test(10, 20, 15, 20)
    assert result["odds_ratio"] == pytest.approx(1.0 / 3.0)


def test_odds_ratio_undefined_when_off_diagonal_zero() -> None:
    # b = control_users - control_conversions = 0 -> denominator (b*c) = 0 -> odds ratio undefined.
    result = fisher_exact_test(10, 10, 3, 8)
    assert result["odds_ratio"] is None
    # The exact p-value is still well defined.
    assert 0.0 <= result["p_value"] <= 1.0


# --- structural properties -----------------------------------------------------------------


def test_arm_swap_leaves_p_value_and_reciprocates_odds_ratio() -> None:
    # Swapping control and treatment is a row swap of the 2x2 table: the exact two-sided p-value is
    # invariant and the sample odds ratio inverts.
    forward = fisher_exact_test(20, 100, 35, 100)
    reverse = fisher_exact_test(35, 100, 20, 100)
    assert forward["p_value"] == pytest.approx(reverse["p_value"])
    assert forward["odds_ratio"] is not None and reverse["odds_ratio"] is not None
    assert forward["odds_ratio"] == pytest.approx(1.0 / reverse["odds_ratio"])


def test_identical_rates_are_not_significant() -> None:
    # Equal proportions in both arms -> the observed table sits at the centre of the hypergeometric
    # mass -> a large p-value (near 1) and an odds ratio of 1.
    result = fisher_exact_test(50, 100, 50, 100)
    assert result["odds_ratio"] == pytest.approx(1.0)
    assert result["p_value"] > 0.9


def test_p_value_monotone_in_separation() -> None:
    # Holding the control arm fixed and pulling the treatment conversion rate further away
    # monotonically shrinks the exact p-value (stronger evidence of a difference).
    p_values = [
        fisher_exact_test(20, 100, treatment_conversions, 100)["p_value"]
        for treatment_conversions in (22, 30, 40, 55)
    ]
    assert p_values[0] > p_values[1] > p_values[2] > p_values[3]


def test_risk_difference_fields() -> None:
    result = fisher_exact_test(30, 100, 45, 100)
    assert result["control_rate"] == pytest.approx(0.30)
    assert result["treatment_rate"] == pytest.approx(0.45)
    assert result["risk_difference"] == pytest.approx(0.15)
    assert result["relative_risk_difference"] == pytest.approx(0.5)


def test_p_value_always_bounded() -> None:
    rng = random.Random(99)
    for _ in range(200):
        cu = rng.randint(2, 60)
        tu = rng.randint(2, 60)
        result = fisher_exact_test(rng.randint(0, cu), cu, rng.randint(0, tu), tu)
        assert 0.0 <= result["p_value"] <= 1.0


# --- convergence to the large-sample z-test ------------------------------------------------


def test_converges_to_normal_approximation_on_large_table() -> None:
    # On a large, non-degenerate table the exact test and the normal-approximation z-test must
    # agree closely: this is exactly the regime where the CLT approximation is good.
    a, n1, c, n2 = 520, 1000, 470, 1000
    exact = fisher_exact_test(a, n1, c, n2)
    z_p = _pooled_two_proportion_z_p(a, n1, c, n2)
    assert exact["p_value"] == pytest.approx(z_p, abs=5e-3)


# --- Monte-Carlo: exact test controls type-I error on small samples ------------------------


def test_monte_carlo_type_one_error_at_or_below_alpha() -> None:
    """Under H0 (a shared conversion rate) the exact test must not over-reject. Because the 2x2
    reference distribution is discrete, the exact test is conservative: the empirical type-I rate
    on small samples stays at or below the nominal alpha."""
    rng = random.Random(20260629)
    alpha = 0.05
    trials = 1500
    rate = 0.3
    n1, n2 = 25, 25
    rejections = 0
    for _ in range(trials):
        a = sum(1 for _ in range(n1) if rng.random() < rate)
        c = sum(1 for _ in range(n2) if rng.random() < rate)
        if fisher_exact_test(a, n1, c, n2)["p_value"] < alpha:
            rejections += 1
    empirical = rejections / trials
    # Conservative discrete test: comfortably at or under alpha (never materially above it).
    assert empirical <= 0.06, empirical


def test_monte_carlo_power_under_real_effect() -> None:
    """With a genuine rate gap the exact test rejects the great majority of the time at moderate n."""
    rng = random.Random(7)
    trials = 400
    n1, n2 = 120, 120
    rejections = 0
    for _ in range(trials):
        a = sum(1 for _ in range(n1) if rng.random() < 0.25)
        c = sum(1 for _ in range(n2) if rng.random() < 0.45)
        if fisher_exact_test(a, n1, c, n2)["p_value"] < 0.05:
            rejections += 1
    assert rejections / trials > 0.8


# --- defensive guards ----------------------------------------------------------------------


def test_negative_counts_raise() -> None:
    with pytest.raises(ValueError):
        fisher_exact_test(5, 3, 1, 4)  # conversions exceed users -> negative failure cell


def test_all_zero_conversions_is_degenerate_but_defined() -> None:
    result = fisher_exact_test(0, 10, 0, 10)
    assert result["p_value"] == pytest.approx(1.0)
    assert result["odds_ratio"] is None
    assert not math.isnan(result["p_value"])


# --- sizing (calculate_fisher_exact_sample_size / fisher_exact_power) ------------------------
# Frozen references from the P2.1 verification run (scratchpad verify_sizing_vs_scipy.py, seed
# 20260703): p0 0.20 -> p1 0.40 at alpha 0.05 / power 0.80 needs z-approx 82 but exact 90 (exact
# power 0.8017 at 90, 0.7956 at 89; simulated power via scipy.stats.fisher_exact = 0.800); p0 0.10
# -> p1 0.30 needs exact 69 (power 0.8073). scipy is cross-checked locally, not a dependency.

from app.backend.app.stats.fisher_exact import (  # noqa: E402
    MAX_FISHER_EXACT_SIZING_PER_ARM,
    calculate_fisher_exact_sample_size,
    fisher_exact_power,
)


def test_exact_power_matches_frozen_enumeration() -> None:
    assert fisher_exact_power(0.20, 0.40, 90, 0.05) == pytest.approx(0.8017, abs=2e-4)
    assert fisher_exact_power(0.20, 0.40, 89, 0.05) == pytest.approx(0.7956, abs=2e-4)


def test_sizing_matches_frozen_reference() -> None:
    plan = calculate_fisher_exact_sample_size(
        baseline_rate=0.20, mde_pct=100.0, alpha=0.05, power=0.80
    )
    assert plan["sample_size_per_variant"] == 90
    assert plan["metric_type"] == "binary"
    assert plan["mde_absolute"] == pytest.approx(0.20)


def test_sizing_second_frozen_case() -> None:
    plan = calculate_fisher_exact_sample_size(
        baseline_rate=0.10, mde_pct=200.0, alpha=0.05, power=0.80
    )
    assert plan["sample_size_per_variant"] == 69


def test_sizing_exceeds_z_approximation() -> None:
    # Fisher's conservatism: the exact plan must need MORE users than the z formula (82 here).
    plan = calculate_fisher_exact_sample_size(0.20, 100.0, 0.05, 0.80)
    assert plan["sample_size_per_variant"] > 82
    assert "82" in " ".join(plan["assumptions"])


def test_sizing_falls_back_to_cps_above_cap() -> None:
    # p0 0.05, +20% -> delta 0.01: the z seed is in the thousands, far above the enumeration cap,
    # so the Casagrande-Pike-Smith continuity-corrected formula must kick in and say so.
    plan = calculate_fisher_exact_sample_size(0.05, 20.0, 0.05, 0.80)
    assert plan["sample_size_per_variant"] > MAX_FISHER_EXACT_SIZING_PER_ARM
    assert "Casagrande" in " ".join(plan["assumptions"])


def test_cps_fallback_is_close_to_exact_at_the_boundary() -> None:
    # Near the cap the exact answer and the CPS approximation must agree closely - this is what
    # justifies the fallback. Frozen check at a small case: exact 90 vs CPS 92 (within ~3%).
    exact = calculate_fisher_exact_sample_size(0.20, 100.0, 0.05, 0.80)["sample_size_per_variant"]
    n_z = 82
    delta = 0.20
    cps = math.ceil(n_z / 4 * (1 + math.sqrt(1 + 4 / (n_z * delta))) ** 2)
    assert abs(cps - exact) / exact < 0.05


def test_sizing_multivariant_applies_bonferroni() -> None:
    two = calculate_fisher_exact_sample_size(0.20, 100.0, 0.05, 0.80, variants_count=2)
    three = calculate_fisher_exact_sample_size(0.20, 100.0, 0.05, 0.80, variants_count=3)
    assert three["adjusted_alpha"] == pytest.approx(0.025)
    assert three["sample_size_per_variant"] > two["sample_size_per_variant"]


def test_sizing_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        calculate_fisher_exact_sample_size(0.0, 100.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_fisher_exact_sample_size(0.20, -5.0, 0.05, 0.80)
    with pytest.raises(ValueError):
        calculate_fisher_exact_sample_size(0.60, 100.0, 0.05, 0.80)  # implied variant rate >= 1
    with pytest.raises(ValueError):
        fisher_exact_power(0.20, 0.40, 1, 0.05)
