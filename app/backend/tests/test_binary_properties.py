from pathlib import Path
import math
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.schemas.api import ObservedResultsBinary, ResultsRequest
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats.binary import (
    calculate_binary_sample_size,
    calculate_detectable_mde_binary,
)

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@st.composite
def binary_sample_params(draw: st.DrawFn) -> dict[str, float | int]:
    baseline_rate = draw(st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS))
    mde_pct = draw(st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS))
    assume(baseline_rate * (1 + mde_pct / 100) < 1)
    return {
        "baseline_rate": baseline_rate,
        "mde_pct": mde_pct,
        "alpha": draw(st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS)),
        "power": draw(st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS)),
        "variants_count": draw(st.integers(min_value=2, max_value=8)),
    }


@st.composite
def binary_observations(draw: st.DrawFn) -> dict[str, int | float]:
    control_users = draw(st.integers(min_value=1, max_value=20_000))
    treatment_users = draw(st.integers(min_value=1, max_value=20_000))
    return {
        "control_conversions": draw(st.integers(min_value=0, max_value=control_users)),
        "control_users": control_users,
        "treatment_conversions": draw(st.integers(min_value=0, max_value=treatment_users)),
        "treatment_users": treatment_users,
        "alpha": draw(st.floats(min_value=0.001, max_value=0.1, **FINITE_FLOATS)),
    }


@settings(max_examples=50, deadline=5000)
@given(params=binary_sample_params())
def test_binary_sample_size_is_positive_and_finite(params: dict[str, float | int]) -> None:
    summary = calculate_binary_sample_size(**params)

    assert summary["sample_size_per_variant"] > 0
    assert summary["total_sample_size"] == summary["sample_size_per_variant"] * params["variants_count"]
    assert math.isfinite(summary["mde_absolute"])
    assert 0 < summary["adjusted_alpha"] <= params["alpha"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_a=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    mde_b=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_binary_sample_size_decreases_as_mde_increases(
    baseline_rate: float,
    mde_a: float,
    mde_b: float,
    alpha: float,
    power: float,
) -> None:
    small_mde, large_mde = sorted((mde_a, mde_b))
    assume(small_mde < large_mde)
    assume(baseline_rate * (1 + large_mde / 100) < 1)

    smaller_effect = calculate_binary_sample_size(baseline_rate, small_mde, alpha, power)
    larger_effect = calculate_binary_sample_size(baseline_rate, large_mde, alpha, power)

    assert smaller_effect["sample_size_per_variant"] >= larger_effect["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha_a=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    alpha_b=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_binary_sample_size_decreases_as_alpha_increases(
    baseline_rate: float,
    mde_pct: float,
    alpha_a: float,
    alpha_b: float,
    power: float,
) -> None:
    lower_alpha, higher_alpha = sorted((alpha_a, alpha_b))
    assume(lower_alpha < higher_alpha)
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    stricter_alpha = calculate_binary_sample_size(baseline_rate, mde_pct, lower_alpha, power)
    looser_alpha = calculate_binary_sample_size(baseline_rate, mde_pct, higher_alpha, power)

    assert stricter_alpha["sample_size_per_variant"] >= looser_alpha["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power_a=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
    power_b=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_binary_sample_size_increases_as_power_increases(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power_a: float,
    power_b: float,
) -> None:
    lower_power, higher_power = sorted((power_a, power_b))
    assume(lower_power < higher_power)
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    weaker_power = calculate_binary_sample_size(baseline_rate, mde_pct, alpha, lower_power)
    stronger_power = calculate_binary_sample_size(baseline_rate, mde_pct, alpha, higher_power)

    assert weaker_power["sample_size_per_variant"] <= stronger_power["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_binary_detectable_mde_round_trip_matches_requested_effect(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
) -> None:
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    summary = calculate_binary_sample_size(baseline_rate, mde_pct, alpha, power)
    detectable_mde = calculate_detectable_mde_binary(
        summary["sample_size_per_variant"],
        baseline_rate,
        alpha,
        power,
    )

    assert math.isclose(detectable_mde, summary["mde_absolute"], rel_tol=0.05, abs_tol=1e-6)


@settings(max_examples=50, deadline=5000)
@given(
    baseline_rate=st.floats(min_value=0.01, max_value=0.99, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
    variants_a=st.integers(min_value=2, max_value=8),
    variants_b=st.integers(min_value=2, max_value=8),
)
def test_binary_multivariant_bonferroni_increases_sample_size(
    baseline_rate: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_a: int,
    variants_b: int,
) -> None:
    fewer_variants, more_variants = sorted((variants_a, variants_b))
    assume(fewer_variants < more_variants)
    assume(baseline_rate * (1 + mde_pct / 100) < 1)

    smaller_design = calculate_binary_sample_size(
        baseline_rate,
        mde_pct,
        alpha,
        power,
        variants_count=fewer_variants,
    )
    larger_design = calculate_binary_sample_size(
        baseline_rate,
        mde_pct,
        alpha,
        power,
        variants_count=more_variants,
    )

    assert smaller_design["sample_size_per_variant"] <= larger_design["sample_size_per_variant"]
    assert smaller_design["adjusted_alpha"] >= larger_design["adjusted_alpha"]


@settings(max_examples=50, deadline=5000)
@given(observation=binary_observations())
def test_binary_analyze_results_swap_flips_effect_and_preserves_p_value(
    observation: dict[str, int | float],
) -> None:
    original = analyze_results(
        ResultsRequest(metric_type="binary", binary=ObservedResultsBinary(**observation))
    )
    swapped = analyze_results(
        ResultsRequest(
            metric_type="binary",
            binary=ObservedResultsBinary(
                control_conversions=observation["treatment_conversions"],
                control_users=observation["treatment_users"],
                treatment_conversions=observation["control_conversions"],
                treatment_users=observation["control_users"],
                alpha=observation["alpha"],
            ),
        )
    )

    assert math.isclose(original.observed_effect, -swapped.observed_effect, abs_tol=1e-4)
    assert math.isclose(original.p_value, swapped.p_value, abs_tol=1e-6)
    assert original.is_significant == swapped.is_significant


@settings(max_examples=50, deadline=5000)
@given(observation=binary_observations())
def test_binary_analyze_results_outputs_bounded_probabilities(
    observation: dict[str, int | float],
) -> None:
    result = analyze_results(ResultsRequest(metric_type="binary", binary=ObservedResultsBinary(**observation)))

    assert 0.0 <= result.p_value <= 1.0
    assert 0.0 <= result.power_achieved <= 1.0
    assert math.isfinite(result.observed_effect)
    assert math.isfinite(result.ci_lower)
    assert math.isfinite(result.ci_upper)
