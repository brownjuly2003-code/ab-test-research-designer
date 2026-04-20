from app.backend.app.schemas.report import ExperimentReport
from app.backend.app.stats.binary import calculate_detectable_mde_binary
from app.backend.app.stats.continuous import calculate_detectable_mde_continuous


def _variant_names(variants_count: int) -> list[str]:
    names = []
    for index in range(variants_count):
        names.append(chr(ord("A") + index))
    return names


def build_guardrail_section(guardrail_metrics: list[dict], primary_n: int) -> list[dict]:
    results = []

    for guardrail in guardrail_metrics:
        if guardrail["metric_type"] == "binary":
            detectable_mde = calculate_detectable_mde_binary(
                n=primary_n,
                baseline_rate=guardrail["baseline_rate"] / 100,
                alpha=0.05,
                power=0.8,
            )
            results.append(
                {
                    "name": guardrail["name"],
                    "metric_type": "binary",
                    "baseline": guardrail["baseline_rate"],
                    "detectable_mde_pp": round(detectable_mde * 100, 3),
                    "note": (
                        f"With N={primary_n:,} per variant, can detect >= "
                        f"{detectable_mde * 100:.2f} pp change at 80% power"
                    ),
                }
            )
            continue

        detectable_mde = calculate_detectable_mde_continuous(
            n=primary_n,
            std_dev=guardrail["std_dev"],
            alpha=0.05,
            power=0.8,
        )
        results.append(
            {
                "name": guardrail["name"],
                "metric_type": "continuous",
                "baseline": guardrail["baseline_mean"],
                "detectable_mde_absolute": round(detectable_mde, 4),
                "note": (
                    f"With N={primary_n:,} per variant, can detect >= "
                    f"{detectable_mde:.4f} change at 80% power"
                ),
            }
        )

    return results


def build_experiment_report(payload: dict, calculation_result: dict, llm_advice: dict | None = None) -> dict:
    project = payload["project"]
    hypothesis = payload["hypothesis"]
    setup = payload["setup"]
    metrics = payload["metrics"]
    constraints = payload["constraints"]
    warnings = calculation_result.get("warnings", [])

    variant_names = _variant_names(setup["variants_count"])
    variants = [
        {
            "name": name,
            "description": "current experience" if index == 0 else hypothesis["change_description"],
        }
        for index, name in enumerate(variant_names)
    ]

    warning_messages = [warning["message"] for warning in warnings]
    llm_improvements = (llm_advice or {}).get("design_improvements", [])
    guardrail_metrics = metrics.get("guardrail_metrics") or []
    guardrail_metric_names = [guardrail["name"] for guardrail in guardrail_metrics]
    guardrail_report = build_guardrail_section(
        guardrail_metric_names and guardrail_metrics or [],
        calculation_result["results"]["sample_size_per_variant"],
    )

    report = ExperimentReport(
        executive_summary=(
            f"{project['project_name']} tests whether {hypothesis['change_description'].lower()} "
            f"can improve {metrics['primary_metric_name']} for {hypothesis['target_audience']}. "
            f"The deterministic plan estimates {calculation_result['results']['estimated_duration_days']} days "
            f"with {calculation_result['results']['sample_size_per_variant']} users per variant."
        ),
        calculations={
            "sample_size_per_variant": calculation_result["results"]["sample_size_per_variant"],
            "total_sample_size": calculation_result["results"]["total_sample_size"],
            "estimated_duration_days": calculation_result["results"]["estimated_duration_days"],
            "assumptions": calculation_result["assumptions"],
        },
        experiment_design={
            "variants": variants,
            "randomization_unit": setup["randomization_unit"],
            "traffic_split": setup["traffic_split"],
            "target_audience": hypothesis["target_audience"],
            "inclusion_criteria": setup["inclusion_criteria"],
            "exclusion_criteria": setup["exclusion_criteria"],
            "recommended_duration_days": calculation_result["results"]["estimated_duration_days"],
            "stopping_conditions": [
                "planned duration reached",
                "critical instrumentation failure",
            ],
        },
        metrics_plan={
            "primary": [metrics["primary_metric_name"]],
            "secondary": metrics.get("secondary_metrics") or [],
            "guardrail": guardrail_metric_names,
            "diagnostic": [
                "assignment_rate",
                "exposure_balance",
                f"{metrics['primary_metric_name']}_by_segment",
            ],
        },
        guardrail_metrics=guardrail_report,
        risks={
            "statistical": warning_messages or ["No major deterministic warnings identified at this stage."],
            "product": [
                f"Expected result depends on the hypothesis that {hypothesis['desired_result']}.",
            ],
            "technical": [
                constraints["technical_constraints"] or "No explicit technical constraints provided.",
            ],
            "operational": [
                constraints["known_risks"] or "No explicit operational risks provided.",
            ],
        },
        recommendations={
            "before_launch": [
                "Validate tracking and assignment before exposing live traffic.",
                *llm_improvements,
            ] or ["Validate tracking and assignment before exposing live traffic."],
            "during_test": [
                "Monitor guardrail metrics and sample accumulation daily.",
                "Avoid stopping the test early on short-term volatility.",
            ],
            "after_test": [
                "Interpret lift together with guardrail and diagnostic metrics.",
                "Document segmentation effects before rollout decisions.",
            ],
        },
        open_questions=[
            f"How will the team validate {hypothesis['what_to_validate']} before launch?",
            f"Is the market context '{project['market']}' stable during the planned test window?",
        ],
    )
    return report.model_dump()
