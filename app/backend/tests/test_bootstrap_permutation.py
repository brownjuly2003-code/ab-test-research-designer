"""Tests for the resampling estimator (``stats/bootstrap_permutation.py``): a permutation test for
the difference in means plus a percentile bootstrap CI.

Covers: the exact small-sample p-value against a hand enumeration (the C(8,4)=70 split count is exact
and stdlib-checkable, no scipy needed), the exact↔Monte-Carlo threshold, mean-difference recovery,
arm-swap antisymmetry of the p-value (identical in the exact regime), reproducibility under the fixed
seed, monotonicity of p in the shift, a clean-shift CI that excludes zero, Cohen's d, the degenerate
guards, and Monte-Carlo proofs of type-I control under H0 and power under a real shift.
"""

import math
import random

import pytest

from app.backend.app.stats.bootstrap_permutation import (
    DEFAULT_RESAMPLES,
    bootstrap_permutation_test,
)


# --- exact small-sample p-value vs hand enumeration ----------------------------------------


def test_exact_small_sample_matches_enumeration() -> None:
    # control=[1,2,3,4], treatment=[5,6,7,8]: observed mean difference = 6.5 − 2.5 = 4.0. Over the
    # C(8,4)=70 relabellings the only ones with |Δ| ≥ 4 are the two extreme splits ({5,6,7,8} → +4
    # and {1,2,3,4} → −4), so the exact two-sided permutation p-value is exactly 2/70.
    result = bootstrap_permutation_test([1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0])
    assert result is not None
    assert result["is_exact"] is True
    assert result["n_resamples"] == 70
    assert result["observed_diff"] == pytest.approx(4.0)
    assert result["p_value"] == pytest.approx(2 / 70, abs=1e-12)
    assert result["is_significant"] is True
    # Cohen's d on the pooled SD (both arms have variance 5/3): 4.0 / sqrt(5/3) = 3.0984.
    assert result["cohens_d"] == pytest.approx(4.0 / math.sqrt(5 / 3), abs=1e-3)


def test_exact_threshold_switches_to_monte_carlo() -> None:
    # C(6,3)=20 ≤ default budget -> exact; two arms of 20 (C(40,20) ≈ 1.4e11) -> Monte Carlo.
    small = bootstrap_permutation_test([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    assert small is not None and small["is_exact"] is True and small["n_resamples"] == 20
    big = bootstrap_permutation_test([float(i) for i in range(20)], [float(i) + 1.0 for i in range(20)])
    assert big is not None and big["is_exact"] is False
    assert big["n_resamples"] == DEFAULT_RESAMPLES


def test_mean_difference_is_recovered() -> None:
    control = [3.0, 5.0, 1.0, 8.0, 2.0, 7.0]
    treatment = [6.0, 9.0, 4.0, 10.0, 5.0, 11.0]
    result = bootstrap_permutation_test(control, treatment)
    assert result is not None
    expected = sum(treatment) / len(treatment) - sum(control) / len(control)
    assert result["observed_diff"] == pytest.approx(expected)
    assert result["control_mean"] == pytest.approx(sum(control) / len(control))
    assert result["treatment_mean"] == pytest.approx(sum(treatment) / len(treatment))


def test_arm_swap_flips_effect_and_keeps_pvalue() -> None:
    # In the exact regime the permutation p-value is deterministic and symmetric under arm swap;
    # the observed difference flips sign and Cohen's d flips with it.
    control = [1.0, 2.0, 3.0, 4.0, 5.0]
    treatment = [4.0, 6.0, 8.0, 9.0, 11.0]
    forward = bootstrap_permutation_test(control, treatment)
    reverse = bootstrap_permutation_test(treatment, control)
    assert forward is not None and reverse is not None
    assert forward["is_exact"] and reverse["is_exact"]
    assert forward["observed_diff"] == pytest.approx(-reverse["observed_diff"])
    assert forward["p_value"] == pytest.approx(reverse["p_value"])
    assert forward["cohens_d"] == pytest.approx(-reverse["cohens_d"])


def test_reproducible_under_fixed_seed() -> None:
    # The Monte-Carlo p-value and bootstrap interval must be identical across calls on identical
    # inputs (fixed seed) — no run-to-run drift in the API response.
    control = [random.Random(1).gauss(0.0, 1.0) for _ in range(40)]
    treatment = [random.Random(2).gauss(0.5, 1.0) for _ in range(40)]
    first = bootstrap_permutation_test(control, treatment)
    second = bootstrap_permutation_test(control, treatment)
    assert first is not None and second is not None
    assert first["is_exact"] is False
    assert first["p_value"] == second["p_value"]
    assert first["ci_lower"] == second["ci_lower"]
    assert first["ci_upper"] == second["ci_upper"]


def test_pvalue_monotone_in_treatment_shift() -> None:
    control = [float(i) for i in range(20)]
    p_values = []
    for shift in (0.0, 2.0, 5.0, 10.0):
        result = bootstrap_permutation_test(control, [c + shift for c in control])
        assert result is not None
        p_values.append(result["p_value"])
    assert p_values[0] > p_values[1] > p_values[2] > p_values[3]


def test_clean_shift_is_significant_and_ci_excludes_zero() -> None:
    control = [float(i) for i in range(30)]
    result = bootstrap_permutation_test(control, [c + 6.0 for c in control], alpha=0.05)
    assert result is not None
    assert result["is_significant"] is True
    assert result["p_value"] < 0.05
    assert result["ci_lower"] > 0.0
    assert result["observed_diff"] == pytest.approx(6.0)


def test_cohens_d_sign_tracks_effect() -> None:
    positive = bootstrap_permutation_test([1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0])
    negative = bootstrap_permutation_test([5.0, 6.0, 7.0, 8.0], [1.0, 2.0, 3.0, 4.0])
    assert positive is not None and negative is not None
    assert positive["cohens_d"] is not None and positive["cohens_d"] > 0
    assert negative["cohens_d"] is not None and negative["cohens_d"] < 0


# --- robustness: the reason a distribution-free mean test exists ----------------------------


def test_detects_mean_shift_without_normality() -> None:
    # Skewed (lognormal) arms with a genuine upward shift: the permutation test keys on the pooled
    # exchangeability null, not on a normal-sampling assumption the data would violate.
    rng = random.Random(909)
    control = [rng.lognormvariate(0.0, 0.5) for _ in range(60)]
    treatment = [rng.lognormvariate(0.5, 0.5) for _ in range(60)]
    result = bootstrap_permutation_test(control, treatment, alpha=0.05)
    assert result is not None
    assert result["observed_diff"] > 0
    assert result["is_significant"] is True


# --- Monte-Carlo: type-I control under H0 and power under a real shift ----------------------


def test_monte_carlo_type_one_error_near_alpha() -> None:
    """Under H0 (both arms from the same distribution) the permutation test rejects at roughly the
    nominal rate. A small resample budget keeps the test fast; the permutation test stays valid."""
    rng = random.Random(20260629)
    alpha = 0.05
    trials = 250
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(30)]
        treatment = [rng.gauss(0.0, 1.0) for _ in range(30)]
        result = bootstrap_permutation_test(control, treatment, alpha=alpha, n_resamples=299)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    empirical = rejections / trials
    assert 0.02 <= empirical <= 0.10, empirical


def test_monte_carlo_power_under_real_shift() -> None:
    rng = random.Random(77)
    trials = 200
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(30)]
        treatment = [rng.gauss(0.9, 1.0) for _ in range(30)]
        result = bootstrap_permutation_test(control, treatment, alpha=0.05, n_resamples=299)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    assert rejections / trials > 0.6


