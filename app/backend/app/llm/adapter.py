from collections.abc import Callable
import time

import httpx

from app.backend.app.llm.parser import LlmAdviceParseError, parse_llm_advice
from app.backend.app.llm.prompt_builder import build_llm_advice_prompt


class LocalOrchestratorAdapter:
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        timeout_seconds: float = 60.0,
        pattern: str = "single",
        model: str = "Claude Sonnet 4.6",
        reasoning: bool = True,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 0.1,
        backoff_multiplier: float = 2.0,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.pattern = pattern
        self.model = model
        self.reasoning = reasoning
        self.transport = transport
        self.max_attempts = max_attempts
        self.initial_backoff_seconds = initial_backoff_seconds
        self.backoff_multiplier = backoff_multiplier
        self.sleep_func = sleep_func or time.sleep

    def _fallback(self, error: str, *, raw_text: str | None = None, error_code: str | None = None) -> dict:
        return {
            "available": False,
            "provider": "local_orchestrator",
            "model": self.model,
            "advice": None,
            "raw_text": raw_text,
            "error": error,
            "error_code": error_code,
        }

    @staticmethod
    def _extract_raw_text(data: dict) -> str:
        candidate_texts: list[str] = []

        for item in data.get("model_responses", []):
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                candidate_texts.append(item["text"].strip())

        consensus_text = data.get("consensus", {}).get("text")
        if isinstance(consensus_text, str) and consensus_text.strip():
            candidate_texts.append(consensus_text.strip())

        if not candidate_texts:
            return ""

        return max(candidate_texts, key=len)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 429, 500, 502, 503, 504}

    def _sleep_before_retry(self, attempt: int) -> None:
        delay_seconds = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        if delay_seconds > 0:
            self.sleep_func(delay_seconds)

    def _send_request(self, client: httpx.Client, request_payload: dict) -> dict:
        last_error: httpx.HTTPError | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = client.post(
                    f"{self.base_url}/api/gk/orchestrate",
                    json=request_payload,
                )
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if attempt == self.max_attempts or not self._is_retryable_status(exc.response.status_code):
                    raise
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise

            self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to complete orchestrator request")

    def request_advice(self, payload: dict) -> dict:
        prompt = build_llm_advice_prompt(payload)
        request_payload = {
            "query": prompt,
            "pattern": self.pattern,
            "model": self.model,
            "reasoning": self.reasoning,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                data = self._send_request(client, request_payload)
        except httpx.TimeoutException as exc:
            return self._fallback(str(exc), error_code="timeout")
        except httpx.HTTPStatusError as exc:
            return self._fallback(str(exc), error_code="http_error")
        except httpx.RequestError as exc:
            return self._fallback(str(exc), error_code="request_error")

        raw_text = self._extract_raw_text(data)

        if not raw_text:
            return self._fallback("No usable text returned by orchestrator", error_code="empty_response")

        try:
            parsed = parse_llm_advice(raw_text)
        except LlmAdviceParseError as exc:
            return self._fallback(str(exc), raw_text=raw_text, error_code=exc.code)
        except (ValueError, KeyError, TypeError):
            return self._fallback("Failed to parse structured AI advice", raw_text=raw_text, error_code="parse_error")

        return {
            "available": True,
            "provider": "local_orchestrator",
            "model": self.model,
            "advice": parsed,
            "raw_text": raw_text,
            "error": None,
            "error_code": None,
        }
