"""Phase D — live experiment statistics over ingested exposures/conversions.

Covers the per-variation analysis-aggregate repository query (CTE join + dedup + holdout
exclusion), the live-stats service (SRM guardrail, frequentist + Bayesian comparison,
sequential boundary, CUPED variance reduction over an ingested pre-period covariate), and
the read endpoints (live-stats + pre-period ingestion).
"""

from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.constants import MAX_CUPED_COVARIATES
from app.backend.app.main import create_app
from app.backend.app.repository import ProjectRepository
from app.backend.app.services.live_stats_service import build_live_stats


# --- fixtures / builders --------------------------------------------------------------


def _repo() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    return ProjectRepository(str(db_path))


def _project(repo: ProjectRepository) -> str:
    project = repo.create_project(
        {
            "project": {"project_name": "Live exp"},
            "hypothesis": {},
            "setup": {},
            "metrics": {},
            "constraints": {},
            "additional_context": {},
        }
    )
    return project["id"]


def _binary_design(*, n_looks: int = 1) -> dict:
    return {
        "metrics": {
            "primary_metric_name": "purchase",
            "metric_type": "binary",
            "baseline_value": 0.10,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
        },
        "setup": {
            "traffic_split": [50, 50],
            "variants_count": 2,
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
        },
        "constraints": {
            "n_looks": n_looks,
            "analysis_mode": "frequentist",
            "seasonality_present": False,
            "active_campaigns_present": False,
            "long_test_possible": True,
            "credibility": 0.95,
        },
    }


def _continuous_design() -> dict:
    design = _binary_design()
    design["metrics"] = {
        "primary_metric_name": "aov",
        "metric_type": "continuous",
        "baseline_value": 45.0,
        "mde_pct": 4.4,
        "alpha": 0.05,
        "power": 0.8,
        "std_dev": 12.0,
    }
    return design


def _arm(index: int, exposed: int, converted: int, value_sum: float = 0.0, value_sq_sum: float = 0.0) -> dict:
    return {
        "variation_index": index,
        "exposed_users": exposed,
        "converted_users": converted,
        "value_sum": value_sum,
        "value_sq_sum": value_sq_sum,
    }


def _aggregates(*arms: dict) -> dict:
    return {"experiment_id": "e", "metric_name": "purchase", "variations": list(arms)}


def _cuped_arm(
    index: int, xs: list[float], ys: list[float]
) -> dict:
    """A CUPED per-variation sufficient-statistics row from paired (X, Y) values."""
    assert len(xs) == len(ys)
    return {
        "variation_index": index,
        "n": len(xs),
        "sum_x": sum(xs),
        "sum_x2": sum(x * x for x in xs),
        "sum_y": sum(ys),
        "sum_y2": sum(y * y for y in ys),
        "sum_xy": sum(x * y for x, y in zip(xs, ys)),
    }


def _multi_cuped_arm(index: int, covariates: list[list[float]], ys: list[float]) -> dict:
    """A multi-covariate CUPED per-variation row. ``covariates`` is a list of k per-covariate
    value-lists (each length n, aligned with ``ys``); the regression sufficient statistics
    (sum_x[], sum_xy[], symmetric sum_xx[][]) are rolled up here as the repository would."""
    n = len(ys)
    k = len(covariates)
    assert all(len(values) == n for values in covariates)
    return {
        "variation_index": index,
        "n": n,
        "sum_y": float(sum(ys)),
        "sum_y2": float(sum(y * y for y in ys)),
        "sum_x": [float(sum(covariates[j])) for j in range(k)],
        "sum_xy": [float(sum(covariates[j][i] * ys[i] for i in range(n))) for j in range(k)],
        "sum_xx": [
            [float(sum(covariates[i][m] * covariates[j][m] for m in range(n))) for j in range(k)]
            for i in range(k)
        ],
    }


def _multi_cuped_aggregates(names: list[str], *arms: dict, too_many: bool = False) -> dict:
    return {
        "experiment_id": "e",
        "metric_name": "aov",
        "covariate_names": list(names),
        "too_many_covariates": too_many,
        "variations": list(arms),
    }


def _ratio_design(*, n_looks: int = 1) -> dict:
    design = _binary_design(n_looks=n_looks)
    design["metrics"] = {
        "primary_metric_name": "ctr",
        "metric_type": "ratio",
        "numerator_metric_name": "clicks",
        "denominator_metric_name": "impressions",
        "baseline_value": 0.2,
        "mde_pct": 5,
        "alpha": 0.05,
        "power": 0.8,
    }
    return design


def _ratio_aggregates(*arms: dict) -> dict:
    # arms reuse the CUPED sufficient-statistics shape (x = denominator, y = numerator).
    return {
        "experiment_id": "e",
        "numerator_metric": "clicks",
        "denominator_metric": "impressions",
        "variations": list(arms),
    }


# --- repository: analysis aggregates --------------------------------------------------


def test_analysis_aggregates_join_dedups_users_and_excludes_holdout() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 0},
            {"user_id": "u4", "variation_index": 1},
            {"user_id": "u5", "variation_index": 1},
            {"user_id": "uH", "variation_index": -1},  # holdout — excluded from the arms
        ],
    )
    repo.record_conversions(
        exp,
        [
            # u1 converts twice on the primary metric -> counts once, value sums to 2.0
            {"user_id": "u1", "metric": "purchase", "value": 1.0},
            {"user_id": "u1", "metric": "purchase", "value": 1.0},
            {"user_id": "u2", "metric": "purchase", "value": 1.0},
            {"user_id": "u3", "metric": "other", "value": 9.0},  # different metric -> ignored
            {"user_id": "u4", "metric": "purchase", "value": 1.0},
            {"user_id": "uH", "metric": "purchase", "value": 1.0},  # holdout -> excluded
        ],
    )

    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates is not None
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}

    assert by_index[0]["exposed_users"] == 3
    assert by_index[0]["converted_users"] == 2  # u1, u2 (u3 only converted on "other")
    assert by_index[0]["value_sum"] == 3.0  # u1: 2.0 + u2: 1.0 + u3: 0
    assert by_index[0]["value_sq_sum"] == 5.0  # 2.0**2 + 1.0**2 + 0

    assert by_index[1]["exposed_users"] == 2
    assert by_index[1]["converted_users"] == 1  # u4
    assert -1 not in by_index  # holdout never appears


def test_analysis_aggregates_none_for_unknown_experiment() -> None:
    repo = _repo()
    assert repo.get_experiment_analysis_aggregates("missing", "purchase") is None


def test_analysis_aggregates_empty_for_fresh_experiment() -> None:
    repo = _repo()
    exp = _project(repo)
    aggregates = repo.get_experiment_analysis_aggregates(exp, "purchase")
    assert aggregates == {
        "experiment_id": exp,
        "metric_name": "purchase",
        "variations": [],
        "population_policy_version": "analytical_population_v1",
    }


# --- repository: ratio aggregates (F2) ------------------------------------------------


def test_ratio_aggregates_rolls_up_numerator_and_denominator_per_user() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 1},
            {"user_id": "uH", "variation_index": -1},  # holdout — excluded from the arms
        ],
    )
    repo.record_conversions(
        exp,
        [
            # u1: 2 clicks over 10 impressions; u2: 1 click over 20 impressions.
            {"user_id": "u1", "metric": "clicks", "value": 2.0},
            {"user_id": "u1", "metric": "impressions", "value": 10.0},
            {"user_id": "u2", "metric": "clicks", "value": 1.0},
            {"user_id": "u2", "metric": "impressions", "value": 20.0},
            {"user_id": "u2", "metric": "other", "value": 99.0},  # unrelated metric -> ignored
            {"user_id": "u3", "metric": "clicks", "value": 5.0},
            {"user_id": "u3", "metric": "impressions", "value": 50.0},
            {"user_id": "uH", "metric": "clicks", "value": 100.0},  # holdout -> excluded
        ],
    )

    aggregates = repo.get_ratio_aggregates(exp, "clicks", "impressions")
    assert aggregates is not None
    assert aggregates["numerator_metric"] == "clicks"
    assert aggregates["denominator_metric"] == "impressions"
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}

    # arm 0: u1 (x=10, y=2), u2 (x=20, y=1)
    assert by_index[0]["n"] == 2
    assert by_index[0]["sum_x"] == 30.0  # 10 + 20
    assert by_index[0]["sum_y"] == 3.0  # 2 + 1
    assert by_index[0]["sum_x2"] == 500.0  # 100 + 400
    assert by_index[0]["sum_y2"] == 5.0  # 4 + 1
    assert by_index[0]["sum_xy"] == 40.0  # 10*2 + 20*1
    # arm 1: u3 (x=50, y=5)
    assert by_index[1]["n"] == 1
    assert by_index[1]["sum_xy"] == 250.0  # 50*5
    assert -1 not in by_index  # holdout never appears


def test_ratio_aggregates_counts_exposed_users_without_events() -> None:
    # Every exposed user is the analysis unit; one with no numerator/denominator events
    # contributes (x=0, y=0) and still counts toward n (it is not dropped).
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},  # no conversions -> (x=0, y=0)
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "clicks", "value": 3.0},
            {"user_id": "u1", "metric": "impressions", "value": 12.0},
        ],
    )
    aggregates = repo.get_ratio_aggregates(exp, "clicks", "impressions")
    assert aggregates is not None
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}
    assert by_index[0]["n"] == 2  # both exposed users count
    assert by_index[0]["sum_x"] == 12.0
    assert by_index[0]["sum_y"] == 3.0


def test_ratio_aggregates_none_for_unknown_experiment() -> None:
    repo = _repo()
    assert repo.get_ratio_aggregates("missing", "clicks", "impressions") is None


# --- service: SRM guardrail -----------------------------------------------------------


def test_live_stats_srm_ok_when_balanced() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    assert result["srm"]["status"] == "ok"
    assert result["srm"]["is_srm"] is False


def test_live_stats_srm_detected_when_split_is_broken() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 3000, 300))
    )
    assert result["srm"]["status"] == "srm_detected"
    assert result["srm"]["is_srm"] is True
    assert result["srm"]["p_value"] < 0.001


