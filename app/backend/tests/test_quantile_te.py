"""Tests for the quantile treatment-effect estimator (``stats/quantile_te.py``): a permutation test
for the difference of a chosen quantile plus a percentile bootstrap CI.

Covers: the exact small-sample p-value against an independent brute-force enumeration (using
``statistics.median`` as a second quantile implementation for the q = 0.5 path — no scipy needed),
the exact↔Monte-Carlo threshold, quantile recovery at the median and at p90, the motivating
tail-only case where the median is unmoved but an upper quantile shifts, arm-swap antisymmetry of the
effect with an unchanged p-value in the exact regime, reproducibility under the fixed seed,
monotonicity of p in the shift, a clean-shift CI that excludes zero, the degenerate guards, and
Monte-Carlo proofs of type-I control under H0 and power under a real shift.
"""

import math
import random
from itertools import combinations
from statistics import median

import pytest

from app.backend.app.stats.quantile_te import (
    DEFAULT_RESAMPLES,
    quantile_treatment_effect_test,
)


def _brute_force_exact_p_median(control: list[float], treatment: list[float]) -> float:
    """Independent exact two-sided permutation p-value for the *median* difference, computed with
    ``statistics.median`` (a different quantile implementation than the module's interpolation rule,
    which nonetheless coincides at q = 0.5). Used as a gold-standard reference for the exact path."""
    pooled = control + treatment
    total = len(pooled)
    n_treatment = len(treatment)
    observed = abs(median(treatment) - median(control))
    extreme = 0
    count = 0
    for combo in combinations(range(total), n_treatment):
        chosen = set(combo)
        t_sub = [pooled[i] for i in combo]
        c_sub = [pooled[i] for i in range(total) if i not in chosen]
        if abs(median(t_sub) - median(c_sub)) >= observed - 1e-9:
            extreme += 1
        count += 1
    return extreme / count


# --- exact small-sample p-value vs an independent enumeration --------------------------------


def test_exact_median_matches_brute_force_enumeration() -> None:
    control = [1.0, 2.0, 3.0, 4.0]
    treatment = [5.0, 6.0, 7.0, 8.0]
    result = quantile_treatment_effect_test(control, treatment, quantile=0.5)
    assert result is not None
    assert result["is_exact"] is True
    assert result["n_resamples"] == 70  # C(8, 4)
    # The module's linear-interpolation median agrees with statistics.median for even n.
    assert result["control_quantile"] == pytest.approx(median(control))
    assert result["treatment_quantile"] == pytest.approx(median(treatment))
    assert result["observed_diff"] == pytest.approx(4.0)
    assert result["p_value"] == pytest.approx(
        _brute_force_exact_p_median(control, treatment), abs=1e-12
    )


def test_exact_threshold_switches_to_monte_carlo() -> None:
    # C(6, 3) = 20 <= default budget -> exact; two arms of 20 (C(40, 20) ~ 1.4e11) -> Monte Carlo.
    small = quantile_treatment_effect_test([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], quantile=0.5)
    assert small is not None and small["is_exact"] is True and small["n_resamples"] == 20
    big = quantile_treatment_effect_test(
        [float(i) for i in range(20)], [float(i) + 1.0 for i in range(20)], quantile=0.5
    )
    assert big is not None and big["is_exact"] is False
    assert big["n_resamples"] == DEFAULT_RESAMPLES


# --- quantile recovery -----------------------------------------------------------------------


def test_recovers_requested_quantile_at_p90() -> None:
    control = [float(i) for i in range(1, 101)]  # 1..100
    treatment = [float(i) + 10.0 for i in range(1, 101)]  # 11..110
    result = quantile_treatment_effect_test(control, treatment, quantile=0.9, n_resamples=499)
    assert result is not None
    assert result["quantile"] == 0.9
    # 90th percentile (linear interpolation) of 1..100 is 90.1; the +10 shift moves it to 100.1.
    assert result["control_quantile"] == pytest.approx(90.1)
    assert result["treatment_quantile"] == pytest.approx(100.1)
    assert result["observed_diff"] == pytest.approx(10.0)


def test_tail_only_shift_moves_upper_quantile_not_median() -> None:
    # The lower ~80% of both arms is identical; only the treatment's upper tail is inflated. The
    # median effect is ~0 while the p90 effect is large and positive — exactly what a mean / median
    # test would miss and a quantile effect is built to see.
    control = [float(i) for i in range(1, 21)]  # 1..20
    treatment = [float(i) for i in range(1, 17)] + [40.0, 42.0, 44.0, 46.0]
    at_median = quantile_treatment_effect_test(control, treatment, quantile=0.5, n_resamples=499)
    at_p90 = quantile_treatment_effect_test(control, treatment, quantile=0.9, n_resamples=499)
    assert at_median is not None and at_p90 is not None
    assert at_median["observed_diff"] == pytest.approx(0.0)
    assert at_p90["observed_diff"] > 15.0


# --- symmetry, reproducibility, monotonicity -------------------------------------------------


def test_arm_swap_flips_effect_and_keeps_pvalue() -> None:
    control = [1.0, 2.0, 3.0, 4.0, 5.0]
    treatment = [4.0, 6.0, 8.0, 9.0, 11.0]
    forward = quantile_treatment_effect_test(control, treatment, quantile=0.5)
    reverse = quantile_treatment_effect_test(treatment, control, quantile=0.5)
    assert forward is not None and reverse is not None
    assert forward["is_exact"] and reverse["is_exact"]
    assert forward["observed_diff"] == pytest.approx(-reverse["observed_diff"])
    assert forward["p_value"] == pytest.approx(reverse["p_value"])


