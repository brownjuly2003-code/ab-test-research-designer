import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_statistical_oracle import _add_check, _dependency_versions

# The oracle proper needs pandas, scipy, statsmodels and lifelines, which live in
# requirements-oracle.txt and are deliberately absent from the CI verify matrix
# (only the dedicated statistical-oracle job installs them). Without them the
# script exits 2 by design, so pin the coverage assertion to the environments
# that can actually run it instead of failing on an optional-dependency gap.
_MISSING_ORACLE_PACKAGES = sorted(
    name for name, version in _dependency_versions().items() if version == "missing"
)
requires_oracle_dependencies = pytest.mark.skipif(
    bool(_MISSING_ORACLE_PACKAGES),
    reason=f"optional oracle dependencies missing: {', '.join(_MISSING_ORACLE_PACKAGES)}",
)


def test_oracle_relative_tolerance_uses_expected_magnitude_below_one() -> None:
    checks = []
    _add_check(
        checks,
        case="relative_tolerance",
        metric="small_probability",
        observed=0.1006,
        expected=0.1,
        abs_tolerance=0.0,
        rel_tolerance=0.005,
        source="test reference",
    )

    assert checks[0].rel_diff == pytest.approx(0.006)
    assert checks[0].passed is False

    zero_reference_checks = []
    _add_check(
        zero_reference_checks,
        case="absolute_tolerance",
        metric="zero_reference",
        observed=0.0059,
        expected=0.0,
        abs_tolerance=0.055,
        rel_tolerance=0.01,
        source="test reference",
    )

    assert zero_reference_checks[0].rel_diff == pytest.approx(0.0059)
    assert zero_reference_checks[0].passed is True


def test_statistical_oracle_self_test() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_statistical_oracle.py", "--self-test"],
        cwd=".",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "self-test OK" in result.stdout


@requires_oracle_dependencies
def test_statistical_oracle_has_c05_independent_coverage(tmp_path: Path) -> None:
    artifact = tmp_path / "statistical-oracle.json"
    result = subprocess.run(
        [sys.executable, "scripts/run_statistical_oracle.py", "--artifact", str(artifact)],
        cwd=".",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    report = json.loads(artifact.read_text(encoding="utf-8"))
    cases = set(report["summary"]["cases"])
    assert {
        "binary_pooled_z_newcombe",
        "binary_sample_size",
        "continuous_sample_size",
        "post_stratification",
        "live_cuped_ancova",
        "always_valid_msprt_type_i",
        "beta_probability_treatment_beats_control",
    } <= cases
    assert cases.isdisjoint(
        {
            "always_valid_msprt",
            "bayesian_precision_sizing",
            "cluster_design_effect",
            "sequential_sample_size_inflation",
        }
    )
