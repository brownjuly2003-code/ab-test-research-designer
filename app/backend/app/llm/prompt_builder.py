import json
from typing import Any


def build_hypothesis_ideation_prompt(payload: dict[str, Any]) -> str:
    count = int(payload.get("count", 3))
    response_format = {
        "hypotheses": [
            {
                "change": "string — the concrete change to test",
                "rationale": "string — one sentence grounded in the baseline/traffic",
                "primary_metric": "string — the metric this change should move",
                "expected_direction": "increase | decrease",
            }
        ]
    }

    return (
        f"You are an experimentation strategist. Propose {count} distinct, testable A/B test "
        "hypotheses for the product context below. Each hypothesis must name a concrete change, "
        "the primary metric it should move, the expected direction, and a one-sentence rationale "
        "grounded in the provided baseline and traffic. Avoid duplicates and vague ideas. "
        "Return valid JSON only. Do not include markdown fences or prose outside JSON.\n\n"
        f"Input payload:\n{json.dumps(payload, ensure_ascii=True, indent=2)}\n\n"
        "Required JSON schema:\n"
        f"{json.dumps(response_format, ensure_ascii=True, indent=2)}"
    )


def build_llm_advice_prompt(payload: dict[str, Any]) -> str:
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
