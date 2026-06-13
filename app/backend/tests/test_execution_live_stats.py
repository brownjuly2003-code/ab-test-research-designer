"""Phase D — live experiment statistics over ingested exposures/conversions.

Covers the per-variation analysis-aggregate repository query (CTE join + dedup + holdout
exclusion), the live-stats service (SRM guardrail, frequentist + Bayesian comparison,
sequential boundary, CUPED unavailability), and the read endpoint.
"""

from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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


def test_live_stats_comparison_insufficient_data_when_arm_too_small() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 1, 0), _arm(1, 1, 1))
    )
    comparison = result["comparisons"][0]
    assert comparison["status"] == "insufficient_data"
    assert comparison["analysis"] is None


def test_live_stats_continuous_comparison_has_frequentist_but_no_bayesian() -> None:
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
    assert comparison["probability_treatment_beats_control"] is None  # binary-only in the MVP


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


def test_live_stats_cuped_is_unavailable() -> None:
    result = build_live_stats(
        "e", _binary_design(), _aggregates(_arm(0, 100, 10), _arm(1, 100, 12))
    )
    assert result["cuped"]["status"] == "unavailable"


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
    assert data["cuped"]["status"] == "unavailable"
    assert "MVP" in data["disclaimer"]
