import asyncio
from collections.abc import Callable

import httpx

from app.backend.app.llm.adapter import LLMAuthError, LLMTransientError, LocalOrchestratorAdapter
from app.backend.app.llm.parser import LlmAdviceParseError, parse_llm_advice, parse_llm_hypotheses
from app.backend.app.llm.prompt_builder import build_hypothesis_ideation_prompt, build_llm_advice_prompt


class AnthropicAdapter(LocalOrchestratorAdapter):
    api_url = "https://api.anthropic.com/v1/messages"

    def __init__(self, **kwargs) -> None:
        super().__init__(base_url="https://api.anthropic.com", model="claude-haiku-4-5-20251001", reasoning=False, **kwargs)

    @staticmethod
    def _extract_response_text(data: dict) -> str:
        fragments = [
            item.get("text", "").strip()
            for item in data.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str) and item["text"].strip()
        ]
        return "\n".join(fragments).strip()

    async def suggest(
        self,
        prompt: str,
        *,
        token: str,
        parse_fn: Callable[[str], object] = parse_llm_advice,
        result_key: str = "advice",
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "x-api-key": token,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 1024,
                        "temperature": 0.4,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTransientError("Anthropic request timed out. Try again or switch to local suggestions.") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError("Anthropic request failed. Try again or switch to local suggestions.") from exc

        if response.status_code in {401, 403}:
            raise LLMAuthError("Anthropic authentication failed.", status_code=response.status_code)
        if response.status_code == 429:
            raise LLMTransientError("Anthropic rate limited the request. Try again or switch to local suggestions.")
        if response.status_code >= 500:
            raise LLMTransientError("Anthropic is temporarily unavailable. Try again or switch to local suggestions.")
        if response.status_code >= 400:
            raise LLMTransientError(
                f"Anthropic request failed with status {response.status_code}. Try again or switch to local suggestions."
            )

        raw_text = self._extract_response_text(response.json())
        if not raw_text:
            raise LLMTransientError("Anthropic returned an empty response. Try again or switch to local suggestions.")

        try:
            parsed = parse_fn(raw_text)
        except LlmAdviceParseError as exc:
            raise LLMTransientError(
                f"Anthropic returned an invalid structured response ({exc.code}). Try again or switch to local suggestions."
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMTransientError("Anthropic returned an invalid structured response. Try again or switch to local suggestions.") from exc

        return {
            "available": True,
            "provider": "anthropic",
            "model": self.model,
            result_key: parsed,
            "raw_text": raw_text,
            "error": None,
            "error_code": None,
        }

    def _run_with_retry(self, prompt: str, *, token: str, parse_fn: Callable[[str], object], result_key: str) -> dict:
        last_error: LLMTransientError | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return asyncio.run(self.suggest(prompt, token=token, parse_fn=parse_fn, result_key=result_key))
            except LLMAuthError:
                raise
            except LLMTransientError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise
                self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error
        raise LLMTransientError("Anthropic request failed. Try again or switch to local suggestions.")

    def request_advice(self, payload: dict, *, token: str = "") -> dict:
        if not token:
            raise LLMAuthError("Anthropic token is required.")
        return self._run_with_retry(
            build_llm_advice_prompt(payload), token=token, parse_fn=parse_llm_advice, result_key="advice"
        )

    def request_hypotheses(self, payload: dict, *, token: str = "") -> dict:
        if not token:
            raise LLMAuthError("Anthropic token is required.")
        return self._run_with_retry(
            build_hypothesis_ideation_prompt(payload), token=token, parse_fn=parse_llm_hypotheses, result_key="hypotheses"
        )
