from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.schemas.api import ObservedResultsBinary
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.sequential import obrien_fleming_boundaries
from app.backend.app.stats.srm import chi_square_srm


def test_regression_observed_binary_rejects_single_user_arm() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        ObservedResultsBinary(
            control_conversions=0,
            control_users=1,
            treatment_conversions=0,
            treatment_users=2,
        )


def test_regression_continuous_near_zero_std_is_validation_error() -> None:
    with pytest.raises(ValueError, match="std_dev must be positive"):
        calculate_continuous_sample_size(
            baseline_mean=100.0,
            std_dev=1e-13,
            mde_pct=5.0,
            alpha=0.05,
            power=0.8,
        )


def test_regression_continuous_extreme_std_does_not_overflow() -> None:
    with pytest.raises(ValueError, match="too large to be finite"):
        calculate_continuous_sample_size(
            baseline_mean=100.0,
            std_dev=sys.float_info.max / 2,
            mde_pct=5.0,
            alpha=0.05,
            power=0.8,
        )


def test_regression_srm_zero_observed_group_is_validation_error() -> None:
    with pytest.raises(ValueError, match="positive counts"):
        chi_square_srm(observed_counts=[0, 100], expected_fractions=[0.5, 0.5])


def test_regression_sequential_hundred_looks_are_supported() -> None:
    boundaries = obrien_fleming_boundaries(100, alpha=0.05)

    assert len(boundaries) == 100
    assert boundaries[0]["info_fraction"] == 0.01
    assert boundaries[-1]["info_fraction"] == 1.0
