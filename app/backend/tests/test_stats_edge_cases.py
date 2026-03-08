from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days


@pytest.mark.parametrize(
    ("baseline_rate", "mde_pct"),
    [(0.001, 50), (0.98, 1)],
)
def test_binary_sample_size_handles_extreme_valid_baselines(
    baseline_rate: float,
    mde_pct: float,
) -> None:
    result = calculate_binary_sample_size(
        baseline_rate=baseline_rate,
        mde_pct=mde_pct,
        alpha=0.05,
        power=0.8,
    )

    assert result["sample_size_per_variant"] > 0
    assert result["total_sample_size"] == result["sample_size_per_variant"] * 2


@pytest.mark.parametrize("mde_pct", [0, -5])
def test_binary_sample_size_rejects_non_positive_mde(mde_pct: int) -> None:
    with pytest.raises(ValueError, match="mde_pct must be positive"):
        calculate_binary_sample_size(
            baseline_rate=0.1,
            mde_pct=mde_pct,
            alpha=0.05,
            power=0.8,
        )


def test_binary_sample_size_supports_maximum_variant_count() -> None:
    result = calculate_binary_sample_size(
        baseline_rate=0.1,
        mde_pct=10,
        alpha=0.05,
        power=0.8,
        variants_count=10,
    )

    assert result["sample_size_per_variant"] > 0
    assert result["total_sample_size"] == result["sample_size_per_variant"] * 10
    assert "Bonferroni-adjusted alpha is" in result["assumptions"][2]


def test_binary_sample_size_rejects_single_variant() -> None:
    with pytest.raises(ValueError, match="variants_count must be between 2 and 10"):
        calculate_binary_sample_size(
            baseline_rate=0.1,
            mde_pct=10,
            alpha=0.05,
            power=0.8,
            variants_count=1,
        )


def test_continuous_sample_size_rejects_zero_std_dev() -> None:
    with pytest.raises(ValueError, match="std_dev must be positive"):
        calculate_continuous_sample_size(
            baseline_mean=100,
            std_dev=0,
            mde_pct=5,
            alpha=0.05,
            power=0.8,
        )


def test_duration_rejects_zero_daily_traffic() -> None:
    with pytest.raises(ValueError, match="expected_daily_traffic must be positive"):
        estimate_experiment_duration_days(
            sample_size_per_variant=1000,
            expected_daily_traffic=0,
            audience_share_in_test=0.5,
            traffic_split=[50, 50],
        )
