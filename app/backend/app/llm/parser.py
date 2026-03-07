import json


def _extract_json_object(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def parse_llm_advice(raw_text: str) -> dict:
    json_candidate = _extract_json_object(raw_text)
    if not json_candidate:
        raise ValueError("LLM response did not contain a JSON object")

    parsed = json.loads(json_candidate)
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
            normalized[key] = value if isinstance(value, str) else ""
        else:
            normalized[key] = value if isinstance(value, list) else []

    return normalized
