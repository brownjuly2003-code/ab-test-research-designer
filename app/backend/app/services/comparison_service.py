RISK_CATEGORIES = ("statistical", "product", "technical", "operational")


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


def _comparison_entry(project: dict, analysis_run: dict) -> dict:
    report = analysis_run["analysis"]["report"]
    calculations = analysis_run["analysis"]["calculations"]
    warning_codes = _warning_codes(analysis_run)
    primary_metrics = report.get("metrics_plan", {}).get("primary", [])

    return {
        "id": project["id"],
        "project_name": project["project_name"],
        "updated_at": project["updated_at"],
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
    }


def build_project_comparison(base_project: dict, base_analysis_run: dict, candidate_project: dict, candidate_analysis_run: dict) -> dict:
    base_entry = _comparison_entry(base_project, base_analysis_run)
    candidate_entry = _comparison_entry(candidate_project, candidate_analysis_run)

    base_warning_codes = set(base_entry["warning_codes"])
    candidate_warning_codes = set(candidate_entry["warning_codes"])
    sample_size_delta = candidate_entry["total_sample_size"] - base_entry["total_sample_size"]
    duration_delta = candidate_entry["estimated_duration_days"] - base_entry["estimated_duration_days"]

    sample_size_trend = "larger" if sample_size_delta > 0 else "smaller" if sample_size_delta < 0 else "the same"
    duration_trend = "longer" if duration_delta > 0 else "shorter" if duration_delta < 0 else "the same length"

    return {
        "base_project": base_entry,
        "candidate_project": candidate_entry,
        "deltas": {
            "sample_size_per_variant": candidate_entry["sample_size_per_variant"] - base_entry["sample_size_per_variant"],
            "total_sample_size": sample_size_delta,
            "estimated_duration_days": duration_delta,
            "warnings_count": candidate_entry["warnings_count"] - base_entry["warnings_count"],
        },
        "shared_warning_codes": sorted(base_warning_codes & candidate_warning_codes),
        "base_only_warning_codes": sorted(base_warning_codes - candidate_warning_codes),
        "candidate_only_warning_codes": sorted(candidate_warning_codes - base_warning_codes),
        "summary": (
            f"{candidate_entry['project_name']} needs {sample_size_trend} total sample size and "
            f"a {duration_trend} test window than {base_entry['project_name']}."
        ),
    }
