import json


class LlmAdviceParseError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _strip_markdown_fences(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()

    return stripped


def _extract_json_object(raw_text: str) -> str | None:
    normalized_text = _strip_markdown_fences(raw_text)
    if normalized_text.startswith("{") and normalized_text.endswith("}"):
        return normalized_text

    start = normalized_text.find("{")
    end = normalized_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return normalized_text[start : end + 1]


def _normalize_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str):
        items = [item.strip() for item in value.splitlines() if item.strip()]
    else:
        return []

    deduplicated: list[str] = []
    for item in items:
        if item not in deduplicated:
            deduplicated.append(item)
    return deduplicated


def parse_llm_advice(raw_text: str) -> dict:
    json_candidate = _extract_json_object(raw_text)
    if not json_candidate:
        raise LlmAdviceParseError("LLM response did not contain a JSON object", code="missing_json_object")

    try:
        parsed = json.loads(json_candidate)
    except json.JSONDecodeError as exc:
        raise LlmAdviceParseError("LLM response contained invalid JSON", code="invalid_json") from exc

    if not isinstance(parsed, dict):
        raise LlmAdviceParseError("LLM response JSON must be an object", code="json_not_object")

    required_keys = [
        "brief_assessment",
        "key_risks",
        "design_improvements",
        "metric_recommendations",
        "interpretation_pitfalls",
        "additional_checks",
    ]

    normalized = {}
    for key in required_keys:
        value = parsed.get(key)
        if key == "brief_assessment":
            normalized[key] = value.strip() if isinstance(value, str) else ""
        else:
            normalized[key] = _normalize_text_list(value)

    return normalized
