from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.stats.cluster import inflate_for_cluster_design


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


def test_ratio_calculation_reduces_to_continuous_delta_method() -> None:
    base = {
        "baseline_value": 0.05,
        "std_dev": 0.09,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "expected_daily_traffic": 200000,
        "audience_share_in_test": 0.5,
        "traffic_split": [50, 50],
    }
    ratio = calculate_experiment_metrics({**base, "metric_type": "ratio"})
    continuous = calculate_experiment_metrics({**base, "metric_type": "continuous"})

    assert ratio["calculation_summary"]["metric_type"] == "ratio"
    # Ratio sizing is the continuous (delta-method linearized) sample-size formula with the same
    # baseline ratio and per-user std, so the planned sample size matches exactly.
    assert (
        ratio["results"]["sample_size_per_variant"]
        == continuous["results"]["sample_size_per_variant"]
    )
    assert "delta method" in ratio["assumptions"][0].lower()


def test_ratio_calculation_requires_std_dev() -> None:
    with pytest.raises(ValueError):
        calculate_experiment_metrics(
            {
                "metric_type": "ratio",
                "baseline_value": 0.05,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 200000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
            }
        )


def _binary_holdout_payload(**overrides: object) -> dict:
    payload = {
        "metric_type": "binary",
        "baseline_value": 0.042,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
        "expected_daily_traffic": 12000,
        "audience_share_in_test": 0.6,
        "traffic_split": [50, 50],
        "variants_count": 2,
    }
    payload.update(overrides)
    return payload


def test_holdout_and_me_default_to_no_allocation() -> None:
    result = calculate_experiment_metrics(_binary_holdout_payload())

    assert result["results"]["holdout_fraction"] is None
    assert result["results"]["mutually_exclusive_experiments"] is None
    assert result["results"]["allocated_daily_traffic"] is None


def test_holdout_fraction_extends_duration_without_changing_sample_size() -> None:
    base = calculate_experiment_metrics(_binary_holdout_payload())
    held = calculate_experiment_metrics(_binary_holdout_payload(holdout_fraction=0.5))

    assert held["results"]["sample_size_per_variant"] == base["results"]["sample_size_per_variant"]
    assert held["results"]["effective_daily_traffic"] == base["results"]["effective_daily_traffic"]
    assert held["results"]["allocated_daily_traffic"] == pytest.approx(
        base["results"]["effective_daily_traffic"] * 0.5
    )
    assert held["results"]["estimated_duration_days"] >= base["results"]["estimated_duration_days"] * 2 - 1


def test_mutual_exclusion_splits_traffic_across_experiments() -> None:
    base = calculate_experiment_metrics(_binary_holdout_payload())
    shared = calculate_experiment_metrics(_binary_holdout_payload(mutually_exclusive_experiments=3))

    assert shared["results"]["allocated_daily_traffic"] == pytest.approx(
        base["results"]["effective_daily_traffic"] / 3
    )
    assert shared["results"]["estimated_duration_days"] >= base["results"]["estimated_duration_days"] * 3 - 2


def test_holdout_and_me_compose() -> None:
    base = calculate_experiment_metrics(_binary_holdout_payload())
    combined = calculate_experiment_metrics(
        _binary_holdout_payload(holdout_fraction=0.2, mutually_exclusive_experiments=2)
    )

    assert combined["results"]["allocated_daily_traffic"] == pytest.approx(
        base["results"]["effective_daily_traffic"] * 0.8 / 2
    )


def test_holdout_reducing_traffic_below_threshold_flags_low_traffic() -> None:
    # 12000 * 0.6 = 7200 effective; a 0.95 holdout leaves 360/day -> LOW_TRAFFIC.
    result = calculate_experiment_metrics(_binary_holdout_payload(holdout_fraction=0.95))
    codes = {warning["code"] for warning in result["warnings"]}

    assert "LOW_TRAFFIC" in codes


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


def test_continuous_calculation_returns_cuped_comparison_when_covariates_are_provided() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "continuous",
            "baseline_value": 45.0,
            "std_dev": 12.0,
            "mde_pct": 4.4444444444,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 10000,
            "audience_share_in_test": 1.0,
            "traffic_split": [50, 50],
            "cuped_pre_experiment_std": 12.0,
            "cuped_correlation": 0.5,
        }
    )

    assert result["cuped_sample_size_per_variant"] is not None
    assert result["cuped_std"] == pytest.approx(10.3923, abs=0.0001)
    assert result["cuped_variance_reduction_pct"] == pytest.approx(25.0)
    assert result["cuped_sample_size_per_variant"] < result["results"]["sample_size_per_variant"]
    assert result["cuped_sample_size_per_variant"] == pytest.approx(
        result["results"]["sample_size_per_variant"] * 0.75,
        rel=0.01,
    )
    assert result["cuped_duration_days"] is not None
    assert result["cuped_duration_days"] <= result["results"]["estimated_duration_days"]
    # theta = rho * sigma_outcome / sigma_pre = 0.5 * 12 / 12
    assert result["cuped_theta"] == pytest.approx(0.5)