def test_live_stats_srm_insufficient_without_exposures() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 0, 0), _arm(1, 0, 0))
    )
    assert result["srm"]["status"] == "insufficient_data"


# --- service: frequentist + Bayesian comparison ---------------------------------------


def test_live_stats_binary_comparison_runs_frequentist_and_bayesian() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["treatment_index"] == 1
    assert comparison["analysis"]["is_significant"] is True
    assert comparison["analysis"]["observed_effect"] > 0
    prob = comparison["probability_treatment_beats_control"]
    assert 0.0 <= prob <= 1.0
    assert prob > 0.9  # treatment 12% clearly beats control 10%


def test_live_stats_probability_rounded_to_monte_carlo_precision() -> None:
    # P(treatment > control) is a 10k-draw Monte-Carlo estimate whose standard
    # error is ~0.005, so the service rounds it to 3 decimals. Assert it never
    # carries digits below that simulation-noise floor (no false precision).
    binary = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )["comparisons"][0]["probability_treatment_beats_control"]
    continuous = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=3000.0),
            _arm(1, 4, 4, value_sum=180.0, value_sq_sum=8600.0),
        ),
    )["comparisons"][0]["probability_treatment_beats_control"]
    for prob in (binary, continuous):
        assert prob is not None
        assert round(prob, 3) == prob  # rounded; no precision past the 3rd decimal


def test_live_stats_comparison_insufficient_data_when_arm_too_small() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 1, 0), _arm(1, 1, 1))
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "insufficient_data"
    assert comparison["analysis"] is None


def test_live_stats_continuous_comparison_has_frequentist_and_bayesian() -> None:
    # control values mean 25 (sq_sum 3000 over n=4), treatment mean 45 (sq_sum 8600 over n=4)
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=3000.0),
            _arm(1, 4, 4, value_sum=180.0, value_sq_sum=8600.0),
        ),
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["control"]["mean"] == 25.0
    assert comparison["analysis"]["observed_effect"] == 20.0
    prob = comparison["probability_treatment_beats_control"]
    assert 0.0 <= prob <= 1.0
    assert prob > 0.5  # treatment mean 45 > control mean 25


# --- service: ratio metrics (F2, delta method) ----------------------------------------

# Denominators (impressions) shared across arms; numerators (clicks) chosen so control ratio
# ≈ 0.20 and treatment ≈ 0.30, with per-user scatter so the delta-method variance is non-zero.
_RATIO_DEN = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
_RATIO_NUM_CONTROL = [1.0, 5.0, 5.0, 9.0, 12.0, 10.0]  # sum 42 / 210 = 0.20
_RATIO_NUM_TREATMENT = [2.0, 7.0, 9.0, 12.0, 17.0, 16.0]  # sum 63 / 210 = 0.30


def test_live_stats_ratio_runs_delta_method_and_always_valid() -> None:
    result = build_live_stats(
        "e",
        _ratio_design(),
        _aggregates(_arm(0, 6, 0), _arm(1, 6, 0)),
        ratio_aggregates=_ratio_aggregates(
            _cuped_arm(0, _RATIO_DEN, _RATIO_NUM_CONTROL),
            _cuped_arm(1, _RATIO_DEN, _RATIO_NUM_TREATMENT),
        ),
    )
    assert result["metric_type"] == "ratio"
    comparison = result["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["treatment_index"] == 1
    assert comparison["control"]["ratio"] == pytest.approx(0.20, abs=1e-6)
    assert comparison["treatment"]["ratio"] == pytest.approx(0.30, abs=1e-6)
    assert comparison["analysis"]["metric_type"] == "ratio"
    assert comparison["analysis"]["observed_effect"] == pytest.approx(0.10, abs=1e-6)
    # The anytime-valid (mSPRT) view is computed over the same ratio difference.
    assert comparison["always_valid"]["status"] in ("ok", "not_evaluable")
    # Bayesian P(B>A) is not provided for ratio metrics in the MVP.
    assert comparison["probability_treatment_beats_control"] is None
    # CUPED routes through the continuous estimator, so it does not apply to a ratio metric.
    assert result["cuped"]["status"] == "not_applicable"


def test_live_stats_ratio_insufficient_when_arm_too_small() -> None:
    result = build_live_stats(
        "e",
        _ratio_design(),
        _aggregates(_arm(0, 1, 0), _arm(1, 1, 0)),
        ratio_aggregates=_ratio_aggregates(
            _cuped_arm(0, [10.0], [2.0]),
            _cuped_arm(1, [10.0], [3.0]),
        ),
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "insufficient_data"
    assert comparison["analysis"] is None
    assert comparison["control"]["ratio"] is None


def test_live_stats_ratio_multi_arm_uses_bonferroni() -> None:
    design = _ratio_design()
    design["setup"]["variants_count"] = 3
    design["setup"]["traffic_split"] = [34, 33, 33]
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 6, 0), _arm(1, 6, 0), _arm(2, 6, 0)),
        ratio_aggregates=_ratio_aggregates(
            _cuped_arm(0, _RATIO_DEN, _RATIO_NUM_CONTROL),
            _cuped_arm(1, _RATIO_DEN, _RATIO_NUM_TREATMENT),
            _cuped_arm(2, _RATIO_DEN, _RATIO_NUM_TREATMENT),
        ),
    )
    comparisons = result["comparisons"]
    assert len(comparisons) == 2
    for comparison in comparisons:
        if comparison["status"] == "ok":
            # Bonferroni alpha = 0.05 / 2 comparisons = 0.025 -> CI level 0.975.
            assert comparison["analysis"]["ci_level"] == pytest.approx(0.975)
            assert "Bonferroni" in (comparison["note"] or "")


def test_live_stats_ratio_sequential_does_not_crash_with_multiple_looks() -> None:
    # Ratio sizing can produce a planned denominator, but this tiny live read has too little
    # exposure to place a usable sequential boundary.
    result = build_live_stats(
        "e",
        _ratio_design(n_looks=4),
        _aggregates(_arm(0, 6, 0), _arm(1, 6, 0)),
        ratio_aggregates=_ratio_aggregates(
            _cuped_arm(0, _RATIO_DEN, _RATIO_NUM_CONTROL),
            _cuped_arm(1, _RATIO_DEN, _RATIO_NUM_TREATMENT),
        ),
    )
    assert result["sequential"]["status"] == "insufficient_data"
    # The primary comparison still computed fine.
    assert result["comparisons"][0]["status"] == "ok"


def test_live_stats_multi_arm_compares_each_treatment_to_control() -> None:
    design = _binary_design()
    design["setup"]["traffic_split"] = [34, 33, 33]
    design["setup"]["variants_count"] = 3
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 3400, 340), _arm(1, 3300, 360), _arm(2, 3300, 300)),
    )
    assert [c["treatment_index"] for c in result["comparisons"]] == [1, 2]


def test_live_stats_multi_arm_applies_bonferroni_to_each_comparison() -> None:
    # Three variants -> two control-vs-treatment comparisons -> each test runs at alpha / 2 = 0.025,
    # so the reported confidence level is 0.975 and the comparison carries the Bonferroni note. This
    # mirrors the planning side (stats.binary) and keeps the live readout's family-wise error in line
    # with the alpha the sample size was planned for.
    design = _binary_design()
    design["setup"]["traffic_split"] = [34, 33, 33]
    design["setup"]["variants_count"] = 3
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 4000, 400), _arm(1, 4000, 480), _arm(2, 4000, 360)),
    )
    comparisons = result["comparisons"]
    assert [c["treatment_index"] for c in comparisons] == [1, 2]
    for comparison in comparisons:
        assert comparison["status"] == "ok"
        assert comparison["analysis"]["ci_level"] == 0.975
        assert "Bonferroni" in (comparison["note"] or "")


def test_live_stats_two_arm_keeps_nominal_alpha() -> None:
    # One treatment -> Bonferroni is a no-op: nominal 0.05 -> 0.95 CI level, no multiple-comparison
    # note. Guards the two-variant path against regressing when the multi-arm correction was added.
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 4000, 400), _arm(1, 4000, 480))
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["analysis"]["ci_level"] == 0.95
    assert comparison["note"] is None


# --- service: always-valid (mSPRT) ----------------------------------------------------


def test_live_stats_binary_comparison_includes_always_valid_block() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 650))
    )
    block = result["comparisons"][0]["always_valid"]
    assert block is not None
    assert block["status"] == "ok"
    assert 0.0 <= block["always_valid_p_value"] <= 1.0
    assert block["ci_sequence_lower"] < block["ci_sequence_upper"]
    assert block["confidence_level"] == 0.95  # two-arm: nominal alpha
    # tau^2 from the design MDE: baseline 0.10 * 5% relative = 0.005 absolute -> tau^2 = 2.5e-5.
    assert abs(block["mixture_variance"] - 2.5e-5) < 1e-9


def test_live_stats_continuous_comparison_includes_always_valid_block() -> None:
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 50, 50, value_sum=2250.0, value_sq_sum=108000.0),
            _arm(1, 50, 50, value_sum=2400.0, value_sq_sum=123000.0),
        ),
    )
    block = result["comparisons"][0]["always_valid"]
    assert block is not None
    assert block["status"] == "ok"
    assert block["ci_sequence_lower"] < block["ci_sequence_upper"]


def test_live_stats_always_valid_flags_clear_effect_and_excludes_zero() -> None:
    # A large, unambiguous lift (10% -> 14% on 5000/arm) should be anytime-significant, and the
    # confidence sequence must exclude zero in agreement with that verdict (test/CS duality).
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 700))
    )
    block = result["comparisons"][0]["always_valid"]
    assert block["is_significant"] is True
    assert block["ci_sequence_lower"] > 0  # whole sequence above zero
    assert block["always_valid_p_value"] < 0.05


