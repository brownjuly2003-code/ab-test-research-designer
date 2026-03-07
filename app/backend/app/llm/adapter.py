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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.pattern = pattern
        self.model = model
        self.reasoning = reasoning
        self.transport = transport

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
