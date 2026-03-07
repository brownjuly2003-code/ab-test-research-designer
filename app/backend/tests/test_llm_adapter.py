from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.app.llm.adapter import LocalOrchestratorAdapter


def test_llm_adapter_parses_structured_response() -> None:
    response_payload = {
        "status": "completed",
        "model_responses": [
            {
                "model": "Claude Sonnet 4.6",
                "text": """{
                    "brief_assessment": "Feasible test with instrumentation risk.",
                    "key_risks": ["Tracking quality"],
                    "design_improvements": ["Validate event schema"],
                    "metric_recommendations": ["Track checkout step completion"],
                    "interpretation_pitfalls": ["Do not stop early"],
                    "additional_checks": ["Verify exposure balance"]
                }""",
            }
        ],
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    adapter = LocalOrchestratorAdapter(transport=transport)

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is True
    assert result["advice"]["brief_assessment"] == "Feasible test with instrumentation risk."
    assert result["advice"]["key_risks"] == ["Tracking quality"]


def test_llm_adapter_returns_graceful_fallback_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    adapter = LocalOrchestratorAdapter(transport=httpx.MockTransport(handler))

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is False
    assert result["advice"] is None
    assert result["error"] is not None
