from pathlib import Path
import math
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.schemas.api import ObservedResultsContinuous, ResultsRequest
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats.continuous import (
    calculate_continuous_sample_size,
    calculate_cuped_variance_reduction,
    calculate_detectable_mde_continuous,
)

FINITE_FLOATS = {"allow_nan": False, "allow_infinity": False}


@st.composite
def continuous_sample_params(draw: st.DrawFn) -> dict[str, float | int]:
    return {
        "baseline_mean": draw(st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS)),
        "std_dev": draw(st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS)),
        "mde_pct": draw(st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS)),
        "alpha": draw(st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS)),
        "power": draw(st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS)),
        "variants_count": draw(st.integers(min_value=2, max_value=8)),
    }


@st.composite
def continuous_observations(draw: st.DrawFn) -> dict[str, int | float]:
    return {
        "control_mean": draw(st.floats(min_value=-1_000.0, max_value=1_000.0, **FINITE_FLOATS)),
        "control_std": draw(st.floats(min_value=0.001, max_value=200.0, **FINITE_FLOATS)),
        "control_n": draw(st.integers(min_value=2, max_value=20_000)),
        "treatment_mean": draw(st.floats(min_value=-1_000.0, max_value=1_000.0, **FINITE_FLOATS)),
        "treatment_std": draw(st.floats(min_value=0.001, max_value=200.0, **FINITE_FLOATS)),
        "treatment_n": draw(st.integers(min_value=2, max_value=20_000)),
        "alpha": draw(st.floats(min_value=0.001, max_value=0.1, **FINITE_FLOATS)),
    }


@settings(max_examples=50, deadline=5000)
@given(params=continuous_sample_params())
def test_continuous_sample_size_is_positive_and_finite(params: dict[str, float | int]) -> None:
    summary = calculate_continuous_sample_size(**params)

    assert summary["sample_size_per_variant"] > 0
    assert summary["total_sample_size"] == summary["sample_size_per_variant"] * params["variants_count"]
    assert math.isfinite(summary["mde_absolute"])
    assert 0 < summary["adjusted_alpha"] <= params["alpha"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_a=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    mde_b=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_continuous_sample_size_decreases_as_mde_increases(
    baseline_mean: float,
    std_dev: float,
    mde_a: float,
    mde_b: float,
    alpha: float,
    power: float,
) -> None:
    small_mde, large_mde = sorted((mde_a, mde_b))
    assume(small_mde < large_mde)

    smaller_effect = calculate_continuous_sample_size(baseline_mean, std_dev, small_mde, alpha, power)
    larger_effect = calculate_continuous_sample_size(baseline_mean, std_dev, large_mde, alpha, power)

    assert smaller_effect["sample_size_per_variant"] >= larger_effect["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha_a=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    alpha_b=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_continuous_sample_size_decreases_as_alpha_increases(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
    alpha_a: float,
    alpha_b: float,
    power: float,
) -> None:
    lower_alpha, higher_alpha = sorted((alpha_a, alpha_b))
    assume(lower_alpha < higher_alpha)

    stricter_alpha = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, lower_alpha, power)
    looser_alpha = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, higher_alpha, power)

    assert stricter_alpha["sample_size_per_variant"] >= looser_alpha["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power_a=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
    power_b=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_continuous_sample_size_increases_as_power_increases(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
    alpha: float,
    power_a: float,
    power_b: float,
) -> None:
    lower_power, higher_power = sorted((power_a, power_b))
    assume(lower_power < higher_power)

    weaker_power = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha, lower_power)
    stronger_power = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha, higher_power)

    assert weaker_power["sample_size_per_variant"] <= stronger_power["sample_size_per_variant"]


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
)
def test_continuous_detectable_mde_round_trip_matches_requested_effect(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
    alpha: float,
    power: float,
) -> None:
    summary = calculate_continuous_sample_size(baseline_mean, std_dev, mde_pct, alpha, power)
    assume(summary["sample_size_per_variant"] >= 10)

    detectable_mde = calculate_detectable_mde_continuous(
        summary["sample_size_per_variant"],
        std_dev,
        alpha,
        power,
    )

    assert math.isclose(detectable_mde, summary["mde_absolute"], rel_tol=0.06, abs_tol=1e-6)


