from pathlib import Path
import math
import sys

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.schemas.api import ObservedResultsBinary, ObservedResultsContinuous
from app.backend.app.services.monte_carlo_service import simulate_uplift_distribution
from app.backend.app.stats.bayesian import (
    bayesian_sample_size_binary,
    bayesian_sample_size_continuous,
)
from app.backend.app.stats.binary import calculate_binary_sample_size, normal_ppf
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.sequential import (
    obrien_fleming_boundaries,
    sequential_sample_size_inflation,
)
from app.backend.app.stats.srm import chi_square_srm

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@st.composite
def boundary_binary_designs(draw: st.DrawFn) -> tuple[float, float]:
    if draw(st.booleans()):
        baseline_rate = draw(st.floats(min_value=1e-12, max_value=1e-6, **FINITE_FLOATS))
        return baseline_rate, 1.0

    gap_to_one = draw(st.floats(min_value=1e-12, max_value=1e-6, **FINITE_FLOATS))
    return 1.0 - gap_to_one, gap_to_one * 10


def _assert_monte_carlo_shape(result: dict, num_simulations: int) -> None:
    percentiles = result["percentiles"]
    percentile_values = [percentiles[str(level)] for level in (5, 25, 50, 75, 95)]

    assert result["num_simulations"] == num_simulations
    assert len(result["simulated_uplifts"]) == num_simulations
    assert all(left <= right for left, right in zip(percentile_values, percentile_values[1:]))
    assert 0.0 <= result["probability_uplift_positive"] <= 1.0
    assert all(0.0 <= value <= 1.0 for value in result["probability_uplift_above_threshold"].values())
    assert all(math.isfinite(value) for value in result["simulated_uplifts"][:100])


@settings(max_examples=20, deadline=5000)
@given(metric_type=st.sampled_from(["binary", "continuous"]), first_arm=st.booleans())
def test_property_observed_results_reject_sample_size_one(metric_type: str, first_arm: bool) -> None:
    if metric_type == "binary":
        payload = {
            "control_conversions": 0,
            "control_users": 2,
            "treatment_conversions": 0,
            "treatment_users": 2,
        }
        payload["control_users" if first_arm else "treatment_users"] = 1

        with pytest.raises(ValidationError, match="greater than or equal to 2"):
            ObservedResultsBinary(**payload)
        return

    payload = {
        "control_mean": 10.0,
        "control_std": 1.0,
        "control_n": 2,
        "treatment_mean": 10.0,
        "treatment_std": 1.0,
        "treatment_n": 2,
    }
    payload["control_n" if first_arm else "treatment_n"] = 1

    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        ObservedResultsContinuous(**payload)


@settings(max_examples=20, deadline=5000)
@given(baseline_rate=st.sampled_from([0.0, 1.0]))
def test_property_binary_baseline_endpoints_raise_clear_error(baseline_rate: float) -> None:
    with pytest.raises(ValueError, match="baseline_rate must be between 0 and 1"):
        calculate_binary_sample_size(
            baseline_rate=baseline_rate,
            mde_pct=1.0,
            alpha=0.05,
            power=0.8,
        )


@settings(max_examples=100, deadline=5000)
@given(design=boundary_binary_designs())
def test_property_binary_near_boundary_baselines_stay_finite(design: tuple[float, float]) -> None:
    baseline_rate, mde_pct = design
    summary = calculate_binary_sample_size(
        baseline_rate=baseline_rate,
        mde_pct=mde_pct,
        alpha=0.05,
        power=0.8,
    )

    assert summary["sample_size_per_variant"] > 0
    assert math.isfinite(summary["sample_size_per_variant"])
    assert 0 < summary["baseline_value"] < 1
    assert summary["baseline_value"] + summary["mde_absolute"] < 1


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.95, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=1.0, **FINITE_FLOATS),
)
def test_property_binary_extreme_alpha_and_power_inputs_stay_sane(
    baseline_rate: float,
    mde_pct: float,
) -> None:
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    strict = calculate_binary_sample_size(baseline_rate, mde_pct, alpha=0.0001, power=0.8)
    loose = calculate_binary_sample_size(baseline_rate, mde_pct, alpha=0.5, power=0.8)
    coin_flip_power = calculate_binary_sample_size(baseline_rate, mde_pct, alpha=0.05, power=0.5)

    assert strict["sample_size_per_variant"] >= loose["sample_size_per_variant"]
    assert coin_flip_power["sample_size_per_variant"] > 0
    assert math.isfinite(strict["sample_size_per_variant"])
    assert math.isfinite(loose["sample_size_per_variant"])


