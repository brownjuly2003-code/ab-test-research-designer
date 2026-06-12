from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from app.backend.app.llm.adapter import LocalOrchestratorAdapter
from app.backend.app.llm.parser import LlmAdviceParseError, parse_llm_hypotheses


def _hypotheses_transport(payload_text: str) -> httpx.MockTransport:
    response_payload = {
        "status": "completed",
        "model_responses": [{"model": "Claude Sonnet 4.6", "text": payload_text}],
    }
    return httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))


def test_llm_adapter_parses_hypotheses() -> None:
    text = """{
        "hypotheses": [
            {"change": "One-page checkout", "rationale": "Fewer steps reduce drop-off",
             "primary_metric": "purchase_conversion", "expected_direction": "increase"},
            {"change": "Show shipping cost earlier", "rationale": "Reduces late surprises",
             "primary_metric": "checkout_completion", "expected_direction": "INCREASE"}
        ]
    }"""
    adapter = LocalOrchestratorAdapter(transport=_hypotheses_transport(text))

    result = adapter.request_hypotheses({"project_context": {"project_name": "Checkout"}, "count": 2})

    assert result["available"] is True
    assert result["error_code"] is None
    assert len(result["hypotheses"]) == 2
    assert result["hypotheses"][0]["change"] == "One-page checkout"
    assert result["hypotheses"][1]["expected_direction"] == "increase"  # normalized


def test_llm_adapter_hypotheses_fallback_is_empty_list_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    adapter = LocalOrchestratorAdapter(
        transport=httpx.MockTransport(handler), max_attempts=1, sleep_func=lambda _: None
    )

    result = adapter.request_hypotheses({"project_context": {"project_name": "Checkout"}})

    assert result["available"] is False
    assert result["hypotheses"] == []
    assert result["error_code"] == "timeout"


def test_llm_adapter_hypotheses_invalid_when_array_missing() -> None:
    adapter = LocalOrchestratorAdapter(transport=_hypotheses_transport('{"not_hypotheses": []}'))

    result = adapter.request_hypotheses({"project_context": {"project_name": "Checkout"}})

    assert result["available"] is False
    assert result["hypotheses"] == []
    assert result["error_code"] == "missing_hypotheses"


def test_parse_llm_hypotheses_skips_invalid_items_and_normalizes_direction() -> None:
    parsed = parse_llm_hypotheses(
        '{"hypotheses": ['
        '"not-an-object",'
        '{"change": "", "primary_metric": "x"},'
        '{"change": "Add trust badges", "rationale": "Reassures buyers",'
        ' "primary_metric": "conversion", "expected_direction": "sideways"}'
        ']}'
    )

    assert len(parsed) == 1
    assert parsed[0]["change"] == "Add trust badges"
    assert parsed[0]["expected_direction"] == "increase"  # unknown direction -> increase


def test_parse_llm_hypotheses_rejects_empty_result() -> None:
    with pytest.raises(LlmAdviceParseError) as exc:
        parse_llm_hypotheses('{"hypotheses": [{"change": ""}]}')
    assert exc.value.code == "empty_hypotheses"


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
    assert result["error_code"] is None


