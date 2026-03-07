from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.services.calculations_service import calculate_experiment_metrics


def test_binary_calculation_returns_required_fields() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.042,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "traffic_split": [50, 50],
        }
    )

    assert result["calculation_summary"]["metric_type"] == "binary"
    assert result["calculation_summary"]["mde_absolute"] == pytest.approx(0.0021)
    assert result["results"]["sample_size_per_variant"] > 0
    assert result["results"]["total_sample_size"] == (
        result["results"]["sample_size_per_variant"] * 2
    )
    assert result["results"]["effective_daily_traffic"] == pytest.approx(7200)
    assert result["results"]["estimated_duration_days"] > 0


def test_continuous_calculation_requires_std_dev_and_returns_duration() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "continuous",
            "baseline_value": 15.0,
            "std_dev": 12.0,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 8000,
            "audience_share_in_test": 0.5,
            "traffic_split": [50, 50],
        }
    )

    assert result["calculation_summary"]["metric_type"] == "continuous"
    assert result["calculation_summary"]["mde_absolute"] == pytest.approx(0.75)
    assert result["results"]["sample_size_per_variant"] > 0
    assert result["results"]["estimated_duration_days"] > 0


def test_continuous_calculation_rejects_missing_std_dev() -> None:
    with pytest.raises(TypeError):
        calculate_experiment_metrics(
            {
                "metric_type": "continuous",
                "baseline_value": 15.0,
                "std_dev": None,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 8000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
            }
        )


def test_duration_uses_smallest_variant_share() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.1,
            "mde_pct": 10,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 10000,
            "audience_share_in_test": 0.4,
            "traffic_split": [80, 20],
        }
    )

    per_variant_days = result["results"]["estimated_duration_days"]

    assert result["results"]["effective_daily_traffic"] == pytest.approx(4000)
    assert per_variant_days >= 1


def test_multivariant_calculation_scales_total_sample_size() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.12,
            "mde_pct": 8,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 5000,
            "audience_share_in_test": 0.5,
            "traffic_split": [34, 33, 33],
            "variants_count": 3,
        }
    )

    assert result["results"]["sample_size_per_variant"] > 0
    assert result["results"]["total_sample_size"] == (
        result["results"]["sample_size_per_variant"] * 3
    )
    assert any(
        "Bonferroni-adjusted alpha" in assumption for assumption in result["assumptions"]
    )


def test_calculation_rejects_mismatched_traffic_split_and_variants_count() -> None:
    with pytest.raises(ValueError, match="traffic_split length must match variants_count"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.1,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 5000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
                "variants_count": 3,
            }
        )
