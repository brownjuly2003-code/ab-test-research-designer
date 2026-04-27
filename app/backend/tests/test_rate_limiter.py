from pathlib import Path
import sys

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


def test_overrides_apply_per_call() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

    # Override to a stricter cap for this key only.
    assert limiter.allow("strict", max_requests=1).allowed is True
    assert limiter.allow("strict", max_requests=1).allowed is False
    # Default cap still applies for other keys.
    for _ in range(5):
        assert limiter.allow("loose").allowed is True
