import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.llm.adapter import LLMAuthError, LLMTransientError
from app.backend.app.llm.mistral_adapter import MistralAdapter


def _structured_advice_payload() -> str:
    return json.dumps(
        {
            "brief_assessment": "Mistral advice is available.",
            "key_risks": ["Tracking quality"],
            "design_improvements": ["Validate event schema"],
            "metric_recommendations": ["Track checkout step completion"],
            "interpretation_pitfalls": ["Do not stop early"],
            "additional_checks": ["Verify exposure balance"],
        }
    )


def test_mistral_adapter_happy_path_parses_structured_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": _structured_advice_payload()}}]},
        )

    adapter = MistralAdapter(
        timeout_seconds=12.5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    result = asyncio.run(adapter.suggest("Return JSON only.", token="mistral-secret"))

    assert result["available"] is True
    assert result["provider"] == "mistral"
    assert result["model"] == "mistral-small-latest"
    assert result["advice"]["brief_assessment"] == "Mistral advice is available."
    assert result["error_code"] is None
    assert captured["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer mistral-secret"
    assert captured["payload"] == {
        "model": "mistral-small-latest",
        "temperature": 0.4,
        "messages": [{"role": "user", "content": "Return JSON only."}],
    }


def test_mistral_adapter_respects_configured_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": _structured_advice_payload()}}]},
        )

    adapter = MistralAdapter(
        model="open-mistral-7b",
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    result = asyncio.run(adapter.suggest("Return JSON only.", token="mistral-secret"))
    assert result["model"] == "open-mistral-7b"


def test_mistral_adapter_401_raises_auth_error_without_token_leak() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request, json={"error": {"message": "bad token"}})

    adapter = MistralAdapter(max_attempts=1, transport=httpx.MockTransport(handler), sleep_func=lambda _: None)

    with pytest.raises(LLMAuthError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="mistral-secret"))

    assert "mistral-secret" not in str(exc_info.value)


def test_mistral_adapter_timeout_raises_transient_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out", request=request)

    adapter = MistralAdapter(max_attempts=1, transport=httpx.MockTransport(handler), sleep_func=lambda _: None)

    with pytest.raises(LLMTransientError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="mistral-secret"))

    assert "timed out" in str(exc_info.value).lower()


def test_mistral_adapter_rate_limit_raises_transient_error_with_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, json={"error": {"message": "rate limited"}})

    adapter = MistralAdapter(max_attempts=1, transport=httpx.MockTransport(handler), sleep_func=lambda _: None)

    with pytest.raises(LLMTransientError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="mistral-secret"))

    assert "rate limited" in str(exc_info.value).lower()


def test_mistral_adapter_requires_token() -> None:
    adapter = MistralAdapter(max_attempts=1, sleep_func=lambda _: None)
    with pytest.raises(LLMAuthError):
        adapter.request_advice({"project_context": {"project_name": "X"}})
