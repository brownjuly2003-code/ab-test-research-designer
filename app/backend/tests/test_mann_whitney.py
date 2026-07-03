"""Tests for the Mann–Whitney U (Wilcoxon rank-sum) non-parametric estimator (``stats/mann_whitney.py``).

Covers: the closed form against a hand computation (independently cross-checked against
``scipy.stats.mannwhitneyu(method="asymptotic", use_continuity=True)`` at authoring time — the
expected constants below are those scipy values, frozen so the test stays stdlib-only and CI-safe),
the ``U_c + U_t = n_c·n_t`` invariant, arm-swap antisymmetry, the tie correction by hand, location
shift-invariance, monotonicity in the shift, the Hodges–Lehmann shift recovery, the degenerate
guards, and Monte-Carlo proofs of type-I control under H0 and power under a real shift.
"""

import math
import random

import pytest

from app.backend.app.stats.mann_whitney import (
    MAX_EXACT_MANN_WHITNEY_TOTAL,
    mann_whitney_u_test,
)


# --- closed form vs hand computation (cross-checked against scipy asymptotic) ---------------


def test_complete_separation_matches_hand_computation() -> None:
    # control=[1,2,3,4], treatment=[5,6,7,8]: pooled ranks 1..8, R_t=26, U_t=26-10=16=n_c·n_t,
    # so treatment beats control in every pair. μ_U=8, σ²_U=4·4·9/12=12, σ_U=√12.
    # z=(16-8-0.5)/√12=2.16506 (asymptotic, reported descriptively). CLES=16/16=1, r=2·1-1=1.
    # Pairwise t−c differences have median 4 -> Hodges–Lehmann shift = 4. The sample is small and
    # tie-free, so the p-value is the *exact* one: only the two extreme splits (all-high / all-low)
    # are as extreme as the observed U=16, so two-sided p = 2 / C(8,4) = 2/70 = 0.0285714 (the
    # asymptotic normal approximation would give 0.030383; == scipy method="exact").
    result = mann_whitney_u_test([1, 2, 3, 4], [5, 6, 7, 8])
    assert result is not None
    assert result["method"] == "exact"
    assert result["u_statistic"] == pytest.approx(16.0)
    assert result["u_control"] == pytest.approx(0.0)
    assert result["test_statistic"] == pytest.approx(2.16506, abs=1e-4)
    assert result["p_value"] == pytest.approx(2 / 70, abs=1e-9)
    assert result["common_language_effect"] == pytest.approx(1.0)
    assert result["rank_biserial"] == pytest.approx(1.0)
    assert result["hodges_lehmann_shift"] == pytest.approx(4.0)
    assert result["is_significant"] is True


def test_u_statistics_sum_to_pair_count() -> None:
    # U_c + U_t = n_c · n_t is the defining rank-sum identity; it must hold even with ties.
    result = mann_whitney_u_test([1, 2, 2, 7, 9], [2, 3, 4, 9, 10, 11])
    assert result is not None
    assert result["u_statistic"] + result["u_control"] == pytest.approx(5 * 6)


def test_arm_swap_is_antisymmetric() -> None:
    # Swapping the two arms reflects U about its mean, flips the sign of z and of the location
    # shift, and leaves the two-sided p-value unchanged.
    control = [3.1, 4.5, 2.2, 9.9, 1.0, 5.5, 6.7]
    treatment = [4.0, 8.8, 7.7, 2.1, 9.0, 10.1, 3.3, 6.0]
    forward = mann_whitney_u_test(control, treatment)
    reverse = mann_whitney_u_test(treatment, control)
    assert forward is not None and reverse is not None
    assert forward["p_value"] == pytest.approx(reverse["p_value"])
    assert forward["test_statistic"] == pytest.approx(-reverse["test_statistic"])
    assert forward["hodges_lehmann_shift"] == pytest.approx(-reverse["hodges_lehmann_shift"])
    assert forward["u_statistic"] == pytest.approx(reverse["u_control"])


def test_tie_correction_by_hand() -> None:
    # control=[1,2,2], treatment=[2,3,4]: the three 2's share midrank 3. R_t=3+5+6=14, U_t=14-6=8,
    # U_c=1. Tie groups {1},{2,2,2},{3},{4} -> Σ(τ³−τ)=24. σ²_U=(9/12)·(7−24/30)=4.65, below the
    # no-tie 9·7/12=5.25 -> the tie correction shrinks the variance.
    result = mann_whitney_u_test([1, 2, 2], [2, 3, 4])
    assert result is not None
    assert result["u_statistic"] == pytest.approx(8.0)
    assert result["u_control"] == pytest.approx(1.0)
    assert result["ties_present"] is True
    # Recover σ_U from the continuity-corrected z: deviation 8−4.5=3.5, corrected 3.0.
    recovered_sigma = 3.0 / result["test_statistic"]
    assert recovered_sigma**2 == pytest.approx(4.65, abs=1e-6)


