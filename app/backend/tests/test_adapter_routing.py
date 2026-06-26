from pathlib import Path
import sys

from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.config import get_settings
from app.backend.app.llm.adapter import LLMTransientError, LocalOrchestratorAdapter
from app.backend.app.llm.anthropic_adapter import AnthropicAdapter
from app.backend.app.llm.mistral_adapter import MistralAdapter
from app.backend.app.llm.openai_adapter import OpenAIAdapter
from app.backend.app.main import create_app
from app.backend.app.routes.analysis import pick_adapter

_FULL_ADVICE = {
    "brief_assessment": "Insurance advice.",
    "key_risks": ["Tracking quality"],
    "design_improvements": ["Validate event schema"],
    "metric_recommendations": ["Track checkout completion"],
    "interpretation_pitfalls": ["Do not stop early"],
    "additional_checks": ["Verify exposure balance"],
}


def _request_with_headers(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/llm/advice",
            "headers": [(key.lower().encode("utf-8"), value.encode("utf-8")) for key, value in headers.items()],
        }
    )


def test_pick_adapter_returns_remote_or_local_adapter_based_on_headers() -> None:
    local_adapter = LocalOrchestratorAdapter()
    openai_adapter = OpenAIAdapter(max_attempts=1, sleep_func=lambda _: None)
    anthropic_adapter = AnthropicAdapter(max_attempts=1, sleep_func=lambda _: None)

    resolved_openai, openai_token = pick_adapter(
        _request_with_headers(
            {
                "X-AB-LLM-Provider": "openai",
                "X-AB-LLM-Token": "sk-openai-secret",
            }
        ),
        local_adapter=local_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
    )
    resolved_anthropic, anthropic_token = pick_adapter(
        _request_with_headers(
            {
                "X-AB-LLM-Provider": "anthropic",
                "X-AB-LLM-Token": "claude-secret",
            }
        ),
        local_adapter=local_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
    )
    resolved_local, local_token = pick_adapter(
        _request_with_headers({"X-AB-LLM-Provider": "openai"}),
        local_adapter=local_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
    )

    assert resolved_openai is openai_adapter
    assert openai_token == "sk-openai-secret"
    assert resolved_anthropic is anthropic_adapter
    assert anthropic_token == "claude-secret"
    assert resolved_local is local_adapter
    assert local_token == ""


