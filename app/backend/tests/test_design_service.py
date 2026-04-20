from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report


def test_design_service_builds_report_without_llm() -> None:
    payload = {
        "project": {
            "project_name": "Checkout redesign",
            "domain": "e-commerce",
            "product_type": "web app",
            "platform": "web",
            "market": "US",
            "project_description": "We want to test a simplified checkout flow.",
        },
        "hypothesis": {
            "change_description": "Reduce checkout from 4 steps to 2",
            "target_audience": "new users on web",
            "business_problem": "checkout abandonment is high",
            "hypothesis_statement": "If we simplify checkout, purchase conversion will increase.",
            "what_to_validate": "impact on conversion",
            "desired_result": "statistically meaningful uplift",
        },
        "setup": {
            "experiment_type": "ab",
            "randomization_unit": "user",
            "traffic_split": [50, 50],
            "expected_daily_traffic": 12000,
            "audience_share_in_test": 0.6,
            "variants_count": 2,
            "inclusion_criteria": "new users only",
            "exclusion_criteria": "internal staff",
        },
        "metrics": {
            "primary_metric_name": "purchase_conversion",
            "metric_type": "binary",
            "baseline_value": 0.042,
            "expected_uplift_pct": 8,
            "mde_pct": 5,
            "alpha": 0.05,
            "power": 0.8,
            "std_dev": None,
            "secondary_metrics": ["add_to_cart_rate"],
            "guardrail_metrics": [
                {
                    "name": "Payment error rate",
                    "metric_type": "binary",
                    "baseline_rate": 2.4,
                },
                {
                    "name": "Refund value",
                    "metric_type": "continuous",
                    "baseline_mean": 18.0,
                    "std_dev": 6.5,
                },
            ],
        },
        "constraints": {
            "seasonality_present": True,
            "active_campaigns_present": False,
            "returning_users_present": True,
            "interference_risk": "medium",
            "technical_constraints": "legacy event logging",
            "legal_or_ethics_constraints": "none",
            "known_risks": "tracking quality",
            "deadline_pressure": "medium",
            "long_test_possible": True,
        },
    }

    calculation_result = calculate_experiment_metrics(
        {
            "metric_type": payload["metrics"]["metric_type"],
            "baseline_value": payload["metrics"]["baseline_value"],
            "mde_pct": payload["metrics"]["mde_pct"],
            "alpha": payload["metrics"]["alpha"],
            "power": payload["metrics"]["power"],
            "expected_daily_traffic": payload["setup"]["expected_daily_traffic"],
            "audience_share_in_test": payload["setup"]["audience_share_in_test"],
            "traffic_split": payload["setup"]["traffic_split"],
            "variants_count": payload["setup"]["variants_count"],
            "seasonality_present": payload["constraints"]["seasonality_present"],
            "active_campaigns_present": payload["constraints"]["active_campaigns_present"],
            "long_test_possible": payload["constraints"]["long_test_possible"],
        }
    )

    report = build_experiment_report(payload, calculation_result)

    assert "executive_summary" in report
    assert report["calculations"]["sample_size_per_variant"] > 0
    assert report["experiment_design"]["variants"][0]["name"] == "A"
    assert report["metrics_plan"]["primary"] == ["purchase_conversion"]
    assert report["metrics_plan"]["guardrail"] == ["Payment error rate", "Refund value"]
    assert len(report["guardrail_metrics"]) == 2
    assert "statistical" in report["risks"]
    assert len(report["recommendations"]["before_launch"]) >= 1
    assert len(report["open_questions"]) >= 1
