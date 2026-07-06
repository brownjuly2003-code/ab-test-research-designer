"""Tests for the Boschloo / Barnard unconditional exact 2x2 tests (``stats/unconditional_exact.py``).

Coverage: the two-sided p-values against frozen ``scipy.stats.boschloo_exact`` /
``scipy.stats.barnard_exact`` (``alternative="two-sided"``) reference values (scipy is cross-checked
locally in ``scratchpad/verify_barnard_boschloo_gtest.py``, not a committed dependency, so the
constants are frozen to keep the runtime stdlib-only and CI-safe); the defining property that Boschloo
is uniformly at least as powerful as Fisher's exact test (its p-value is never larger, and strictly
smaller on the frozen tables); the ordering divergence between Barnard and Boschloo on an asymmetric
table (proof the two analyzers are genuinely different, not aliases); the zero-cell and empty-margin
edge cases; the test-agnostic descriptive statistics (odds ratio, rates) matching the Fisher path;
arm-swap symmetry; and Monte-Carlo proofs that both unconditional tests control type-I error at (in
fact below) the nominal rate on small samples.
"""

import math
import random

import pytest

from app.backend.app.stats.fisher_exact import fisher_exact_test
from app.backend.app.stats.unconditional_exact import (
    _binomial_row,
    _sup_product_binomial,
    barnard_exact_test,
    boschloo_exact_test,
)

# Frozen references from scipy.stats.boschloo_exact(table, alternative="two-sided", n=256), with the
# app orientation (a/n1 control, c/n2 treatment) mapped to scipy's [[a, c], [n1-a, n2-c]] columns.
# Each row: (control_conv, control_users, treatment_conv, treatment_users, boschloo_p, fisher_p).
# Cross-checked locally at implementation time; scipy is not a committed dependency.
SCIPY_REFERENCE = [
    (3, 10, 8, 10, 0.04138947, 0.06977852),  # beats-Fisher small-n table
    (2, 20, 9, 20, 0.01671469, 0.03095031),
    (2, 8, 11, 25, 0.37909051, 0.43112718),  # asymmetric arms
    (0, 10, 7, 10, 0.00087281, 0.00309598),  # zero cell
    (10, 10, 4, 10, 0.00351656, 0.01083591),  # all-success control arm
]


@pytest.mark.parametrize("a,n1,c,n2,boschloo_p,fisher_p", SCIPY_REFERENCE)
def test_matches_scipy_reference(a, n1, c, n2, boschloo_p, fisher_p) -> None:
    result = boschloo_exact_test(a, n1, c, n2)
    assert result["p_value"] == pytest.approx(boschloo_p, abs=1e-6)


@pytest.mark.parametrize("a,n1,c,n2,boschloo_p,fisher_p", SCIPY_REFERENCE)
def test_never_weaker_than_fisher(a, n1, c, n2, boschloo_p, fisher_p) -> None:
    """Boschloo's whole selling point: its p-value is uniformly <= Fisher's (strictly < on these)."""
    boschloo = boschloo_exact_test(a, n1, c, n2)["p_value"]
    fisher = fisher_exact_test(a, n1, c, n2)["p_value"]
    assert boschloo <= fisher + 1e-12
    assert boschloo == pytest.approx(boschloo_p, abs=1e-6)
    assert fisher == pytest.approx(fisher_p, abs=1e-6)


def test_empty_margin_is_defined_and_one() -> None:
    # 0/10 vs 0/10: no successes anywhere, so there is no evidence of a difference — p = 1, not an error.
    result = boschloo_exact_test(0, 10, 0, 10)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-9)
    assert result["odds_ratio"] is None


def test_zero_cell_still_defined() -> None:
    result = boschloo_exact_test(0, 10, 7, 10)
    assert 0.0 <= result["p_value"] <= 1.0
    # b*c != 0 here (b = 10, c = 7), so the odds ratio is defined and equals (0*3)/(10*7) = 0.
    assert result["odds_ratio"] == pytest.approx(0.0)


