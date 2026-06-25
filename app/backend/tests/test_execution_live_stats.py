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
    assert aggregates == {"experiment_id": exp, "metric_name": "purchase", "variations": []}


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
    # Ratio sizing is a later sub-phase; calculate_experiment_metrics rejects metric_type "ratio".
    # The sequential block must degrade to insufficient_data, not crash the whole live read.
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
    assert result["sequential"]["status"] == "fixed_horizon"


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


def _create_binary_project(client: TestClient) -> str:
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
            "mde_pct": 5,
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
    project_id = _create_binary_project(client)

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
    with repo._backend._connect() as conn:  # type: ignore[attr-defined]
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
