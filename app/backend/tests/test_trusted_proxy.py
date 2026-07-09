"""Client-identity resolution behind (and without) a reverse proxy.

`get_client_identifier` keys both the request rate limiter and the auth-failure
throttle. Reading `X-Forwarded-For` unconditionally would let any caller mint a
fresh bucket per request by varying the header, so the header is only read once
`AB_TRUSTED_PROXY_HOPS` declares how many proxies append to it.
"""

from dataclasses import replace
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import Settings, get_settings
from app.backend.app.http_utils import get_client_identifier
from app.backend.app.main import create_app

WRITE_TOKEN = "super-secret-token"


def _settings(**overrides) -> Settings:
    get_settings.cache_clear()
    base = get_settings()
    get_settings.cache_clear()
    return replace(base, **overrides)


def _request(*, peer: str | None, forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/calculate",
        "headers": headers,
        "client": (peer, 51234) if peer is not None else None,
    }
    return Request(scope)


def test_forwarded_for_is_ignored_without_declared_hops() -> None:
    settings = _settings(trusted_proxy_hops=0)

    identifier = get_client_identifier(
        _request(peer="203.0.113.9", forwarded_for="198.51.100.7"),
        settings,
    )

    assert identifier == "203.0.113.9", "a forged X-Forwarded-For must not become the rate-limit key"


def test_single_trusted_hop_reads_the_rightmost_entry() -> None:
    settings = _settings(trusted_proxy_hops=1)

    # The proxy appends the address it saw; everything to its left came from the client.
    identifier = get_client_identifier(
        _request(peer="10.0.0.1", forwarded_for="9.9.9.9, 198.51.100.7"),
        settings,
    )

    assert identifier == "198.51.100.7", "the spoofed leading hop must be ignored"


def test_two_trusted_hops_step_past_both_proxies() -> None:
    settings = _settings(trusted_proxy_hops=2)

    identifier = get_client_identifier(
        _request(peer="10.0.0.1", forwarded_for="9.9.9.9, 198.51.100.7, 10.0.0.2"),
        settings,
    )

    assert identifier == "198.51.100.7"


def test_short_chain_falls_back_to_the_direct_peer() -> None:
    settings = _settings(trusted_proxy_hops=2)

    # Only one hop present where two were declared: no entry is provably proxy-written.
    identifier = get_client_identifier(
        _request(peer="10.0.0.1", forwarded_for="198.51.100.7"),
        settings,
    )

    assert identifier == "10.0.0.1"


def test_padding_the_chain_cannot_promote_a_client_entry() -> None:
    """A caller that prepends entries still cannot reach the trusted position.

    This is why the hop count is counted from the right: no amount of client-supplied
    padding shifts the N-th-from-last entry, which only a proxy can have written.
    """
    settings = _settings(trusted_proxy_hops=1)

    identifier = get_client_identifier(
        _request(peer="10.0.0.1", forwarded_for="1.1.1.1, 2.2.2.2, 3.3.3.3, 198.51.100.7"),
        settings,
    )

    assert identifier == "198.51.100.7"


def test_non_ip_hop_falls_back_to_the_direct_peer() -> None:
    """A proxy writes an address; anything else means the chain is not what was declared."""
    settings = _settings(trusted_proxy_hops=1)

    assert get_client_identifier(_request(peer="10.0.0.1", forwarded_for="unknown"), settings) == "10.0.0.1"
    assert get_client_identifier(_request(peer="10.0.0.1", forwarded_for="_hidden"), settings) == "10.0.0.1"
    assert get_client_identifier(_request(peer="10.0.0.1", forwarded_for="a, b"), settings) == "10.0.0.1"


def test_ipv6_hop_is_accepted() -> None:
    settings = _settings(trusted_proxy_hops=1)

    identifier = get_client_identifier(
        _request(peer="10.0.0.1", forwarded_for="2001:db8::1"),
        settings,
    )

    assert identifier == "2001:db8::1"


def test_empty_forwarded_header_falls_back_to_the_direct_peer() -> None:
    settings = _settings(trusted_proxy_hops=1)

    assert get_client_identifier(_request(peer="10.0.0.1", forwarded_for="  ,  "), settings) == "10.0.0.1"
    assert get_client_identifier(_request(peer="10.0.0.1"), settings) == "10.0.0.1"


def test_missing_peer_yields_unknown() -> None:
    settings = _settings(trusted_proxy_hops=0)

    assert get_client_identifier(_request(peer=None), settings) == "unknown"


def test_allowlist_rejects_forwarded_for_from_an_untrusted_peer() -> None:
    settings = _settings(trusted_proxy_hops=1, trusted_proxies=("10.0.0.0/8",))

    identifier = get_client_identifier(
        _request(peer="203.0.113.9", forwarded_for="198.51.100.7"),
        settings,
    )

    assert identifier == "203.0.113.9", "only the configured proxies may speak for a client address"


def test_allowlist_honours_forwarded_for_from_a_trusted_peer() -> None:
    settings = _settings(trusted_proxy_hops=1, trusted_proxies=("10.0.0.0/8", "192.0.2.1"))

    assert get_client_identifier(_request(peer="10.4.5.6", forwarded_for="198.51.100.7"), settings) == "198.51.100.7"
    assert get_client_identifier(_request(peer="192.0.2.1", forwarded_for="198.51.100.7"), settings) == "198.51.100.7"