def test_live_stats_always_valid_not_significant_without_effect() -> None:
    # Identical arms: no effect -> always-valid p clamps to 1, sequence straddles zero.
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 500))
    )
    block = result["comparisons"][0]["always_valid"]
    assert block["is_significant"] is False
    assert block["always_valid_p_value"] == 1.0
    assert block["ci_sequence_lower"] < 0 < block["ci_sequence_upper"]


def test_live_stats_always_valid_is_fwer_consistent_in_multi_arm() -> None:
    # Three variants -> each comparison runs at alpha/2 = 0.025, so the anytime-valid sequence uses
    # the same FWER-adjusted level (0.975) as the frequentist CI. Guards the multi-arm path.
    design = _binary_design()
    design["setup"]["traffic_split"] = [34, 33, 33]
    design["setup"]["variants_count"] = 3
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 4000, 400), _arm(1, 4000, 480), _arm(2, 4000, 360)),
    )
    for comparison in result["comparisons"]:
        assert comparison["always_valid"]["confidence_level"] == 0.975


# --- service: sequential + CUPED ------------------------------------------------------


def test_live_stats_sequential_fixed_horizon_when_single_look() -> None:
    result = build_live_stats(
        "e", _binary_design(n_looks=1), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    sequential = result["sequential"]
    assert sequential["status"] == "fixed_horizon"
    # The fixed-horizon block still carries the planned size and the share of it collected so far,
    # so the decision readout can tell the planned single read from an early peek.
    assert sequential["planned_sample_size_per_variant"] > 0
    assert 0.0 < sequential["information_fraction"] <= 1.0


def test_live_stats_fixed_horizon_fraction_is_none_when_sizing_unavailable() -> None:
    # A design whose sizing cannot be computed (continuous metric stored without std_dev) keeps the
    # fixed-horizon block usable — planned size and fraction just stay None instead of crashing.
    design = _binary_design(n_looks=1)
    design["metrics"]["metric_type"] = "continuous"
    design["metrics"]["std_dev"] = None
    result = build_live_stats(
        "e",
        design,
        _aggregates(
            {"variation_index": 0, "exposed_users": 50, "converted_users": 50, "value_sum": 500.0, "value_sq_sum": 5500.0},
            {"variation_index": 1, "exposed_users": 50, "converted_users": 50, "value_sum": 550.0, "value_sq_sum": 6600.0},
        ),
    )
    sequential = result["sequential"]
    assert sequential["status"] == "fixed_horizon"
    assert sequential["planned_sample_size_per_variant"] is None
    assert sequential["information_fraction"] is None


def test_live_stats_sequential_active_with_boundary_when_multiple_looks() -> None:
    result = build_live_stats(
        "e", _binary_design(n_looks=3), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    sequential = result["sequential"]
    assert sequential["status"] == "active"
    assert sequential["planned_sample_size_per_variant"] > 0
    assert 0.0 < sequential["information_fraction"] <= 1.0
    assert sequential["current_boundary_z"] is not None
    # Early in the experiment the O'Brien-Fleming boundary is stricter than the live z,
    # so the comparison is not yet sequential-significant even though the fixed-horizon test is.
    assert result["comparisons"][0]["sequential_significant"] is False


def test_live_stats_cuped_not_applicable_for_binary_metric() -> None:
    # Live CUPED routes through the continuous t-test, so it does not apply to binary metrics.
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 100, 10), _arm(1, 100, 12))
    )
    assert result["cuped"]["status"] == "not_applicable"
    assert result["cuped"]["comparisons"] == []


def test_live_stats_cuped_unavailable_for_continuous_without_covariate() -> None:
    # Continuous metric but no pre-period covariate ingested -> CUPED stays unavailable.
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=3000.0),
            _arm(1, 4, 4, value_sum=180.0, value_sq_sum=8600.0),
        ),
    )
    assert result["cuped"]["status"] == "unavailable"
    assert result["cuped"]["covariate_users_total"] == 0
    assert result["cuped"]["exposed_users_total"] == 8


# --- route ----------------------------------------------------------------------------


def _create_binary_project(client: TestClient, *, mde_pct: float = 5) -> str:
    # mde_pct sets the planned sample size and therefore whether a read at a few hundred users is
    # the planned fixed-horizon read (large mde -> small plan) or an early peek (default plan is
    # ~57.8k/arm, so every small ingest below is "early" unless a test opts out).
    payload = {
        "project": {
            "project_name": "Live route exp",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "Testing the live-stats read.",
        },
        "hypothesis": {
            "change_description": "simpler checkout",
            "target_audience": "new users",
            "business_problem": "abandonment",
            "hypothesis_statement": "simpler checkout lifts conversion",
            "what_to_validate": "conversion",
            "desired_result": "uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "new users",
            "exclusion_criteria": "staff",
        },
        "metrics": {
            "primary_metric_name": "purchase",
            "metric_type": "binary",
            "baseline_value": 0.10,
            "expected_uplift_pct": 8,
            "mde_pct": mde_pct,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
        },
        "constraints": {
            "seasonality_present": False,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "low",
            "technical_constraints": "none",
            "legal_or_ethics_constraints": "none",
            "known_risks": "none",
            "deadline_pressure": "low",
            "long_test_possible": True,
        },
        "additional_context": {"llm_context": ""},
    }
    created = client.post("/api/v1/projects", json=payload)
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_live_stats_route_returns_404_for_unknown_experiment() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/experiments/missing/live-stats")
    assert response.status_code == 404


def test_live_stats_route_reports_srm_and_comparison() -> None:
    client = TestClient(create_app())
    project_id = _create_binary_project(client)

    exposures = [{"user_id": f"c{i}", "variation_index": 0} for i in range(200)]
    exposures += [{"user_id": f"t{i}", "variation_index": 1} for i in range(200)]
    assert (
        client.post(f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}).status_code
        == 200
    )
    conversions = [{"user_id": f"c{i}", "metric": "purchase"} for i in range(20)]
    conversions += [{"user_id": f"t{i}", "metric": "purchase"} for i in range(40)]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": conversions}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metric_type"] == "binary"
    assert data["primary_metric_name"] == "purchase"
    assert data["exposures_total"] == 400
    assert data["srm"]["status"] == "ok"
    assert len(data["comparisons"]) == 1
    assert data["comparisons"][0]["control"]["conversion_rate"] == 0.1
    assert data["comparisons"][0]["treatment"]["conversion_rate"] == 0.2
    assert data["cuped"]["status"] == "not_applicable"  # binary metric
    assert "MVP" in data["disclaimer"]


# --- decision readout route -----------------------------------------------------------


def test_decision_route_returns_404_for_unknown_experiment() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/experiments/missing/decision")
    assert response.status_code == 404


def test_decision_route_ships_on_a_clear_win() -> None:
    client = TestClient(create_app())
    # mde 100% plans ~199/arm, so the 200/arm ingest below is the planned fixed-horizon read.
    project_id = _create_binary_project(client, mde_pct=100)

    exposures = [{"user_id": f"c{i}", "variation_index": 0} for i in range(200)]
    exposures += [{"user_id": f"t{i}", "variation_index": 1} for i in range(200)]
    assert (
        client.post(f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}).status_code
        == 200
    )
    conversions = [{"user_id": f"c{i}", "metric": "purchase"} for i in range(20)]  # control 10%
    conversions += [{"user_id": f"t{i}", "metric": "purchase"} for i in range(40)]  # treatment 20%
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": conversions}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/decision")
    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["experiment_id"] == project_id
    assert decision["verdict"] == "ship"
    assert decision["confidence"] in {"high", "medium"}
    assert any(reason["code"] == "significant_win" for reason in decision["reasons"])
    assert decision["blockers"] == []


# --- CUPED on live data (E5) ----------------------------------------------------------


def test_cuped_constant_covariate_gives_zero_theta_and_matches_unadjusted() -> None:
    # A constant covariate has var(X) = 0 -> theta = 0 -> CUPED collapses to the unadjusted
    # estimate: adjusted means equal raw means and the variance reduction is exactly zero.
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=2600.0),
            _arm(1, 4, 4, value_sum=180.0, value_sq_sum=8200.0),
        ),
        _multi_cuped_aggregates(
            ["__default__"],
            _multi_cuped_arm(0, [[5, 5, 5, 5]], [20, 30, 20, 30]),
            _multi_cuped_arm(1, [[5, 5, 5, 5]], [40, 50, 40, 50]),
        ),
    )
    cuped = result["cuped"]
    assert cuped["status"] == "available"
    assert cuped["theta"] == 0.0
    assert cuped["num_covariates"] == 1
    assert cuped["variance_reduction_pct"] == 0.0
    comparison = cuped["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["control"]["adjusted_mean"] == comparison["control"]["unadjusted_mean"] == 25.0
    assert comparison["treatment"]["adjusted_mean"] == comparison["treatment"]["unadjusted_mean"] == 45.0
    assert comparison["analysis"]["observed_effect"] == 20.0


def test_cuped_correlated_covariate_reduces_variance_and_preserves_effect() -> None:
    # X and Y are positively correlated, with equal X means across arms -> the treatment effect
    # is preserved while the residual variance (and thus the t-test denominator) shrinks.
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=2950.0),
            _arm(1, 4, 4, value_sum=130.0, value_sq_sum=4550.0),
        ),
        _multi_cuped_aggregates(
            ["__default__"],
            _multi_cuped_arm(0, [[1, 2, 3, 4]], [10, 25, 25, 40]),
            _multi_cuped_arm(1, [[1, 2, 3, 4]], [20, 30, 35, 45]),
        ),
    )
    cuped = result["cuped"]
    assert cuped["status"] == "available"
    assert cuped["theta"] == 8.5  # cov(X,Y)/var(X) pooled = (85/7)/(10/7)
    assert cuped["covariates"] == [{"name": "__default__", "theta": 8.5}]
    assert cuped["variance_reduction_pct"] > 50.0  # strong correlation -> large reduction
    assert cuped["covariate_users_total"] == 8
    comparison = cuped["comparisons"][0]
    assert comparison["status"] == "ok"
    # X means are equal across arms, so the adjusted effect equals the raw mean difference (7.5).
    assert comparison["analysis"]["observed_effect"] == 7.5
    assert comparison["control"]["adjusted_std"] is not None
    assert comparison["treatment"]["adjusted_std"] is not None


