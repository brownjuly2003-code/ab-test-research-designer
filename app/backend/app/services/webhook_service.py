from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.backend.app.errors import ApiError


class WebhookService:
    retry_schedule_seconds = (1, 5, 30, 300, 1800)

    def __init__(
        self,
        repository,
        *,
        environment: str,
        client: httpx.Client | None = None,
        sleep=time.sleep,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.repository = repository
        self.environment = environment
        self.sleep = sleep
        self.client = client or httpx.Client(timeout=10.0, follow_redirects=False)
        self.executor = executor or ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhooks")
        self._owns_client = client is None
        self._owns_executor = executor is None
        self._closed = False

    def shutdown(self, *, wait: bool = True) -> None:
        self._closed = True
        if self._owns_client:
            self.client.close()
        if self._owns_executor:
            self.executor.shutdown(wait=wait)

    def dispatch_audit_event(self, audit_event: dict[str, Any]) -> None:
        if self._closed:
            return
        self.executor.submit(self.process_audit_event, dict(audit_event))

    def process_audit_event(self, audit_event: dict[str, Any]) -> None:
        subscriptions = self.repository.list_matching_webhook_subscriptions(
            event_type=str(audit_event["action"]),
            key_id=audit_event.get("key_id"),
        )
        for subscription in subscriptions:
            delivery = self.repository.create_webhook_delivery(
                subscription_id=subscription["id"],
                event_id=int(audit_event["id"]),
            )
            self._deliver_with_retry(
                subscription,
                audit_event,
                delivery_id=delivery["id"],
                max_attempts=len(self.retry_schedule_seconds),
            )

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
        delivery = self.repository.create_webhook_delivery(
            subscription_id=subscription["id"],
            event_id=int(audit_event["id"]),
        )
        self._deliver_with_retry(subscription, audit_event, delivery_id=delivery["id"], max_attempts=1)
        refreshed = self.repository.get_webhook_delivery(delivery["id"])
        if refreshed is None:
            raise ApiError("Webhook delivery not found", error_code="webhook_delivery_not_found", status_code=404)
        return {
            "delivery_id": refreshed["id"],
            "status": refreshed["status"],
            "response_code": refreshed["response_code"],
        }

    def _deliver_with_retry(
        self,
        subscription: dict[str, Any],
        audit_event: dict[str, Any],
        *,
        delivery_id: str,
        max_attempts: int,
    ) -> None:
        for attempt_index in range(max_attempts):
            body = self._build_body(subscription, audit_event)
            headers = self._build_headers(subscription, body)

            try:
                response = self.client.post(
                    str(subscription["target_url"]),
                    content=body,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                should_retry = attempt_index < max_attempts - 1
                self.repository.update_webhook_delivery(
                    delivery_id,
                    subscription_id=subscription["id"],
                    status="retrying" if should_retry else "failed",
                    error_message=str(exc),
                )
                if should_retry:
                    self.sleep(self.retry_schedule_seconds[attempt_index])
                    continue
                return

            status_code = int(response.status_code)
            response_body = response.text
            if 200 <= status_code < 300:
                self.repository.update_webhook_delivery(
                    delivery_id,
                    subscription_id=subscription["id"],
                    status="delivered",
                    response_code=status_code,
                    response_body=response_body,
                )
                return

            should_retry = status_code >= 500 and attempt_index < max_attempts - 1
            self.repository.update_webhook_delivery(
                delivery_id,
                subscription_id=subscription["id"],
                status="retrying" if should_retry else "failed",
                response_code=status_code,
                response_body=response_body,
                error_message=f"HTTP {status_code}",
            )
            if should_retry:
                self.sleep(self.retry_schedule_seconds[attempt_index])
                continue
            return

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
