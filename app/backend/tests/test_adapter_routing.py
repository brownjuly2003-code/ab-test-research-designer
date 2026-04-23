from pathlib import Path
import sys

from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.llm.adapter import LLMTransientError, LocalOrchestratorAdapter
from app.backend.app.llm.anthropic_adapter import AnthropicAdapter
from app.backend.app.llm.openai_adapter import OpenAIAdapter
from app.backend.app.main import create_app
from app.backend.app.routes.analysis import pick_adapter


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