def test_cuped_insufficient_when_arm_has_under_two_covariate_users() -> None:
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=2950.0),
            _arm(1, 4, 4, value_sum=130.0, value_sq_sum=4550.0),
        ),
        _multi_cuped_aggregates(
            ["__default__"],
            _multi_cuped_arm(0, [[1, 2, 3, 4]], [10, 25, 25, 40]),
            _multi_cuped_arm(1, [[1]], [20]),  # only one covariate user in the treatment arm
        ),
    )
    assert result["cuped"]["status"] == "available"
    assert result["cuped"]["comparisons"][0]["status"] == "insufficient_data"


def test_cuped_aggregates_restrict_to_covariate_users_and_exclude_holdout() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 0},  # no covariate -> excluded from CUPED
            {"user_id": "u4", "variation_index": 1},
            {"user_id": "u5", "variation_index": 1},
            {"user_id": "uH", "variation_index": -1},  # holdout -> excluded
        ],
    )
    repo.record_pre_period_values(
        exp,
        [
            {"user_id": "u1", "value": 10.0},
            {"user_id": "u2", "value": 20.0},
            {"user_id": "u4", "value": 40.0},
            {"user_id": "u5", "value": 50.0},
            {"user_id": "uH", "value": 99.0},  # holdout covariate present but arm excluded
            {"user_id": "u9", "value": 7.0},  # never exposed -> excluded
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "aov", "value": 1.0},
            {"user_id": "u1", "metric": "aov", "value": 1.0},  # u1 Y sums to 2.0
            {"user_id": "u2", "metric": "aov", "value": 3.0},
            {"user_id": "u4", "metric": "aov", "value": 5.0},
            # u5 has no conversion -> Y = 0
        ],
    )

    aggregates = repo.get_cuped_aggregates(exp, "aov")
    assert aggregates is not None
    # Legacy single-covariate ingestion lands under the reserved "__default__" name.
    assert aggregates["covariate_names"] == ["__default__"]
    assert aggregates["too_many_covariates"] is False
    by_index = {arm["variation_index"]: arm for arm in aggregates["variations"]}

    assert by_index[0]["n"] == 2  # u1, u2 (u3 has no covariate)
    assert by_index[0]["sum_x"] == [30.0]
    assert by_index[0]["sum_xx"] == [[500.0]]  # 10^2 + 20^2 (raw second moment = diagonal)
    assert by_index[0]["sum_y"] == 5.0  # u1: 2.0 + u2: 3.0
    assert by_index[0]["sum_y2"] == 13.0  # 2^2 + 3^2
    assert by_index[0]["sum_xy"] == [80.0]  # 10*2 + 20*3

    assert by_index[1]["n"] == 2  # u4, u5
    assert by_index[1]["sum_y"] == 5.0  # u4: 5.0 + u5: 0
    assert by_index[1]["sum_xy"] == [200.0]  # 40*5 + 50*0
    assert -1 not in by_index  # holdout never appears


def test_cuped_aggregates_none_for_unknown_experiment() -> None:
    repo = _repo()
    assert repo.get_cuped_aggregates("missing", "aov") is None


def test_record_pre_period_values_dedups_per_user() -> None:
    repo = _repo()
    exp = _project(repo)
    first = repo.record_pre_period_values(
        exp, [{"user_id": "u1", "value": 5.0}, {"user_id": "u2", "value": 6.0}]
    )
    assert first == {"received": 2, "recorded": 2, "deduplicated": 0}
    # First-write-wins: a later value for u1 is dropped.
    second = repo.record_pre_period_values(exp, [{"user_id": "u1", "value": 99.0}])
    assert second == {"received": 1, "recorded": 0, "deduplicated": 1}


def test_record_pre_period_values_dedups_per_named_covariate() -> None:
    # First-write-wins is per (user, covariate): two different covariates for the same user are
    # both recorded; a repeat of the same (user, covariate) is dropped (F3a).
    repo = _repo()
    exp = _project(repo)
    first = repo.record_pre_period_values(
        exp,
        [
            {"user_id": "u1", "covariate_name": "spend", "value": 5.0},
            {"user_id": "u1", "covariate_name": "visits", "value": 2.0},
        ],
    )
    assert first == {"received": 2, "recorded": 2, "deduplicated": 0}
    repeat = repo.record_pre_period_values(
        exp, [{"user_id": "u1", "covariate_name": "spend", "value": 99.0}]
    )
    assert repeat == {"received": 1, "recorded": 0, "deduplicated": 1}


def test_cuped_aggregates_multi_covariate_requires_complete_vector() -> None:
    # Multi-covariate CUPED only adjusts users that carry every covariate (F3a). A user missing one
    # covariate is dropped, mirroring E5's "must have the covariate" rule for the vector case.
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "a", "variation_index": 0},
            {"user_id": "b", "variation_index": 0},
            {"user_id": "c", "variation_index": 0},  # only one covariate -> incomplete -> excluded
        ],
    )
    repo.record_pre_period_values(
        exp,
        [
            {"user_id": "a", "covariate_name": "spend", "value": 2.0},
            {"user_id": "a", "covariate_name": "visits", "value": 1.0},
            {"user_id": "b", "covariate_name": "spend", "value": 4.0},
            {"user_id": "b", "covariate_name": "visits", "value": 3.0},
            {"user_id": "c", "covariate_name": "spend", "value": 9.0},  # no "visits" -> incomplete
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "a", "metric": "rev", "value": 10.0},
            {"user_id": "b", "metric": "rev", "value": 20.0},
        ],
    )

    aggregates = repo.get_cuped_aggregates(exp, "rev")
    assert aggregates is not None
    assert aggregates["covariate_names"] == ["spend", "visits"]  # discovered, sorted
    arm0 = {arm["variation_index"]: arm for arm in aggregates["variations"]}[0]
    assert arm0["n"] == 2  # a, b (c dropped — incomplete vector)
    assert arm0["sum_x"] == [6.0, 4.0]  # spend 2+4, visits 1+3
    assert arm0["sum_y"] == 30.0 and arm0["sum_y2"] == 500.0
    # symmetric raw cross-moment matrix: spend^2=4+16=20, spend*visits=2+12=14, visits^2=1+9=10
    assert arm0["sum_xx"] == [[20.0, 14.0], [14.0, 10.0]]
    assert arm0["sum_xy"] == [100.0, 70.0]  # spend*y 20+80, visits*y 10+60


def test_cuped_multi_covariate_live_returns_theta_vector() -> None:
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=80.0, value_sq_sum=1808.0),
            _arm(1, 4, 4, value_sum=112.0, value_sq_sum=3344.0),
        ),
        _multi_cuped_aggregates(
            ["spend", "visits"],
            _multi_cuped_arm(0, [[1, 2, 3, 4], [2, 1, 4, 3]], [10, 12, 30, 28]),
            _multi_cuped_arm(1, [[1, 2, 3, 4], [2, 1, 4, 3]], [18, 20, 38, 36]),
        ),
    )
    cuped = result["cuped"]
    assert cuped["status"] == "available"
    assert cuped["num_covariates"] == 2
    assert cuped["theta"] is None  # scalar convenience only for the single-covariate case
    assert [c["name"] for c in cuped["covariates"]] == ["spend", "visits"]
    assert cuped["variance_reduction_pct"] is not None
    assert cuped["comparisons"][0]["status"] == "ok"


def test_cuped_too_many_covariates_flagged() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(exp, [{"user_id": "u1", "variation_index": 0}])
    over_cap = MAX_CUPED_COVARIATES + 1
    repo.record_pre_period_values(
        exp,
        [{"user_id": "u1", "covariate_name": f"c{i:02d}", "value": float(i)} for i in range(over_cap)],
    )
    aggregates = repo.get_cuped_aggregates(exp, "rev")
    assert aggregates is not None
    assert aggregates["too_many_covariates"] is True
    assert aggregates["variations"] == []  # heavy rollup skipped
    block = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(
            _arm(0, 4, 4, value_sum=100.0, value_sq_sum=2600.0),
            _arm(1, 4, 4, value_sum=180.0, value_sq_sum=8200.0),
        ),
        aggregates,
    )["cuped"]
    assert block["status"] == "too_many_covariates"
    assert block["num_covariates"] == over_cap


