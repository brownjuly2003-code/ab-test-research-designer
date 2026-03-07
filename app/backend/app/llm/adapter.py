import httpx

from app.backend.app.llm.parser import parse_llm_advice
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.pattern = pattern
        self.model = model
        self.reasoning = reasoning
        self.transport = transport

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
                response = client.post(
                    f"{self.base_url}/api/gk/orchestrate",
                    json=request_payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
            return {
                "available": False,
                "provider": "local_orchestrator",
                "model": self.model,
                "advice": None,
                "raw_text": None,
                "error": str(exc),
            }

        raw_text = ""
        for item in data.get("model_responses", []):
            if item.get("text"):
                raw_text = item["text"]
                break

        if not raw_text and data.get("consensus", {}).get("text"):
            raw_text = data["consensus"]["text"]

        if not raw_text:
            return {
                "available": False,
                "provider": "local_orchestrator",
                "model": self.model,
                "advice": None,
                "raw_text": None,
                "error": "No usable text returned by orchestrator",
            }

        try:
            parsed = parse_llm_advice(raw_text)
        except (ValueError, KeyError, TypeError):
            return {
                "available": False,
                "provider": "local_orchestrator",
                "model": self.model,
                "advice": None,
                "raw_text": raw_text,
                "error": "Failed to parse structured AI advice",
            }

        return {
            "available": True,
            "provider": "local_orchestrator",
            "model": self.model,
            "advice": parsed,
            "raw_text": raw_text,
            "error": None,
        }