def test_llm_adapter_parses_fenced_json_and_normalizes_lists() -> None:
    response_payload = {
        "status": "completed",
        "model_responses": [
            {"model": "Claude Sonnet 4.6", "text": ""}
        ],
        "consensus": {
            "text": """```json
            {
                "brief_assessment": "  Strong candidate for a test.  ",
                "key_risks": "Tracking quality\\nTracking quality\\nSeasonality",
                "design_improvements": ["Validate event schema", "Validate event schema"],
                "metric_recommendations": "Track funnel completion",
                "interpretation_pitfalls": ["Avoid peeking"],
                "additional_checks": "SRM check\\nExposure parity"
            }
            ```"""
        },
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    adapter = LocalOrchestratorAdapter(transport=transport)

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is True
    assert result["advice"]["brief_assessment"] == "Strong candidate for a test."
    assert result["advice"]["key_risks"] == ["Tracking quality", "Seasonality"]
    assert result["advice"]["design_improvements"] == ["Validate event schema"]
    assert result["advice"]["metric_recommendations"] == ["Track funnel completion"]
    assert result["advice"]["additional_checks"] == ["SRM check", "Exposure parity"]


def test_llm_adapter_prefers_longest_available_text_candidate() -> None:
    short_json = '{"brief_assessment":"Short","key_risks":[],"design_improvements":[],"metric_recommendations":[],"interpretation_pitfalls":[],"additional_checks":[]}'
    long_json = """{
        "brief_assessment": "Detailed answer selected from consensus.",
        "key_risks": ["Tracking quality"],
        "design_improvements": ["Validate schema"],
        "metric_recommendations": ["Track step conversion"],
        "interpretation_pitfalls": ["Avoid peeking"],
        "additional_checks": ["SRM check"]
    }"""
    response_payload = {
        "status": "completed",
        "model_responses": [
            {"model": "Claude Sonnet 4.6", "text": short_json}
        ],
        "consensus": {"text": long_json},
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    adapter = LocalOrchestratorAdapter(transport=transport)

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is True
    assert result["raw_text"] is not None
    assert "Detailed answer selected from consensus." in result["raw_text"]
    assert result["advice"]["brief_assessment"] == "Detailed answer selected from consensus."


def test_llm_adapter_returns_graceful_fallback_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    adapter = LocalOrchestratorAdapter(
        transport=httpx.MockTransport(handler),
        max_attempts=1,
        sleep_func=lambda _: None,
    )

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is False
    assert result["advice"] is None
    assert result["error"] is not None
    assert result["error_code"] == "timeout"


def test_llm_adapter_retries_transient_request_errors_with_exponential_backoff() -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    response_payload = {
        "status": "completed",
        "model_responses": [
            {
                "model": "Claude Sonnet 4.6",
                "text": """{
                    "brief_assessment": "Recovered after retry.",
                    "key_risks": [],
                    "design_improvements": [],
                    "metric_recommendations": [],
                    "interpretation_pitfalls": [],
                    "additional_checks": []
                }""",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.ConnectError("connection dropped", request=request)
        return httpx.Response(200, json=response_payload, request=request)

    adapter = LocalOrchestratorAdapter(
        transport=httpx.MockTransport(handler),
        initial_backoff_seconds=0.25,
        backoff_multiplier=3,
        sleep_func=sleep_calls.append,
    )

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert attempts["count"] == 3
    assert sleep_calls == [0.25, 0.75]
    assert result["available"] is True
    assert result["advice"]["brief_assessment"] == "Recovered after retry."


def test_llm_adapter_retries_retryable_http_statuses() -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []
    response_payload = {
        "status": "completed",
        "model_responses": [
            {
                "model": "Claude Sonnet 4.6",
                "text": """{
                    "brief_assessment": "Recovered after 503.",
                    "key_risks": [],
                    "design_improvements": [],
                    "metric_recommendations": [],
                    "interpretation_pitfalls": [],
                    "additional_checks": []
                }""",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=response_payload, request=request)

    adapter = LocalOrchestratorAdapter(
        transport=httpx.MockTransport(handler),
        sleep_func=sleep_calls.append,
    )

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert attempts["count"] == 2
    assert sleep_calls == [0.1]
    assert result["available"] is True
    assert result["advice"]["brief_assessment"] == "Recovered after 503."


def test_llm_adapter_does_not_retry_non_retryable_http_statuses() -> None:
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, request=request, json={"detail": "bad request"})

    adapter = LocalOrchestratorAdapter(
        transport=httpx.MockTransport(handler),
        sleep_func=sleep_calls.append,
    )

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert attempts["count"] == 1
    assert sleep_calls == []
    assert result["available"] is False
    assert result["error_code"] == "http_error"


def test_llm_adapter_returns_structured_error_code_for_invalid_json() -> None:
    response_payload = {
        "status": "completed",
        "model_responses": [
            {
                "model": "Claude Sonnet 4.6",
                "text": """{
                    "brief_assessment": "Broken payload",
                    "key_risks": ["Tracking quality",]
                }""",
            }
        ],
    }

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_payload))
    adapter = LocalOrchestratorAdapter(transport=transport)

    result = adapter.request_advice({"project_context": {"project_name": "Checkout redesign"}})

    assert result["available"] is False
    assert result["advice"] is None
    assert result["raw_text"] is not None
    assert result["error_code"] == "invalid_json"
