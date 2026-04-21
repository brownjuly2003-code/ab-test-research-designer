from pathlib import Path
import sys
import uuid

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository
from app.backend.app.services.webhook_service import WebhookService


def _repository() -> ProjectRepository:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"{uuid.uuid4()}.sqlite3"
    return ProjectRepository(str(db_path))


def _create_subscription(
    repository: ProjectRepository,
    *,
    name: str = "Partner endpoint",
    target_url: str = "https://example.com/webhook",
    secret: str = "top-secret",
    format: str = "generic",
    event_filter: list[str] | None = None,
    scope: str = "global",
    api_key_id: str | None = None,
) -> dict:
    return repository.create_webhook_subscription(
        name=name,
        target_url=target_url,
        secret=secret,
        format=format,
        event_filter=event_filter or [],
        scope=scope,
        api_key_id=api_key_id,
    )


def _create_audit_event(repository: ProjectRepository, *, action: str = "api_key_created", key_id: str | None = None) -> dict:
    event = repository.log_audit_entry(
        action=action,
        key_id=key_id,
        actor="admin_token",
        request_id="req-1",
        ip_address="127.0.0.1",
        project_id="project-1",
        project_name="Checkout redesign",
    )
    if event is None:
        raise AssertionError("Expected audit event to be returned")
    return event


def test_process_audit_event_delivers_generic_webhook_and_signs_body() -> None:
    repository = _repository()
    subscription = _create_subscription(repository, event_filter=["api_key_created"])
    audit_event = _create_audit_event(repository)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    service = WebhookService(
        repository,
        environment="local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    service.process_audit_event(audit_event)
    deliveries = repository.list_webhook_deliveries(subscription["id"])

    assert captured["url"] == "https://example.com/webhook"
    assert captured["headers"]["x-ab-signature"].startswith("sha256=")
    assert '"event_type":"api_key_created"' in captured["body"]
    assert deliveries["deliveries"][0]["status"] == "delivered"
    assert deliveries["deliveries"][0]["attempt_count"] == 1
    assert deliveries["deliveries"][0]["response_code"] == 200


def test_process_audit_event_retries_with_backoff_on_server_errors() -> None:
    repository = _repository()
    subscription = _create_subscription(repository, event_filter=["api_key_created"])
    audit_event = _create_audit_event(repository)
    calls: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        if len(calls) < 3:
            return httpx.Response(502, text="upstream down")
        return httpx.Response(200, json={"ok": True})

    service = WebhookService(
        repository,
        environment="local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )

    service.process_audit_event(audit_event)
    deliveries = repository.list_webhook_deliveries(subscription["id"])

    assert calls == [1, 2, 3]
    assert sleeps == [1, 5]
    assert deliveries["deliveries"][0]["status"] == "delivered"
    assert deliveries["deliveries"][0]["attempt_count"] == 3
    assert deliveries["deliveries"][0]["response_code"] == 200


def test_process_audit_event_marks_delivery_failed_after_max_attempts() -> None:
    repository = _repository()
    subscription = _create_subscription(repository, event_filter=["api_key_created"])
    audit_event = _create_audit_event(repository)
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still failing")

    service = WebhookService(
        repository,
        environment="local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )

    service.process_audit_event(audit_event)
    deliveries = repository.list_webhook_deliveries(subscription["id"], status="failed")

    assert sleeps == [1, 5, 30, 300]
    assert deliveries["deliveries"][0]["status"] == "failed"
    assert deliveries["deliveries"][0]["attempt_count"] == 5
    assert deliveries["deliveries"][0]["response_code"] == 503
    assert "503" in deliveries["deliveries"][0]["error_message"]


def test_process_audit_event_builds_slack_payload_without_signature() -> None:
    repository = _repository()
    subscription = _create_subscription(
        repository,
        target_url="https://hooks.slack.com/services/test",
        secret="unused",
        format="slack",
        event_filter=["api_key_created"],
    )
    audit_event = _create_audit_event(repository)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    service = WebhookService(
        repository,
        environment="local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    service.process_audit_event(audit_event)
    deliveries = repository.list_webhook_deliveries(subscription["id"])

    assert "x-ab-signature" not in captured["headers"]
    assert '"text":"' in captured["body"]
    assert '"blocks":[' in captured["body"]
    assert deliveries["deliveries"][0]["status"] == "delivered"


def test_process_audit_event_only_targets_matching_api_key_scope_subscription() -> None:
    repository = _repository()
    api_key_id = repository.create_api_key(name="Scoped key", scope="write")["id"]
    matching = _create_subscription(
        repository,
        name="Matching key scope",
        event_filter=["api_key_created"],
        scope="api_key",
        api_key_id=api_key_id,
    )
    _create_subscription(
        repository,
        name="Other key scope",
        event_filter=["api_key_created"],
        scope="api_key",
        api_key_id=repository.create_api_key(name="Other key", scope="write")["id"],
    )
    audit_event = _create_audit_event(repository, key_id=api_key_id)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    service = WebhookService(
        repository,
        environment="local",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    service.process_audit_event(audit_event)

    assert calls == ["https://example.com/webhook"]
    assert repository.list_webhook_deliveries(matching["id"])["deliveries"][0]["status"] == "delivered"
