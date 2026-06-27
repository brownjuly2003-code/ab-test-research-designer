from typing import Any

from app.backend.app.llm.external_chat_adapter import ExternalChatAdapter


class AnthropicAdapter(ExternalChatAdapter):
    """Anthropic Messages API adapter.

    Opt-in provider selected by the caller via the ``X-AB-LLM-Provider`` header
    with their own ``X-AB-LLM-Token``; never used on the default path. Overrides
    the auth header, request body and response extraction for Anthropic's native
    Messages API (``x-api-key`` auth, ``max_tokens`` body, ``content[].text``
    response) while reusing the shared retry/parse flow.
    """

    api_url = "https://api.anthropic.com/v1/messages"
    provider_name = "anthropic"
    vendor_label = "Anthropic"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(base_url="https://api.anthropic.com", model="claude-haiku-4-5-20251001", reasoning=False, **kwargs)

    def _build_headers(self, token: str) -> dict[str, str]:
        return {
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _build_payload(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": 1024,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
        }

    @staticmethod
    def _extract_response_text(data: dict[str, Any]) -> str:
        fragments = [
            item.get("text", "").strip()
            for item in data.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str) and item["text"].strip()
        ]
        return "\n".join(fragments).strip()
