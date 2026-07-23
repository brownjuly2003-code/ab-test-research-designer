import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.http_utils import SlidingWindowRateLimiter


def test_allow_within_limit_grants_then_throttles() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)

    assert limiter.allow("client-a").allowed is True
    assert limiter.allow("client-a").allowed is True
    decision = limiter.allow("client-a")
    assert decision.allowed is False
    assert decision.retry_after_seconds >= 1


def test_independent_keys_get_independent_buckets() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)

    assert limiter.allow("a").allowed is True
    assert limiter.allow("b").allowed is True
    assert limiter.allow("a").allowed is False
    assert limiter.allow("b").allowed is False


def test_periodic_prune_drops_stale_buckets(monkeypatch) -> None:
    fake_time = [1000.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    monkeypatch.setattr("app.backend.app.http_utils.monotonic", fake_monotonic)

    limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
    limiter._PRUNE_INTERVAL = 5  # type: ignore[misc]

    # Create stale buckets for keys that never come back.
    for key in ("ip-1", "ip-2", "ip-3"):
        limiter.allow(key)

    assert len(limiter._events) == 3

    # Jump past the window so previous events are stale.
    fake_time[0] += 120.0

    # Trigger prune by hitting _PRUNE_INTERVAL.
    for _ in range(limiter._PRUNE_INTERVAL):
        limiter.allow("active-key")

    assert "ip-1" not in limiter._events
    assert "ip-2" not in limiter._events
    assert "ip-3" not in limiter._events
    assert "active-key" in limiter._events


def test_prune_keeps_active_buckets(monkeypatch) -> None:
    fake_time = [2000.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    monkeypatch.setattr("app.backend.app.http_utils.monotonic", fake_monotonic)

    limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
    limiter._PRUNE_INTERVAL = 3  # type: ignore[misc]

    limiter.allow("recent")
    fake_time[0] += 30.0  # still inside window
    limiter.allow("older")

    fake_time[0] += 35.0  # 'recent' now outside window, 'older' inside

    for _ in range(limiter._PRUNE_INTERVAL):
        limiter.allow("trigger")

    assert "recent" not in limiter._events
    assert "older" in limiter._events
    assert "trigger" in limiter._events


def test_prune_respects_per_key_window_override(monkeypatch) -> None:
    fake_time = [3000.0]

    def fake_monotonic() -> float:
        return fake_time[0]

    monkeypatch.setattr("app.backend.app.http_utils.monotonic", fake_monotonic)

    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
    limiter._PRUNE_INTERVAL = 3  # type: ignore[misc]

    # API key with a 600s window — its events must survive a global 60s prune.
    limiter.allow("api-key-long", window_seconds=600)
    fake_time[0] += 120.0  # past global window, still inside the 600s override

    for _ in range(limiter._PRUNE_INTERVAL):
        limiter.allow("trigger-prune")

    assert "api-key-long" in limiter._events, (
        "prune dropped a bucket whose per-call window was longer than the global default — "
        "subsequent allow() with the override would silently bypass its limit"
    )

    # Push past the override window and re-trigger prune — now it must drop.
    fake_time[0] += 600.0
    for _ in range(limiter._PRUNE_INTERVAL):
        limiter.allow("trigger-prune")

    assert "api-key-long" not in limiter._events


def test_overrides_apply_per_call() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

    # Override to a stricter cap for this key only.
    assert limiter.allow("strict", max_requests=1).allowed is True
    assert limiter.allow("strict", max_requests=1).allowed is False
    # Default cap still applies for other keys.
    for _ in range(5):
        assert limiter.allow("loose").allowed is True

def test_buffer_request_body_rejects_when_streamed_chunks_exceed_limit() -> None:
    """Chunked body without usable Content-Length is capped by actual bytes read."""
    import asyncio

    from starlette.requests import Request

    from app.backend.app.http_utils import (
        RequestBodyTooLargeError,
        buffer_request_body_with_limit,
    )

    chunks = [b"a" * 100, b"b" * 100, b"c" * 100]
    index = {"i": 0}

    async def receive() -> dict:
        i = index["i"]
        if i >= len(chunks):
            return {"type": "http.request", "body": b"", "more_body": False}
        body = chunks[i]
        index["i"] = i + 1
        return {"type": "http.request", "body": body, "more_body": i + 1 < len(chunks)}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/slack/commands",
        "raw_path": b"/slack/commands",
        "query_string": b"",
        "headers": [],  # no Content-Length
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope, receive)

    async def run() -> None:
        try:
            await buffer_request_body_with_limit(request, max_bytes=150)
            raise AssertionError("expected RequestBodyTooLargeError")
        except RequestBodyTooLargeError as exc:
            assert exc.limit_bytes == 150

    asyncio.run(run())


def test_get_request_body_limit_uses_slack_cap() -> None:
    from app.backend.app.config import get_settings
    from app.backend.app.http_utils import get_request_body_limit, is_slack_ingress_path

    get_settings.cache_clear()
    settings = get_settings()
    assert is_slack_ingress_path("/slack/commands") is True
    assert is_slack_ingress_path("/slack/install") is False
    assert get_request_body_limit("/slack/commands", "POST", settings) == settings.max_slack_body_bytes
    assert get_request_body_limit("/slack/events", "POST", settings) == settings.max_slack_body_bytes
    assert get_request_body_limit("/api/v1/projects", "POST", settings) == settings.max_request_body_bytes
    get_settings.cache_clear()
