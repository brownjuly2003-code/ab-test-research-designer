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


def parse_llm_hypotheses(raw_text: str) -> list[dict]:
    json_candidate = _extract_json_object(raw_text)
    if not json_candidate:
        raise LlmAdviceParseError("LLM response did not contain a JSON object", code="missing_json_object")

    try:
        parsed = json.loads(json_candidate)
    except json.JSONDecodeError as exc:
        raise LlmAdviceParseError("LLM response contained invalid JSON", code="invalid_json") from exc

    if not isinstance(parsed, dict):
        raise LlmAdviceParseError("LLM response JSON must be an object", code="json_not_object")

    raw_items = parsed.get("hypotheses")
    if not isinstance(raw_items, list):
        raise LlmAdviceParseError("LLM response must contain a 'hypotheses' array", code="missing_hypotheses")

    normalized: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        change = str(item.get("change", "")).strip()
        if not change:
            continue
        direction = str(item.get("expected_direction", "")).strip().lower()
        if direction not in {"increase", "decrease"}:
            direction = "increase"
        normalized.append(
            {
                "change": change,
                "rationale": str(item.get("rationale", "")).strip(),
                "primary_metric": str(item.get("primary_metric", "")).strip(),
                "expected_direction": direction,
            }
        )

    if not normalized:
        raise LlmAdviceParseError("LLM response contained no usable hypotheses", code="empty_hypotheses")

    return normalized


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