def test_allowlist_ignores_a_non_ip_peer() -> None:
    settings = _settings(trusted_proxy_hops=1, trusted_proxies=("10.0.0.0/8",))

    # A unix-socket / test peer has no address to match against the allowlist.
    assert get_client_identifier(_request(peer="testclient", forwarded_for="198.51.100.7"), settings) == "testclient"


def _auth_failure_statuses(monkeypatch, *, trusted_proxy_hops: str) -> list[int]:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_API_TOKEN", WRITE_TOKEN)
    monkeypatch.setenv("AB_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AB_AUTH_FAILURE_LIMIT", "3")
    monkeypatch.setenv("AB_AUTH_FAILURE_WINDOW_SECONDS", "60")
    monkeypatch.setenv("AB_TRUSTED_PROXY_HOPS", trusted_proxy_hops)
    get_settings.cache_clear()

    statuses = []
    with TestClient(create_app()) as client:
        for attempt in range(6):
            response = client.get(
                "/api/v1/projects",
                headers={
                    "Authorization": "Bearer wrong-token",
                    "X-Forwarded-For": f"198.51.100.{attempt}",
                },
            )
            statuses.append(response.status_code)

    get_settings.cache_clear()
    return statuses


def test_forged_forwarded_for_cannot_reset_the_auth_failure_throttle(monkeypatch) -> None:
    """Regression: rotating X-Forwarded-For used to mint a fresh throttle bucket per request."""
    statuses = _auth_failure_statuses(monkeypatch, trusted_proxy_hops="0")

    assert 429 in statuses, f"auth-failure throttle never engaged: {statuses}"
    assert statuses[-1] == 429


def test_behind_a_trusted_proxy_each_real_client_gets_its_own_throttle_bucket(monkeypatch) -> None:
    """The mirror image of the regression above: with a declared hop the header IS read.

    Six distinct clients arriving through one trusted proxy must not throttle each
    other, which is also what makes the hops=0 default the load-bearing part of the fix.
    """
    statuses = _auth_failure_statuses(monkeypatch, trusted_proxy_hops="1")

    assert statuses == [401] * 6, f"per-client bucketing broke: {statuses}"


def _diagnostics_network(monkeypatch, *, trusted_proxy_hops: str, forwarded_for: str) -> dict:
    temp_dir = Path(__file__).resolve().parent / ".tmp"
    temp_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("AB_DB_PATH", str(temp_dir / f"{uuid.uuid4()}.sqlite3"))
    monkeypatch.setenv("AB_SERVE_FRONTEND_DIST", "false")
    monkeypatch.setenv("AB_TRUSTED_PROXY_HOPS", trusted_proxy_hops)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/diagnostics", headers={"X-Forwarded-For": forwarded_for})

    get_settings.cache_clear()
    assert response.status_code == 200
    return response.json()["network"]


def test_diagnostics_echoes_the_untrusted_network_view(monkeypatch) -> None:
    """With hops=0 the chain is echoed for measurement but never resolved from.

    This is the read-back an operator uses on a fresh deployment: send a marker
    header, count the entries real proxies appended to its right, and only then
    declare `AB_TRUSTED_PROXY_HOPS`.
    """
    network = _diagnostics_network(monkeypatch, trusted_proxy_hops="0", forwarded_for="203.0.113.7, 198.51.100.9")

    assert network["trusted_proxy_hops"] == 0
    assert network["trusted_proxies"] == []
    assert network["forwarded_for_chain"] == ["203.0.113.7", "198.51.100.9"]
    assert network["resolved_from"] == "direct_peer"
    assert network["direct_peer"] == "testclient"
    assert network["resolved_client"] == "testclient"


def test_diagnostics_reports_resolution_from_a_trusted_header(monkeypatch) -> None:
    network = _diagnostics_network(monkeypatch, trusted_proxy_hops="1", forwarded_for="203.0.113.7, 198.51.100.9")

    assert network["trusted_proxy_hops"] == 1
    assert network["forwarded_for_chain"] == ["203.0.113.7", "198.51.100.9"]
    assert network["resolved_from"] == "forwarded_header"
    assert network["resolved_client"] == "198.51.100.9"


@pytest.mark.parametrize(
    ("env_value", "message"),
    [
        ("-1", "AB_TRUSTED_PROXY_HOPS must be zero or greater"),
    ],
)
def test_settings_reject_negative_trusted_proxy_hops(monkeypatch, env_value: str, message: str) -> None:
    monkeypatch.setenv("AB_TRUSTED_PROXY_HOPS", env_value)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match=message):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_unparseable_trusted_proxies(monkeypatch) -> None:
    monkeypatch.setenv("AB_TRUSTED_PROXY_HOPS", "1")
    monkeypatch.setenv("AB_TRUSTED_PROXIES", "not-an-ip")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_TRUSTED_PROXIES must be a comma-separated list"):
        get_settings()

    get_settings.cache_clear()


def test_settings_reject_trusted_proxies_without_hops(monkeypatch) -> None:
    monkeypatch.setenv("AB_TRUSTED_PROXIES", "10.0.0.0/8")
    monkeypatch.delenv("AB_TRUSTED_PROXY_HOPS", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="AB_TRUSTED_PROXIES has no effect"):
        get_settings()

    get_settings.cache_clear()
