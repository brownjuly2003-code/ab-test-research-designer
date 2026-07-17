from typing import Any

from app.backend.app.llm.external_chat_adapter import ExternalChatAdapter


class OpenAIAdapter(ExternalChatAdapter):
    """OpenAI chat-completions adapter.

    Opt-in provider selected by the caller via the ``X-AB-LLM-Provider`` header
    with their own ``X-AB-LLM-Token``; never used on the default path. Uses the
    OpenAI-compatible request/response contract from ``ExternalChatAdapter``.
    """

    api_url = "https://api.openai.com/v1/chat/completions"
    provider_name = "openai"
    vendor_label = "OpenAI"

    def __init__(self, model: str = "gpt-5.6-luna", **kwargs: Any) -> None:
        super().__init__(base_url="https://api.openai.com", model=model, reasoning=False, **kwargs)