def test_cuped_aggregates_migrate_legacy_single_covariate() -> None:
    # A database written before F3a has rows only in the legacy pre_period_values table; reopening
    # the repository backfills them into pre_period_covariates under the "__default__" name.
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp, [{"user_id": "u1", "variation_index": 0}, {"user_id": "u2", "variation_index": 0}]
    )
    repo.record_conversions(exp, [{"user_id": "u1", "metric": "aov", "value": 4.0}])
    with repo._backend._transaction() as conn:  # type: ignore[attr-defined]
        conn.execute("DELETE FROM pre_period_covariates")
        conn.execute(
            "INSERT INTO pre_period_values (id, experiment_id, user_id, value, created_at) "
            "VALUES (?,?,?,?,?)",
            ("legacy1", exp, "u1", 10.0, "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO pre_period_values (id, experiment_id, user_id, value, created_at) "
            "VALUES (?,?,?,?,?)",
            ("legacy2", exp, "u2", 20.0, "2026-01-01"),
        )
        conn.commit()

    reopened = ProjectRepository(str(repo._backend.db_path))  # type: ignore[attr-defined]
    aggregates = reopened.get_cuped_aggregates(exp, "aov")
    assert aggregates is not None
    assert aggregates["covariate_names"] == ["__default__"]
    arm0 = {arm["variation_index"]: arm for arm in aggregates["variations"]}[0]
    assert arm0["n"] == 2 and arm0["sum_x"] == [30.0]  # 10 + 20 migrated


def _create_continuous_project(client: TestClient) -> str:
    payload = {
        "project": {
            "project_name": "Live CUPED exp",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "Testing live CUPED.",
        },
        "hypothesis": {
            "change_description": "bigger basket",
            "target_audience": "all users",
            "business_problem": "low AOV",
            "hypothesis_statement": "recommendations lift AOV",
            "what_to_validate": "AOV",
            "desired_result": "uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "all",
            "exclusion_criteria": "staff",
        },
        "metrics": {
            "primary_metric_name": "aov",
            "metric_type": "continuous",
            "baseline_value": 45.0,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": 12.0,
        },
        "constraints": {
            "seasonality_present": False,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "low",
            "technical_constraints": "none",
            "legal_or_ethics_constraints": "none",
            "known_risks": "none",
            "deadline_pressure": "low",
            "long_test_possible": True,
        },
        "additional_context": {"llm_context": ""},
    }
    created = client.post("/api/v1/projects", json=payload)
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_live_stats_route_reports_available_cuped_after_pre_period_ingest() -> None:
    client = TestClient(create_app())
    project_id = _create_continuous_project(client)

    control = [f"c{i}" for i in range(6)]
    treatment = [f"t{i}" for i in range(6)]
    exposures = [{"user_id": u, "variation_index": 0} for u in control]
    exposures += [{"user_id": u, "variation_index": 1} for u in treatment]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}
        ).status_code
        == 200
    )

    control_x = [10, 12, 14, 16, 18, 20]
    treatment_x = [11, 13, 15, 17, 19, 21]
    pre_period = [{"user_id": u, "value": x} for u, x in zip(control, control_x)]
    pre_period += [{"user_id": u, "value": x} for u, x in zip(treatment, treatment_x)]
    pre_resp = client.post(
        f"/api/v1/experiments/{project_id}/pre-period", json={"pre_period_values": pre_period}
    )
    assert pre_resp.status_code == 200, pre_resp.text
    assert pre_resp.json() == {"received": 12, "recorded": 12, "deduplicated": 0}
    # A retry for an already-recorded user is deduped (first-write-wins).
    retry = client.post(
        f"/api/v1/experiments/{project_id}/pre-period",
        json={"pre_period_values": [{"user_id": "c0", "value": 999.0}]},
    )
    assert retry.json() == {"received": 1, "recorded": 0, "deduplicated": 1}

    control_y = [40, 45, 55, 60, 50, 48]
    treatment_y = [50, 55, 60, 70, 65, 58]
    conversions = [
        {"user_id": u, "metric": "aov", "value": float(y)} for u, y in zip(control, control_y)
    ]
    conversions += [
        {"user_id": u, "metric": "aov", "value": float(y)} for u, y in zip(treatment, treatment_y)
    ]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": conversions}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metric_type"] == "continuous"
    cuped = data["cuped"]
    assert cuped["status"] == "available"
    assert cuped["theta"] is not None
    assert cuped["covariate_users_total"] == 12
    assert cuped["exposed_users_total"] == 12
    assert len(cuped["comparisons"]) == 1
    assert cuped["comparisons"][0]["status"] == "ok"
    assert cuped["comparisons"][0]["analysis"] is not None


# --- post-stratification (F3b) --------------------------------------------------------


def _stratum(name: str, *arms: dict) -> dict:
    return {"stratum": name, "variations": list(arms)}


def _stratified_aggregates(
    *strata: dict, num_strata: int | None = None, too_many: bool = False
) -> dict:
    if too_many:
        return {
            "experiment_id": "e",
            "metric_name": "aov",
            "strata": [],
            "num_strata": num_strata if num_strata is not None else 99,
            "too_many_strata": True,
        }
    return {
        "experiment_id": "e",
        "metric_name": "aov",
        "strata": list(strata),
        "num_strata": num_strata if num_strata is not None else len(strata),
    }


def test_stratified_unavailable_without_strata() -> None:
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(_arm(0, 4, 4, 100.0, 2600.0), _arm(1, 4, 4, 180.0, 8200.0)),
        None,
        None,
        None,
    )
    assert result["stratified"]["status"] == "unavailable"


def test_stratified_not_applicable_for_ratio_metric() -> None:
    result = build_live_stats(
        "e",
        _ratio_design(),
        _aggregates(_arm(0, 4, 0), _arm(1, 4, 0)),
        None,
        _ratio_aggregates(
            _cuped_arm(0, [1, 1, 1, 1], [1, 0, 1, 0]),
            _cuped_arm(1, [1, 1, 1, 1], [1, 1, 1, 0]),
        ),
        None,
    )
    # A ratio metric has no single per-user outcome the combine reads.
    assert result["stratified"]["status"] == "unavailable"


def test_stratified_single_stratum_matches_unadjusted_continuous() -> None:
    # One stratum holding all users -> the post-stratified effect equals the naive unadjusted
    # mean difference and the variance reduction is exactly zero (weight 1, pooled == stratified).
    control = _arm(0, 4, 4, 40.0, 408.0)  # values [10,12,8,10] -> mean 10
    treatment = _arm(1, 4, 4, 48.0, 584.0)  # values [12,14,10,12] -> mean 12
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(control, treatment),
        None,
        None,
        _stratified_aggregates(_stratum("all", control, treatment)),
    )
    unadjusted_effect = result["comparisons"][0]["analysis"]["observed_effect"]
    stratified = result["stratified"]
    assert stratified["status"] == "available"
    assert stratified["num_strata"] == 1
    assert stratified["stratified_users_total"] == 8
    comparison = stratified["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["effect"] == pytest.approx(unadjusted_effect)
    assert comparison["effect"] == pytest.approx(2.0)
    assert comparison["variance_reduction_pct"] == pytest.approx(0.0)
    assert comparison["num_strata"] == 1


def test_stratified_reduces_variance_when_strata_explain_outcome_continuous() -> None:
    # Two strata with very different outcome levels (large between-strata variation) but small
    # within-stratum variance and the same +2 effect in each. The naive pooled estimate carries
    # the between-strata variance; post-stratification removes it, so variance drops sharply while
    # the effect is preserved.
    strata = _stratified_aggregates(
        _stratum("low", _arm(0, 4, 4, 40.0, 408.0), _arm(1, 4, 4, 48.0, 584.0)),  # ~10 vs ~12
        _stratum("high", _arm(0, 4, 4, 400.0, 40008.0), _arm(1, 4, 4, 408.0, 41624.0)),  # ~100 vs ~102
    )
    pooled_control = _arm(0, 8, 8, 440.0, 40416.0)
    pooled_treatment = _arm(1, 8, 8, 456.0, 42208.0)
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(pooled_control, pooled_treatment),
        None,
        None,
        strata,
    )
    stratified = result["stratified"]
    assert stratified["status"] == "available"
    assert stratified["num_strata"] == 2
    comparison = stratified["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["effect"] == pytest.approx(2.0)  # effect preserved
    assert comparison["variance_reduction_pct"] > 90.0  # between-strata variance removed
    assert comparison["num_strata"] == 2


def test_stratified_binary_two_strata_happy() -> None:
    strata = _stratified_aggregates(
        _stratum("A", _arm(0, 100, 10), _arm(1, 100, 20)),  # 0.10 vs 0.20
        _stratum("B", _arm(0, 100, 40), _arm(1, 100, 50)),  # 0.40 vs 0.50
    )
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 200, 50), _arm(1, 200, 70)),
        None,
        None,
        strata,
    )
    stratified = result["stratified"]
    assert stratified["status"] == "available"
    comparison = stratified["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["effect"] == pytest.approx(0.10)  # both strata show +0.10
    assert comparison["num_strata"] == 2
    assert len(comparison["strata"]) == 2


def test_stratified_drops_stratum_with_a_sparse_arm() -> None:
    # Stratum "B" has a treatment arm with a single user (<2) -> dropped from the combine, shown
    # with a null effect; only stratum "A" contributes.
    strata = _stratified_aggregates(
        _stratum("A", _arm(0, 100, 10), _arm(1, 100, 20)),
        _stratum("B", _arm(0, 100, 40), _arm(1, 1, 1)),
    )
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 200, 50), _arm(1, 101, 21)),
        None,
        None,
        strata,
    )
    comparison = result["stratified"]["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["num_strata"] == 1  # only "A" contributed
    by_name = {row["stratum"]: row for row in comparison["strata"]}
    assert by_name["A"]["effect"] is not None
    assert by_name["B"]["effect"] is None  # sparse arm -> dropped from the combine


def test_stratified_insufficient_when_no_stratum_has_both_arms() -> None:
    # The only stratum has a control arm but no treatment arm -> no per-stratum effect -> the
    # comparison is insufficient_data even though the block itself is "available".
    strata = _stratified_aggregates(_stratum("solo", _arm(0, 50, 10)))
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 50, 10), _arm(1, 50, 15)),
        None,
        None,
        strata,
    )
    stratified = result["stratified"]
    assert stratified["status"] == "available"
    assert stratified["comparisons"][0]["status"] == "insufficient_data"


def test_stratified_too_many_strata_flag() -> None:
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 50, 10), _arm(1, 50, 15)),
        None,
        None,
        _stratified_aggregates(num_strata=99, too_many=True),
    )
    assert result["stratified"]["status"] == "too_many_strata"
    assert result["stratified"]["num_strata"] == 99


