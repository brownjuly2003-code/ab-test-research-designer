from typing import Any


def project_status_blocks(project: dict, analysis_run: dict | None) -> list[dict[str, Any]]:
    fields = [
        {"type": "mrkdwn", "text": f"*Project*\n{project['project_name']}"},
        {"type": "mrkdwn", "text": f"*ID*\n`{project['id']}`"},
    ]
    if project.get("last_analysis_at"):
        fields.append({"type": "mrkdwn", "text": f"*Last analysis*\n{project['last_analysis_at']}"})
    if analysis_run is not None:
        summary = analysis_run.get("summary") or {}
        duration = summary.get("estimated_duration_days")
        sample = summary.get("total_sample_size")
        fields.append({"type": "mrkdwn", "text": f"*Sample size*\n{sample or 'n/a'}"})
        fields.append({"type": "mrkdwn", "text": f"*Duration*\n{duration or 'n/a'} days"})
    return [
        {"type": "section", "fields": fields},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve analysis"},
                    "style": "primary",
                    "action_id": "approve_analysis",
                    "value": project["id"],
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Request review"},
                    "action_id": "request_review",
                    "value": project["id"],
                },
            ],
        },
    ]
