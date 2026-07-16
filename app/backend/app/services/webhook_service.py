"""Durable webhook delivery (audit F-09).

Deliveries are an outbox: ``log_audit_entry`` commits pending rows together with the
audit event, and a single worker thread claims due rows under a database lease,
attempts each once, and reschedules failures via ``next_attempt_at``. Retries
therefore survive process restarts, and replicas never race the same row.

Targets are refused when they resolve to a non-public address (SSRF guard) and
response bodies are read from the network up to a fixed cap. The resolve-then-check
leaves a DNS-rebinding window (a hostile resolver could answer differently on the
delivery connection); closing it needs a pinned-address transport, deliberately out
of scope here.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from app.backend.app.errors import ApiError

if TYPE_CHECKING:
    from app.backend.app.repository import ProjectRepository

logger = logging.getLogger(__name__)


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


class WebhookService:
    retry_schedule_seconds = (1, 5, 30, 300, 1800)
    max_attempts = 5
    response_body_cap_bytes = 65536
    lease_seconds = 60.0
    poll_interval_seconds = 1.0
    claim_batch_size = 10

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        environment: str,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.repository = repository
        self.environment = environment
        self.clock = clock or (lambda: datetime.now(UTC))
        self.resolver = resolver or _default_resolver
        self.client = client or httpx.Client(timeout=10.0, follow_redirects=False)
        self._owns_client = client is None
        self._closed = False
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    # -- worker lifecycle ---------------------------------------------------

    def start_worker(self) -> None:
        """Start the outbox worker; also drains rows left over from a previous run."""
        if self._worker is not None or self._closed:
            return
        self._worker = threading.Thread(target=self._worker_loop, name="webhook-outbox", daemon=True)
        self._worker.start()

    def notify_enqueued(self) -> None:
        """Called after an enqueue commits; wakes the worker without polling delay."""
        self._wake.set()

    def shutdown(self, *, wait: bool = True) -> None:
        self._closed = True
        self._stop.set()
        self._wake.set()
        if self._worker is not None and wait:
            self._worker.join(timeout=30.0)
        self._worker = None
        if self._owns_client:
            self.client.close()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                processed = self.run_due_deliveries()
            except Exception:
                logger.exception("webhooks: worker pass failed")
                processed = 0
            if processed and not self._stop.is_set():
                continue
            self._wake.wait(timeout=self.poll_interval_seconds)
            self._wake.clear()

    # -- delivery -----------------------------------------------------------

    def run_due_deliveries(self, *, limit: int | None = None) -> int:
        """Claim due outbox rows and attempt each once. Returns rows processed.

        The worker loop calls this repeatedly; tests call it directly with an
        injected clock, so retry schedules are asserted without real sleeps.
        """
        now = self.clock()
        claimed = self.repository.claim_due_webhook_deliveries(
            now=now.isoformat(),
            lease_expires_at=(now + timedelta(seconds=self.lease_seconds)).isoformat(),
            limit=limit if limit is not None else self.claim_batch_size,
        )
        for delivery in claimed:
            self._attempt_claimed_delivery(delivery)
        return len(claimed)

    def _attempt_claimed_delivery(self, delivery: dict[str, Any]) -> None:
        subscription = self.repository.get_webhook_subscription(
            str(delivery["subscription_id"]), include_secret=True
        )
        if subscription is None or not subscription.get("enabled", True):
            self._record_outcome(
                delivery,
                final=True,
                error_message="Webhook subscription missing or disabled",
            )
            return
        event = self.repository.get_audit_entry(int(delivery["event_id"]))
        if event is None:
            self._record_outcome(delivery, final=True, error_message="Audit event no longer exists")
            return
        self._attempt_once(subscription, event, delivery, final=False)

    def _attempt_once(
        self,
        subscription: dict[str, Any],
        audit_event: dict[str, Any],
        delivery: dict[str, Any],
        *,
        final: bool,
    ) -> None:
        """One HTTP attempt; records the outcome. ``final`` forbids rescheduling."""
        target_url = str(subscription["target_url"])
        blocked_reason = self._target_blocked_reason(target_url)
        if blocked_reason is not None:
            # A private target does not become public by waiting: fail, no retry.
            self._record_outcome(delivery, final=True, error_message=blocked_reason)
            return

        body = self._build_body(subscription, audit_event)
        headers = self._build_headers(subscription, body)
        try:
            status_code, response_body = self._post_with_cap(target_url, body, headers)
        except httpx.HTTPError as exc:
            self._record_outcome(delivery, final=final, error_message=str(exc))
            return

        if 200 <= status_code < 300:
            self._record_outcome(delivery, delivered=True, response_code=status_code, response_body=response_body)
            return
        self._record_outcome(
            delivery,
            # 4xx is a permanent answer from the receiver; only 5xx reschedules.
            final=final or status_code < 500,
            response_code=status_code,
            response_body=response_body,
            error_message=f"HTTP {status_code}",
        )

    def _post_with_cap(self, url: str, body: str, headers: dict[str, str]) -> tuple[int, str]:
        """POST and read at most ``response_body_cap_bytes`` off the wire.

        ``response.text`` would buffer an arbitrarily large hostile response in
        memory before the storage-side truncation ever ran; streaming caps the read
        itself.
        """
        request = self.client.build_request("POST", url, content=body, headers=headers)
        response = self.client.send(request, stream=True)
        raw = b""
        truncated = False
        try:
            for chunk in response.iter_bytes():
                raw += chunk
                if len(raw) > self.response_body_cap_bytes:
                    raw = raw[: self.response_body_cap_bytes]
                    truncated = True
                    break
        finally:
            response.close()
        text = raw.decode("utf-8", errors="replace")
        if truncated:
            text += f" …[truncated at {self.response_body_cap_bytes} bytes]"
        return int(response.status_code), text

    def _record_outcome(
        self,
        delivery: dict[str, Any],
        *,
        delivered: bool = False,
        final: bool = False,
        response_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
    ) -> None:
        attempt_number = int(delivery["attempt_count"]) + 1
        if delivered:
            status = "delivered"
            next_attempt_at = None
        elif final or attempt_number >= self.max_attempts:
            status = "failed"
            next_attempt_at = None
        else:
            status = "retrying"
            delay = self.retry_schedule_seconds[min(attempt_number - 1, len(self.retry_schedule_seconds) - 1)]
            next_attempt_at = (self.clock() + timedelta(seconds=delay)).isoformat()
        self.repository.update_webhook_delivery(
            str(delivery["id"]),
            subscription_id=str(delivery["subscription_id"]),
            status=status,
            response_code=response_code,
            response_body=response_body,
            error_message=error_message,
            next_attempt_at=next_attempt_at,
        )

    # -- SSRF guard -----------------------------------------------------------

    def _target_blocked_reason(self, url: str) -> str | None:
        """Non-None means the target must never be contacted (resolves non-public).

        AB_ENV=local is exempt: developers deliver to local receivers, and the
        create-time rule already restricts non-HTTPS targets to localhost there.
        DNS failures return None — the HTTP attempt fails and retries normally.
        """
        host = urlparse(url).hostname
        if not host:
            return "Webhook target URL has no host"
        if self.environment == "local":
            return None
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address]
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(item) for item in self.resolver(host)]
            except (OSError, ValueError):
                return None
        for address in addresses:
            if not address.is_global:
                return f"Webhook target resolves to a non-public address ({address}); delivery refused"
        return None

    # -- test event -----------------------------------------------------------

    def send_test_event(
        self,
        subscription_id: str,
        *,
        actor: str,
        request_id: str | None,
        ip_address: str | None,
    ) -> dict[str, Any]:
        subscription = self.repository.get_webhook_subscription(subscription_id, include_secret=True)
        if subscription is None:
            raise ApiError("Webhook subscription not found", error_code="webhook_not_found", status_code=404)

        audit_event = self.repository.log_audit_entry(
            action="webhook.test",
            key_id=subscription.get("api_key_id"),
            actor=actor,
            request_id=request_id,
            ip_address=ip_address,
            project_id=None,
            project_name=None,
            dispatch_webhooks=False,
        )
        # next_attempt_at stays NULL so the worker can never claim this row: the
        # test attempt is synchronous, single-shot, and owned by this call.
        delivery = self.repository.create_webhook_delivery(
            subscription_id=str(subscription["id"]),
            event_id=int(audit_event["id"]),
            next_attempt_at=None,
            enqueue=False,
        )
        self._attempt_once(subscription, audit_event, delivery, final=True)
        refreshed = self.repository.get_webhook_delivery(str(delivery["id"]))
        if refreshed is None:
            raise ApiError("Webhook delivery not found", error_code="webhook_delivery_not_found", status_code=404)
        return {
            "delivery_id": refreshed["id"],
            "status": refreshed["status"],
            "response_code": refreshed["response_code"],
        }

    # -- payload building -----------------------------------------------------

    def _build_headers(self, subscription: dict[str, Any], body: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AB-Test-Research-Designer-Webhooks/1.0",
        }
        if subscription["format"] == "generic" and subscription["secret"]:
            signature = hmac.new(
                str(subscription["secret"]).encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-AB-Signature"] = f"sha256={signature}"
        return headers

    def _build_body(self, subscription: dict[str, Any], audit_event: dict[str, Any]) -> str:
        if subscription["format"] == "slack":
            return json.dumps(self._build_slack_body(audit_event), separators=(",", ":"))
        return json.dumps(self._build_generic_body(audit_event), separators=(",", ":"))

    def _build_generic_body(self, audit_event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_type": audit_event["action"],
            "event_id": str(audit_event["id"]),
            "timestamp": audit_event["ts"],
            "actor": audit_event["actor"],
            "payload": {
                "project_id": audit_event.get("project_id"),
                "project_name": audit_event.get("project_name"),
                "key_id": audit_event.get("key_id"),
                "request_id": audit_event.get("request_id"),
                "ip_address": audit_event.get("ip_address"),
                "payload_diff": audit_event.get("payload_diff"),
            },
        }

    def _build_slack_body(self, audit_event: dict[str, Any]) -> dict[str, Any]:
        summary = self._build_slack_summary(audit_event)
        return {
            "text": summary,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": summary,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Event*\n{audit_event['action']}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Actor*\n{audit_event.get('actor') or 'unknown'}",
                        },
                    ],
                },
            ],
        }

    def _build_slack_summary(self, audit_event: dict[str, Any]) -> str:
        project_name = audit_event.get("project_name")
        key_id = audit_event.get("key_id")
        if project_name:
            return f"Audit event `{audit_event['action']}` for project *{project_name}*."
        if key_id:
            return f"Audit event `{audit_event['action']}` for key `{key_id}`."
        return f"Audit event `{audit_event['action']}` was recorded."