# --- degenerate guards ---------------------------------------------------------------------


def test_empty_arm_is_none() -> None:
    assert bootstrap_permutation_test([], [1.0, 2.0]) is None
    assert bootstrap_permutation_test([1.0, 2.0], []) is None


def test_all_values_identical_is_valid_p_one() -> None:
    # A fully tied pooled sample is not degenerate for a mean test: the difference is 0, every
    # relabelling is "as extreme", so p = 1 and Cohen's d is undefined (pooled SD collapses).
    result = bootstrap_permutation_test([5.0, 5.0, 5.0], [5.0, 5.0, 5.0])
    assert result is not None
    assert result["observed_diff"] == 0.0
    assert result["p_value"] == pytest.approx(1.0)
    assert result["is_significant"] is False
    assert result["cohens_d"] is None
    assert result["ci_lower"] == pytest.approx(0.0)
    assert result["ci_upper"] == pytest.approx(0.0)


def test_invalid_alpha_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_permutation_test([1.0, 2.0], [3.0, 4.0], alpha=0.0)
    with pytest.raises(ValueError):
        bootstrap_permutation_test([1.0, 2.0], [3.0, 4.0], alpha=1.0)


def test_invalid_n_resamples_raises() -> None:
    with pytest.raises(ValueError):
        bootstrap_permutation_test([1.0, 2.0], [3.0, 4.0], n_resamples=0)


def test_non_finite_values_raise() -> None:
    with pytest.raises(ValueError):
        bootstrap_permutation_test([1.0, float("nan")], [3.0, 4.0])
    with pytest.raises(ValueError):
        bootstrap_permutation_test([1.0, 2.0], [float("inf"), 4.0])


def test_pvalue_and_power_bounded() -> None:
    result = bootstrap_permutation_test([1.0, 2.0, 3.0, 100.0], [2.0, 3.0, 4.0, 5.0])
    assert result is not None
    assert 0.0 <= result["p_value"] <= 1.0
    assert 0.0 <= result["power_achieved"] <= 1.0
    assert math.isfinite(result["test_statistic"])