def test_stratified_aggregates_group_by_stratum_and_exclude_holdout_and_unstratified() -> None:
    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "u2", "variation_index": 0},
            {"user_id": "u3", "variation_index": 1},
            {"user_id": "u4", "variation_index": 1},
            {"user_id": "u5", "variation_index": 0},  # no stratum -> excluded
            {"user_id": "uH", "variation_index": -1},  # holdout -> excluded
        ],
    )
    repo.record_strata(
        exp,
        [
            {"user_id": "u1", "stratum": "ios"},
            {"user_id": "u2", "stratum": "android"},
            {"user_id": "u3", "stratum": "ios"},
            {"user_id": "u4", "stratum": "android"},
            {"user_id": "uH", "stratum": "ios"},  # holdout has a stratum but the arm is excluded
        ],
    )
    repo.record_conversions(
        exp,
        [
            {"user_id": "u1", "metric": "purchase", "value": 1.0},
            {"user_id": "u3", "metric": "purchase", "value": 1.0},
        ],
    )

    aggregates = repo.get_stratified_aggregates(exp, "purchase")
    assert aggregates is not None
    assert aggregates["num_strata"] == 2
    by_name = {stratum["stratum"]: stratum for stratum in aggregates["strata"]}
    assert sorted(by_name) == ["android", "ios"]
    ios = {arm["variation_index"]: arm for arm in by_name["ios"]["variations"]}
    assert ios[0]["exposed_users"] == 1 and ios[0]["converted_users"] == 1  # u1
    assert ios[1]["exposed_users"] == 1 and ios[1]["converted_users"] == 1  # u3
    android = {arm["variation_index"]: arm for arm in by_name["android"]["variations"]}
    assert android[0]["exposed_users"] == 1 and android[0]["converted_users"] == 0  # u2
    assert android[1]["exposed_users"] == 1 and android[1]["converted_users"] == 0  # u4
    total_users = sum(arm["exposed_users"] for s in aggregates["strata"] for arm in s["variations"])
    assert total_users == 4  # u5 (no stratum) and uH (holdout) never appear


def test_stratified_aggregates_resolves_identity_and_excludes_filtered_users() -> None:
    """Post-stratification (F3b) applies the same identity fold and manual/rate-spike exclusion as
    the primary rollup (P1.2 fix, audit finding D) — without this, a user the primary rollup has
    already dropped can still surface in the stratified count, letting ``stratified_users_total``
    exceed ``exposed_users_total`` on the page (the audit's "4000 of 3992")."""
    from app.backend.app.constants import BOT_CONVERSION_EVENT_THRESHOLD

    repo = _repo()
    exp = _project(repo)
    repo.record_exposures(
        exp,
        [
            {"user_id": "u1", "variation_index": 0},
            {"user_id": "excluded_user", "variation_index": 0},
            {"user_id": "bot", "variation_index": 1},
            # An earlier anonymous exposure for u2, resolved onto its canonical id below.
            {"user_id": "anon2", "variation_index": 1, "occurred_at": "2026-01-01T00:00:00+00:00"},
            {"user_id": "u2", "variation_index": 1, "occurred_at": "2026-01-01T01:00:00+00:00"},
        ],
    )
    repo.record_identities(exp, [{"anonymous_id": "anon2", "canonical_id": "u2"}])
    repo.record_strata(
        exp,
        [
            {"user_id": "u1", "stratum": "ios"},
            {"user_id": "excluded_user", "stratum": "ios"},
            {"user_id": "bot", "stratum": "android"},
            {"user_id": "u2", "stratum": "android"},
        ],
    )
    repo.record_exclusions(exp, [{"user_id": "excluded_user", "exclusion_reason": "internal_qa"}])
    repo.record_conversions(
        exp,
        [
            {"user_id": "bot", "metric": "purchase", "idempotency_key": f"k{i}"}
            for i in range(BOT_CONVERSION_EVENT_THRESHOLD + 1)
        ],
    )

    exposed = repo.get_experiment_analysis_aggregates(exp, "purchase")
    stratified = repo.get_stratified_aggregates(exp, "purchase")
    assert exposed is not None and stratified is not None
    exposed_total = sum(v["exposed_users"] for v in exposed["variations"])
    stratified_total = sum(arm["exposed_users"] for s in stratified["strata"] for arm in s["variations"])
    # u1 (control) + u2 (treatment, resolved from its anonymous exposure) survive in both rollups;
    # 'excluded_user' (manual deny-list) and 'bot' (rate-spike) are dropped from both alike.
    assert exposed_total == 2
    assert stratified_total == 2
    assert stratified_total <= exposed_total

    android = next(s for s in stratified["strata"] if s["stratum"] == "android")
    arm1 = next(arm for arm in android["variations"] if arm["variation_index"] == 1)
    assert arm1["exposed_users"] == 1  # u2 counted once, not twice via its anonymous exposure


def test_stratified_aggregates_none_for_unknown_experiment() -> None:
    repo = _repo()
    assert repo.get_stratified_aggregates("missing", "purchase") is None


def test_record_strata_dedups_per_user() -> None:
    repo = _repo()
    exp = _project(repo)
    first = repo.record_strata(
        exp, [{"user_id": "u1", "stratum": "ios"}, {"user_id": "u2", "stratum": "android"}]
    )
    assert first == {"received": 2, "recorded": 2, "deduplicated": 0}
    # First-write-wins: a later stratum for u1 is dropped and the original is kept.
    second = repo.record_strata(exp, [{"user_id": "u1", "stratum": "android"}])
    assert second == {"received": 1, "recorded": 0, "deduplicated": 1}


def test_strata_ingestion_endpoint_records_and_dedups() -> None:
    client = TestClient(create_app())
    project_id = _create_binary_project(client)
    first = client.post(
        f"/api/v1/experiments/{project_id}/strata",
        json={"strata": [{"user_id": "u1", "stratum": "ios"}, {"user_id": "u2", "stratum": "android"}]},
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"received": 2, "recorded": 2, "deduplicated": 0}
    again = client.post(
        f"/api/v1/experiments/{project_id}/strata",
        json={"strata": [{"user_id": "u1", "stratum": "android"}]},
    )
    assert again.status_code == 200
    assert again.json()["deduplicated"] == 1


# --- guardrail metrics on live data (F4) ----------------------------------------------
#
# Each declared guardrail metric is measured on the ordinary conversion stream (one conversion
# metric per guardrail name) and checked with a directed one-sided breach test. The block reports
# ok / warning / breached / unavailable; a breach is what the decision readout vetoes a ship on.


def _guardrail_metric(
    name: str,
    *,
    metric_type: str = "binary",
    baseline_rate: float | None = None,
    baseline_mean: float | None = None,
    std_dev: float | None = None,
    direction: str = "increase_is_bad",
    margin_pct: float | None = None,
) -> dict:
    return {
        "name": name,
        "metric_type": metric_type,
        "baseline_rate": baseline_rate,
        "baseline_mean": baseline_mean,
        "std_dev": std_dev,
        "direction": direction,
        "non_inferiority_margin_pct": margin_pct,
    }


def _with_guardrails(base: dict, *guardrails: dict) -> dict:
    base["metrics"]["guardrail_metrics"] = list(guardrails)
    return base


def test_guardrail_unavailable_when_none_declared() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    block = result["guardrail"]
    assert block["status"] == "unavailable"
    assert block["any_breached"] is False
    assert block["metrics"] == []
    assert "declared" in block["note"]  # the "none declared" note, not the "no data yet" note


def test_guardrail_unavailable_when_declared_but_no_data_ingested() -> None:
    # The guardrail is declared but no aggregates arrive (no guardrail outcomes ingested) -> each
    # metric is insufficient_data and the block stays unavailable, distinct from "none declared".
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0))
    result = build_live_stats(
        "e", design, _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)), guardrail_aggregates=None
    )
    block = result["guardrail"]
    assert block["status"] == "unavailable"
    assert block["any_breached"] is False
    assert len(block["metrics"]) == 1  # declared, just unmeasured
    assert block["metrics"][0]["status"] == "insufficient_data"
    assert "no guardrail outcomes" in block["note"]


def test_guardrail_ok_when_treatment_improves_the_metric() -> None:
    # The treatment lowers the error rate (8% -> 2%): harm is negative, never a breach.
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0))
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        guardrail_aggregates={"error_rate": _aggregates(_arm(0, 5000, 400), _arm(1, 5000, 100))},
    )
    block = result["guardrail"]
    assert block["status"] == "ok"
    assert block["any_breached"] is False
    comparison = block["metrics"][0]["comparisons"][0]
    assert comparison["status"] == "ok"
    assert comparison["is_breached"] is False
    assert comparison["harm"] == pytest.approx(-0.06, abs=1e-6)


def test_guardrail_breach_on_binary_increase_is_bad() -> None:
    # Error rate climbs 2% -> 8% at n=5000/arm: a large, significant degradation -> breach.
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0))
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        guardrail_aggregates={"error_rate": _aggregates(_arm(0, 5000, 100), _arm(1, 5000, 400))},
    )
    block = result["guardrail"]
    assert block["status"] == "breached"
    assert block["any_breached"] is True
    metric = block["metrics"][0]
    assert metric["name"] == "error_rate"
    assert metric["direction"] == "increase_is_bad"
    assert metric["status"] == "breached"
    comparison = metric["comparisons"][0]
    assert comparison["status"] == "breached"
    assert comparison["is_breached"] is True
    assert comparison["harm"] == pytest.approx(0.06, abs=1e-6)
    assert comparison["control"]["point_estimate"] == pytest.approx(0.02)
    assert comparison["treatment"]["point_estimate"] == pytest.approx(0.08)
    assert comparison["p_value"] < 0.05


def test_guardrail_warning_when_point_degrades_but_not_significant() -> None:
    # +1.2pp degradation at n=1000/arm: the point estimate worsens past the (zero) margin but the
    # one-sided lower bound does not clear it -> warning, not a breach. The operator is alerted.
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0))
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        guardrail_aggregates={"error_rate": _aggregates(_arm(0, 1000, 50), _arm(1, 1000, 62))},
    )
    block = result["guardrail"]
    assert block["status"] == "warning"
    assert block["any_breached"] is False
    comparison = block["metrics"][0]["comparisons"][0]
    assert comparison["status"] == "warning"
    assert comparison["is_breached"] is False
    assert comparison["harm"] > 0
    assert comparison["p_value"] >= 0.05


def test_guardrail_insufficient_when_an_arm_is_too_small() -> None:
    # Fewer than 2 exposed users in an arm: no point estimate, so the breach test cannot run.
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0))
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        guardrail_aggregates={"error_rate": _aggregates(_arm(0, 1, 0), _arm(1, 5000, 400))},
    )
    block = result["guardrail"]
    assert block["status"] == "unavailable"  # the only metric is unmeasurable
    metric = block["metrics"][0]
    assert metric["status"] == "insufficient_data"
    comparison = metric["comparisons"][0]
    assert comparison["status"] == "insufficient_data"
    assert comparison["is_breached"] is None


