"""The experiment definition: context, setup, metrics, constraints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import (
    MAX_SUPPORTED_VARIANTS,
    MetricType,
)
from app.backend.app.i18n import translate
from app.backend.app.schemas.api._results import ResultsRequest, ResultsResponse


class ProjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    domain: str
    product_type: str
    platform: str
    market: str
    project_description: str


class HypothesisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_description: str
    target_audience: str
    business_problem: str
    hypothesis_statement: str
    what_to_validate: str
    desired_result: str


class NamespaceConfig(BaseModel):
    """Mutual-exclusion namespace: experiments sharing an ``id`` but reserving
    non-overlapping ``[range_start, range_end)`` slots never assign the same user."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    range_start: float = Field(ge=0.0, le=1.0)
    range_end: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_range(self) -> "NamespaceConfig":
        if self.range_start >= self.range_end:
            raise ValueError(translate("errors.schemas.namespace_range_order"))
        return self


class TargetingRule(BaseModel):
    """One attribute-based eligibility rule. All rules on an experiment are AND-ed."""

    model_config = ConfigDict(extra="forbid")

    attribute: str = Field(min_length=1, max_length=100)
    operator: Literal["equals", "not_equals", "in", "gt", "lt", "gte", "lte"]
    value: str | float | int | bool | list[str | float | int | bool]

    @model_validator(mode="after")
    def validate_value(self) -> "TargetingRule":
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError(translate("errors.schemas.targeting_in_requires_list"))
        if self.operator in {"gt", "lt", "gte", "lte"} and isinstance(self.value, (list, bool)):
            raise ValueError(translate("errors.schemas.targeting_numeric_requires_number"))
        return self


def _validate_cluster_params(avg_cluster_size: float | None, icc: float | None) -> None:
    """Range-validate the cluster design-effect inputs (P5.2) with i18n error keys.

    ``avg_cluster_size`` (m) must be >= 1 — m = 1 is allowed (the Kish design effect degenerates to 1)
    but a fractional-below-1 cluster is nonsense. ``icc`` must be in [0, 1]. Both are optional and are
    consumed only when ``randomization_unit == "cluster"`` (see stats/cluster.py); validated whenever
    supplied so a cluster design left over from the 5.1 warning-only flow (no params) still validates.
    """
    if avg_cluster_size is not None and avg_cluster_size < 1:
        raise ValueError(translate("errors.schemas.cluster_size_min"))
    if icc is not None and not 0 <= icc <= 1:
        raise ValueError(translate("errors.schemas.icc_range"))


class ExperimentSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_type: str
    randomization_unit: str
    traffic_split: list[int] = Field(min_length=2)
    expected_daily_traffic: int = Field(gt=0)
    audience_share_in_test: float = Field(gt=0, le=1)
    variants_count: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    inclusion_criteria: str
    exclusion_criteria: str
    # Cluster-randomized sizing (P5.2): the average cluster size (m) and intraclass correlation (ICC)
    # that drive the Kish design effect DEFF = 1 + (m - 1)*ICC. Consumed only when
    # randomization_unit == "cluster" (inflates the per-arm sample size); ignored otherwise.
    avg_cluster_size: float | None = None
    icc: float | None = None
    # Optional mutual-exclusion namespace (execution layer); planning flow ignores it.
    namespace: NamespaceConfig | None = None
    # Optional attribute-based targeting rules (AND); planning flow ignores them.
    targeting_rules: list[TargetingRule] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_variants(self) -> "ExperimentSetup":
        if len(self.traffic_split) != self.variants_count:
            raise ValueError(translate("errors.schemas.traffic_split_length"))
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError(translate("errors.schemas.traffic_split_positive"))
        return self

    @model_validator(mode="after")
    def validate_cluster_params(self) -> "ExperimentSetup":
        _validate_cluster_params(self.avg_cluster_size, self.icc)
        return self


class GuardrailMetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    metric_type: Literal["binary", "continuous"]
    baseline_rate: float | None = Field(default=None, gt=0, lt=100)
    baseline_mean: float | None = None
    std_dev: float | None = Field(default=None, gt=0)
    # Harm direction for the live breach test: an increase is bad for latency / error rates, a
    # decrease is bad for revenue / retention. Defaults to increase_is_bad (the classic latency /
    # error guardrail) so existing designs that predate this field keep validating unchanged.
    direction: Literal["increase_is_bad", "decrease_is_bad"] = "increase_is_bad"
    # Largest tolerated degradation as a percent of this guardrail's baseline (non-inferiority
    # margin). None / 0 means any statistically significant degradation is a breach.
    non_inferiority_margin_pct: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "GuardrailMetricInput":
        if self.metric_type == "binary" and self.baseline_rate is None:
            raise ValueError(translate("errors.schemas.binary_guardrail_requires_baseline_rate"))
        if self.metric_type == "continuous" and (self.baseline_mean is None or self.std_dev is None):
            raise ValueError(translate("errors.schemas.continuous_guardrail_requires_mean_and_std"))
        return self


