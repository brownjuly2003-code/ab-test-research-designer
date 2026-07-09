"""Sample-size / sensitivity / SRM / assignment planning payloads."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import (
    MAX_SUPPORTED_METRICS,
    MAX_SUPPORTED_VARIANTS,
)
from app.backend.app.i18n import translate
from app.backend.app.schemas.api._experiment import (
    PLANNED_TESTS_BY_METRIC_TYPE,
    _validate_cluster_params,
)


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal["binary", "continuous", "ratio", "count"]
    baseline_value: float
    std_dev: float | None = None
    # Count / rate exposure per user (see MetricsConfig.exposure_per_user); None → 1.0 at the service.
    exposure_per_user: float | None = Field(default=None, gt=0)
    cuped_pre_experiment_std: float | None = Field(default=None, gt=0)
    cuped_correlation: float | None = Field(default=None, gt=-1.0, lt=1.0)
    mde_pct: float = Field(gt=0)
    # Planned analysis method the sample size is computed for. None resolves to the historical
    # normal-approximation plan ("z_test"). "fisher_exact" pairs with binary metrics (exact power,
    # small n); "mann_whitney" and "tost" pair with continuous metrics (rank-test ARE inflation and
    # two-one-sided-tests equivalence power respectively) — see stats/{fisher_exact,mann_whitney,
    # equivalence}.py for the sizing math and sources.
    planned_test: Literal["z_test", "fisher_exact", "mann_whitney", "tost"] | None = None
    # Symmetric equivalence margin, relative to the baseline like mde_pct. Required for a TOST
    # plan (it is what drives the sample size there); ignored by every other planned test.
    equivalence_margin_pct: float | None = Field(default=None, gt=0)
    alpha: float = Field(gt=0, lt=1)
    power: float = Field(gt=0, lt=1)
    expected_daily_traffic: int = Field(gt=0)
    audience_share_in_test: float = Field(gt=0, le=1)
    traffic_split: list[int] = Field(min_length=2)
    variants_count: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    # Informational for the rules engine (warns when "cluster"); also the switch that turns on the
    # cluster design-effect sizing below (naive SEs assume independent units).
    randomization_unit: str | None = None
    # Cluster design-effect sizing (P5.2): average cluster size (m) and ICC feeding
    # DEFF = 1 + (m - 1)*ICC. Consumed only when randomization_unit == "cluster" (see
    # stats/cluster.py); range-validated whenever supplied, ignored for other units.
    avg_cluster_size: float | None = None
    icc: float | None = None
    actual_counts: list[int] | None = Field(default=None, min_length=2, max_length=MAX_SUPPORTED_VARIANTS)
    seasonality_present: bool | None = None
    active_campaigns_present: bool | None = None
    long_test_possible: bool | None = None
    n_looks: int = Field(default=1, ge=1, le=100)
    analysis_mode: Literal["frequentist", "bayesian"] = "frequentist"
    desired_precision: float | None = Field(default=None, gt=0)
    credibility: float = Field(default=0.95, gt=0.5, lt=1.0)
    holdout_fraction: float | None = Field(default=None, ge=0, lt=1)
    mutually_exclusive_experiments: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_variants(self) -> "CalculationRequest":
        if len(self.traffic_split) != self.variants_count:
            raise ValueError(translate("errors.schemas.traffic_split_length"))
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError(translate("errors.schemas.traffic_split_positive"))
        return self

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "CalculationRequest":
        if self.metric_type == "binary" and not 0 < self.baseline_value < 1:
            raise ValueError(translate("errors.schemas.binary_baseline_range"))
        if self.metric_type == "continuous":
            if self.baseline_value <= 0:
                raise ValueError(translate("errors.schemas.continuous_baseline_positive"))
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError(translate("errors.schemas.continuous_std_positive"))
        # Ratio sizing reuses the continuous (delta-method linearized) sample-size formula, so it
        # needs a positive baseline ratio R and a positive per-user linearized standard deviation.
        if self.metric_type == "ratio":
            if self.baseline_value <= 0:
                raise ValueError(translate("errors.schemas.ratio_baseline_positive"))
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError(translate("errors.schemas.ratio_std_positive"))
        # Count / rate: baseline_value is the baseline event rate per exposure unit (must be positive).
        if self.metric_type == "count" and self.baseline_value <= 0:
            raise ValueError(translate("errors.schemas.count_baseline_positive"))
        return self

    @model_validator(mode="after")
    def validate_planned_test(self) -> "CalculationRequest":
        if self.planned_test is not None and self.planned_test not in PLANNED_TESTS_BY_METRIC_TYPE.get(
            self.metric_type, set()
        ):
            raise ValueError(translate("errors.schemas.planned_test_metric_mismatch"))
        if self.planned_test == "tost" and self.equivalence_margin_pct is None:
            raise ValueError(translate("errors.schemas.tost_margin_required"))
        return self

    @model_validator(mode="after")
    def validate_actual_counts(self) -> "CalculationRequest":
        if self.actual_counts is None:
            return self
        if len(self.actual_counts) != self.variants_count:
            raise ValueError(translate("errors.schemas.actual_counts_length"))
        if any(count < 0 for count in self.actual_counts):
            raise ValueError(translate("errors.schemas.actual_counts_non_negative"))
        # A zero in one variant is an extreme SRM, not invalid input — let the
        # SRM rule flag it. Only an all-zero vector (no data) is rejected here.
        if sum(self.actual_counts) <= 0:
            raise ValueError(translate("errors.schemas.actual_counts_positive_sum"))
        return self

    @model_validator(mode="after")
    def validate_analysis_mode(self) -> "CalculationRequest":
        if self.analysis_mode == "bayesian" and self.desired_precision is None:
            raise ValueError(translate("errors.schemas.bayesian_requires_precision"))
        return self

    @model_validator(mode="after")
    def validate_cluster_params(self) -> "CalculationRequest":
        _validate_cluster_params(self.avg_cluster_size, self.icc)
        return self


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal["binary", "continuous", "ratio"]
    baseline_rate: float | None = None
    baseline_mean: float | None = None
    std_dev: float | None = None
    variants: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS, default=2)
    alpha: float = Field(gt=0, lt=1, default=0.05)
    daily_traffic: float = Field(gt=0, default=1000.0)
    audience_share: float = Field(gt=0, le=1, default=1.0)
    traffic_split: list[float] | None = None
    mde_values: list[float] = Field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0, 5.0], min_length=1)
    power_values: list[float] = Field(default_factory=lambda: [0.7, 0.8, 0.9, 0.95], min_length=1)

    @model_validator(mode="after")
    def validate_metric_specific_fields(self) -> "SensitivityRequest":
        if self.metric_type == "binary":
            if self.baseline_rate is None or not 0 < self.baseline_rate < 100:
                raise ValueError(translate("errors.schemas.baseline_rate_range"))
        if self.metric_type == "continuous":
            if self.baseline_mean is None or self.baseline_mean <= 0:
                raise ValueError(translate("errors.schemas.baseline_mean_positive"))
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError(translate("errors.schemas.continuous_std_positive"))
        # Ratio sensitivity reuses the delta-method-linearized continuous formula (same as
        # CalculationRequest/MetricsConfig sizing), so it needs the same two fields as continuous —
        # baseline_mean here carries the baseline ratio R, std_dev the per-user linearized std.
        if self.metric_type == "ratio":
            if self.baseline_mean is None or self.baseline_mean <= 0:
                raise ValueError(translate("errors.schemas.ratio_baseline_mean_positive"))
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError(translate("errors.schemas.ratio_std_positive"))
        if any(value <= 0 for value in self.mde_values):
            raise ValueError(translate("errors.schemas.mde_values_positive"))
        if any(value <= 0 or value >= 1 for value in self.power_values):
            raise ValueError(translate("errors.schemas.power_values_range"))
        return self

    @model_validator(mode="after")
    def validate_traffic_split(self) -> "SensitivityRequest":
        if self.traffic_split is None:
            self.traffic_split = [1.0] * self.variants
            return self
        if len(self.traffic_split) != self.variants:
            raise ValueError(translate("errors.schemas.traffic_split_variants"))
        if any(weight <= 0 for weight in self.traffic_split):
            raise ValueError(translate("errors.schemas.traffic_split_positive"))
        return self


class SensitivityCell(BaseModel):
    mde: float
    power: float
    sample_size_per_variant: int
    duration_days: float


class SensitivityResponse(BaseModel):
    cells: list[SensitivityCell]
    current_mde: float | None = None
    current_power: float | None = None


class SrmCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_counts: list[int] = Field(min_length=2, max_length=MAX_SUPPORTED_VARIANTS)
    expected_fractions: list[float] = Field(min_length=2, max_length=MAX_SUPPORTED_VARIANTS)

    @model_validator(mode="after")
    def validate_lengths_and_fractions(self) -> "SrmCheckRequest":
        if len(self.observed_counts) != len(self.expected_fractions):
            raise ValueError(translate("errors.schemas.observed_expected_same_length"))
        if any(count < 0 for count in self.observed_counts):
            raise ValueError(translate("errors.schemas.observed_counts_non_negative"))
        # A zero in one variant is an extreme SRM, not invalid input — chi_square_srm
        # handles it. Only an all-zero vector (no data) is rejected here.
        if sum(self.observed_counts) <= 0:
            raise ValueError(translate("errors.schemas.observed_counts_positive_sum"))
        if any(fraction < 0 for fraction in self.expected_fractions):
            raise ValueError(translate("errors.schemas.expected_fractions_non_negative"))
        total_fraction = sum(self.expected_fractions)
        if abs(total_fraction - 1.0) > 0.01:
            raise ValueError(
                translate("errors.schemas.expected_fractions_sum", {"total": f"{total_fraction:.4f}"})
            )
        return self


class SrmCheckResponse(BaseModel):
    chi_square: float
    p_value: float
    is_srm: bool
    verdict: str
    observed_counts: list[int]
    expected_counts: list[float]


class MetricPValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    p_value: float = Field(ge=0.0, le=1.0)


class MultipleTestingRequest(BaseModel):
    """A battery of per-metric p-values to correct for multiple testing.

    ``method`` selects the error rate controlled at ``level``: ``bh`` (Benjamini-Hochberg) bounds the
    false discovery rate, ``holm`` (Holm-Bonferroni) bounds the family-wise error rate.
    """

    model_config = ConfigDict(extra="forbid")

    metrics: list[MetricPValue] = Field(min_length=1, max_length=MAX_SUPPORTED_METRICS)
    level: float = Field(default=0.05, gt=0.0, lt=1.0)
    method: Literal["bh", "holm"] = "bh"


class MultipleTestingMetricResult(BaseModel):
    label: str
    p_value: float
    adjusted_p_value: float
    rejected: bool


class MultipleTestingResponse(BaseModel):
    method: Literal["bh", "holm"]
    level: float
    num_tests: int
    num_rejected: int
    threshold_rank: int
    critical_value: float
    results: list[MultipleTestingMetricResult]


class BanditSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm_rates: list[float] = Field(min_length=2, max_length=MAX_SUPPORTED_VARIANTS)
    horizon: int = Field(ge=10, le=5000)
    num_simulations: int = Field(default=400, ge=1, le=2000)
    seed: int | None = 42

    @model_validator(mode="after")
    def validate_arm_rates(self) -> "BanditSimulationRequest":
        if any(not 0 <= rate <= 1 for rate in self.arm_rates):
            raise ValueError(translate("errors.schemas.bandit_arm_rates_range"))
        return self


class BanditRegretPoint(BaseModel):
    step: int
    bandit_cumulative_regret: float
    uniform_cumulative_regret: float


class BanditSimulationResponse(BaseModel):
    arm_allocation: list[float]
    best_arm_index: int
    best_arm_allocation: float
    probability_best_arm: float
    final_bandit_regret: float
    final_uniform_regret: float
    regret_curve: list[BanditRegretPoint]
    num_simulations: int
    horizon: int


class AssignmentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: str = Field(min_length=1, max_length=200)
    num_variations: int = Field(ge=2, le=MAX_SUPPORTED_VARIANTS)
    coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    weights: list[float] | None = None
    sample_size: int = Field(default=1000, ge=1, le=100000)
    user_id_prefix: str = Field(default="user-", max_length=80)
    hash_version: Literal[1, 2] = 2


class AssignmentDistributionBucket(BaseModel):
    variation_index: int
    count: int
    fraction: float


class AssignmentPreviewSample(BaseModel):
    user_id: str
    variation_index: int


class AssignmentPreviewResponse(BaseModel):
    sample_size: int
    in_experiment_fraction: float
    distribution: list[AssignmentDistributionBucket]
    sample_assignments: list[AssignmentPreviewSample]


class ExperimentAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    # Evaluated against the experiment's targeting_rules (if any). When the experiment has
    # no targeting rules, attributes are ignored and only user_id drives the assignment.
    attributes: dict[str, Any] | None = None
    hash_version: Literal[1, 2] = 2


class GrowthBookAssignmentResult(BaseModel):
    """GrowthBook-compatible ``Result`` block (camelCase keys, by_alias on output) so an
    off-the-shelf MIT GrowthBook SDK can consume the assignment directly."""

    model_config = ConfigDict(populate_by_name=True)

    key: str
    variation_id: int = Field(alias="variationId")
    in_experiment: bool = Field(alias="inExperiment")
    hash_used: bool = Field(alias="hashUsed")
    hash_attribute: str = Field(alias="hashAttribute")
    hash_value: str = Field(alias="hashValue")
    bucket: float | None = None


class ExperimentAssignmentResponse(BaseModel):
    experiment_id: str
    user_id: str
    seed: str
    variation_index: int
    in_experiment: bool
    hash: float | None = None
    num_variations: int
    coverage: float
    weights: list[float]
    hash_version: int
    # True when the variation came from a previously recorded exposure (sticky bucketing)
    # rather than a fresh hash — so a user keeps their variation even if weights/coverage change.
    sticky: bool = False
    # True when the user is excluded because they fall outside this experiment's
    # mutual-exclusion namespace slot (distinct from a holdout/coverage tail).
    namespace_excluded: bool = False
    # True when the user is excluded because they fail the experiment's targeting rules.
    targeting_excluded: bool = False
    growthbook: GrowthBookAssignmentResult

class WarningResponse(BaseModel):
    code: str
    severity: str
    message: str
    source: str


class CalculationSummaryResponse(BaseModel):
    metric_type: str
    baseline_value: float
    mde_pct: float
    mde_absolute: float
    alpha: float
    power: float
    # Resolved planned analysis method the sample size was computed for ("z_test" when the request
    # did not name one). The margin echoes are populated only for a TOST equivalence plan.
    planned_test: str | None = None
    equivalence_margin_pct: float | None = None
    equivalence_margin_absolute: float | None = None


class CalculationResultsResponse(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    effective_daily_traffic: float
    estimated_duration_days: int
    holdout_fraction: float | None = None
    mutually_exclusive_experiments: int | None = None
    allocated_daily_traffic: float | None = None


class CalculationResponse(BaseModel):
    calculation_summary: CalculationSummaryResponse
    results: CalculationResultsResponse
    assumptions: list[str]
    warnings: list[WarningResponse]
    bonferroni_note: str | None = None
    # Cluster-randomized design effect (P5.2). Populated only when randomization_unit == "cluster" and
    # the average cluster size + ICC were supplied; otherwise null. design_effect = 1 + (m - 1)*ICC,
    # clusters_per_variant = ceil(individual n * design_effect / m).
    design_effect: float | None = None
    avg_cluster_size: float | None = None
    icc: float | None = None
    clusters_per_variant: int | None = None
    bayesian_sample_size_per_variant: int | None = None
    bayesian_credibility: float | None = None
    bayesian_note: str | None = None
    sequential_boundaries: list[dict[str, Any]] | None = None
    sequential_inflation_factor: float | None = None
    sequential_adjusted_sample_size: int | None = None
    cuped_std: float | None = None
    cuped_sample_size_per_variant: int | None = None
    cuped_variance_reduction_pct: float | None = None
    cuped_duration_days: float | None = None
    cuped_theta: float | None = None