def test_continuous_calculation_keeps_naive_sample_size_for_zero_correlation() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "continuous",
            "baseline_value": 45.0,
            "std_dev": 12.0,
            "mde_pct": 4.4444444444,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 10000,
            "audience_share_in_test": 1.0,
            "traffic_split": [50, 50],
            "cuped_pre_experiment_std": 12.0,
            "cuped_correlation": 0.0,
        }
    )

    assert result["cuped_sample_size_per_variant"] == result["results"]["sample_size_per_variant"]
    assert result["cuped_variance_reduction_pct"] == pytest.approx(0.0)


def test_binary_calculation_ignores_cuped_inputs() -> None:
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
            "cuped_pre_experiment_std": 12.0,
            "cuped_correlation": 0.5,
        }
    )

    assert result["cuped_std"] is None
    assert result["cuped_sample_size_per_variant"] is None
    assert result["cuped_variance_reduction_pct"] is None
    assert result["cuped_duration_days"] is None


def test_continuous_calculation_rejects_missing_std_dev() -> None:
    with pytest.raises(ValueError, match="std_dev must be positive"):
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


@pytest.mark.parametrize("baseline_value", [0.0005, 0.95])
def test_binary_calculation_handles_extreme_but_valid_baselines(baseline_value: float) -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": baseline_value,
            "mde_pct": 2,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 25000,
            "audience_share_in_test": 0.5,
            "traffic_split": [50, 50],
        }
    )

    assert result["results"]["sample_size_per_variant"] > 0
    assert result["results"]["estimated_duration_days"] >= 1


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
        "Bonferroni-adjusted alpha is" in assumption for assumption in result["assumptions"]
    )
    assert any(
        warning["code"] == "CONSERVATIVE_MULTIVARIANT_ALPHA"
        for warning in result["warnings"]
    )
    assert result["bonferroni_note"] is not None


@pytest.mark.parametrize("mde_pct", [0, -5])
def test_calculation_rejects_non_positive_mde(mde_pct: int) -> None:
    with pytest.raises(ValueError, match="mde_pct must be positive"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.12,
                "mde_pct": mde_pct,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 5000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
                "variants_count": 2,
            }
        )


def test_continuous_calculation_rejects_zero_std_dev() -> None:
    with pytest.raises(ValueError, match="std_dev must be positive"):
        calculate_experiment_metrics(
            {
                "metric_type": "continuous",
                "baseline_value": 15.0,
                "std_dev": 0,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 8000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
            }
        )


def test_calculation_rejects_binary_mde_that_pushes_variant_rate_above_one() -> None:
    with pytest.raises(ValueError, match="invalid variant rate"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.9,
                "mde_pct": 15,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 8000,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
            }
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


@pytest.mark.parametrize("audience_share", [0, -0.2, 1.1])
def test_calculation_rejects_invalid_audience_share(audience_share: float) -> None:
    with pytest.raises(ValueError, match="audience_share_in_test must be between 0 and 1"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.1,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 5000,
                "audience_share_in_test": audience_share,
                "traffic_split": [50, 50],
                "variants_count": 2,
            }
        )


@pytest.mark.parametrize("variants_count", [1, 11])
def test_calculation_rejects_variants_outside_supported_range(variants_count: int) -> None:
    with pytest.raises(ValueError, match="variants_count must be between 2 and 10"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.1,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 5000,
                "audience_share_in_test": 0.5,
                "traffic_split": [100] if variants_count == 1 else [10] * 11,
                "variants_count": variants_count,
            }
        )


def test_calculation_rejects_zero_daily_traffic() -> None:
    with pytest.raises(ValueError, match="expected_daily_traffic must be positive"):
        calculate_experiment_metrics(
            {
                "metric_type": "binary",
                "baseline_value": 0.1,
                "mde_pct": 5,
                "alpha": 0.05,
                "power": 0.8,
                "expected_daily_traffic": 0,
                "audience_share_in_test": 0.5,
                "traffic_split": [50, 50],
                "variants_count": 2,
            }
        )


# --- planned_test routing (P2.1 sizing parity) -----------------------------------------------


