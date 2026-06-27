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


class ExternalChatAdapter(LocalOrchestratorAdapter):
    """Shared base for external hosted chat providers (OpenAI / Mistral / Anthropic).

    All three drive the same flow: POST a single-message chat completion to an
    async HTTP endpoint, map transport/HTTP failures onto ``LLMAuthError`` /
    ``LLMTransientError``, extract the assistant text, parse it into the
    structured advice/hypotheses shape, and retry transient failures with the
    base class's backoff schedule. Subclasses customise only the parts that
    actually differ between vendors:

    - ``api_url`` / ``provider_name`` / ``vendor_label`` (endpoint, response
      ``provider`` value, and the human label used in error messages)
    - ``_build_headers`` (auth scheme) and ``_build_payload`` (request body)
    - ``_extract_response_text`` (vendor response shape)

    The default header/body/extraction implement the OpenAI-compatible
    ``choices[0].message.content`` contract, which OpenAI and Mistral share
    verbatim; Anthropic overrides the three hooks for its native Messages API.
    """

    api_url: str = ""
    provider_name: str = ""
    vendor_label: str = ""

    def _build_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
        }

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
        label = self.vendor_label
        # The shared self.transport is typed BaseTransport | None for the base
        # class's sync httpx.Client; here it only ever feeds an AsyncClient.
        async_transport = cast("httpx.AsyncBaseTransport | None", self.transport)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=async_transport) as client:
                response = await client.post(
                    self.api_url,
                    headers=self._build_headers(token),
                    json=self._build_payload(prompt),
                )
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"{label} request timed out. Try again or switch to local suggestions.") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError(f"{label} request failed. Try again or switch to local suggestions.") from exc

        if response.status_code in {401, 403}:
            raise LLMAuthError(f"{label} authentication failed.", status_code=response.status_code)
        if response.status_code == 429:
            raise LLMTransientError(f"{label} rate limited the request. Try again or switch to local suggestions.")
        if response.status_code >= 500:
            raise LLMTransientError(f"{label} is temporarily unavailable. Try again or switch to local suggestions.")
        if response.status_code >= 400:
            raise LLMTransientError(
                f"{label} request failed with status {response.status_code}. Try again or switch to local suggestions."
            )

        raw_text = self._extract_response_text(response.json())
        if not raw_text:
            raise LLMTransientError(f"{label} returned an empty response. Try again or switch to local suggestions.")

        try:
            parsed = parse_fn(raw_text)
        except LlmAdviceParseError as exc:
            raise LLMTransientError(
                f"{label} returned an invalid structured response ({exc.code}). Try again or switch to local suggestions."
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMTransientError(
                f"{label} returned an invalid structured response. Try again or switch to local suggestions."
            ) from exc

        return {
            "available": True,
            "provider": self.provider_name,
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
        raise LLMTransientError(f"{self.vendor_label} request failed. Try again or switch to local suggestions.")

    def request_advice(self, payload: dict[str, Any], *, token: str = "") -> dict[str, Any]:
        if not token:
            raise LLMAuthError(f"{self.vendor_label} token is required.")
        return self._run_with_retry(
            build_llm_advice_prompt(payload), token=token, parse_fn=parse_llm_advice, result_key="advice"
        )

    def request_hypotheses(self, payload: dict[str, Any], *, token: str = "") -> dict[str, Any]:
        if not token:
            raise LLMAuthError(f"{self.vendor_label} token is required.")
        return self._run_with_retry(
            build_hypothesis_ideation_prompt(payload), token=token, parse_fn=parse_llm_hypotheses, result_key="hypotheses"
        )
