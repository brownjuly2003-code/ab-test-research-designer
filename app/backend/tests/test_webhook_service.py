"""Webhook outbox behavior (audit F-09).

The clock and DNS resolver are injected, so retry schedules and SSRF verdicts are
asserted without real sleeps or network lookups. Every test drives the public
surface: enqueue via ``log_audit_entry``, delivery via ``run_due_deliveries``.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import uuid

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.repository import ProjectRepository
from app.backend.app.services.webhook_service import WebhookService

PUBLIC_IP = "93.184.216.34"


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 12, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


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


def _service(
    repository: ProjectRepository,
    handler,
    *,
    environment: str = "production",
    clock: FakeClock | None = None,
    resolver=None,
) -> WebhookService:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    service = WebhookService(
        repository,
        environment=environment,
        client=client,
        clock=clock,
        resolver=resolver or (lambda host: [PUBLIC_IP]),
    )
    repository.set_webhook_service(service)
    return service


def _log_event(repository: ProjectRepository, *, action: str = "api_key_created", key_id: str | None = None) -> dict:
    return repository.log_audit_entry(
        action=action,
        key_id=key_id,
        actor="admin_token",
        request_id="req-1",
        ip_address="127.0.0.1",
        project_id="project-1",
        project_name="Checkout redesign",
    )


def _deliveries(repository: ProjectRepository, subscription_id: str) -> list[dict]:
    return repository.list_webhook_deliveries(subscription_id, limit=50)["deliveries"]


def test_log_audit_entry_enqueues_pending_outbox_rows() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    _service(repository, lambda request: httpx.Response(200))

    _log_event(repository)

    deliveries = _deliveries(repository, subscription["id"])
    assert len(deliveries) == 1
    row = deliveries[0]
    assert row["status"] == "pending"
    assert row["attempt_count"] == 0
    assert row["next_attempt_at"] is not None
    assert row["lease_expires_at"] is None


def test_run_due_deliveries_delivers_and_signs_generic_webhook() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="ok")

    clock = FakeClock()
    service = _service(repository, handler, clock=clock)
    _log_event(repository)
    clock.advance(0.001)

    processed = service.run_due_deliveries()

    assert processed == 1
    assert len(captured) == 1
    assert captured[0].headers["X-AB-Signature"].startswith("sha256=")
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "delivered"
    assert delivery["response_code"] == 200
    assert delivery["lease_expires_at"] is None


def test_retries_follow_the_schedule_and_dead_letter_after_max_attempts() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(503), clock=clock)
    _log_event(repository)

    for attempt_index in range(WebhookService.max_attempts):
        clock.advance(1800.0)  # beyond the longest backoff step
        assert service.run_due_deliveries() == 1, f"attempt {attempt_index + 1} should be due"

    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "failed"
    assert delivery["attempt_count"] == WebhookService.max_attempts
    assert delivery["next_attempt_at"] is None

    clock.advance(1800.0)
    assert service.run_due_deliveries() == 0, "dead-lettered rows must never be claimed again"


def test_retry_is_not_due_before_its_backoff_elapses() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(500), clock=clock)
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "retrying"

    # First backoff step is 1s: nothing is due immediately after the failure.
    assert service.run_due_deliveries() == 0
    clock.advance(1.1)
    assert service.run_due_deliveries() == 1


def test_outbox_rows_survive_a_service_restart() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    clock = FakeClock()
    first = _service(repository, lambda request: httpx.Response(500), clock=clock)
    _log_event(repository)
    clock.advance(0.001)
    assert first.run_due_deliveries() == 1
    first.shutdown()

    # A new process: fresh service over the same database picks the retry up.
    second = _service(repository, lambda request: httpx.Response(200), clock=clock)
    clock.advance(2.0)
    assert second.run_due_deliveries() == 1
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "delivered"
    assert delivery["attempt_count"] == 2


def test_lease_blocks_a_second_claim_until_it_expires() -> None:
    repository = _repository()
    _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(200), clock=clock)
    _log_event(repository)
    clock.advance(0.001)

    now = clock().isoformat()
    lease = (clock() + timedelta(seconds=60)).isoformat()
    claimed = repository.claim_due_webhook_deliveries(now=now, lease_expires_at=lease, limit=10)
    assert len(claimed) == 1

    # Same instant: the lease is held, a second worker gets nothing.
    assert repository.claim_due_webhook_deliveries(now=now, lease_expires_at=lease, limit=10) == []

    # A worker that died mid-attempt: after the lease expires the row is claimable.
    clock.advance(61.0)
    later = clock().isoformat()
    reclaimed = repository.claim_due_webhook_deliveries(
        now=later,
        lease_expires_at=(clock() + timedelta(seconds=60)).isoformat(),
        limit=10,
    )
    assert len(reclaimed) == 1
    service.shutdown()


def test_private_target_is_refused_without_retry() -> None:
    repository = _repository()
    subscription = _create_subscription(repository, target_url="https://internal.corp/webhook")
    clock = FakeClock()
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    service = _service(repository, handler, clock=clock, resolver=lambda host: ["10.0.0.5"])
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    assert calls == [], "a non-public target must never be contacted"
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "failed"
    assert "non-public address" in (delivery["error_message"] or "")

    clock.advance(3600.0)
    assert service.run_due_deliveries() == 0, "SSRF refusal is permanent, not retried"


def test_local_environment_allows_loopback_targets() -> None:
    repository = _repository()
    subscription = _create_subscription(repository, target_url="http://127.0.0.1:9999/hook")
    clock = FakeClock()
    service = _service(
        repository,
        lambda request: httpx.Response(200),
        environment="local",
        clock=clock,
        resolver=lambda host: ["127.0.0.1"],
    )
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "delivered"


def test_demo_environment_keeps_ssrf_guard_active() -> None:
    # The public HF Space runs AB_ENV=demo: only the literal "local" environment
    # may skip the SSRF guard, so a loopback target must be refused here.
    repository = _repository()
    subscription = _create_subscription(repository, target_url="https://internal.example/hook")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    clock = FakeClock()
    service = _service(
        repository,
        handler,
        environment="demo",
        clock=clock,
        resolver=lambda host: ["127.0.0.1"],
    )
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    assert calls == [], "a loopback-resolving target must never be contacted outside AB_ENV=local"
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "failed"
    assert "non-public address" in (delivery["error_message"] or "")


def test_4xx_response_fails_without_retry() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(410), clock=clock)
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "failed"
    assert delivery["attempt_count"] == 1


def test_response_body_read_is_capped_at_the_network_layer() -> None:
    oversized = "x" * (WebhookService.response_body_cap_bytes + 4096)
    service = _service(_repository(), lambda request: httpx.Response(200, text=oversized))

    status_code, text = service._post_with_cap("https://example.com/webhook", "{}", {})

    assert status_code == 200
    assert text.endswith(f"…[truncated at {WebhookService.response_body_cap_bytes} bytes]")
    assert len(text) <= WebhookService.response_body_cap_bytes + 64


def test_slack_payload_is_built_without_signature() -> None:
    repository = _repository()
    subscription = _create_subscription(
        repository,
        target_url="https://hooks.slack.com/services/test",
        format="slack",
        secret="",
    )
    clock = FakeClock()
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    service = _service(repository, handler, clock=clock)
    _log_event(repository)
    clock.advance(0.001)

    assert service.run_due_deliveries() == 1
    assert "X-AB-Signature" not in captured[0].headers
    body = captured[0].content.decode("utf-8")
    assert '"blocks"' in body
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["status"] == "delivered"


def test_key_scoped_subscription_only_receives_its_key_events() -> None:
    repository = _repository()
    key = repository.create_api_key(name="ci", scope="write")
    scoped = _create_subscription(
        repository,
        name="Scoped",
        scope="api_key",
        api_key_id=key["id"],
    )
    other = _create_subscription(repository, name="Global")
    _service(repository, lambda request: httpx.Response(200))

    _log_event(repository, key_id="some-other-key")

    assert _deliveries(repository, scoped["id"]) == []
    assert len(_deliveries(repository, other["id"])) == 1


def test_send_test_event_is_synchronous_and_not_claimable_by_the_worker() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(200, text="ok"), clock=clock)

    result = service.send_test_event(
        subscription["id"],
        actor="admin_token",
        request_id="req-t",
        ip_address="127.0.0.1",
    )

    assert result["status"] == "delivered"
    assert result["response_code"] == 200
    (delivery,) = _deliveries(repository, subscription["id"])
    assert delivery["next_attempt_at"] is None

    clock.advance(3600.0)
    assert service.run_due_deliveries() == 0


def test_queue_stats_report_depth_and_oldest_due_age() -> None:
    repository = _repository()
    _create_subscription(repository)
    clock = FakeClock()
    service = _service(repository, lambda request: httpx.Response(500), clock=clock)
    _log_event(repository)
    clock.advance(0.001)
    assert service.run_due_deliveries() == 1  # -> retrying
    _log_event(repository)  # -> pending

    stats = repository.get_webhook_queue_stats()

    assert stats["pending"] == 1
    assert stats["retrying"] == 1
    assert stats["delivered"] == 0
    assert stats["failed"] == 0
    assert stats["oldest_due_age_seconds"] is not None


def test_worker_thread_starts_and_shuts_down_cleanly() -> None:
    repository = _repository()
    service = _service(repository, lambda request: httpx.Response(200))
    service.start_worker()
    worker = service._worker
    assert worker is not None and worker.is_alive()

    service.shutdown(wait=True)

    assert not worker.is_alive()
    assert service._worker is None


def test_legacy_rows_without_next_attempt_at_become_due_after_migration() -> None:
    repository = _repository()
    subscription = _create_subscription(repository)
    service = _service(repository, lambda request: httpx.Response(200))
    event = repository.log_audit_entry(
        action="api_key_created",
        actor="admin_token",
        request_id=None,
        ip_address=None,
        dispatch_webhooks=False,
    )
    # A row written by a pre-outbox build: pending, but with no due time.
    legacy = repository.create_webhook_delivery(
        subscription_id=subscription["id"],
        event_id=int(event["id"]),
        enqueue=False,
    )
    assert service.run_due_deliveries() == 0, "NULL next_attempt_at is invisible to the worker"

    from app.backend.app.repository._schema import migrate_db

    with repository._transaction() as connection:
        migrate_db(connection)

    assert service.run_due_deliveries() == 1
    refreshed = repository.get_webhook_delivery(legacy["id"])
    assert refreshed is not None and refreshed["status"] == "delivered"