def test_common_language_effect_and_rank_biserial_consistent() -> None:
    result = mann_whitney_u_test([5, 1, 8, 3, 9, 2], [4, 7, 6, 10, 11, 12])
    assert result is not None
    assert 0.0 <= result["common_language_effect"] <= 1.0
    assert result["rank_biserial"] == pytest.approx(
        2.0 * result["common_language_effect"] - 1.0
    )


# --- exact small-sample p-value (tie-free) -------------------------------------------------


def _brute_force_exact_two_sided_p(control: list[float], treatment: list[float]) -> float:
    """Independent exact two-sided Mann–Whitney p by enumerating every n_t-subset of the pooled
    sample (no DP, no scipy) — the gold-standard reference for the module's exact path."""
    from itertools import combinations

    pooled = control + treatment
    total = len(pooled)
    n_treatment = len(treatment)

    def u_of(treatment_indices: tuple[int, ...]) -> float:
        chosen = set(treatment_indices)
        t_values = [pooled[i] for i in treatment_indices]
        c_values = [pooled[i] for i in range(total) if i not in chosen]
        wins = sum(1 for a in t_values for b in c_values if a > b)
        ties = sum(1 for a in t_values for b in c_values if a == b)
        return wins + 0.5 * ties

    u_observed = u_of(tuple(range(len(control), total)))
    statistics = [u_of(combo) for combo in combinations(range(total), n_treatment)]
    total_count = len(statistics)
    lower = sum(1 for u in statistics if u <= u_observed + 1e-9)
    upper = sum(1 for u in statistics if u >= u_observed - 1e-9)
    return min(1.0, 2.0 * min(lower, upper) / total_count)


def test_exact_p_matches_brute_force_enumeration() -> None:
    # Several small tie-free samples; the module's exact p must equal an independent full enumeration
    # of all C(N, n_t) relabellings to the last digit.
    cases = [
        ([1, 2, 5, 8], [3, 4, 9, 11]),
        ([1, 2, 3, 4], [5, 6, 7, 8]),
        ([2, 4, 6], [1, 3, 5, 7, 9]),
        ([10, 20, 30, 40, 50], [15, 25, 35]),
        ([1.5, 2.5, 9.5], [3.5, 4.5, 5.5, 6.5]),
    ]
    for control, treatment in cases:
        result = mann_whitney_u_test(control, treatment)
        assert result is not None
        assert result["method"] == "exact"
        assert result["p_value"] == pytest.approx(
            _brute_force_exact_two_sided_p(control, treatment), abs=1e-12
        ), (control, treatment)


def test_exact_below_cap_and_asymptotic_above() -> None:
    # Tie-free samples: exact at and below the cap on total N, asymptotic once the pooled sample
    # exceeds it. Disjoint even/odd integers keep both arms tie-free at any size.
    half = MAX_EXACT_MANN_WHITNEY_TOTAL // 2
    control = [float(2 * i) for i in range(half)]  # evens
    treatment = [float(2 * i + 1) for i in range(half)]  # odds, interleaved -> tie-free
    at_cap = mann_whitney_u_test(control, treatment)
    assert at_cap is not None and at_cap["method"] == "exact"

    bigger_control = control + [float(2 * half)]
    bigger_treatment = treatment + [float(2 * half + 1), float(2 * half + 3)]
    over_cap = mann_whitney_u_test(bigger_control, bigger_treatment)
    assert over_cap is not None
    assert len(bigger_control) + len(bigger_treatment) > MAX_EXACT_MANN_WHITNEY_TOTAL
    assert over_cap["method"] == "asymptotic"


def test_ties_force_asymptotic_even_when_small() -> None:
    # A tiny sample, but a value shared across the arms breaks the tie-free assumption, so the exact
    # recurrence does not apply and the test falls back to the corrected normal approximation.
    result = mann_whitney_u_test([1, 2, 3, 4], [4, 5, 6, 7])
    assert result is not None
    assert result["ties_present"] is True
    assert result["method"] == "asymptotic"