@settings(max_examples=20, deadline=5000)
@given(std_dev=st.floats(min_value=0.0, max_value=1e-12, **FINITE_FLOATS))
def test_property_continuous_near_zero_std_is_rejected(std_dev: float) -> None:
    with pytest.raises(ValueError, match="std_dev must be positive"):
        calculate_continuous_sample_size(
            baseline_mean=100.0,
            std_dev=std_dev,
            mde_pct=5.0,
            alpha=0.05,
            power=0.8,
        )


def test_property_continuous_extreme_std_rejects_without_overflow() -> None:
    with pytest.raises(ValueError, match="sample size is too large|finite"):
        calculate_continuous_sample_size(
            baseline_mean=100.0,
            std_dev=sys.float_info.max / 2,
            mde_pct=5.0,
            alpha=0.05,
            power=0.8,
        )


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=1.0, **FINITE_FLOATS),
)
def test_property_continuous_extreme_alpha_and_power_inputs_stay_sane(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
) -> None:
    strict = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha=0.0001, power=0.8)
    loose = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha=0.5, power=0.8)
    coin_flip_power = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha=0.05, power=0.5)

    assert strict["sample_size_per_variant"] >= loose["sample_size_per_variant"]
    assert coin_flip_power["sample_size_per_variant"] > 0
    assert math.isfinite(strict["sample_size_per_variant"])
    assert math.isfinite(loose["sample_size_per_variant"])


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.001, max_value=0.999, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.0005, max_value=0.05, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_property_bayesian_binary_credible_half_width_respects_precision(
    baseline_rate: float,
    desired_precision: float,
    credibility: float,
) -> None:
    sample_size = bayesian_sample_size_binary(baseline_rate, desired_precision, credibility)
    z_value = normal_ppf(1 - (1 - credibility) / 2)
    half_width = z_value * math.sqrt(2 * baseline_rate * (1 - baseline_rate) / sample_size)

    assert sample_size >= 1
    assert half_width <= desired_precision + 1e-12


@settings(max_examples=50, deadline=5000)
@given(
    std_dev=st.floats(min_value=1e-12, max_value=500.0, **FINITE_FLOATS),
    desired_precision=st.floats(min_value=0.0005, max_value=100.0, **FINITE_FLOATS),
    credibility=st.floats(min_value=0.51, max_value=0.99, **FINITE_FLOATS),
)
def test_property_bayesian_continuous_credible_half_width_respects_precision(
    std_dev: float,
    desired_precision: float,
    credibility: float,
) -> None:
    sample_size = bayesian_sample_size_continuous(std_dev, desired_precision, credibility)
    z_value = normal_ppf(1 - (1 - credibility) / 2)
    half_width = z_value * math.sqrt(2) * std_dev / math.sqrt(sample_size)

    assert sample_size >= 1
    assert half_width <= desired_precision + 1e-12


@settings(max_examples=50, deadline=5000)
@given(total_per_arm=st.integers(min_value=1, max_value=100_000))
def test_property_srm_perfect_balance_has_unit_p_value(total_per_arm: int) -> None:
    chi_square, p_value, is_srm = chi_square_srm(
        observed_counts=[total_per_arm, total_per_arm],
        expected_fractions=[0.5, 0.5],
    )

    assert math.isclose(chi_square, 0.0, abs_tol=1e-12)
    assert p_value > 0.999
    assert is_srm is False


@settings(max_examples=50, deadline=5000)
@given(multiplier=st.integers(min_value=100, max_value=10_000))
def test_property_srm_extreme_imbalance_collapses_p_value(multiplier: int) -> None:
    chi_square, p_value, is_srm = chi_square_srm(
        observed_counts=[99 * multiplier, multiplier],
        expected_fractions=[0.5, 0.5],
    )

    assert chi_square > 0
    assert p_value < 0.001
    assert is_srm is True


@settings(max_examples=20, deadline=5000)
@given(total=st.integers(min_value=1, max_value=100_000), zero_first=st.booleans())
def test_property_srm_zero_observed_group_is_rejected(total: int, zero_first: bool) -> None:
    observed_counts = [0, total] if zero_first else [total, 0]

    with pytest.raises(ValueError, match="positive counts"):
        chi_square_srm(observed_counts=observed_counts, expected_fractions=[0.5, 0.5])


@settings(max_examples=20, deadline=5000)
@given(alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS))
def test_property_sequential_one_look_matches_fixed_horizon(alpha: float) -> None:
    boundary = obrien_fleming_boundaries(1, alpha)[0]
    fixed_horizon_z = normal_ppf(1 - alpha / 2)

    assert sequential_sample_size_inflation(1, alpha=alpha, power=0.8) == 1.0
    assert math.isclose(boundary["info_fraction"], 1.0, abs_tol=1e-12)
    assert math.isclose(boundary["z_boundary"], fixed_horizon_z, rel_tol=0.0, abs_tol=5e-4)


