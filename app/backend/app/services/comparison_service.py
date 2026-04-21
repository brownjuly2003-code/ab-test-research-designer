from statistics import median

from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days

RISK_CATEGORIES = ("statistical", "product", "technical", "operational")
WARNING_SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}
DEFAULT_MDE_VALUES = [0.1, 0.5, 1, 2, 5]
DEFAULT_POWER_VALUES = [0.7, 0.8, 0.9, 0.95]


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized


def _warning_codes(analysis_run: dict) -> list[str]:
    warnings = analysis_run.get("analysis", {}).get("calculations", {}).get("warnings", [])
    codes: list[str] = []
    for warning in warnings:
        code = warning.get("code")
        if isinstance(code, str) and code not in codes:
            codes.append(code)
    return codes


def _risk_highlights(analysis_run: dict) -> list[str]:
    risks = analysis_run.get("analysis", {}).get("report", {}).get("risks", {})
    highlights: list[str] = []

    for category in RISK_CATEGORIES:
        items = risks.get(category, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                highlights.append(item.strip())
                if len(highlights) == 4:
                    return highlights

    return highlights


def _recommendation_highlights(analysis_run: dict) -> list[str]:
    recommendations = analysis_run.get("analysis", {}).get("report", {}).get("recommendations", {})
    highlights: list[str] = []

    for key in ("before_launch", "during_test", "after_test"):
        items = recommendations.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                highlights.append(item.strip())
                if len(highlights) == 4:
                    return highlights

    return highlights


def _warning_severity(analysis_run: dict) -> str:
    warnings = analysis_run.get("analysis", {}).get("calculations", {}).get("warnings", [])
    highest_severity = "none"
    highest_rank = 0

    for warning in warnings:
        severity = warning.get("severity")
        rank = WARNING_SEVERITY_ORDER.get(severity, 0)
        if rank > highest_rank:
            highest_severity = severity
            highest_rank = rank

    return highest_severity


def _build_sensitivity_scale(default_values: list[float], current_value: float, limit: int) -> list[float]:
    normalized_current = round(float(current_value), 4)
    available = sorted({round(float(value), 4) for value in [*default_values, normalized_current]})
    if len(available) <= limit:
        return available

    selected = {normalized_current}
    remaining = sorted(
        (value for value in available if value != normalized_current),
        key=lambda value: (abs(value - normalized_current), value),
    )
    for value in remaining:
        if len(selected) >= limit:
            break
        selected.add(value)
    return sorted(selected)


def _build_sensitivity(project: dict, analysis_run: dict) -> dict | None:
    calculations = analysis_run.get("analysis", {}).get("calculations", {})
    summary = calculations.get("calculation_summary", {})
    results = calculations.get("results", {})
    report = analysis_run.get("analysis", {}).get("report", {})
    experiment_design = report.get("experiment_design", {})
    traffic_split = experiment_design.get("traffic_split", [])
    variants = len(experiment_design.get("variants", [])) or len(traffic_split)
    metric_type = summary.get("metric_type")

    if variants < 2 or len(traffic_split) != variants:
        return None
    if metric_type not in {"binary", "continuous"}:
        return None

    current_mde = summary.get("mde_absolute") if metric_type == "continuous" else summary.get("mde_pct")
    current_power = summary.get("power")
    baseline_value = summary.get("baseline_value")
    alpha = summary.get("alpha")
    daily_traffic = results.get("effective_daily_traffic")
    if not all(isinstance(value, (int, float)) for value in (current_mde, current_power, baseline_value, alpha, daily_traffic)):
        return None

    mde_values = _build_sensitivity_scale(DEFAULT_MDE_VALUES, float(current_mde), 5)
    power_values = _build_sensitivity_scale(DEFAULT_POWER_VALUES, float(current_power), 4)
    cells: list[dict[str, float | int]] = []

    for mde in mde_values:
        for power in power_values:
            if metric_type == "continuous":
                std_dev = project.get("payload", {}).get("metrics", {}).get("std_dev")
                if not isinstance(std_dev, (int, float)) or std_dev <= 0:
                    return None
                calculation = calculate_continuous_sample_size(
                    baseline_mean=float(baseline_value),
                    std_dev=float(std_dev),
                    mde_pct=(float(mde) / float(baseline_value)) * 100,
                    alpha=float(alpha),
                    power=float(power),
                    variants_count=variants,
                )
            else:
                calculation = calculate_binary_sample_size(
                    baseline_rate=float(baseline_value),
                    mde_pct=float(mde),
                    alpha=float(alpha),
                    power=float(power),
                    variants_count=variants,
                )

            duration = estimate_experiment_duration_days(
                sample_size_per_variant=int(calculation["sample_size_per_variant"]),
                expected_daily_traffic=float(daily_traffic),
                audience_share_in_test=1,
                traffic_split=traffic_split,
            )
            cells.append(
                {
                    "mde": float(mde),
                    "power": float(power),
                    "sample_size_per_variant": int(calculation["sample_size_per_variant"]),
                    "duration_days": float(duration["estimated_duration_days"]),
                }
            )

    return {
        "cells": cells,
        "current_mde": float(current_mde),
        "current_power": float(current_power),
    }


def _saved_observed_results(project: dict) -> dict | None:
    additional_context = project.get("payload", {}).get("additional_context")
    if not isinstance(additional_context, dict):
        return None
    observed_results = additional_context.get("observed_results")
    if not isinstance(observed_results, dict):
        return None
    analysis = observed_results.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def _shared_items(entries: list[dict], field_name: str) -> list[str]:
    if not entries:
        return []
    shared = _unique_strings(entries[0].get(field_name, []))
    for entry in entries[1:]:
        entry_values = set(_unique_strings(entry.get(field_name, [])))
        shared = [item for item in shared if item in entry_values]
    return shared


def _unique_items_by_project(entries: list[dict], field_name: str) -> dict[str, list[str]]:
    frequencies: dict[str, int] = {}
    values_by_project: dict[str, list[str]] = {}
    for entry in entries:
        values = _unique_strings(entry.get(field_name, []))
        values_by_project[entry["id"]] = values
        for value in values:
            frequencies[value] = frequencies.get(value, 0) + 1
    return {
        project_id: [value for value in values if frequencies.get(value, 0) == 1]
        for project_id, values in values_by_project.items()
    }


def _aggregate_recommendations(entries: list[dict]) -> list[str]:
    frequencies: dict[str, int] = {}
    for entry in entries:
        for recommendation in _unique_strings(entry.get("recommendation_highlights", [])):
            frequencies[recommendation] = frequencies.get(recommendation, 0) + 1
    total_projects = len(entries)
    return [
        f"{recommendation} appears in {count}/{total_projects} projects."
        for recommendation, count in sorted(
            frequencies.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )[:5]
    ]


def _overlap_lists(base_items: list[str], candidate_items: list[str]) -> tuple[list[str], list[str], list[str]]:
    candidate_set = set(candidate_items)
    base_set = set(base_items)
    shared = [item for item in base_items if item in candidate_set]
    base_only = [item for item in base_items if item not in candidate_set]
    candidate_only = [item for item in candidate_items if item not in base_set]
    return shared, base_only, candidate_only


def _metric_alignment_note(base_entry: dict, candidate_entry: dict) -> str:
    same_metric_type = base_entry["metric_type"] == candidate_entry["metric_type"]
    same_primary_metric = base_entry["primary_metric"] == candidate_entry["primary_metric"]

    if same_metric_type and same_primary_metric:
        return "Both snapshots evaluate the same primary metric and metric family."
    if same_metric_type:
        return "Snapshots use the same metric family, but the primary metric labels differ."
    if same_primary_metric:
        return "Snapshots share the primary metric label, but use different metric families."
    return "Snapshots differ in both primary metric and metric family."


def _comparison_highlights(
    base_entry: dict,
    candidate_entry: dict,
    *,
    sample_size_delta: int,
    duration_delta: int,
    warnings_delta: int,
    candidate_only_warning_codes: list[str],
    base_only_assumptions: list[str],
    candidate_only_assumptions: list[str],
    metric_alignment_note: str,
) -> list[str]:
    highlights = [
        (
            f"{candidate_entry['project_name']} changes total sample size by {sample_size_delta:+d} "
            f"and estimated duration by {duration_delta:+d} days versus {base_entry['project_name']}."
        ),
        metric_alignment_note,
    ]

    if warnings_delta > 0:
        highlights.append(
            f"{candidate_entry['project_name']} introduces {warnings_delta} more warning(s) than the base snapshot."
        )
    elif warnings_delta < 0:
        highlights.append(
            f"{candidate_entry['project_name']} removes {abs(warnings_delta)} warning(s) relative to the base snapshot."
        )
    else:
        highlights.append("Both snapshots trigger the same number of warning rules.")

    if candidate_only_warning_codes:
        highlights.append(
            f"Candidate-only warning codes: {', '.join(candidate_only_warning_codes)}."
        )

    if base_only_assumptions or candidate_only_assumptions:
        highlights.append(
            f"Assumptions diverge across snapshots ({len(base_only_assumptions)} base-only, "
            f"{len(candidate_only_assumptions)} candidate-only)."
        )

    if candidate_entry["advice_available"] != base_entry["advice_available"]:
        available_for = candidate_entry["project_name"] if candidate_entry["advice_available"] else base_entry["project_name"]
        highlights.append(f"Optional AI advice is only available for {available_for}.")

    return highlights[:5]


def _comparison_entry(project: dict, analysis_run: dict) -> dict:
    report = analysis_run["analysis"]["report"]
    calculations = analysis_run["analysis"]["calculations"]
    warning_codes = _warning_codes(analysis_run)
    primary_metrics = report.get("metrics_plan", {}).get("primary", [])

    return {
        "id": project["id"],
        "project_name": project["project_name"],
        "updated_at": project["updated_at"],
        "analysis_created_at": analysis_run["created_at"],
        "last_analysis_at": project["last_analysis_at"],
        "analysis_run_id": analysis_run["id"],
        "metric_type": calculations["calculation_summary"]["metric_type"],
        "primary_metric": primary_metrics[0] if primary_metrics else project["payload"]["metrics"]["primary_metric_name"],
        "sample_size_per_variant": calculations["results"]["sample_size_per_variant"],
        "total_sample_size": calculations["results"]["total_sample_size"],
        "estimated_duration_days": calculations["results"]["estimated_duration_days"],
        "warnings_count": len(warning_codes),
        "warning_codes": warning_codes,
        "risk_highlights": _risk_highlights(analysis_run),
        "assumptions": report.get("calculations", {}).get("assumptions", []),
        "advice_available": bool(analysis_run["analysis"].get("advice", {}).get("available")),
        "executive_summary": report.get("executive_summary", ""),
        "warning_severity": _warning_severity(analysis_run),
        "recommendation_highlights": _recommendation_highlights(analysis_run),
        "sensitivity": _build_sensitivity(project, analysis_run),
        "observed_results": _saved_observed_results(project),
    }


def build_project_comparison(base_project: dict, base_analysis_run: dict, candidate_project: dict, candidate_analysis_run: dict) -> dict:
    base_entry = _comparison_entry(base_project, base_analysis_run)
    candidate_entry = _comparison_entry(candidate_project, candidate_analysis_run)

    base_warning_codes = set(base_entry["warning_codes"])
    candidate_warning_codes = set(candidate_entry["warning_codes"])
    base_assumptions = _unique_strings(base_entry["assumptions"])
    candidate_assumptions = _unique_strings(candidate_entry["assumptions"])
    base_risk_highlights = _unique_strings(base_entry["risk_highlights"])
    candidate_risk_highlights = _unique_strings(candidate_entry["risk_highlights"])
    sample_size_delta = candidate_entry["total_sample_size"] - base_entry["total_sample_size"]
    duration_delta = candidate_entry["estimated_duration_days"] - base_entry["estimated_duration_days"]
    warnings_delta = candidate_entry["warnings_count"] - base_entry["warnings_count"]

    sample_size_trend = "larger" if sample_size_delta > 0 else "smaller" if sample_size_delta < 0 else "the same"
    duration_trend = "longer" if duration_delta > 0 else "shorter" if duration_delta < 0 else "the same length"
    shared_assumptions, base_only_assumptions, candidate_only_assumptions = _overlap_lists(
        base_assumptions,
        candidate_assumptions,
    )
    shared_risk_highlights, base_only_risk_highlights, candidate_only_risk_highlights = _overlap_lists(
        base_risk_highlights,
        candidate_risk_highlights,
    )
    metric_alignment_note = _metric_alignment_note(base_entry, candidate_entry)
    candidate_only_warning_codes = sorted(candidate_warning_codes - base_warning_codes)

    return {
        "base_project": base_entry,
        "candidate_project": candidate_entry,
        "deltas": {
            "sample_size_per_variant": candidate_entry["sample_size_per_variant"] - base_entry["sample_size_per_variant"],
            "total_sample_size": sample_size_delta,
            "estimated_duration_days": duration_delta,
            "warnings_count": warnings_delta,
        },
        "shared_warning_codes": sorted(base_warning_codes & candidate_warning_codes),
        "base_only_warning_codes": sorted(base_warning_codes - candidate_warning_codes),
        "candidate_only_warning_codes": candidate_only_warning_codes,
        "shared_assumptions": shared_assumptions,
        "base_only_assumptions": base_only_assumptions,
        "candidate_only_assumptions": candidate_only_assumptions,
        "shared_risk_highlights": shared_risk_highlights,
        "base_only_risk_highlights": base_only_risk_highlights,
        "candidate_only_risk_highlights": candidate_only_risk_highlights,
        "metric_alignment_note": metric_alignment_note,
        "highlights": _comparison_highlights(
            base_entry,
            candidate_entry,
            sample_size_delta=sample_size_delta,
            duration_delta=duration_delta,
            warnings_delta=warnings_delta,
            candidate_only_warning_codes=candidate_only_warning_codes,
            base_only_assumptions=base_only_assumptions,
            candidate_only_assumptions=candidate_only_assumptions,
            metric_alignment_note=metric_alignment_note,
        ),
        "summary": (
            f"{candidate_entry['project_name']} needs {sample_size_trend} total sample size and "
            f"a {duration_trend} test window than {base_entry['project_name']}."
        ),
    }


def build_multi_project_comparison(projects_with_runs: list[tuple[dict, dict]]) -> dict:
    entries = [_comparison_entry(project, analysis_run) for project, analysis_run in projects_with_runs]
    shared_warnings = _shared_items(entries, "warning_codes")
    shared_assumptions = _shared_items(entries, "assumptions")
    shared_risks = _shared_items(entries, "risk_highlights")
    unique_warning_codes = _unique_items_by_project(entries, "warning_codes")
    unique_risks = _unique_items_by_project(entries, "risk_highlights")
    unique_assumptions = _unique_items_by_project(entries, "assumptions")
    metric_types_used = sorted({entry["metric_type"] for entry in entries})

    if len(metric_types_used) > 1:
        shared_warnings = [
            *shared_warnings,
            "Mixed metric types — direct effect comparison not meaningful",
        ]

    sample_sizes = [entry["total_sample_size"] for entry in entries]
    durations = [entry["estimated_duration_days"] for entry in entries]

    return {
        "projects": entries,
        "shared_warnings": shared_warnings,
        "shared_risks": shared_risks,
        "shared_assumptions": shared_assumptions,
        "unique_per_project": {
            entry["id"]: {
                "warnings": unique_warning_codes[entry["id"]],
                "risks": unique_risks[entry["id"]],
                "assumptions": unique_assumptions[entry["id"]],
            }
            for entry in entries
        },
        "sample_size_range": {
            "min": min(sample_sizes),
            "max": max(sample_sizes),
            "median": float(median(sample_sizes)),
        },
        "duration_range": {
            "min": min(durations),
            "max": max(durations),
            "median": float(median(durations)),
        },
        "metric_types_used": metric_types_used,
        "recommendation_highlights": _aggregate_recommendations(entries),
    }