_BINARY_BASE = {
    "metric_type": "binary",
    "baseline_value": 0.20,
    "mde_pct": 100.0,
    "alpha": 0.05,
    "power": 0.8,
    "expected_daily_traffic": 1000,
    "audience_share_in_test": 1.0,
    "traffic_split": [50, 50],
}

_CONTINUOUS_BASE = {
    "metric_type": "continuous",
    "baseline_value": 100.0,
    "std_dev": 20.0,
    "mde_pct": 5.0,
    "alpha": 0.05,
    "power": 0.8,
    "expected_daily_traffic": 1000,
    "audience_share_in_test": 1.0,
    "traffic_split": [50, 50],
}


def test_default_planned_test_is_z_test() -> None:
    result = calculate_experiment_metrics(dict(_BINARY_BASE))
    assert result["calculation_summary"]["planned_test"] == "z_test"
    assert result["calculation_summary"]["equivalence_margin_pct"] is None


def test_binary_fisher_exact_plan_exceeds_z_plan() -> None:
    z_plan = calculate_experiment_metrics(dict(_BINARY_BASE))
    exact_plan = calculate_experiment_metrics({**_BINARY_BASE, "planned_test": "fisher_exact"})
    # Frozen P2.1 references: z 82, exact 90 for p 0.20 -> 0.40 at alpha 0.05 / power 0.80.
    assert z_plan["results"]["sample_size_per_variant"] == 82
    assert exact_plan["results"]["sample_size_per_variant"] == 90
    assert exact_plan["calculation_summary"]["planned_test"] == "fisher_exact"


def test_continuous_mann_whitney_plan_inflates_by_are() -> None:
    z_plan = calculate_experiment_metrics(dict(_CONTINUOUS_BASE))
    mw_plan = calculate_experiment_metrics({**_CONTINUOUS_BASE, "planned_test": "mann_whitney"})
    assert z_plan["results"]["sample_size_per_variant"] == 252
    assert mw_plan["results"]["sample_size_per_variant"] == 264
    assert mw_plan["calculation_summary"]["planned_test"] == "mann_whitney"


def test_continuous_tost_plan_uses_margin_and_echoes_it() -> None:
    result = calculate_experiment_metrics(
        {**_CONTINUOUS_BASE, "planned_test": "tost", "equivalence_margin_pct": 2.0}
    )
    assert result["results"]["sample_size_per_variant"] == 1713
    assert result["calculation_summary"]["planned_test"] == "tost"
    assert result["calculation_summary"]["equivalence_margin_pct"] == pytest.approx(2.0)
    assert result["calculation_summary"]["equivalence_margin_absolute"] == pytest.approx(2.0)
    # The user's MDE is echoed untouched even though the margin drives the plan.
    assert result["calculation_summary"]["mde_pct"] == pytest.approx(5.0)


def test_tost_plan_requires_margin() -> None:
    with pytest.raises(ValueError):
        calculate_experiment_metrics({**_CONTINUOUS_BASE, "planned_test": "tost"})


def test_planned_test_metric_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        calculate_experiment_metrics({**_BINARY_BASE, "planned_test": "mann_whitney"})
    with pytest.raises(ValueError):
        calculate_experiment_metrics({**_CONTINUOUS_BASE, "planned_test": "fisher_exact"})
    with pytest.raises(ValueError):
        calculate_experiment_metrics(
            {**_CONTINUOUS_BASE, "metric_type": "ratio", "planned_test": "tost"}
        )


def test_count_metric_routes_to_poisson_rate_sizing() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "count",
            "baseline_value": 0.30,
            "mde_pct": 20.0,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 5000,
            "audience_share_in_test": 1.0,
            "traffic_split": [50, 50],
        }
    )
    # Frozen P2.1 reference: 948 total events -> 1437 users per variant at unit exposure.
    assert result["results"]["sample_size_per_variant"] == 1437
    assert result["calculation_summary"]["metric_type"] == "count"
    assert result["calculation_summary"]["planned_test"] == "poisson_rate"
    assert result["results"]["estimated_duration_days"] > 0


def test_count_metric_honors_exposure_per_user() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "count",
            "baseline_value": 0.30,
            "mde_pct": 20.0,
            "alpha": 0.05,
            "power": 0.8,
            "exposure_per_user": 2.0,
            "expected_daily_traffic": 5000,
            "audience_share_in_test": 1.0,
            "traffic_split": [50, 50],
        }
    )
    assert result["results"]["sample_size_per_variant"] == 719


