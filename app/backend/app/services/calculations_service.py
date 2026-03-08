from app.backend.app.constants import MAX_SUPPORTED_VARIANTS
from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days
from app.backend.app.rules.engine import evaluate_warnings


def _validate_variant_configuration(variants_count: int, traffic_split: list[int]) -> None:
    if not 2 <= variants_count <= MAX_SUPPORTED_VARIANTS:
        raise ValueError(f"variants_count must be between 2 and {MAX_SUPPORTED_VARIANTS}")
    if len(traffic_split) != variants_count:
        raise ValueError("traffic_split length must match variants_count")


def _build_bonferroni_note(variants_count: int, adjusted_alpha: float | None) -> str | None:
    if variants_count <= 2 or adjusted_alpha is None:
        return None

    comparison_count = max(1, variants_count - 1)
    return (
        f"Bonferroni correction is applied across {comparison_count} treatment-vs-control comparisons "
        f"with adjusted alpha {adjusted_alpha:.6g}. Consider a less conservative correction if the design "
        "becomes impractically large."
    )


def calculate_experiment_metrics(payload: dict) -> dict:
    metric_type = payload["metric_type"]
    variants_count = int(payload.get("variants_count", len(payload["traffic_split"])))
    traffic_split = payload["traffic_split"]

    _validate_variant_configuration(variants_count, traffic_split)

    if metric_type == "binary":
        calculation_summary = calculate_binary_sample_size(
            baseline_rate=payload["baseline_value"],
            mde_pct=payload["mde_pct"],
            alpha=payload["alpha"],
            power=payload["power"],
            variants_count=variants_count,
        )
    elif metric_type == "continuous":
        if payload.get("std_dev") is None:
            raise ValueError("std_dev must be positive for continuous metrics")
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
        "bonferroni_note": _build_bonferroni_note(
            variants_count,
            calculation_summary.get("adjusted_alpha"),
        ),
    }
