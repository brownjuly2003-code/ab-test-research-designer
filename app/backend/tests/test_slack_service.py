from pathlib import Path
import sys
import uuid

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository
from app.backend.app.services.slack_service import SlackService


def _repository() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    return ProjectRepository(str(temp_dir / f"{uuid.uuid4()}.sqlite3"))


def test_slack_installation_crud() -> None:
    repository = _repository()
    service = SlackService(repository, bot_token="xoxb-token")

    saved = service.save_installation(
        team_id="T123",
        team_name="Example",
        bot_token="xoxb-installed",
        user_token=None,
    )

    assert saved["team_id"] == "T123"
    assert saved["team_name"] == "Example"
    assert saved["bot_token"] == "xoxb-installed"
    assert service.get_installation("T123")["bot_token"] == "xoxb-installed"
    assert service.is_installed() is True


def test_slack_send_message_posts_json() -> None:
    repository = _repository()
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True, "ts": "123.456"})

    service = SlackService(
        repository,
        bot_token="xoxb-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = service.send_message("C123", text="Hello", blocks=[{"type": "section"}])

    assert response["ok"] is True
    assert captured["url"] == "https://slack.com/api/chat.postMessage"
    assert captured["headers"]["authorization"] == "Bearer xoxb-token"
    assert '"channel":"C123"' in captured["body"]
    assert '"text":"Hello"' in captured["body"]
