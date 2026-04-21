from app.backend.app.schemas.report import ExperimentReport
from app.backend.app.i18n import translate
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
                    "note": translate(
                        "report.guardrails.binary_note",
                        {
                            "sample_size_per_variant": f"{primary_n:,}",
                            "detectable_mde": f"{detectable_mde * 100:.2f}",
                        },
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
                "note": translate(
                    "report.guardrails.continuous_note",
                    {
                        "sample_size_per_variant": f"{primary_n:,}",
                        "detectable_mde": f"{detectable_mde:.4f}",
                    },
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
            "description": (
                translate("report.variant_control_description")
                if index == 0
                else hypothesis["change_description"]
            ),
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
            translate(
                "report.executive_summary",
                {
                    "project_name": project["project_name"],
                    "change_description": hypothesis["change_description"].lower(),
                    "primary_metric_name": metrics["primary_metric_name"],
                    "target_audience": hypothesis["target_audience"],
                    "estimated_duration_days": calculation_result["results"]["estimated_duration_days"],
                    "sample_size_per_variant": calculation_result["results"]["sample_size_per_variant"],
                },
            )
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
                translate("report.stopping_conditions.planned_duration_reached"),
                translate("report.stopping_conditions.critical_instrumentation_failure"),
            ],
        },
        metrics_plan={
            "primary": [metrics["primary_metric_name"]],
            "secondary": metrics.get("secondary_metrics") or [],
            "guardrail": guardrail_metric_names,
            "diagnostic": [
                translate("report.diagnostic_assignment_rate"),
                translate("report.diagnostic_exposure_balance"),
                translate(
                    "report.diagnostic_segment_metric",
                    {"primary_metric_name": metrics["primary_metric_name"]},
                ),
            ],
        },
        guardrail_metrics=guardrail_report,
        risks={
            "statistical": warning_messages or [translate("report.risks.no_major_warnings")],
            "product": [
                translate("report.risks.product", {"desired_result": hypothesis["desired_result"]}),
            ],
            "technical": [
                constraints["technical_constraints"] or translate("report.risks.no_technical_constraints"),
            ],
            "operational": [
                constraints["known_risks"] or translate("report.risks.no_operational_risks"),
            ],
        },
        recommendations={
            "before_launch": [
                translate("report.recommendations.before_launch_default"),
                *llm_improvements,
            ] or [translate("report.recommendations.before_launch_default")],
            "during_test": [
                translate("report.recommendations.during_test_monitor"),
                translate("report.recommendations.during_test_avoid_early_stop"),
            ],
            "after_test": [
                translate("report.recommendations.after_test_interpret"),
                translate("report.recommendations.after_test_segment"),
            ],
        },
        open_questions=[
            translate("report.open_questions.validate", {"what_to_validate": hypothesis["what_to_validate"]}),
            translate("report.open_questions.market_stability", {"market": project["market"]}),
        ],
    )
    return report.model_dump()