def test_llm_advice_endpoint_uses_selected_remote_adapter(monkeypatch) -> None:
    def fake_request_advice(self, payload, *, token=""):
        assert token == "sk-openai-secret"
        return {
            "available": True,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "advice": {
                "brief_assessment": "Remote advice is available.",
                "key_risks": ["Tracking quality"],
                "design_improvements": ["Validate event schema"],
                "metric_recommendations": ["Track checkout step completion"],
                "interpretation_pitfalls": ["Do not stop early"],
                "additional_checks": ["Verify exposure balance"],
            },
            "raw_text": "{\"brief_assessment\":\"Remote advice is available.\"}",
            "error": None,
            "error_code": None,
        }

    monkeypatch.setattr(OpenAIAdapter, "request_advice", fake_request_advice)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/llm/advice",
        json={"project_context": {"project_name": "Checkout redesign"}},
        headers={
            "X-AB-LLM-Provider": "openai",
            "X-AB-LLM-Token": "sk-openai-secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    assert response.json()["model"] == "gpt-4o-mini"


def test_llm_advice_endpoint_returns_503_for_transient_remote_errors(monkeypatch) -> None:
    def failing_request_advice(self, payload, *, token=""):
        raise LLMTransientError("Rate limited. Try again or switch to local suggestions.")

    monkeypatch.setattr(OpenAIAdapter, "request_advice", failing_request_advice)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/llm/advice",
        json={"project_context": {"project_name": "Checkout redesign"}},
        headers={
            "X-AB-LLM-Provider": "openai",
            "X-AB-LLM-Token": "sk-openai-secret",
        },
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "llm_transient"
    assert "switch to local" in str(response.json()["detail"]).lower()


def test_pick_adapter_routes_explicit_mistral_only_when_configured() -> None:
    local_adapter = LocalOrchestratorAdapter()
    openai_adapter = OpenAIAdapter(max_attempts=1, sleep_func=lambda _: None)
    anthropic_adapter = AnthropicAdapter(max_attempts=1, sleep_func=lambda _: None)
    mistral_adapter = MistralAdapter(max_attempts=1, sleep_func=lambda _: None)

    headers = {"X-AB-LLM-Provider": "mistral", "X-AB-LLM-Token": "mistral-secret"}
    resolved, token = pick_adapter(
        _request_with_headers(headers),
        local_adapter=local_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
        mistral_adapter=mistral_adapter,
    )
    assert resolved is mistral_adapter
    assert token == "mistral-secret"

    # Without a configured Mistral adapter, an explicit mistral request falls back to local.
    resolved_local, local_token = pick_adapter(
        _request_with_headers(headers),
        local_adapter=local_adapter,
        openai_adapter=openai_adapter,
        anthropic_adapter=anthropic_adapter,
        mistral_adapter=None,
    )
    assert resolved_local is local_adapter
    assert local_token == ""


def test_local_unavailable_falls_back_to_free_mistral_insurance(monkeypatch) -> None:
    monkeypatch.setenv("AB_MISTRAL_API_KEY", "mistral-server-key")
    get_settings.cache_clear()

    def local_unavailable(self, payload):
        return {
            "available": False,
            "provider": "local_orchestrator",
            "model": self.model,
            "advice": None,
            "raw_text": None,
            "error": "orchestrator down",
            "error_code": "request_error",
        }

    def mistral_ok(self, payload, *, token=""):
        assert token == "mistral-server-key"
        return {
            "available": True,
            "provider": "mistral",
            "model": self.model,
            "advice": dict(_FULL_ADVICE),
            "raw_text": "{}",
            "error": None,
            "error_code": None,
        }

    monkeypatch.setattr(LocalOrchestratorAdapter, "request_advice", local_unavailable)
    monkeypatch.setattr(MistralAdapter, "request_advice", mistral_ok)
    try:
        client = TestClient(create_app())
        # No provider header → default local path; local is down → free Mistral insurance answers.
        response = client.post(
            "/api/v1/llm/advice",
            json={"project_context": {"project_name": "Checkout redesign"}},
        )
        assert response.status_code == 200
        assert response.json()["provider"] == "mistral"
        assert response.json()["available"] is True
    finally:
        get_settings.cache_clear()


def test_explicit_provider_error_is_not_swapped_to_mistral(monkeypatch) -> None:
    # Even with a server Mistral key configured, an explicitly chosen provider's
    # failure must propagate (the caller picked it) — insurance is only for local.
    monkeypatch.setenv("AB_MISTRAL_API_KEY", "mistral-server-key")
    get_settings.cache_clear()

    def failing_request_advice(self, payload, *, token=""):
        raise LLMTransientError("Rate limited. Try again or switch to local suggestions.")

    def mistral_should_not_run(self, payload, *, token=""):
        raise AssertionError("Mistral insurance must not run for an explicit provider choice")

    monkeypatch.setattr(OpenAIAdapter, "request_advice", failing_request_advice)
    monkeypatch.setattr(MistralAdapter, "request_advice", mistral_should_not_run)
    try:
        client = TestClient(create_app())
        response = client.post(
            "/api/v1/llm/advice",
            json={"project_context": {"project_name": "Checkout redesign"}},
            headers={"X-AB-LLM-Provider": "openai", "X-AB-LLM-Token": "sk-openai-secret"},
        )
        assert response.status_code == 503
        assert response.json()["error_code"] == "llm_transient"
    finally:
        get_settings.cache_clear()
