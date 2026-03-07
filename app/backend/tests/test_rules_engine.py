from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.rules.engine import evaluate_warnings
from app.backend.app.services.calculations_service import calculate_experiment_metrics


def test_rules_engine_warns_for_missing_variance() -> None:
    warnings = evaluate_warnings(
        payload={"metric_type": "continuous", "std_dev": None},
        results={},
    )

    codes = {warning["code"] for warning in warnings}
    assert "MISSING_VARIANCE" in codes


def test_rules_engine_warns_for_long_duration_and_context_risks() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.03,
            "mde_pct": 2,
            "alpha": 0.05,
            "power": 0.8,
            "expected_daily_traffic": 300,
            "audience_share_in_test": 0.3,
            "traffic_split": [50, 50],
            "variants_count": 2,
            "seasonality_present": True,
            "active_campaigns_present": True,
            "long_test_possible": False,
        }
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert "LONG_DURATION" in codes
    assert "LOW_TRAFFIC" in codes
    assert "SEASONALITY_PRESENT" in codes
    assert "CAMPAIGN_CONTAMINATION" in codes
    assert "LONG_TEST_NOT_POSSIBLE" in codes


def test_rules_engine_warns_for_many_variants_with_low_traffic() -> None:
    result = calculate_experiment_metrics(
        {
            "metric_type": "binary",
            "baseline_value": 0.12,
            "mde_pct": 8,
            "alpha": 0.05,
            "power": 0.75,
            "expected_daily_traffic": 2000,
            "audience_share_in_test": 0.5,
            "traffic_split": [40, 30, 30],
            "variants_count": 3,
        }
    )

    codes = {warning["code"] for warning in result["warnings"]}
    assert "MANY_VARIANTS_LOW_TRAFFIC" in codes
    assert "UNDERPOWERED_DESIGN" in codes