@settings(max_examples=50, deadline=5000)
@given(
    baseline_mean=st.floats(min_value=1.0, max_value=1_000.0, **FINITE_FLOATS),
    std_dev=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    mde_pct=st.floats(min_value=0.5, max_value=50.0, **FINITE_FLOATS),
    alpha=st.floats(min_value=0.001, max_value=0.2, **FINITE_FLOATS),
    power=st.floats(min_value=0.5, max_value=0.99, **FINITE_FLOATS),
    variants_a=st.integers(min_value=2, max_value=8),
    variants_b=st.integers(min_value=2, max_value=8),
)
def test_continuous_multivariant_bonferroni_increases_sample_size(
    baseline_mean: float,
    std_dev: float,
    mde_pct: float,
    alpha: float,
    power: float,
    variants_a: int,
    variants_b: int,
) -> None:
    fewer_variants, more_variants = sorted((variants_a, variants_b))
    assume(fewer_variants < more_variants)

    smaller_design = calculate_continuous_sample_size(
        baseline_mean,
        std_dev,
        mde_pct,
        alpha,
        power,
        variants_count=fewer_variants,
    )
    larger_design = calculate_continuous_sample_size(
        baseline_mean,
        std_dev,
        mde_pct,
        alpha,
        power,
        variants_count=more_variants,
    )

    assert smaller_design["sample_size_per_variant"] <= larger_design["sample_size_per_variant"]
    assert smaller_design["adjusted_alpha"] >= larger_design["adjusted_alpha"]


@settings(max_examples=50, deadline=5000)
@given(observation=continuous_observations())
def test_continuous_analyze_results_swap_flips_effect_and_preserves_p_value(
    observation: dict[str, int | float],
) -> None:
    original = analyze_results(
        ResultsRequest(metric_type="continuous", continuous=ObservedResultsContinuous(**observation))
    )
    swapped = analyze_results(
        ResultsRequest(
            metric_type="continuous",
            continuous=ObservedResultsContinuous(
                control_mean=observation["treatment_mean"],
                control_std=observation["treatment_std"],
                control_n=observation["treatment_n"],
                treatment_mean=observation["control_mean"],
                treatment_std=observation["control_std"],
                treatment_n=observation["control_n"],
                alpha=observation["alpha"],
            ),
        )
    )

    assert math.isclose(original.observed_effect, -swapped.observed_effect, abs_tol=1e-4)
    assert math.isclose(original.p_value, swapped.p_value, abs_tol=1e-6)
    assert original.is_significant == swapped.is_significant


@settings(max_examples=50, deadline=5000)
@given(observation=continuous_observations())
def test_continuous_analyze_results_outputs_bounded_and_finite_values(
    observation: dict[str, int | float],
) -> None:
    result = analyze_results(
        ResultsRequest(metric_type="continuous", continuous=ObservedResultsContinuous(**observation))
    )

    assert 0.0 <= result.p_value <= 1.0
    assert math.isfinite(result.observed_effect)
    assert math.isfinite(result.ci_lower)
    assert math.isfinite(result.ci_upper)


@settings(max_examples=50, deadline=5000)
@given(
    outcome_std=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    pre_experiment_std=st.floats(min_value=0.1, max_value=500.0, **FINITE_FLOATS),
    correlation_a=st.floats(min_value=-0.99, max_value=0.99, **FINITE_FLOATS),
    correlation_b=st.floats(min_value=-0.99, max_value=0.99, **FINITE_FLOATS),
)
def test_cuped_variance_reduction_stays_bounded_and_grows_with_correlation_magnitude(
    outcome_std: float,
    pre_experiment_std: float,
    correlation_a: float,
    correlation_b: float,
) -> None:
    lower_corr, higher_corr = sorted((abs(correlation_a), abs(correlation_b)))
    lower_std, lower_variance_reduction = calculate_cuped_variance_reduction(
        outcome_std,
        pre_experiment_std,
        lower_corr,
    )
    higher_std, higher_variance_reduction = calculate_cuped_variance_reduction(
        outcome_std,
        pre_experiment_std,
        higher_corr,
    )

    assert 0.0 <= lower_variance_reduction < 1.0
    assert 0.0 <= higher_variance_reduction < 1.0
    assert 0.0 <= lower_std <= outcome_std
    assert 0.0 <= higher_std <= outcome_std
    assert lower_variance_reduction <= higher_variance_reduction
    assert lower_std >= higher_std