# Which planned analysis methods can size which metric type. "z_test" is the historical
# normal-approximation plan; the alternatives were added by the P2.1 sizing-parity increment
# (fisher_exact = exact small-n binary power, mann_whitney = rank-test ARE inflation,
# tost = two-one-sided-tests equivalence power). Shared by MetricsConfig and CalculationRequest.
PLANNED_TESTS_BY_METRIC_TYPE: dict[str, set[str]] = {
    "binary": {"z_test", "fisher_exact"},
    "continuous": {"z_test", "mann_whitney", "tost"},
    "ratio": {"z_test"},
}


class MetricsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric_name: str
    metric_type: MetricType
    baseline_value: float
    expected_uplift_pct: float | None = None
    mde_pct: float = Field(gt=0)
    # Count / rate metrics: how much exposure one user contributes over the experiment (sessions,
    # device-days, ...). 1.0 (the default when omitted) means the user itself is the exposure unit.
    # Consumed only when metric_type == "count"; ignored otherwise.
    exposure_per_user: float | None = Field(default=None, gt=0)
    # Planned analysis method for sample sizing (see CalculationRequest.planned_test); None keeps
    # the historical normal-approximation plan. equivalence_margin_pct is required for "tost".
    planned_test: Literal["z_test", "fisher_exact", "mann_whitney", "tost"] | None = None
    equivalence_margin_pct: float | None = Field(default=None, gt=0)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    std_dev: float | None = None
    cuped_pre_experiment_std: float | None = Field(default=None, gt=0)
    cuped_correlation: float | None = Field(default=None, gt=-1.0, lt=1.0)
    # Ratio metrics (R = sum(numerator)/sum(denominator), e.g. clicks/impressions) are carried as
    # two ingested conversion metrics. Both names are required when metric_type == "ratio" and
    # ignored otherwise; the live executor rolls them up per user via get_ratio_aggregates.
    numerator_metric_name: str | None = Field(default=None, max_length=100)
    denominator_metric_name: str | None = Field(default=None, max_length=100)
    secondary_metrics: list[str] = Field(default_factory=list)
    guardrail_metrics: list[GuardrailMetricInput] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "MetricsConfig":
        if self.metric_type == "binary" and not 0 < self.baseline_value < 1:
            raise ValueError(translate("errors.schemas.binary_baseline_range"))
        if self.metric_type == "continuous":
            if self.baseline_value <= 0:
                raise ValueError(translate("errors.schemas.continuous_baseline_positive"))
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError(translate("errors.schemas.continuous_std_positive"))
        if self.metric_type == "ratio":
            if not self.numerator_metric_name or not self.denominator_metric_name:
                raise ValueError(
                    "ratio metric_type requires numerator_metric_name and denominator_metric_name"
                )
            if self.numerator_metric_name == self.denominator_metric_name:
                raise ValueError(
                    "numerator_metric_name and denominator_metric_name must be different"
                )
        if self.metric_type == "count" and self.baseline_value <= 0:
            raise ValueError(translate("errors.schemas.count_baseline_positive"))
        return self

    @model_validator(mode="after")
    def validate_planned_test(self) -> "MetricsConfig":
        if self.planned_test is not None and self.planned_test not in PLANNED_TESTS_BY_METRIC_TYPE.get(
            self.metric_type, set()
        ):
            raise ValueError(translate("errors.schemas.planned_test_metric_mismatch"))
        if self.planned_test == "tost" and self.equivalence_margin_pct is None:
            raise ValueError(translate("errors.schemas.tost_margin_required"))
        return self


class ConstraintsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seasonality_present: bool
    active_campaigns_present: bool
    returning_users_present: bool
    interference_risk: str
    technical_constraints: str
    legal_or_ethics_constraints: str
    known_risks: str
    deadline_pressure: str
    long_test_possible: bool
    n_looks: int = Field(default=1, ge=1, le=100)
    analysis_mode: Literal["frequentist", "bayesian"] = "frequentist"
    desired_precision: float | None = Field(default=None, gt=0)
    credibility: float = Field(default=0.95, gt=0.5, lt=1.0)
    holdout_fraction: float | None = Field(default=None, ge=0, lt=1)
    mutually_exclusive_experiments: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_analysis_mode(self) -> "ConstraintsConfig":
        if self.analysis_mode == "bayesian" and self.desired_precision is None:
            raise ValueError(translate("errors.schemas.bayesian_requires_precision"))
        return self

class SavedObservedResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: ResultsRequest
    analysis: ResultsResponse
    saved_at: str | None = None


class AdditionalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_context: str = ""
    observed_results: SavedObservedResults | None = None


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectContext
    hypothesis: HypothesisContext
    setup: ExperimentSetup
    metrics: MetricsConfig
    constraints: ConstraintsConfig
    additional_context: AdditionalContext = Field(default_factory=AdditionalContext)
