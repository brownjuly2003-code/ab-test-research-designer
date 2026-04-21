from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from textwrap import fill

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days

PAGE_SIZE = (8.27, 11.69)


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "Not recorded"
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:.2f}"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    return str(value)


def _page_title(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.text(0.07, 0.965, title, fontsize=20, fontweight="bold", color="#0f172a")
    fig.text(0.07, 0.943, subtitle, fontsize=9, color="#64748b")
    fig.text(0.93, 0.943, "AB Test Research Designer", fontsize=9, color="#64748b", ha="right")


def _render_table(axis: plt.Axes, rows: list[list[str]], headers: list[str], *, font_size: int = 9) -> None:
    axis.axis("off")
    if not rows:
        axis.text(0.0, 0.5, "No data available.", fontsize=10, color="#64748b", va="center")
        return
    table = axis.table(cellText=rows, colLabels=headers, loc="center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(1, 1.4)
    for (row_index, _col_index), cell in table.get_celld().items():
        cell.set_edgecolor("#dbe4ea")
        if row_index == 0:
            cell.set_facecolor("#e2f5f2")
            cell.set_text_props(weight="bold", color="#0f172a")
        else:
            cell.set_facecolor("#ffffff")


def _warning_lines(calculations: dict) -> list[str]:
    warnings = calculations.get("warnings", [])
    lines: list[str] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code", "warning"))
        message = str(warning.get("message", ""))
        lines.append(f"{code}: {message}".strip(": "))
    return lines or ["No deterministic warnings recorded."]


def _recommendation_lines(analysis: dict) -> list[str]:
    lines: list[str] = []
    advice = analysis.get("advice", {})
    advice_payload = advice.get("advice") if isinstance(advice, dict) else None
    if isinstance(advice_payload, dict):
        for key in (
            "brief_assessment",
            "key_risks",
            "design_improvements",
            "metric_recommendations",
            "interpretation_pitfalls",
            "additional_checks",
        ):
            value = advice_payload.get(key)
            if isinstance(value, list):
                lines.extend(str(item) for item in value if str(item).strip())
            elif value:
                lines.append(str(value))
    report = analysis.get("report", {})
    recommendations = report.get("recommendations", {}) if isinstance(report, dict) else {}
    if isinstance(recommendations, dict):
        for key in ("before_launch", "during_test", "after_test"):
            value = recommendations.get(key, [])
            if isinstance(value, list):
                lines.extend(str(item) for item in value if str(item).strip())
    return lines or ["No recommendations recorded."]


def _revision_lines(revisions: list[dict]) -> list[str]:
    if not revisions:
        return ["No saved revisions recorded."]
    lines: list[str] = []
    for revision in revisions[:8]:
        source = str(revision.get("source", "revision")).replace("_", " ")
        created_at = _format_timestamp(str(revision.get("created_at", "")))
        project_name = revision.get("payload", {}).get("project", {}).get("project_name")
        lines.append(f"{created_at} | {source} | {project_name or '-'}")
    return lines


def _candidate_mde_values(current_mde: float) -> list[float]:
    candidates = [
        max(1.0, current_mde * 0.5),
        current_mde,
        current_mde * 1.5,
        current_mde * 2.0,
    ]
    rounded = sorted({round(value, 2) for value in candidates if value > 0})
    return rounded[:4]


def _build_sensitivity_rows(project_payload: dict, calculations: dict) -> list[dict[str, object]]:
    metrics = project_payload.get("metrics", {})
    setup = project_payload.get("setup", {})
    metric_type = str(metrics.get("metric_type", "binary"))
    alpha = float(calculations.get("calculation_summary", {}).get("alpha", 0.05))
    variants_count = int(setup.get("variants_count", len(setup.get("traffic_split", [50, 50])) or 2))
    traffic_split = [int(value) for value in setup.get("traffic_split", [50, 50])]
    expected_daily_traffic = int(setup.get("expected_daily_traffic", 1))
    audience_share = float(setup.get("audience_share_in_test", 1.0))
    current_mde = float(calculations.get("calculation_summary", {}).get("mde_pct", 5.0))
    rows: list[dict[str, object]] = []

    for mde in _candidate_mde_values(current_mde):
        row: dict[str, object] = {"effect_size": mde}
        for power in (0.8, 0.9):
            if metric_type == "continuous":
                calculation = calculate_continuous_sample_size(
                    baseline_mean=float(metrics.get("baseline_value", 1.0)),
                    std_dev=float(metrics.get("std_dev", 1.0)),
                    mde_pct=mde,
                    alpha=alpha,
                    power=power,
                    variants_count=variants_count,
                )
            else:
                calculation = calculate_binary_sample_size(
                    baseline_rate=float(metrics.get("baseline_value", 0.01)),
                    mde_pct=mde,
                    alpha=alpha,
                    power=power,
                    variants_count=variants_count,
                )
            duration = estimate_experiment_duration_days(
                sample_size_per_variant=int(calculation["sample_size_per_variant"]),
                expected_daily_traffic=expected_daily_traffic,
                audience_share_in_test=audience_share,
                traffic_split=traffic_split,
            )
            row[f"n_{int(power * 100)}"] = int(calculation["sample_size_per_variant"])
            row[f"days_{int(power * 100)}"] = int(duration["estimated_duration_days"])
        rows.append(row)

    return rows


def _build_power_curve_points(calculations: dict, metrics: dict) -> tuple[list[float], list[int]]:
    summary = calculations.get("calculation_summary", {})
    results = calculations.get("results", {})
    sample_size = int(results.get("sample_size_per_variant", 0) or 0)
    alpha = float(summary.get("alpha", 0.05))
    metric_type = str(summary.get("metric_type", "binary"))
    mde_pct = float(summary.get("mde_pct", 5.0))
    baseline_value = float(summary.get("baseline_value", 0.01))
    std_dev = metrics.get("std_dev")
    powers = [0.7, 0.8, 0.9, 0.95]

    if sample_size <= 0:
        return powers, [0, 0, 0, 0]

    points: list[int] = []
    for power in powers:
        if metric_type == "continuous":
            calculation = calculate_continuous_sample_size(
                baseline_mean=baseline_value,
                std_dev=float(std_dev or 1.0),
                mde_pct=mde_pct,
                alpha=alpha,
                power=power,
                variants_count=2,
            )
        else:
            calculation = calculate_binary_sample_size(
                baseline_rate=baseline_value,
                mde_pct=mde_pct,
                alpha=alpha,
                power=power,
                variants_count=2,
            )
        points.append(int(calculation["sample_size_per_variant"]))
    return powers, points


def generate_report_pdf(project: dict, analysis: dict, revisions: list[dict]) -> bytes:
    payload = project.get("payload", {})
    calculations = analysis.get("calculations", {})
    report = analysis.get("report", {})
    setup = payload.get("setup", {})
    metrics = payload.get("metrics", {})
    variants = report.get("experiment_design", {}).get("variants", [])
    traffic_split = report.get("experiment_design", {}).get("traffic_split", setup.get("traffic_split", []))
    expected_daily_traffic = setup.get("expected_daily_traffic", "-")
    sensitivity_rows = _build_sensitivity_rows(payload, calculations)
    powers, sample_sizes = _build_power_curve_points(calculations, metrics)
    buffer = BytesIO()

    with PdfPages(buffer) as pdf:
        summary_fig = plt.figure(figsize=PAGE_SIZE)
        _page_title(summary_fig, "Experiment Summary", f"Generated {_format_timestamp(project.get('updated_at'))}")
        summary_fig.text(0.07, 0.90, f"Project: {project.get('project_name', '-')}", fontsize=13, fontweight="bold")
        summary_fig.text(0.07, 0.875, fill(f"Hypothesis: {payload.get('hypothesis', {}).get('hypothesis_statement', '-')}", 95), fontsize=10)
        summary_fig.text(0.07, 0.84, f"Created: {_format_timestamp(project.get('created_at'))}", fontsize=10)
        summary_fig.text(0.07, 0.815, f"Metric type: {metrics.get('metric_type', '-')}", fontsize=10)
        summary_fig.text(0.07, 0.79, f"Primary metric: {metrics.get('primary_metric_name', '-')}", fontsize=10)
        summary_fig.text(0.07, 0.765, f"MDE: {_format_value(calculations.get('calculation_summary', {}).get('mde_pct'))}%", fontsize=10)
        summary_fig.text(0.07, 0.74, f"Test type: two-tailed (default)", fontsize=10)
        variant_axis = summary_fig.add_axes([0.07, 0.12, 0.86, 0.54])
        variant_rows = [
            [
                str(variant.get("name", f"Variant {index + 1}")),
                _format_value(traffic_split[index] if index < len(traffic_split) else "-"),
            ]
            for index, variant in enumerate(variants)
        ]
        _render_table(variant_axis, variant_rows, ["Variant", "Traffic split %"])
        pdf.savefig(summary_fig)
        plt.close(summary_fig)

        results_fig = plt.figure(figsize=PAGE_SIZE)
        _page_title(results_fig, "Sample Size Results", "Required sample, traffic, and guardrail detectability")
        sample_axis = results_fig.add_axes([0.07, 0.58, 0.86, 0.28])
        sample_rows = [
            [
                str(variant.get("name", f"Variant {index + 1}")),
                _format_value(calculations.get("results", {}).get("sample_size_per_variant")),
                _format_value(expected_daily_traffic),
                _format_value(calculations.get("results", {}).get("estimated_duration_days")),
            ]
            for index, variant in enumerate(variants)
        ]
        _render_table(sample_axis, sample_rows, ["Variant", "Required n", "Daily traffic", "Duration (days)"])
        results_fig.text(
            0.07,
            0.53,
            "Power settings: "
            f"alpha={_format_value(calculations.get('calculation_summary', {}).get('alpha'))}, "
            f"power={_format_value(calculations.get('calculation_summary', {}).get('power'))}, "
            f"MDE={_format_value(calculations.get('calculation_summary', {}).get('mde_pct'))}%",
            fontsize=10,
        )
        guardrail_axis = results_fig.add_axes([0.07, 0.12, 0.86, 0.33])
        guardrail_rows = [
            [
                str(item.get("name", "-")),
                _format_value(item.get("detectable_mde_pp") or item.get("detectable_mde_absolute")),
                "Tracked" if item.get("note") else "Pending",
            ]
            for item in report.get("guardrail_metrics", [])
        ]
        _render_table(guardrail_axis, guardrail_rows, ["Guardrail", "Detectable MDE", "Status"])
        pdf.savefig(results_fig)
        plt.close(results_fig)

        chart_fig = plt.figure(figsize=PAGE_SIZE)
        _page_title(chart_fig, "Power Curve", "Power curve plus a compact sensitivity table")
        chart_axis = chart_fig.add_axes([0.10, 0.55, 0.80, 0.28])
        chart_axis.plot(powers, sample_sizes, marker="o", linewidth=2.5, color="#0f766e")
        chart_axis.set_title("Power Curve", fontsize=12)
        chart_axis.set_xlabel("Power target")
        chart_axis.set_ylabel("Sample size / variant")
        chart_axis.grid(True, linestyle="--", linewidth=0.6, alpha=0.35)
        sensitivity_axis = chart_fig.add_axes([0.07, 0.12, 0.86, 0.30])
        sensitivity_table_rows = [
            [
                f"{row['effect_size']}%",
                _format_value(row.get("n_80")),
                _format_value(row.get("n_90")),
            ]
            for row in sensitivity_rows
        ]
        _render_table(
            sensitivity_axis,
            sensitivity_table_rows,
            ["Effect size", "Required n (80% power)", "Required n (90% power)"],
        )
        pdf.savefig(chart_fig)
        plt.close(chart_fig)

        warning_fig = plt.figure(figsize=PAGE_SIZE)
        _page_title(warning_fig, "Warnings & Recommendations", "Warnings, analyst guidance, and recent revision history")
        warning_axis = warning_fig.add_axes([0.07, 0.08, 0.40, 0.80])
        recommendation_axis = warning_fig.add_axes([0.53, 0.08, 0.40, 0.80])
        for axis in (warning_axis, recommendation_axis):
            axis.axis("off")
        warning_axis.text(0.0, 0.98, "Warnings", fontsize=12, fontweight="bold", va="top")
        for index, line in enumerate(_warning_lines(calculations)):
            warning_axis.text(0.0, 0.92 - (index * 0.06), fill(f"- {line}", 42), fontsize=9.5, va="top")
        warning_axis.text(0.0, 0.48, "Revision history", fontsize=12, fontweight="bold", va="top")
        for index, line in enumerate(_revision_lines(revisions)):
            warning_axis.text(0.0, 0.42 - (index * 0.05), fill(f"- {line}", 42), fontsize=9.0, va="top")
        recommendation_axis.text(0.0, 0.98, "Recommendations", fontsize=12, fontweight="bold", va="top")
        for index, line in enumerate(_recommendation_lines(analysis)):
            recommendation_axis.text(0.0, 0.92 - (index * 0.055), fill(f"- {line}", 42), fontsize=9.5, va="top")
        pdf.savefig(warning_fig)
        plt.close(warning_fig)

    return buffer.getvalue()