def test_exact_two_sided_symmetric_under_arm_swap() -> None:
    control = [1.0, 3.0, 5.0, 12.0]
    treatment = [2.0, 4.0, 9.0, 11.0, 14.0]
    forward = mann_whitney_u_test(control, treatment)
    reverse = mann_whitney_u_test(treatment, control)
    assert forward is not None and reverse is not None
    assert forward["method"] == "exact" and reverse["method"] == "exact"
    assert forward["p_value"] == pytest.approx(reverse["p_value"], abs=1e-12)


# --- distribution-level properties ---------------------------------------------------------


def test_location_shift_invariance() -> None:
    # Adding the same constant to both arms shifts every pooled value equally -> ranks, U, z and p
    # are unchanged; only the Hodges–Lehmann location estimate is invariant to a *common* shift.
    control = [2.0, 5.0, 1.0, 8.0, 3.0]
    treatment = [4.0, 9.0, 6.0, 7.0]
    base = mann_whitney_u_test(control, treatment)
    shifted = mann_whitney_u_test([c + 100.0 for c in control], [t + 100.0 for t in treatment])
    assert base is not None and shifted is not None
    assert base["u_statistic"] == pytest.approx(shifted["u_statistic"])
    assert base["p_value"] == pytest.approx(shifted["p_value"])
    assert base["hodges_lehmann_shift"] == pytest.approx(shifted["hodges_lehmann_shift"])


def test_p_value_monotone_in_treatment_shift() -> None:
    # Sliding the treatment arm further above the control monotonically strengthens the evidence:
    # the larger the shift, the smaller the two-sided p-value.
    control = [float(i) for i in range(20)]
    p_values = []
    for shift in (0.0, 2.0, 5.0, 10.0):
        result = mann_whitney_u_test(control, [c + shift for c in control])
        assert result is not None
        p_values.append(result["p_value"])
    assert p_values[0] > p_values[1] > p_values[2] > p_values[3]


def test_hodges_lehmann_recovers_known_shift() -> None:
    # treatment = control + δ for a constant δ makes every pairwise difference equal to δ, so the
    # Hodges–Lehmann median-of-differences recovers δ exactly and its CI brackets it.
    control = [1.0, 4.0, 2.0, 9.0, 5.0, 7.0, 3.0, 8.0]
    delta = 3.5
    result = mann_whitney_u_test(control, [c + delta for c in control])
    assert result is not None
    assert result["hodges_lehmann_shift"] == pytest.approx(delta)
    assert result["ci_lower"] <= delta <= result["ci_upper"]


def test_significant_shift_ci_excludes_zero() -> None:
    result = mann_whitney_u_test(
        [float(i) for i in range(30)], [float(i) + 6.0 for i in range(30)]
    )
    assert result is not None
    assert result["is_significant"] is True
    assert result["ci_lower"] > 0.0


# --- robustness: the reason this test exists ----------------------------------------------


def test_detects_distribution_shift_under_heavy_tail_outliers() -> None:
    # A heavy-tailed treatment whose bulk is shifted up but whose mean is dragged around by a few
    # extreme values: the rank test keys on the consistent ordering, not the outlier-sensitive mean.
    rng = random.Random(4242)
    control = [rng.lognormvariate(0.0, 1.0) for _ in range(80)]
    treatment = [rng.lognormvariate(0.6, 1.0) for _ in range(80)]
    result = mann_whitney_u_test(control, treatment)
    assert result is not None
    assert result["common_language_effect"] > 0.5
    assert result["is_significant"] is True


# --- Monte-Carlo: type-I control under H0 and power under a real shift ----------------------


def test_monte_carlo_type_one_error_near_alpha() -> None:
    """Under H0 (both arms drawn from the *same* distribution) the asymptotic rank test must reject
    at roughly the nominal rate. Empirical type-I error over many trials stays close to alpha."""
    rng = random.Random(20260628)
    alpha = 0.05
    trials = 800
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(35)]
        treatment = [rng.gauss(0.0, 1.0) for _ in range(35)]
        result = mann_whitney_u_test(control, treatment, alpha=alpha)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    empirical = rejections / trials
    # Continuity-corrected asymptotic test is mildly conservative at n=35; allow a generous band.
    assert 0.02 <= empirical <= 0.085, empirical


def test_monte_carlo_power_under_real_shift() -> None:
    """Under a genuine location shift the test should reject the great majority of the time."""
    rng = random.Random(11)
    trials = 400
    rejections = 0
    for _ in range(trials):
        control = [rng.gauss(0.0, 1.0) for _ in range(40)]
        treatment = [rng.gauss(0.8, 1.0) for _ in range(40)]
        result = mann_whitney_u_test(control, treatment, alpha=0.05)
        assert result is not None
        if result["is_significant"]:
            rejections += 1
    assert rejections / trials > 0.75


