from pydantic import BaseModel


class CalculationsSection(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    estimated_duration_days: int
    assumptions: list[str]


class VariantDefinition(BaseModel):
    name: str
    description: str


class ExperimentDesignSection(BaseModel):
    variants: list[VariantDefinition]
    randomization_unit: str
    traffic_split: list[int]
    target_audience: str
    inclusion_criteria: str
    exclusion_criteria: str
    recommended_duration_days: int
    stopping_conditions: list[str]


class MetricsPlanSection(BaseModel):
    primary: list[str]
    secondary: list[str]
    guardrail: list[str]
    diagnostic: list[str]


class GuardrailMetricReport(BaseModel):
    name: str
    metric_type: str
    baseline: float
    detectable_mde_pp: float | None = None
    detectable_mde_absolute: float | None = None
    note: str


class RisksSection(BaseModel):
    statistical: list[str]
    product: list[str]
    technical: list[str]
    operational: list[str]


class RecommendationsSection(BaseModel):
    before_launch: list[str]
    during_test: list[str]
    after_test: list[str]


class ExperimentReport(BaseModel):
    executive_summary: str
    calculations: CalculationsSection
    experiment_design: ExperimentDesignSection
    metrics_plan: MetricsPlanSection
    guardrail_metrics: list[GuardrailMetricReport] = []
    risks: RisksSection
    recommendations: RecommendationsSection
    open_questions: list[str]