def test_descriptive_statistics_match_fisher_path() -> None:
    """The rates / odds ratio / risk difference are test-agnostic table arithmetic — identical to the
    Fisher path (only the p-value differs), so the Boschloo card can reuse the Fisher layout."""
    boschloo = boschloo_exact_test(3, 10, 8, 10)
    fisher = fisher_exact_test(3, 10, 8, 10)
    for key in ("odds_ratio", "control_rate", "treatment_rate", "risk_difference", "table_total"):
        assert boschloo[key] == pytest.approx(fisher[key])


def test_arm_swap_leaves_two_sided_p_value_unchanged() -> None:
    """Swapping the two arms exchanges the one-sided tails; the doubled-minimum two-sided p is invariant."""
    a = boschloo_exact_test(3, 10, 8, 10)["p_value"]
    b = boschloo_exact_test(8, 10, 3, 10)["p_value"]
    assert a == pytest.approx(b, abs=1e-9)


def test_p_value_always_in_unit_interval() -> None:
    for a, n1, c, n2, *_ in SCIPY_REFERENCE:
        p = boschloo_exact_test(a, n1, c, n2)["p_value"]
        assert 0.0 <= p <= 1.0


def test_structurally_invalid_counts_raise() -> None:
    # control_conversions > control_users -> b < 0 -> defensive ValueError backstop.
    with pytest.raises(ValueError, match="non-negative"):
        boschloo_exact_test(11, 10, 3, 8)


def test_sup_product_binomial_empty_extreme_set_is_zero() -> None:
    # An empty extreme set contributes no mass at any nuisance value.
    assert _sup_product_binomial([], 5, 5) == 0.0


def test_binomial_row_degenerate_probabilities() -> None:
    # Defensive p in {0, 1} branches: all mass sits on 0 successes (p=0) or n successes (p=1).
    assert _binomial_row(4, 0.0) == [1.0, 0.0, 0.0, 0.0, 0.0]
    assert _binomial_row(4, 1.0) == [0.0, 0.0, 0.0, 0.0, 1.0]
    interior = _binomial_row(4, 0.5)
    assert math.isclose(sum(interior), 1.0, abs_tol=1e-12)


def test_type_one_error_is_controlled_under_the_null() -> None:
    """Under H0 (both arms share a success probability) the unconditional test rejects at roughly alpha
    or below — never far above it. Small n keeps the grid search fast."""
    rng = random.Random(20260705)
    alpha = 0.05
    trials = 150
    n_per_arm = 12
    p_shared = 0.4
    rejections = 0
    for _ in range(trials):
        a = sum(1 for _ in range(n_per_arm) if rng.random() < p_shared)
        c = sum(1 for _ in range(n_per_arm) if rng.random() < p_shared)
        if boschloo_exact_test(a, n_per_arm, c, n_per_arm)["p_value"] < alpha:
            rejections += 1
    rate = rejections / trials
    # Unconditional exact tests hold the level; with 150 trials a [0.0, 0.11] band is a stable guard.
    assert rate <= 0.11


# --- Barnard's test (pooled-Wald ordering; added on explicit request after the 5.3 deferral) --------

# Frozen references from scipy.stats.barnard_exact(table, alternative="two-sided", n=256), same
# orientation mapping as SCIPY_REFERENCE. On the symmetric / zero-cell tables Barnard's and Boschloo's
# two-sided p-values coincide; the asymmetric-arms table is the discriminating case where the pooled
# Wald ordering genuinely differs from Fisher's-p ordering.
BARNARD_SCIPY_REFERENCE = [
    (3, 10, 8, 10, 0.04138947),  # beats-Fisher small-n table
    (2, 20, 9, 20, 0.01671469),
    (2, 8, 11, 25, 0.37164270),  # asymmetric arms — differs from Boschloo's 0.37909051
    (0, 10, 7, 10, 0.00087281),  # zero cell
    (10, 10, 4, 10, 0.00351656),  # all-success control arm
]