# --- degenerate guards ---------------------------------------------------------------------


def test_all_values_tied_is_none() -> None:
    # Every observation identical across both arms -> single tie group -> rank variance 0 -> no
    # signal -> None (the service renders this as a degenerate result).
    assert mann_whitney_u_test([5.0, 5.0, 5.0], [5.0, 5.0, 5.0]) is None


def test_empty_arm_is_none() -> None:
    assert mann_whitney_u_test([], [1.0, 2.0]) is None
    assert mann_whitney_u_test([1.0, 2.0], []) is None


def test_invalid_alpha_raises() -> None:
    with pytest.raises(ValueError):
        mann_whitney_u_test([1.0, 2.0], [3.0, 4.0], alpha=0.0)
    with pytest.raises(ValueError):
        mann_whitney_u_test([1.0, 2.0], [3.0, 4.0], alpha=1.0)


def test_non_finite_values_raise() -> None:
    with pytest.raises(ValueError):
        mann_whitney_u_test([1.0, float("nan")], [3.0, 4.0])
    with pytest.raises(ValueError):
        mann_whitney_u_test([1.0, 2.0], [float("inf"), 4.0])


def test_power_and_pvalue_bounded() -> None:
    result = mann_whitney_u_test([1, 2, 3, 100], [2, 3, 4, 5])
    assert result is not None
    assert 0.0 <= result["p_value"] <= 1.0
    assert 0.0 <= result["power_achieved"] <= 1.0
    assert math.isfinite(result["test_statistic"])


# --- sizing (calculate_mann_whitney_sample_size) --------------------------------------------
# Frozen references from the P2.1 verification run (scratchpad verify_sizing_vs_scipy.py, seed
# 20260703): parametric z-n 252 (statsmodels TTestIndPower 252.1) -> MW plan 264; Monte-Carlo
# power of scipy.stats.mannwhitneyu at 264 under the normal shift = 0.802, at the uninflated 252
# only 0.775. scipy/statsmodels are cross-checked locally, not committed dependencies.

from app.backend.app.stats.mann_whitney import (  # noqa: E402
    MANN_WHITNEY_ARE_LOWER_BOUND,
    MANN_WHITNEY_ARE_NORMAL,
    calculate_mann_whitney_sample_size,
)


def test_sizing_matches_frozen_reference() -> None:
    plan = calculate_mann_whitney_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8
    )
    assert plan["sample_size_per_variant"] == 264
    assert plan["total_sample_size"] == 528
    assert plan["metric_type"] == "continuous"
    assert plan["mde_absolute"] == pytest.approx(5.0)


def test_sizing_is_are_inflation_of_parametric_n() -> None:
    from app.backend.app.stats.continuous import calculate_continuous_sample_size

    parametric = calculate_continuous_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8
    )
    plan = calculate_mann_whitney_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8
    )
    assert plan["sample_size_per_variant"] == math.ceil(
        parametric["sample_size_per_variant"] / MANN_WHITNEY_ARE_NORMAL
    )
    assert plan["sample_size_per_variant"] > parametric["sample_size_per_variant"]


def test_sizing_assumptions_state_are_basis_and_worst_case() -> None:
    plan = calculate_mann_whitney_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8
    )
    text = " ".join(plan["assumptions"])
    assert "3/pi" in text
    assert str(MANN_WHITNEY_ARE_LOWER_BOUND) in text
    # ceil(252 / 0.864) = 292 - the honest worst-case bound must be spelled out.
    assert "292" in text


def test_sizing_multivariant_applies_bonferroni() -> None:
    two = calculate_mann_whitney_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8, variants_count=2
    )
    three = calculate_mann_whitney_sample_size(
        baseline_mean=100, std_dev=20, mde_pct=5, alpha=0.05, power=0.8, variants_count=3
    )
    assert three["adjusted_alpha"] == pytest.approx(0.025)
    assert three["sample_size_per_variant"] > two["sample_size_per_variant"]


def test_sizing_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        calculate_mann_whitney_sample_size(0, 20, 5, 0.05, 0.8)
    with pytest.raises(ValueError):
        calculate_mann_whitney_sample_size(100, 0, 5, 0.05, 0.8)
    with pytest.raises(ValueError):
        calculate_mann_whitney_sample_size(100, 20, -1, 0.05, 0.8)
    with pytest.raises(ValueError):
        calculate_mann_whitney_sample_size(100, 20, 5, 0.05, 0.8, variants_count=1)