@settings(max_examples=20, deadline=5000)
@given(alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS))
def test_property_sequential_hundred_looks_have_nondegenerate_boundaries(alpha: float) -> None:
    boundaries = obrien_fleming_boundaries(100, alpha)
    z_values = [entry["z_boundary"] for entry in boundaries]
    cumulative_alpha = [entry["cumulative_alpha_spent"] for entry in boundaries]
    inflation = sequential_sample_size_inflation(100, alpha=alpha, power=0.8)

    assert len(boundaries) == 100
    assert inflation > 1.0
    assert all(math.isfinite(value) and value > 0 for value in z_values)
    assert all(left >= right for left, right in zip(z_values, z_values[1:]))
    assert all(left <= right for left, right in zip(cumulative_alpha, cumulative_alpha[1:]))
    assert cumulative_alpha[-1] <= alpha + 1e-6
    assert boundaries[0]["info_fraction"] > 0
    assert boundaries[-1]["info_fraction"] == 1.0


@settings(max_examples=25, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
    relative_uplift=st.floats(min_value=-0.2, max_value=0.2, **FINITE_FLOATS),
)
def test_property_monte_carlo_minimum_cap_distribution_shape(
    baseline_rate: float,
    relative_uplift: float,
) -> None:
    observed_conversion_b = min(0.99, max(0.001, baseline_rate * (1 + relative_uplift)))
    result = simulate_uplift_distribution(
        baseline_conversion=baseline_rate,
        observed_conversion_a=baseline_rate,
        sample_size_a=5_000,
        observed_conversion_b=observed_conversion_b,
        sample_size_b=5_000,
        num_simulations=1_000,
        seed=42,
    )

    _assert_monte_carlo_shape(result, 1_000)


def test_property_monte_carlo_maximum_cap_distribution_shape() -> None:
    result = simulate_uplift_distribution(
        baseline_conversion=0.041,
        observed_conversion_a=0.041,
        sample_size_a=10_000,
        observed_conversion_b=0.0472,
        sample_size_b=10_000,
        num_simulations=50_000,
        seed=42,
    )

    _assert_monte_carlo_shape(result, 50_000)


@settings(max_examples=25, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
    sample_size=st.integers(min_value=8_000, max_value=20_000),
)
def test_property_monte_carlo_equal_rates_stay_near_coin_flip(
    baseline_rate: float,
    sample_size: int,
) -> None:
    result = simulate_uplift_distribution(
        baseline_conversion=baseline_rate,
        observed_conversion_a=baseline_rate,
        sample_size_a=sample_size,
        observed_conversion_b=baseline_rate,
        sample_size_b=sample_size,
        num_simulations=10_000,
        seed=42,
    )

    assert 0.45 <= result["probability_uplift_positive"] <= 0.55


@settings(max_examples=25, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
    observed_conversion_b=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
)
def test_property_monte_carlo_imbalanced_sample_sizes_do_not_crash(
    baseline_rate: float,
    observed_conversion_b: float,
) -> None:
    result = simulate_uplift_distribution(
        baseline_conversion=baseline_rate,
        observed_conversion_a=baseline_rate,
        sample_size_a=10,
        observed_conversion_b=observed_conversion_b,
        sample_size_b=10_000,
        num_simulations=1_000,
        seed=42,
    )

    _assert_monte_carlo_shape(result, 1_000)


@settings(max_examples=25, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
    observed_conversion_b=st.floats(min_value=0.01, max_value=0.5, **FINITE_FLOATS),
    sample_size_a=st.integers(min_value=100, max_value=20_000),
    sample_size_b=st.integers(min_value=100, max_value=20_000),
)
def test_property_monte_carlo_seeded_runs_are_bit_exact(
    baseline_rate: float,
    observed_conversion_b: float,
    sample_size_a: int,
    sample_size_b: int,
) -> None:
    first = simulate_uplift_distribution(
        baseline_conversion=baseline_rate,
        observed_conversion_a=baseline_rate,
        sample_size_a=sample_size_a,
        observed_conversion_b=observed_conversion_b,
        sample_size_b=sample_size_b,
        num_simulations=1_000,
        seed=42,
    )
    second = simulate_uplift_distribution(
        baseline_conversion=baseline_rate,
        observed_conversion_a=baseline_rate,
        sample_size_a=sample_size_a,
        observed_conversion_b=observed_conversion_b,
        sample_size_b=sample_size_b,
        num_simulations=1_000,
        seed=42,
    )

    assert first["percentiles"] == second["percentiles"]
    assert first["simulated_uplifts"] == second["simulated_uplifts"]
