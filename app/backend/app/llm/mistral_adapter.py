import asyncio
from collections.abc import Callable
from typing import Any, cast

import httpx

from app.backend.app.llm.adapter import (
    LLMAuthError,
    LLMTransientError,
    LocalOrchestratorAdapter,
)
from app.backend.app.llm.parser import (
    LlmAdviceParseError,
    parse_llm_advice,
    parse_llm_hypotheses,
)
from app.backend.app.llm.prompt_builder import (
    build_hypothesis_ideation_prompt,
    build_llm_advice_prompt,
)


class MistralAdapter(LocalOrchestratorAdapter):
    """Mistral chat-completions adapter.

    Mistral's API is OpenAI-compatible (Bearer auth, ``choices[0].message.content``
    response shape), so this mirrors ``OpenAIAdapter``. It exists as a free
    insurance/fallback provider: when the default local-orchestrator path is
    unavailable (e.g. the hosted demo has no orchestrator), the analysis routes
    fall back to Mistral using a server-side ``AB_MISTRAL_API_KEY`` so AI advice
    still works without a paid provider.
    """

    api_url = "https://api.mistral.ai/v1/chat/completions"

    def __init__(self, model: str = "mistral-small-latest", **kwargs: Any) -> None:
        super().__init__(base_url="https://api.mistral.ai", model=model, reasoning=False, **kwargs)

    @staticmethod
    def _extract_response_text(data: dict[str, Any]) -> str:
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            fragments = [
                item.get("text", "").strip()
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip()
            ]
            return "\n".join(fragments).strip()
        return ""

    async def suggest(
        self,
        prompt: str,
        *,
        token: str,
        parse_fn: Callable[[str], object] = parse_llm_advice,
        result_key: str = "advice",
    ) -> dict[str, Any]:
        # The shared self.transport is typed BaseTransport | None for the base
        # class's sync httpx.Client; here it only ever feeds an AsyncClient.
        async_transport = cast("httpx.AsyncBaseTransport | None", self.transport)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=async_transport) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "temperature": 0.4,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTransientError("Mistral request timed out. Try again or switch to local suggestions.") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError("Mistral request failed. Try again or switch to local suggestions.") from exc

        if response.status_code in {401, 403}:
            raise LLMAuthError("Mistral authentication failed.", status_code=response.status_code)
        if response.status_code == 429:
            raise LLMTransientError("Mistral rate limited the request. Try again or switch to local suggestions.")
        if response.status_code >= 500:
            raise LLMTransientError("Mistral is temporarily unavailable. Try again or switch to local suggestions.")
        if response.status_code >= 400:
            raise LLMTransientError(
                f"Mistral request failed with status {response.status_code}. Try again or switch to local suggestions."
            )

        raw_text = self._extract_response_text(response.json())
        if not raw_text:
            raise LLMTransientError("Mistral returned an empty response. Try again or switch to local suggestions.")

        try:
            parsed = parse_fn(raw_text)
        except LlmAdviceParseError as exc:
            raise LLMTransientError(
                f"Mistral returned an invalid structured response ({exc.code}). Try again or switch to local suggestions."
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMTransientError("Mistral returned an invalid structured response. Try again or switch to local suggestions.") from exc

        return {
            "available": True,
            "provider": "mistral",
            "model": self.model,
            result_key: parsed,
            "raw_text": raw_text,
            "error": None,
            "error_code": None,
        }

    def _run_with_retry(self, prompt: str, *, token: str, parse_fn: Callable[[str], object], result_key: str) -> dict[str, Any]:
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
        raise LLMTransientError("Mistral request failed. Try again or switch to local suggestions.")

    def request_advice(self, payload: dict[str, Any], *, token: str = "") -> dict[str, Any]:
        if not token:
            raise LLMAuthError("Mistral token is required.")
        return self._run_with_retry(
            build_llm_advice_prompt(payload), token=token, parse_fn=parse_llm_advice, result_key="advice"
        )

    def request_hypotheses(self, payload: dict[str, Any], *, token: str = "") -> dict[str, Any]:
        if not token:
            raise LLMAuthError("Mistral token is required.")
        return self._run_with_retry(
            build_hypothesis_ideation_prompt(payload), token=token, parse_fn=parse_llm_hypotheses, result_key="hypotheses"
        )