def test_cuped_companion_only_on_the_default_plan() -> None:
    cuped_inputs = {"cuped_pre_experiment_std": 18.0, "cuped_correlation": 0.6}
    default_plan = calculate_experiment_metrics({**_CONTINUOUS_BASE, **cuped_inputs})
    mw_plan = calculate_experiment_metrics(
        {**_CONTINUOUS_BASE, **cuped_inputs, "planned_test": "mann_whitney"}
    )
    assert default_plan["cuped_sample_size_per_variant"] is not None
    assert mw_plan["cuped_sample_size_per_variant"] is None


# --- Cluster design effect (P5.2) ---------------------------------------------------------------

_CLUSTER = {"randomization_unit": "cluster", "avg_cluster_size": 100, "icc": 0.02}


def test_cluster_design_inflates_primary_sample_size() -> None:
    base = calculate_experiment_metrics(dict(_BINARY_BASE))
    base_n = base["results"]["sample_size_per_variant"]
    expected = inflate_for_cluster_design(base_n, 100, 0.02, variants_count=2)

    result = calculate_experiment_metrics({**_BINARY_BASE, **_CLUSTER})

    assert result["design_effect"] == pytest.approx(2.98, abs=1e-4)
    assert result["avg_cluster_size"] == 100
    assert result["icc"] == 0.02
    assert result["clusters_per_variant"] == expected["clusters_per_variant"]
    assert result["results"]["sample_size_per_variant"] == expected["sample_size_per_variant"]
    assert result["results"]["total_sample_size"] == expected["total_sample_size"]
    # Inflated n takes at least as long to enrol at the same traffic.
    assert result["results"]["estimated_duration_days"] >= base["results"]["estimated_duration_days"]
    assert any("design effect" in note.lower() for note in result["assumptions"])


def test_cluster_design_icc_zero_matches_non_cluster_exactly() -> None:
    base = calculate_experiment_metrics(dict(_BINARY_BASE))
    result = calculate_experiment_metrics(
        {**_BINARY_BASE, "randomization_unit": "cluster", "avg_cluster_size": 100, "icc": 0.0}
    )
    assert result["design_effect"] == 1.0
    assert result["results"]["sample_size_per_variant"] == base["results"]["sample_size_per_variant"]
    assert result["results"]["total_sample_size"] == base["results"]["total_sample_size"]


def test_cluster_params_ignored_for_non_cluster_unit() -> None:
    base = calculate_experiment_metrics(dict(_BINARY_BASE))
    result = calculate_experiment_metrics(
        {**_BINARY_BASE, "randomization_unit": "user", "avg_cluster_size": 100, "icc": 0.02}
    )
    assert result["design_effect"] is None
    assert result["clusters_per_variant"] is None
    assert result["results"]["sample_size_per_variant"] == base["results"]["sample_size_per_variant"]


def test_cluster_unit_without_params_does_not_inflate() -> None:
    # The 5.1 warning-only path: cluster selected but no m / ICC supplied yet.
    base = calculate_experiment_metrics(dict(_BINARY_BASE))
    result = calculate_experiment_metrics({**_BINARY_BASE, "randomization_unit": "cluster"})
    assert result["design_effect"] is None
    assert result["results"]["sample_size_per_variant"] == base["results"]["sample_size_per_variant"]


def test_cluster_design_inflates_cuped_companion() -> None:
    cuped_inputs = {"cuped_pre_experiment_std": 18.0, "cuped_correlation": 0.6}
    base = calculate_experiment_metrics({**_CONTINUOUS_BASE, **cuped_inputs})
    base_cuped_n = base["cuped_sample_size_per_variant"]
    expected = inflate_for_cluster_design(base_cuped_n, 100, 0.02, variants_count=2)

    result = calculate_experiment_metrics({**_CONTINUOUS_BASE, **cuped_inputs, **_CLUSTER})

    assert result["cuped_sample_size_per_variant"] == expected["sample_size_per_variant"]
    assert result["cuped_sample_size_per_variant"] > base_cuped_n


def test_cluster_design_inflates_bayesian_companion() -> None:
    bayes_inputs = {"analysis_mode": "bayesian", "desired_precision": 2.0, "credibility": 0.95}
    base = calculate_experiment_metrics({**_CONTINUOUS_BASE, **bayes_inputs})
    base_bayes_n = base["bayesian_sample_size_per_variant"]
    expected = inflate_for_cluster_design(base_bayes_n, 100, 0.02, variants_count=2)

    result = calculate_experiment_metrics({**_CONTINUOUS_BASE, **bayes_inputs, **_CLUSTER})

    assert result["bayesian_sample_size_per_variant"] == expected["sample_size_per_variant"]
    assert result["bayesian_sample_size_per_variant"] > base_bayes_n