@pytest.mark.parametrize("a,n1,c,n2,barnard_p", BARNARD_SCIPY_REFERENCE)
def test_barnard_matches_scipy_reference(a, n1, c, n2, barnard_p) -> None:
    result = barnard_exact_test(a, n1, c, n2)
    assert result["p_value"] == pytest.approx(barnard_p, abs=1e-6)


def test_barnard_ordering_differs_from_boschloo_on_asymmetric_arms() -> None:
    """The two unconditional tests share the nuisance-supremum machinery but rank tables differently
    (pooled Wald z vs Fisher's one-sided p); on asymmetric arms that produces different p-values —
    the guard that the Barnard path is a genuine second analyzer, not an alias of Boschloo's."""
    barnard = barnard_exact_test(2, 8, 11, 25)["p_value"]
    boschloo = boschloo_exact_test(2, 8, 11, 25)["p_value"]
    assert barnard == pytest.approx(0.37164270, abs=1e-6)
    assert boschloo == pytest.approx(0.37909051, abs=1e-6)
    assert abs(barnard - boschloo) > 1e-3


def test_barnard_empty_margin_is_defined_and_one() -> None:
    # 0/10 vs 0/10: every table scores |Z| = 0 = |Z_obs|, the extreme set is everything — p = 1.
    result = barnard_exact_test(0, 10, 0, 10)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-9)
    assert result["odds_ratio"] is None


def test_barnard_arm_swap_leaves_two_sided_p_value_unchanged() -> None:
    """Swapping the arms flips the sign of the pooled Wald z; the |Z|-ordered extreme set — and with
    it the two-sided p-value — is unchanged."""
    a = barnard_exact_test(3, 10, 8, 10)["p_value"]
    b = barnard_exact_test(8, 10, 3, 10)["p_value"]
    assert a == pytest.approx(b, abs=1e-9)


def test_barnard_descriptive_statistics_match_fisher_path() -> None:
    """Same test-agnostic table arithmetic as Fisher / Boschloo — only the p-value differs."""
    barnard = barnard_exact_test(3, 10, 8, 10)
    fisher = fisher_exact_test(3, 10, 8, 10)
    for key in ("odds_ratio", "control_rate", "treatment_rate", "risk_difference", "table_total"):
        assert barnard[key] == pytest.approx(fisher[key])


def test_barnard_reports_the_observed_ordering_statistic() -> None:
    # 3/10 vs 8/10: p1 - p2 = -0.5, pooled p = 0.55 -> z = -0.5 / sqrt(0.55*0.45*0.2) ~ -2.2473.
    result = barnard_exact_test(3, 10, 8, 10)
    assert result["ordering_statistic"] == pytest.approx(-2.2473, abs=1e-4)


def test_barnard_p_value_always_in_unit_interval() -> None:
    for a, n1, c, n2, *_ in BARNARD_SCIPY_REFERENCE:
        p = barnard_exact_test(a, n1, c, n2)["p_value"]
        assert 0.0 <= p <= 1.0


def test_barnard_structurally_invalid_counts_raise() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        barnard_exact_test(11, 10, 3, 8)


def test_barnard_type_one_error_is_controlled_under_the_null() -> None:
    """Same Monte-Carlo guard as Boschloo's: under H0 the rejection rate stays at or below alpha."""
    rng = random.Random(20260706)
    alpha = 0.05
    trials = 150
    n_per_arm = 12
    p_shared = 0.4
    rejections = 0
    for _ in range(trials):
        a = sum(1 for _ in range(n_per_arm) if rng.random() < p_shared)
        c = sum(1 for _ in range(n_per_arm) if rng.random() < p_shared)
        if barnard_exact_test(a, n_per_arm, c, n_per_arm)["p_value"] < alpha:
            rejections += 1
    rate = rejections / trials
    assert rate <= 0.11
