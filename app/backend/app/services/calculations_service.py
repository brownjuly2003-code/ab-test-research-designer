from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days
from app.backend.app.rules.engine import evaluate_warnings


def calculate_experiment_metrics(payload: dict) -> dict:
    metric_type = payload["metric_type"]
    variants_count = int(payload.get("variants_count", len(payload["traffic_split"])))
    traffic_split = payload["traffic_split"]

    if variants_count < 2:
        raise ValueError("variants_count must be at least 2")
    if len(traffic_split) != variants_count:
        raise ValueError("traffic_split length must match variants_count")

    if metric_type == "binary":
        calculation_summary = calculate_binary_sample_size(
            baseline_rate=payload["baseline_value"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
    elif metric_type == "continuous":
        calculation_summary = calculate_continuous_sample_size(
            baseline_mean=payload["baseline_value"],
            std_dev=payload["std_dev"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
    else:
        raise ValueError(f"Unsupported metric_type: {metric_type}")

    duration = estimate_experiment_duration_days(
        sample_size_per_variant=calculation_summary["sample_size_per_variant"],
        expected_daily_traffic=payload["expected_daily_traffic"],
        audience_share_in_test=payload["audience_share_in_test"],
        traffic_split=traffic_split,
    )

    return {
        "calculation_summary": {
            "metric_type": calculation_summary["metric_type"],
            "baseline_value": calculation_summary["baseline_value"],
            "mde_pct": calculation_summary["mde_pct"],
            "mde_absolute": calculation_summary["mde_absolute"],
            "alpha": calculation_summary["alpha"],
            "power": calculation_summary["power"],
        },
        "results": {
            "sample_size_per_variant": calculation_summary["sample_size_per_variant"],
            "total_sample_size": calculation_summary["total_sample_size"],
            "effective_daily_traffic": duration["effective_daily_traffic"],
            "estimated_duration_days": duration["estimated_duration_days"],
        },
        "assumptions": calculation_summary["assumptions"],
        "warnings": evaluate_warnings(
            payload=payload,
            results={
                "effective_daily_traffic": duration["effective_daily_traffic"],
                "estimated_duration_days": duration["estimated_duration_days"],
            },
        ),
    }
