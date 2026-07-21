"""Slack workspace installations (OAuth bot tokens)."""

from datetime import UTC, datetime
from typing import Any

from app.backend.app.errors import ApiError
from app.backend.app.repository._core import _BackendCore


class _SlackMixin(_BackendCore):
    def upsert_slack_installation(
        self,
        *,
        team_id: str,
        team_name: str | None,
        bot_token: str,
        user_token: str | None = None,
    ) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO slack_installations (
                    team_id,
                    team_name,
                    bot_token,
                    user_token,
                    installed_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = excluded.team_name,
                    bot_token = excluded.bot_token,
                    user_token = excluded.user_token,
                    updated_at = excluded.updated_at
                """,
                (team_id, team_name, bot_token, user_token, timestamp, timestamp),
            )
        installation = self.get_slack_installation(team_id)
        if installation is None:
            raise ApiError("Slack installation not found", error_code="slack_installation_not_found", status_code=500)
        return installation

    def get_slack_installation(self, team_id: str) -> dict[str, Any] | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT team_id, team_name, bot_token, user_token, installed_at, updated_at
                FROM slack_installations
                WHERE team_id = ?
                """,
                (team_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_latest_slack_installation(self) -> dict[str, Any] | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT team_id, team_name, bot_token, user_token, installed_at, updated_at
                FROM slack_installations
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row is not None else None