def test_reproducible_under_fixed_seed() -> None:
    control = [random.Random(1).gauss(0.0, 1.0) for _ in range(40)]
    treatment = [random.Random(2).gauss(0.5, 1.0) for _ in range(40)]
    first = quantile_treatment_effect_test(control, treatment, quantile=0.5)
    second = quantile_treatment_effect_test(control, treatment, quantile=0.5)
    assert first is not None and second is not None
    assert first["is_exact"] is False
    assert first["p_value"] == second["p_value"]
    assert first["ci_lower"] == second["ci_lower"]
    assert first["ci_upper"] == second["ci_upper"]


def test_pvalue_monotone_in_treatment_shift() -> None:
    control = [float(i) for i in range(20)]
    p_values = []
    for shift in (0.0, 3.0, 7.0, 14.0):
        result = quantile_treatment_effect_test(
            control, [c + shift for c in control], quantile=0.5, n_resamples=999
        )
        assert result is not None
        p_values.append(result["p_value"])
    assert p_values[0] > p_values[1] > p_values[2] >= p_values[3]


def test_clean_shift_is_significant_and_ci_excludes_zero() -> None:
    # Two tight clusters a constant apart: the median shift is unambiguous.
    control = [1.0] * 15 + [2.0] * 15
    treatment = [11.0] * 15 + [12.0] * 15
    result = quantile_treatment_effect_test(control, treatment, quantile=0.5, n_resamples=999)
    assert result is not None
    assert result["is_significant"] is True
    assert result["p_value"] < 0.05
    assert result["ci_lower"] > 0.0
    assert result["observed_diff"] == pytest.approx(10.0)


def test_detects_median_shift_on_skewed_data() -> None:
    rng = random.Random(909)
    control = [rng.lognormvariate(0.0, 0.5) for _ in range(60)]
    treatment = [rng.lognormvariate(0.6, 0.5) for _ in range(60)]
    result = quantile_treatment_effect_test(control, treatment, quantile=0.5, n_resamples=499)
    assert result is not None
    assert result["observed_diff"] > 0
    assert result["is_significant"] is True


# --- Monte-Carlo: type-I control under H0 and power under a real shift ------------------------


def test_monte_carlo_type_one_error_near_alpha() -> None:
    rng = random.Random(20260629)
    alpha = 0.05
    trials = 250
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(30)]
        treatment = [rng.gauss(0.0, 1.0) for _ in range(30)]
        result = quantile_treatment_effect_test(
            control, treatment, quantile=0.5, alpha=alpha, n_resamples=299
        )
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    empirical = rejections / trials
    assert 0.01 <= empirical <= 0.10, empirical


def test_monte_carlo_power_under_real_shift() -> None:
    rng = random.Random(77)
    trials = 200
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(40)]
        treatment = [rng.gauss(1.1, 1.0) for _ in range(40)]
        result = quantile_treatment_effect_test(
            control, treatment, quantile=0.5, alpha=0.05, n_resamples=299
        )
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    assert rejections / trials > 0.5


# --- degenerate guards -----------------------------------------------------------------------


def test_empty_arm_is_none() -> None:
    assert quantile_treatment_effect_test([], [1.0, 2.0], quantile=0.5) is None
    assert quantile_treatment_effect_test([1.0, 2.0], [], quantile=0.5) is None


def test_all_values_identical_is_valid_p_one() -> None:
    # A fully tied pooled sample is not degenerate for a quantile test: the difference is 0, every
    # relabelling is "as extreme", so p = 1 and the bootstrap interval collapses to [0, 0].
    result = quantile_treatment_effect_test([5.0, 5.0, 5.0], [5.0, 5.0, 5.0], quantile=0.5)
    assert result is not None
    assert result["observed_diff"] == 0.0
    assert result["p_value"] == pytest.approx(1.0)
    assert result["is_significant"] is False
    assert result["ci_lower"] == pytest.approx(0.0)
    assert result["ci_upper"] == pytest.approx(0.0)
    assert result["test_statistic"] == 0.0


def test_invalid_alpha_raises() -> None:
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [3.0, 4.0], quantile=0.5, alpha=0.0)
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [3.0, 4.0], quantile=0.5, alpha=1.0)


def test_invalid_quantile_raises() -> None:
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [3.0, 4.0], quantile=0.0)
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [3.0, 4.0], quantile=1.0)


def test_invalid_n_resamples_raises() -> None:
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [3.0, 4.0], quantile=0.5, n_resamples=0)


def test_non_finite_values_raise() -> None:
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, float("nan")], [3.0, 4.0], quantile=0.5)
    with pytest.raises(ValueError):
        quantile_treatment_effect_test([1.0, 2.0], [float("inf"), 4.0], quantile=0.5)


def test_pvalue_and_power_bounded() -> None:
    result = quantile_treatment_effect_test(
        [1.0, 2.0, 3.0, 100.0], [2.0, 3.0, 4.0, 5.0], quantile=0.5
    )
    assert result is not None
    assert 0.0 <= result["p_value"] <= 1.0
    assert 0.0 <= result["power_achieved"] <= 1.0
    assert math.isfinite(result["test_statistic"])
