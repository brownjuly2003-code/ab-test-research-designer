import json
from typing import Any

import httpx

from app.backend.app.errors import ApiError
from app.backend.app.slack.blocks import project_status_blocks


class SlackService:
    def __init__(
        self,
        repository,
        *,
        bot_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.repository = repository
        self.bot_token = bot_token
        self.client = client or httpx.Client(timeout=10.0, follow_redirects=False)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def save_installation(
        self,
        *,
        team_id: str,
        team_name: str | None,
        bot_token: str,
        user_token: str | None,
    ) -> dict:
        return self.repository.upsert_slack_installation(
            team_id=team_id,
            team_name=team_name,
            bot_token=bot_token,
            user_token=user_token,
        )

    def get_installation(self, team_id: str) -> dict | None:
        return self.repository.get_slack_installation(team_id)

    def is_installed(self) -> bool:
        return self.repository.get_latest_slack_installation() is not None

    def send_message(
        self,
        channel: str,
        *,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        resolved_token = token or self.bot_token
        if not resolved_token:
            raise ApiError("Slack bot token is not configured", error_code="slack_not_configured", status_code=503)
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        response = self.client.post(
            "https://slack.com/api/chat.postMessage",
            content=json.dumps(payload, separators=(",", ":")),
            headers={
                "Authorization": f"Bearer {resolved_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        data = response.json()
        if not data.get("ok"):
            raise ApiError(str(data.get("error") or "Slack API error"), error_code="slack_api_error", status_code=502)
        return data

    def build_projects_response(self) -> dict[str, Any]:
        projects = self.repository.list_projects(include_archived=False)
        if not projects:
            return {"response_type": "ephemeral", "text": "No active projects found."}
        lines = [
            f"*{project['project_name']}* `{project['id']}`"
            for project in projects[:10]
        ]
        return {"response_type": "ephemeral", "text": "\n".join(lines)}

    def build_status_response(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project is None:
            return {"response_type": "ephemeral", "text": f"Project `{project_id}` was not found."}
        history = self.repository.get_project_history(project_id, analysis_limit=1, export_limit=1)
        analysis_run = history["analysis_runs"][0] if history and history["analysis_runs"] else None
        return {
            "response_type": "ephemeral",
            "text": f"Status for {project['project_name']}",
            "blocks": project_status_blocks(project, analysis_run),
        }

    def handle_command(self, text: str) -> dict[str, Any]:
        parts = text.strip().split()
        command = parts[0].lower() if parts else "projects"
        if command == "projects":
            return self.build_projects_response()
        if command == "status" and len(parts) >= 2:
            return self.build_status_response(parts[1])
        if command == "run" and len(parts) >= 2:
            return {
                "response_type": "ephemeral",
                "text": f"Analysis run queued for `{parts[1]}`.",
            }
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/ab-test projects`, `/ab-test status <project_id>`, or `/ab-test run <project_id>`.",
        }