def test_guardrail_decrease_is_bad_continuous_breach() -> None:
    # Revenue per user (decrease_is_bad) drops 45 -> 40: a −5 effect is +5 of harm -> breach.
    design = _with_guardrails(
        _continuous_design(),
        _guardrail_metric(
            "revenue_per_user",
            metric_type="continuous",
            baseline_mean=45.0,
            std_dev=12.0,
            direction="decrease_is_bad",
        ),
    )
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 4, 4, 100.0, 3000.0), _arm(1, 4, 4, 180.0, 8600.0)),
        guardrail_aggregates={
            "revenue_per_user": _aggregates(
                _arm(0, 4, 0, value_sum=180.0, value_sq_sum=8102.0),  # mean 45
                _arm(1, 4, 0, value_sum=160.0, value_sq_sum=6402.0),  # mean 40
            )
        },
    )
    block = result["guardrail"]
    assert block["status"] == "breached"
    metric = block["metrics"][0]
    assert metric["metric_type"] == "continuous"
    assert metric["direction"] == "decrease_is_bad"
    comparison = metric["comparisons"][0]
    assert comparison["effect"] == pytest.approx(-5.0)  # treatment mean 40 − control mean 45
    assert comparison["harm"] == pytest.approx(5.0)  # decrease_is_bad flips the sign
    assert comparison["is_breached"] is True


def test_guardrail_margin_absorbs_degradation_within_tolerance() -> None:
    # The same +6pp degradation that breaches at margin 0 is tolerated by a 10pp margin (5% baseline
    # × 200%): harm sits below the margin -> ok. This isolates the non-inferiority margin's effect.
    design = _with_guardrails(
        _binary_design(), _guardrail_metric("error_rate", baseline_rate=5.0, margin_pct=200.0)
    )
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        guardrail_aggregates={"error_rate": _aggregates(_arm(0, 5000, 100), _arm(1, 5000, 400))},
    )
    block = result["guardrail"]
    comparison = block["metrics"][0]["comparisons"][0]
    assert comparison["margin"] == pytest.approx(0.10)  # 0.05 baseline × 200%
    assert comparison["status"] == "ok"
    assert comparison["is_breached"] is False
    assert block["status"] == "ok"


def test_guardrail_multi_treatment_reports_the_worst_status() -> None:
    # Three variants: one treatment only warns, the other breaches. The metric and the block both
    # report the worst comparison (breached > warning > ok).
    design = _with_guardrails(_binary_design(), _guardrail_metric("error_rate", baseline_rate=2.0))
    design["setup"]["variants_count"] = 3
    design["setup"]["traffic_split"] = [34, 33, 33]
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 520), _arm(2, 5000, 540)),
        guardrail_aggregates={
            "error_rate": _aggregates(
                _arm(0, 5000, 100),  # 2.0%
                _arm(1, 5000, 110),  # 2.2% -> warning
                _arm(2, 5000, 400),  # 8.0% -> breach
            )
        },
    )
    metric = result["guardrail"]["metrics"][0]
    assert len(metric["comparisons"]) == 2
    assert metric["comparisons"][0]["status"] == "warning"
    assert metric["comparisons"][1]["status"] == "breached"
    assert metric["status"] == "breached"  # worst across treatments
    assert result["guardrail"]["status"] == "breached"
    assert result["guardrail"]["any_breached"] is True


def _create_guardrail_project(client: TestClient, guardrail: dict) -> str:
    """A binary primary experiment that declares one guardrail metric, for the endpoint path."""
    payload = {
        "project": {
            "project_name": "Guardrail route exp",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "Testing the live guardrail read.",
        },
        "hypothesis": {
            "change_description": "faster checkout",
            "target_audience": "all users",
            "business_problem": "abandonment",
            "hypothesis_statement": "faster checkout lifts conversion",
            "what_to_validate": "conversion",
            "desired_result": "uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "all",
            "exclusion_criteria": "staff",
        },
        "metrics": {
            "primary_metric_name": "purchase",
            "metric_type": "binary",
            "baseline_value": 0.10,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
            "guardrail_metrics": [guardrail],
        },
        "constraints": {
            "seasonality_present": False,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "low",
            "technical_constraints": "none",
            "legal_or_ethics_constraints": "none",
            "known_risks": "none",
            "deadline_pressure": "low",
            "long_test_possible": True,
        },
        "additional_context": {"llm_context": ""},
    }
    created = client.post("/api/v1/projects", json=payload)
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_live_stats_route_collects_guardrail_aggregates_by_name() -> None:
    # End-to-end: a guardrail's outcomes ride the ordinary conversion stream under the guardrail's
    # name; the endpoint rolls them up per name and the live block reports the breach. This proves
    # routes/execution._compute_live_stats assembles guardrail_aggregates keyed by metric name.
    client = TestClient(create_app())
    project_id = _create_guardrail_project(
        client,
        {
            "name": "error_rate",
            "metric_type": "binary",
            "baseline_rate": 5.0,
            "direction": "increase_is_bad",
        },
    )

    control = [f"c{i}" for i in range(40)]
    treatment = [f"t{i}" for i in range(40)]
    exposures = [{"user_id": u, "variation_index": 0} for u in control]
    exposures += [{"user_id": u, "variation_index": 1} for u in treatment]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}
        ).status_code
        == 200
    )

    # Guardrail outcomes under the guardrail's own metric name: 2/40 control vs 20/40 treatment.
    guardrail_events = [
        {"user_id": u, "metric": "error_rate", "value": 1.0} for u in control[:2]
    ]
    guardrail_events += [
        {"user_id": u, "metric": "error_rate", "value": 1.0} for u in treatment[:20]
    ]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": guardrail_events}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert response.status_code == 200, response.text
    block = response.json()["guardrail"]
    assert block["status"] == "breached"
    assert block["any_breached"] is True
    metric = block["metrics"][0]
    assert metric["name"] == "error_rate"
    comparison = metric["comparisons"][0]
    assert comparison["is_breached"] is True
    assert comparison["control"]["point_estimate"] == pytest.approx(0.05)  # 2/40
    assert comparison["treatment"]["point_estimate"] == pytest.approx(0.5)  # 20/40


# --- holdout groups (F5) --------------------------------------------------------------


def _holdout_aggregates(
    exposed: int, converted: int, value_sum: float = 0.0, value_sq_sum: float = 0.0
) -> dict:
    """A held-back (variation_index = -1) rollup as repository.get_holdout_aggregates returns it."""
    return {
        "experiment_id": "e",
        "metric_name": "purchase",
        "holdout": {
            "exposed_users": exposed,
            "converted_users": converted,
            "value_sum": value_sum,
            "value_sq_sum": value_sq_sum,
        },
    }


def test_holdout_unavailable_when_no_holdout_ingested() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600))
    )
    block = result["holdout"]
    assert block["status"] == "unavailable"
    assert block["treated"] is None
    assert block["holdout"] is None
    assert "No holdout users" in block["note"]


def test_holdout_unavailable_for_ratio_metric() -> None:
    # A ratio metric has no single per-user outcome the pool reads -> holdout is not applicable.
    result = build_live_stats(
        "e",
        _ratio_design(),
        _aggregates(_arm(0, 100, 0), _arm(1, 100, 0)),
        holdout_aggregates=_holdout_aggregates(100, 10),
    )
    block = result["holdout"]
    assert block["status"] == "unavailable"
    assert "ratio metric" in block["note"]


def test_holdout_insufficient_when_holdout_too_small() -> None:
    # A single held-back user cannot form a variance, so the cumulative test cannot run yet. The
    # treated total still reflects the pooled treatment arms (control excluded).
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 5000, 500), _arm(1, 5000, 600)),
        holdout_aggregates=_holdout_aggregates(1, 0),
    )
    block = result["holdout"]
    assert block["status"] == "insufficient_data"
    assert block["holdout_users_total"] == 1
    assert block["treated_users_total"] == 5000  # arm 1 only; the control arm is not "treated"


def test_holdout_ok_binary_pools_treated_arms_excluding_control() -> None:
    # Two treatment arms fold into one treated pool (control arm 0 excluded); the pool is compared
    # against the held-back holdout group. Treated 700/6000 (=300+400 over 3000+3000); holdout 50/2000.
    design = _binary_design()
    design["setup"]["variants_count"] = 3
    design["setup"]["traffic_split"] = [34, 33, 33]
    result = build_live_stats(
        "e",
        design,
        _aggregates(_arm(0, 3000, 600), _arm(1, 3000, 300), _arm(2, 3000, 400)),
        holdout_aggregates=_holdout_aggregates(2000, 50),
    )
    block = result["holdout"]
    assert block["status"] == "ok"
    assert block["treated_users_total"] == 6000  # arms 1 + 2 pooled; control (arm 0) excluded
    assert block["holdout_users_total"] == 2000
    assert block["treated"]["label"] == "treated"
    assert block["treated"]["exposed_users"] == 6000
    assert block["treated"]["converted_users"] == 700  # 300 + 400 (control's 600 not pooled)
    assert block["treated"]["conversion_rate"] == pytest.approx(700 / 6000, abs=1e-6)
    assert block["holdout"]["label"] == "holdout"
    assert block["holdout"]["conversion_rate"] == pytest.approx(50 / 2000)
    # observed_effect is in percentage points for a binary metric (rate difference × 100).
    assert block["analysis"]["observed_effect"] == pytest.approx((700 / 6000 - 50 / 2000) * 100, abs=1e-3)
    assert block["analysis"]["is_significant"] is True  # large positive cumulative effect
    assert block["probability_treated_beats_holdout"] is not None
    assert block["always_valid"]["status"] == "ok"


