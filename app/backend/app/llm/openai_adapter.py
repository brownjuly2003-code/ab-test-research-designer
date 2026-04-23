import asyncio

import httpx

from app.backend.app.llm.adapter import LLMAuthError, LLMTransientError, LocalOrchestratorAdapter
from app.backend.app.llm.parser import LlmAdviceParseError, parse_llm_advice
from app.backend.app.llm.prompt_builder import build_llm_advice_prompt


class OpenAIAdapter(LocalOrchestratorAdapter):
    api_url = "https://api.openai.com/v1/chat/completions"

    def __init__(self, **kwargs) -> None:
        super().__init__(base_url="https://api.openai.com", model="gpt-4o-mini", reasoning=False, **kwargs)

    @staticmethod
    def _extract_response_text(data: dict) -> str:
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

    async def suggest(self, prompt: str, *, token: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
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
            raise LLMTransientError("OpenAI request timed out. Try again or switch to local suggestions.") from exc
        except httpx.RequestError as exc:
            raise LLMTransientError("OpenAI request failed. Try again or switch to local suggestions.") from exc

        if response.status_code in {401, 403}:
            raise LLMAuthError("OpenAI authentication failed.", status_code=response.status_code)
        if response.status_code == 429:
            raise LLMTransientError("OpenAI rate limited the request. Try again or switch to local suggestions.")
        if response.status_code >= 500:
            raise LLMTransientError("OpenAI is temporarily unavailable. Try again or switch to local suggestions.")
        if response.status_code >= 400:
            raise LLMTransientError(
                f"OpenAI request failed with status {response.status_code}. Try again or switch to local suggestions."
            )

        raw_text = self._extract_response_text(response.json())
        if not raw_text:
            raise LLMTransientError("OpenAI returned an empty response. Try again or switch to local suggestions.")

        try:
            parsed = parse_llm_advice(raw_text)
        except LlmAdviceParseError as exc:
            raise LLMTransientError(
                f"OpenAI returned an invalid structured response ({exc.code}). Try again or switch to local suggestions."
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMTransientError("OpenAI returned an invalid structured response. Try again or switch to local suggestions.") from exc

        return {
            "available": True,
            "provider": "openai",
            "model": self.model,
            "advice": parsed,
            "raw_text": raw_text,
            "error": None,
            "error_code": None,
        }

    def request_advice(self, payload: dict, *, token: str = "") -> dict:
        if not token:
            raise LLMAuthError("OpenAI token is required.")

        prompt = build_llm_advice_prompt(payload)
        last_error: LLMTransientError | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return asyncio.run(self.suggest(prompt, token=token))
            except LLMAuthError:
                raise
            except LLMTransientError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise
                self._sleep_before_retry(attempt)

        if last_error is not None:
            raise last_error
        raise LLMTransientError("OpenAI request failed. Try again or switch to local suggestions.")
