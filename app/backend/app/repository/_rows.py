"""Row -> record mappers. Each takes a DB row and returns a plain dict."""

import sqlite3
from typing import Any

from app.backend.app.repository._utils import decode_json_value


def row_to_project(row: sqlite3.Row) -> dict[str, Any]:
    project = dict(row)
    payload_json = project.pop("payload_json")
    project["payload"] = decode_json_value(payload_json)
    project["has_analysis_snapshot"] = bool(project.get("last_analysis_run_id"))
    project["is_archived"] = bool(project.get("archived_at"))
    return project


def build_analysis_summary(analysis_payload: dict[str, Any]) -> dict[str, Any]:
    calculations = analysis_payload.get("calculations", {})
    calculation_summary = calculations.get("calculation_summary", {})
    results = calculations.get("results", {})
    warnings = calculations.get("warnings", [])
    advice = analysis_payload.get("advice", {})

    return {
        "metric_type": calculation_summary.get("metric_type"),
        "sample_size_per_variant": results.get("sample_size_per_variant"),
        "total_sample_size": results.get("total_sample_size"),
        "estimated_duration_days": results.get("estimated_duration_days"),
        "warnings_count": len(warnings) if isinstance(warnings, list) else 0,
        "advice_available": bool(advice.get("available")),
    }


def analysis_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    analysis = decode_json_value(row["analysis_json"])
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "summary": build_analysis_summary(analysis),
        "analysis": analysis,
    }


def analysis_row_to_workspace_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "analysis": decode_json_value(row["analysis_json"]),
    }


def export_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def revision_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "source": row["source"],
        "created_at": row["created_at"],
        "payload": decode_json_value(row["payload_json"]),
    }


def api_key_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "scope": row["scope"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "revoked_at": row["revoked_at"],
        "rate_limit_requests": row["rate_limit_requests"],
        "rate_limit_window_seconds": row["rate_limit_window_seconds"],
    }


def webhook_subscription_row_to_record(
    row: sqlite3.Row,
    *,
    include_secret: bool = False,
) -> dict[str, Any]:
    event_filter_raw = row["event_filter"]
    return {
        "id": row["id"],
        "name": row["name"],
        "target_url": row["target_url"],
        "secret": row["secret"] if include_secret else None,
        "format": row["format"],
        "event_filter": decode_json_value(event_filter_raw) if event_filter_raw else [],
        "scope": row["scope"],
        "api_key_id": row["api_key_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_delivered_at": row["last_delivered_at"],
        "last_error_at": row["last_error_at"],
        "enabled": bool(row["enabled"]),
    }


def webhook_delivery_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "subscription_id": row["subscription_id"],
        "event_id": row["event_id"],
        "status": row["status"],
        "attempt_count": int(row["attempt_count"]),
        "last_attempt_at": row["last_attempt_at"],
        "delivered_at": row["delivered_at"],
        "response_code": row["response_code"],
        "response_body": row["response_body"],
        "error_message": row["error_message"],
    }


def audit_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    payload_diff_json = row["payload_diff"]
    return {
        "id": row["id"],
        "ts": row["ts"],
        "action": row["action"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "key_id": row["key_id"],
        "actor": row["actor"],
        "request_id": row["request_id"],
        "payload_diff": decode_json_value(payload_diff_json) if payload_diff_json else None,
        "ip_address": row["ip_address"],
    }


def project_row_to_workspace_record(row: sqlite3.Row) -> dict[str, Any]:
    project = row_to_project(row)
    project.pop("revision_count", None)
    project.pop("last_revision_at", None)
    project.pop("has_analysis_snapshot", None)
    project.pop("is_archived", None)
    return project


def project_list_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    project = dict(row)
    project["has_analysis_snapshot"] = bool(project.get("has_analysis_snapshot"))
    project["is_archived"] = bool(project.get("is_archived"))
    return project


def template_row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "built_in": bool(row["built_in"]),
        "tags": decode_json_value(row["tags_json"]),
        "payload": decode_json_value(row["payload_json"]),
        "usage_count": int(row["usage_count"]),
    }
