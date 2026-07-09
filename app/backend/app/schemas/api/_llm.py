"""LLM advice and hypothesis-ideation payloads."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AdvicePayload(BaseModel):
    brief_assessment: str
    key_risks: list[str]
    design_improvements: list[str]
    metric_recommendations: list[str]
    interpretation_pitfalls: list[str]
    additional_checks: list[str]


class LlmAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_context: dict[str, Any]
    hypothesis: dict[str, Any] | None = None
    setup: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    additional_context: dict[str, Any] | None = None
    calculation_results: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] | None = None


class LlmAdviceResponse(BaseModel):
    available: bool
    provider: str
    model: str
    advice: AdvicePayload | None
    raw_text: str | None
    error: str | None
    error_code: str | None = None


class HypothesisIdeationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_context: dict[str, Any]
    business_problem: str | None = None
    setup: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    count: int = Field(default=3, ge=1, le=5)


class HypothesisCandidate(BaseModel):
    change: str
    rationale: str
    primary_metric: str
    expected_direction: Literal["increase", "decrease"]


class HypothesisIdeationResponse(BaseModel):
    available: bool
    provider: str
    model: str
    hypotheses: list[HypothesisCandidate]
    raw_text: str | None
    error: str | None
    error_code: str | None = None
