from typing import Any

from app.backend.app.llm.external_chat_adapter import ExternalChatAdapter


class MistralAdapter(ExternalChatAdapter):
    """Mistral chat-completions adapter (OpenAI-compatible contract).

    Free insurance/fallback provider: when the default local-orchestrator path
    is unavailable (e.g. the hosted demo has no orchestrator), the analysis
    routes fall back to Mistral using a server-side ``AB_MISTRAL_API_KEY`` so AI
    advice still works without a paid provider.
    """

    api_url = "https://api.mistral.ai/v1/chat/completions"
    provider_name = "mistral"
    vendor_label = "Mistral"

    def __init__(self, model: str = "mistral-small-latest", **kwargs: Any) -> None:
        super().__init__(base_url="https://api.mistral.ai", model=model, reasoning=False, **kwargs)
