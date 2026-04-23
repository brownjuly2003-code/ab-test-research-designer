import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.llm.adapter import LLMAuthError, LLMTransientError
from app.backend.app.llm.openai_adapter import OpenAIAdapter


def _structured_advice_payload() -> str:
    return json.dumps(
        {
            "brief_assessment": "OpenAI advice is available.",
            "key_risks": ["Tracking quality"],
            "design_improvements": ["Validate event schema"],
            "metric_recommendations": ["Track checkout step completion"],
            "interpretation_pitfalls": ["Do not stop early"],
            "additional_checks": ["Verify exposure balance"],
        }
    )


def test_openai_adapter_happy_path_parses_structured_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": _structured_advice_payload(),
                        }
                    }
                ]
            },
        )

    adapter = OpenAIAdapter(
        timeout_seconds=12.5,
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    result = asyncio.run(adapter.suggest("Return JSON only.", token="sk-openai-secret"))

    assert result["available"] is True
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini"
    assert result["advice"]["brief_assessment"] == "OpenAI advice is available."
    assert result["error_code"] is None
    assert captured["headers"]["authorization"] == "Bearer sk-openai-secret"
    assert captured["payload"] == {
        "model": "gpt-4o-mini",
        "temperature": 0.4,
        "messages": [{"role": "user", "content": "Return JSON only."}],
    }


def test_openai_adapter_401_raises_auth_error_without_token_leak() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, request=request, json={"error": {"message": "bad token"}})

    adapter = OpenAIAdapter(
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    with pytest.raises(LLMAuthError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="sk-openai-secret"))

    assert "sk-openai-secret" not in str(exc_info.value)


def test_openai_adapter_timeout_raises_transient_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out", request=request)

    adapter = OpenAIAdapter(
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    with pytest.raises(LLMTransientError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="sk-openai-secret"))

    assert "timed out" in str(exc_info.value).lower()


def test_openai_adapter_rate_limit_raises_transient_error_with_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, json={"error": {"message": "rate limited"}})

    adapter = OpenAIAdapter(
        max_attempts=1,
        transport=httpx.MockTransport(handler),
        sleep_func=lambda _: None,
    )

    with pytest.raises(LLMTransientError) as exc_info:
        asyncio.run(adapter.suggest("Return JSON only.", token="sk-openai-secret"))

    assert "rate limited" in str(exc_info.value).lower()