def test_holdout_ok_continuous_cumulative_effect() -> None:
    # Continuous primary: pooled treated mean 48 vs holdout mean 45 -> +3 cumulative effect.
    treated = _arm(1, 4000, 0, value_sum=192000.0, value_sq_sum=9791856.0)  # mean 48, var 144
    control = _arm(0, 4000, 0, value_sum=180000.0, value_sq_sum=9215856.0)  # excluded from the pool
    result = build_live_stats(
        "e",
        _continuous_design(),
        _aggregates(control, treated),
        holdout_aggregates=_holdout_aggregates(2000, 0, value_sum=90000.0, value_sq_sum=4337856.0),
    )
    block = result["holdout"]
    assert block["status"] == "ok"
    assert block["treated"]["mean"] == pytest.approx(48.0, abs=1e-6)
    assert block["holdout"]["mean"] == pytest.approx(45.0, abs=1e-6)
    assert block["treated"]["std"] is not None  # continuous arms carry mean/std, not a rate
    assert block["analysis"]["observed_effect"] == pytest.approx(3.0, abs=1e-6)
    assert block["analysis"]["is_significant"] is True
    assert block["always_valid"]["status"] == "ok"


def test_live_stats_route_collects_holdout_aggregates() -> None:
    # End-to-end: held-back users are ingested via POST /holdout (variation_index = -1 exposures), the
    # treated arm via /exposures, and outcomes for both ride the ordinary /conversions stream under the
    # primary metric. The endpoint rolls up the holdout tail and the block reports the cumulative
    # treated-vs-holdout effect — proving routes/execution._compute_live_stats wires get_holdout_aggregates.
    client = TestClient(create_app())
    project_id = _create_binary_project(client)

    control = [f"c{i}" for i in range(100)]
    treatment = [f"t{i}" for i in range(100)]
    held_back = [f"h{i}" for i in range(100)]
    exposures = [{"user_id": u, "variation_index": 0} for u in control]
    exposures += [{"user_id": u, "variation_index": 1} for u in treatment]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/holdout",
            json={"holdout": [{"user_id": u} for u in held_back]},
        ).status_code
        == 200
    )

    # Primary outcomes: treated 30/100, holdout 8/100 (control 10/100 is not part of the holdout read).
    conversions = [{"user_id": u, "metric": "purchase"} for u in control[:10]]
    conversions += [{"user_id": u, "metric": "purchase"} for u in treatment[:30]]
    conversions += [{"user_id": u, "metric": "purchase"} for u in held_back[:8]]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": conversions}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert response.status_code == 200, response.text
    block = response.json()["holdout"]
    assert block["status"] == "ok"
    assert block["treated_users_total"] == 100  # treatment arm only; control excluded
    assert block["holdout_users_total"] == 100
    assert block["treated"]["conversion_rate"] == pytest.approx(0.30)
    assert block["holdout"]["conversion_rate"] == pytest.approx(0.08)
    # observed_effect is in percentage points for a binary metric (0.30 − 0.08 = 0.22 → 22.0).
    assert block["analysis"]["observed_effect"] == pytest.approx(22.0, abs=1e-3)
    assert block["analysis"]["is_significant"] is True
    # The holdout tail never inflates the primary arms: exposures_total counts only vi >= 0.
    assert response.json()["exposures_total"] == 200


def test_live_stats_event_timing_unavailable_without_summary() -> None:
    # No event-timing summary supplied -> the block is "unavailable" (never fabricated).
    result = build_live_stats("e", _binary_design(), _aggregates(_arm(0, 100, 10), _arm(1, 100, 12)))
    assert result["event_timing"]["status"] == "unavailable"
    assert result["event_timing"]["late"] is None


def test_live_stats_route_reports_event_timing() -> None:
    # End-to-end (P4.2): conversions ingested with client event times are classified relative to each
    # user's exposure and the /live-stats event_timing block reports the late / out-of-order counts,
    # proving routes/execution._compute_live_stats wires get_event_timing_summary.
    client = TestClient(create_app())
    project_id = _create_binary_project(client)

    exposures = [
        {"user_id": "u1", "variation_index": 0, "occurred_at": "2026-05-01T12:00:00+00:00"},
        {"user_id": "u2", "variation_index": 1, "occurred_at": "2026-05-01T12:00:00+00:00"},
        {"user_id": "u3", "variation_index": 0, "occurred_at": "2026-05-10T12:00:00+00:00"},
    ]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}
        ).status_code
        == 200
    )
    conversions = [
        {"user_id": "u1", "metric": "purchase", "occurred_at": "2026-05-02T12:00:00+00:00"},  # in-window
        {"user_id": "u2", "metric": "purchase", "occurred_at": "2026-05-20T12:00:00+00:00"},  # late (+19d)
        {"user_id": "u3", "metric": "purchase", "occurred_at": "2026-05-08T12:00:00+00:00"},  # out-of-order
    ]
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions", json={"conversions": conversions}
        ).status_code
        == 200
    )

    response = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert response.status_code == 200, response.text
    block = response.json()["event_timing"]
    assert block["status"] == "ok"
    assert block["horizon_days"] == 14.0
    assert block["in_window"] == 1
    assert block["late"] == 1
    assert block["out_of_order"] == 1
    assert block["total"] == 3


def test_live_stats_identity_resolution_inactive_without_summary() -> None:
    # No identity-resolution summary supplied -> the block is "inactive" (hidden by the frontend).
    result = build_live_stats("e", _binary_design(), _aggregates(_arm(0, 100, 10), _arm(1, 100, 12)))
    assert result["identity_resolution"]["status"] == "inactive"
    assert result["identity_resolution"]["linked_identities"] == 0
    assert result["identity_resolution"]["merged_users"] is None


def test_live_stats_identity_resolution_block_active() -> None:
    # A non-empty summary surfaces the active indicator with its counts.
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 100, 10), _arm(1, 100, 12)),
        identity_resolution_summary={
            "experiment_id": "e",
            "linked_identities": 3,
            "canonicalized_events": 5,
            "merged_users": 2,
        },
    )
    block = result["identity_resolution"]
    assert block["status"] == "active"
    assert block["linked_identities"] == 3
    assert block["canonicalized_events"] == 5
    assert block["merged_users"] == 2


def test_live_stats_route_reports_identity_resolution() -> None:
    # End-to-end (P4.3): a user exposed under an anonymous id who converts under their canonical id is
    # attributed to the exposed arm once the link is ingested, and the /live-stats identity_resolution
    # block reports the active resolution — proving routes/execution wires the resolution + summary.
    client = TestClient(create_app())
    project_id = _create_binary_project(client)

    # 'anon' is exposed to the treatment arm; the conversion arrives under the logged-in id 'user'.
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exposures",
            json={"exposures": [{"user_id": "anon", "variation_index": 1}]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/conversions",
            json={"conversions": [{"user_id": "user", "metric": "purchase"}]},
        ).status_code
        == 200
    )

    # Before the link: the conversion is orphaned and the block is inactive.
    before = client.get(f"/api/v1/experiments/{project_id}/live-stats").json()
    assert before["identity_resolution"]["status"] == "inactive"

    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/identities",
            json={"identities": [{"anonymous_id": "anon", "canonical_id": "user"}]},
        ).status_code
        == 200
    )

    after = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert after.status_code == 200, after.text
    body = after.json()
    block = body["identity_resolution"]
    assert block["status"] == "active"
    assert block["linked_identities"] == 1
    assert block["canonicalized_events"] == 1  # the anonymous exposure was re-attributed
    assert block["merged_users"] == 1
    # The conversion (ingested under the canonical id) is now attributed to the exposed arm — the
    # treatment comparison reports one converted user (attribution itself is covered in depth by the
    # repository tests; this proves routes/execution wires the resolution into the live read).
    treatment = next(c for c in body["comparisons"] if c["treatment_index"] == 1)
    assert treatment["treatment"]["converted_users"] == 1


def test_live_stats_exclusion_inactive_without_summary() -> None:
    # No exclusion summary supplied -> the block is "inactive" (hidden by the frontend).
    result = build_live_stats("e", _binary_design(), _aggregates(_arm(0, 100, 10), _arm(1, 100, 12)))
    assert result["exclusions"]["status"] == "inactive"
    assert result["exclusions"]["total_filtered"] == 0
    assert result["exclusions"]["manual_filtered"] is None


def test_live_stats_exclusion_block_active() -> None:
    # A non-empty summary surfaces the active indicator with its per-reason split.
    result = build_live_stats(
        "e",
        _binary_design(),
        _aggregates(_arm(0, 100, 10), _arm(1, 100, 12)),
        exclusion_summary={
            "experiment_id": "e",
            "total_filtered": 5,
            "manual_filtered": 2,
            "rate_spike_filtered": 3,
        },
    )
    block = result["exclusions"]
    assert block["status"] == "active"
    assert block["total_filtered"] == 5
    assert block["manual_filtered"] == 2
    assert block["rate_spike_filtered"] == 3


def test_live_stats_route_reports_exclusions() -> None:
    # End-to-end (P4.4): a manually excluded user is dropped from the rollup and the /live-stats
    # exclusions block reports the filter — proving routes/execution wires the exclusion + summary.
    client = TestClient(create_app())
    project_id = _create_binary_project(client)

    exposures = [
        {"user_id": "keep", "variation_index": 1},
        {"user_id": "drop", "variation_index": 1},
    ]
    assert (
        client.post(f"/api/v1/experiments/{project_id}/exposures", json={"exposures": exposures}).status_code
        == 200
    )
    # Before any exclusion the block is inactive.
    before = client.get(f"/api/v1/experiments/{project_id}/live-stats").json()
    assert before["exclusions"]["status"] == "inactive"

    assert (
        client.post(
            f"/api/v1/experiments/{project_id}/exclusions",
            json={"exclusions": [{"user_id": "drop", "exclusion_reason": "known_bot"}]},
        ).status_code
        == 200
    )

    after = client.get(f"/api/v1/experiments/{project_id}/live-stats")
    assert after.status_code == 200, after.text
    body = after.json()
    block = body["exclusions"]
    assert block["status"] == "active"
    assert block["total_filtered"] == 1
    assert block["manual_filtered"] == 1
    assert block["rate_spike_filtered"] == 0
    # The excluded user is gone from the treatment arm's exposed count.
    treatment = next(c for c in body["comparisons"] if c["treatment_index"] == 1)
    assert treatment["treatment"]["exposed_users"] == 1
