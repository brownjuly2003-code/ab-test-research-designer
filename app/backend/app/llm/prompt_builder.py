import json


def build_llm_advice_prompt(payload: dict) -> str:
    response_format = {
        "brief_assessment": "string",
        "key_risks": ["string"],
        "design_improvements": ["string"],
        "metric_recommendations": ["string"],
        "interpretation_pitfalls": ["string"],
        "additional_checks": ["string"],
    }

    return (
        "You are an experiment design advisor. Review the structured A/B test context "
        "and return valid JSON only. Do not include markdown fences or prose outside JSON.\n\n"
        f"Input payload:\n{json.dumps(payload, ensure_ascii=True, indent=2)}\n\n"
        "Required JSON schema:\n"
        f"{json.dumps(response_format, ensure_ascii=True, indent=2)}"
    )
