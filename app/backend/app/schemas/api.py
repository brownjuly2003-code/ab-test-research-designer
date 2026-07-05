from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import (
    MAX_CONTINGENCY_DIM,
    MAX_OBSERVED_SAMPLE_SIZE,
    MAX_OMNIBUS_GROUPS,
    MAX_SUPPORTED_METRICS,
    MAX_SUPPORTED_VARIANTS,
)
from app.backend.app.i18n import translate
from app.backend.app.schemas.report import ExperimentReport


class ErrorResponse(BaseModel):
    detail: Any
    error_code: str
    status_code: int
    request_id: str


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
    metric_type: Literal["binary", "continuous", "ratio", "count"]
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


class ObservedResultsBinary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_conversions: int = Field(ge=0)
    control_users: int = Field(ge=2)
    treatment_conversions: int = Field(ge=0)
    treatment_users: int = Field(ge=2)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def validate_counts(self) -> "ObservedResultsBinary":
        if self.control_conversions > self.control_users:
            raise ValueError(translate("errors.schemas.control_conversions_exceed_users"))
        if self.treatment_conversions > self.treatment_users:
            raise ValueError(translate("errors.schemas.treatment_conversions_exceed_users"))
        return self


class ObservedResultsContinuous(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_mean: float
    control_std: float = Field(gt=0)
    control_n: int = Field(ge=2)
    treatment_mean: float
    treatment_std: float = Field(gt=0)
    treatment_n: int = Field(ge=2)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
    # Equivalence margin in the natural units of the mean difference, consumed only by the TOST
    # equivalence analyzer (``metric_type="equivalence"``); the difference t-test ignores it. The
    # two arms are declared equivalent when the mean difference stays within ``±equivalence_margin``.
    equivalence_margin: float | None = Field(default=None, gt=0)


class ObservedResultsRanked(BaseModel):
    """Raw per-unit samples for the distribution-free analyzers (Mann–Whitney, bootstrap/permutation,
    quantile treatment effect, Yuen–Welch trimmed means).

    Unlike the binary / continuous observed-results models, which carry only summary statistics, these
    tests need the actual observations: they rank or resample the pooled sample. Each arm is capped at
    ``MAX_OBSERVED_SAMPLE_SIZE`` because the Hodges–Lehmann CI materializes all pairwise differences.
    ``quantile`` is consumed only by the quantile treatment-effect analyzer (which quantile to compare,
    median by default) and ``trim`` only by the Yuen–Welch trimmed-means analyzer (the fraction
    trimmed from each tail before the robust mean test); the other analyzers ignore them.
    """

    model_config = ConfigDict(extra="forbid")

    control_values: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    treatment_values: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
    quantile: float = Field(default=0.5, gt=0.0, lt=1.0)
    trim: float = Field(default=0.2, ge=0.0, lt=0.5)

    @model_validator(mode="after")
    def validate_values(self) -> "ObservedResultsRanked":
        if any(not isfinite(value) for value in self.control_values) or any(
            not isfinite(value) for value in self.treatment_values
        ):
            raise ValueError(translate("errors.schemas.ranked_values_finite"))
        return self


class ObservedResultsCount(BaseModel):
    """Event counts over exposure, for the Poisson rate test.

    A rate metric is a count of events accrued over an amount of exposure (time, sessions, users —
    any common denominator). The two arms may have different exposures; the test compares the rates
    ``events / exposure``, not the raw counts.
    """

    model_config = ConfigDict(extra="forbid")

    control_events: int = Field(ge=0)
    control_exposure: float = Field(gt=0)
    treatment_events: int = Field(ge=0)
    treatment_exposure: float = Field(gt=0)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)


class ResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_type: Literal[
        "binary",
        "continuous",
        "equivalence",
        "mann_whitney",
        "bootstrap",
        "quantile",
        "trimmed_t",
        "fisher_exact",
        "boschloo_exact",
        "count",
    ]
    binary: ObservedResultsBinary | None = None
    continuous: ObservedResultsContinuous | None = None
    ranked: ObservedResultsRanked | None = None
    count: ObservedResultsCount | None = None

    @model_validator(mode="after")
    def check_type(self) -> "ResultsRequest":
        if self.metric_type == "binary":
            if self.binary is None:
                raise ValueError(translate("errors.schemas.binary_requires_binary_data"))
            if self.continuous is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.binary_rejects_continuous_data"))
        if self.metric_type == "fisher_exact":
            # Fisher's exact reuses the 2x2 binary observed-results shape (counts per arm); it is an
            # exact alternative analysis of the same data, not a new input model.
            if self.binary is None:
                raise ValueError(translate("errors.schemas.fisher_exact_requires_binary_data"))
            if self.continuous is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.fisher_exact_rejects_other_data"))
        if self.metric_type == "boschloo_exact":
            # Boschloo's unconditional exact test also reuses the 2x2 binary shape — it is another exact
            # alternative analysis of the same counts (uniformly at least as powerful as Fisher's).
            if self.binary is None:
                raise ValueError(translate("errors.schemas.boschloo_exact_requires_binary_data"))
            if self.continuous is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.boschloo_exact_rejects_other_data"))
        if self.metric_type == "continuous":
            if self.continuous is None:
                raise ValueError(translate("errors.schemas.continuous_requires_continuous_data"))
            if self.binary is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.continuous_rejects_binary_data"))
        if self.metric_type == "equivalence":
            # TOST equivalence reuses the continuous summary-statistics shape; it is an alternative
            # analysis of the same data plus an equivalence margin that the difference test ignores.
            if self.continuous is None:
                raise ValueError(translate("errors.schemas.equivalence_requires_continuous_data"))
            if self.binary is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.equivalence_rejects_other_data"))
            if self.continuous.equivalence_margin is None:
                raise ValueError(translate("errors.schemas.equivalence_requires_margin"))
        if self.metric_type == "mann_whitney":
            if self.ranked is None:
                raise ValueError(translate("errors.schemas.mann_whitney_requires_ranked_data"))
            if self.binary is not None or self.continuous is not None:
                raise ValueError(translate("errors.schemas.mann_whitney_rejects_other_data"))
        if self.metric_type == "bootstrap":
            # Bootstrap / permutation reuses the raw per-unit samples (the same ranked input shape as
            # Mann–Whitney); it is an alternative distribution-free analysis of the same data.
            if self.ranked is None:
                raise ValueError(translate("errors.schemas.bootstrap_requires_ranked_data"))
            if self.binary is not None or self.continuous is not None:
                raise ValueError(translate("errors.schemas.bootstrap_rejects_other_data"))
        if self.metric_type == "quantile":
            # Quantile treatment effect reuses the raw per-unit samples (the same ranked input shape as
            # Mann–Whitney / bootstrap); the ranked.quantile field picks which quantile to compare.
            if self.ranked is None:
                raise ValueError(translate("errors.schemas.quantile_requires_ranked_data"))
            if self.binary is not None or self.continuous is not None:
                raise ValueError(translate("errors.schemas.quantile_rejects_other_data"))
        if self.metric_type == "trimmed_t":
            # Yuen–Welch trimmed-means t-test reuses the raw per-unit samples (the same ranked input
            # shape as Mann–Whitney / bootstrap); the ranked.trim field sets the tail fraction trimmed.
            if self.ranked is None:
                raise ValueError(translate("errors.schemas.trimmed_t_requires_ranked_data"))
            if self.binary is not None or self.continuous is not None:
                raise ValueError(translate("errors.schemas.trimmed_t_rejects_other_data"))
        if self.metric_type == "count":
            if self.count is None:
                raise ValueError(translate("errors.schemas.count_requires_count_data"))
            if self.binary is not None or self.continuous is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.count_rejects_other_data"))
        return self


class ResultsResponse(BaseModel):
    metric_type: str
    observed_effect: float
    observed_effect_relative: float
    control_rate: float | None = None
    treatment_rate: float | None = None
    ci_lower: float
    ci_upper: float
    ci_level: float
    p_value: float
    test_statistic: float
    is_significant: bool
    power_achieved: float
    verdict: str
    interpretation: str
    # Populated by the rank-sum analyzer: a distribution-level effect size (rank-biserial
    # correlation) and its i18n label. ``None`` for the mean-based binary / continuous / ratio paths.
    effect_size: float | None = None
    effect_size_label: str | None = None
    # Fisher's exact only: the mid-p conditional exact confidence interval for the odds ratio (the
    # ``effect_size``). ``effect_size_ci_upper`` is ``None`` when the interval is unbounded above (+∞);
    # both are ``None`` for every other analyzer and when no estimable interval exists.
    effect_size_ci_lower: float | None = None
    effect_size_ci_upper: float | None = None


class CategoricalResultsRequest(BaseModel):
    """An r×c contingency table for the chi-square test of independence.

    ``table`` is a list of rows (the groups, e.g. experiment arms), each a list of non-negative
    integer cell counts (the categorical outcome levels). The table is omnibus — it does not reduce to
    a single scalar effect with a confidence interval, so it has its own request/response shapes
    rather than reusing ``ResultsRequest`` / ``ResultsResponse``.
    """

    model_config = ConfigDict(extra="forbid")

    table: list[list[int]] = Field(min_length=2, max_length=MAX_CONTINGENCY_DIM)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
    # Which independence statistic to compute on the same r×c table: Pearson's chi-square (the default,
    # preserving every existing caller) or the G-test (likelihood-ratio chi-square). Both reference the
    # χ² distribution and share the response shape; only the statistic and its label differ.
    test_type: Literal["chi_square", "g_test"] = "chi_square"

    @model_validator(mode="after")
    def validate_table(self) -> "CategoricalResultsRequest":
        num_cols = len(self.table[0])
        if num_cols < 2:
            raise ValueError(translate("errors.schemas.categorical_min_columns"))
        if num_cols > MAX_CONTINGENCY_DIM:
            raise ValueError(translate("errors.schemas.categorical_max_columns"))
        if any(len(row) != num_cols for row in self.table):
            raise ValueError(translate("errors.schemas.categorical_rectangular"))
        if any(count < 0 for row in self.table for count in row):
            raise ValueError(translate("errors.schemas.categorical_non_negative"))
        return self


class CategoricalResultsResponse(BaseModel):
    """Outcome of an r×c test of independence — an omnibus statistic, not a scalar effect.

    Shared by Pearson's chi-square and the G-test (likelihood-ratio chi-square); ``test_type`` says
    which one produced ``chi_square`` (the test statistic, Pearson χ² or G², both referred to the χ²
    distribution) so the UI can label it correctly.
    """

    test_type: str
    chi_square: float
    degrees_of_freedom: int
    p_value: float
    is_significant: bool
    cramers_v: float
    n_total: int
    num_rows: int
    num_cols: int
    min_expected_count: float
    low_expected_warning: bool
    verdict: str
    interpretation: str


class PairedResultsRequest(BaseModel):
    """Two equal-length arrays of paired (within-subject) observations for the paired-test family.

    ``control_values`` and ``treatment_values`` are two measurements of the *same units* (before/after,
    control/treatment on the same user), paired by index — hence they must be the same length. One
    input form feeds three analyzers via ``test_type``: the paired t-test and the Wilcoxon signed-rank
    test consume the per-pair differences of arbitrary real values, while McNemar's test needs paired
    **binary** data, so every value must be 0 or 1 there. Separate from ``ResultsRequest`` (which holds
    independent-arm summaries / samples) because the observations are paired and the outcome shape
    differs per test.
    """

    model_config = ConfigDict(extra="forbid")

    test_type: Literal["paired_t", "wilcoxon", "mcnemar"]
    control_values: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    treatment_values: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def validate_pairs(self) -> "PairedResultsRequest":
        if len(self.control_values) != len(self.treatment_values):
            raise ValueError(translate("errors.schemas.paired_length_mismatch"))
        if any(not isfinite(value) for value in self.control_values) or any(
            not isfinite(value) for value in self.treatment_values
        ):
            raise ValueError(translate("errors.schemas.paired_values_finite"))
        if self.test_type == "mcnemar":
            if any(value not in (0.0, 1.0) for value in self.control_values) or any(
                value not in (0.0, 1.0) for value in self.treatment_values
            ):
                raise ValueError(translate("errors.schemas.paired_mcnemar_binary"))
        return self


class PairedResultsResponse(BaseModel):
    """Outcome of a paired-family test: a scalar effect on the paired difference plus a CI.

    ``effect`` is the mean difference (paired t), the Hodges–Lehmann pseudomedian (Wilcoxon) or the
    marginal proportion difference (McNemar); ``effect_size`` / ``effect_size_label`` carry Cohen's
    d_z, the rank-biserial correlation or the discordance odds ratio respectively (odds ratio is
    ``None`` when no ``1 → 0`` pairs exist). ``n_zero_differences`` is populated only for Wilcoxon,
    the discordant counts only for McNemar; ``method`` records the McNemar branch (exact vs
    chi-square). The mean-based paths leave the paired-specific fields ``None``.
    """

    test_type: str
    n_pairs: int
    effect: float
    effect_label: str
    ci_lower: float
    ci_upper: float
    ci_level: float
    p_value: float
    test_statistic: float
    is_significant: bool
    effect_size: float | None = None
    effect_size_label: str | None = None
    method: str | None = None
    n_zero_differences: int | None = None
    n_discordant: int | None = None
    discordant_positive: int | None = None
    discordant_negative: int | None = None
    verdict: str
    interpretation: str


class OmnibusResultsRequest(BaseModel):
    """Per-group value arrays for an omnibus comparison across more than two groups.

    ``groups`` is a list of arms (e.g. an A/B/C/… experiment), each a list of the metric's raw per-unit
    values. One input form feeds two analyzers via ``test_type``: Welch's heteroscedastic one-way ANOVA
    (parametric, on the group means) and the Kruskal–Wallis H test (distribution-free, on ranks). Both
    need at least two groups with at least two observations each. Separate from ``ResultsRequest``
    (which holds two-arm summaries / samples) because the outcome is omnibus — a single statistic over
    all groups, not a scalar effect with a confidence interval — so it has its own request / response
    shapes, exactly as the categorical (chi-square) analyzer does.
    """

    model_config = ConfigDict(extra="forbid")

    test_type: Literal["welch_anova", "kruskal_wallis"]
    groups: list[list[float]] = Field(min_length=2, max_length=MAX_OMNIBUS_GROUPS)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def validate_groups(self) -> "OmnibusResultsRequest":
        if any(len(group) < 2 for group in self.groups):
            raise ValueError(translate("errors.schemas.omnibus_min_group_size"))
        if any(len(group) > MAX_OBSERVED_SAMPLE_SIZE for group in self.groups):
            raise ValueError(translate("errors.schemas.omnibus_group_too_large"))
        if any(not isfinite(value) for group in self.groups for value in group):
            raise ValueError(translate("errors.schemas.omnibus_values_finite"))
        return self


class OmnibusGroupSummary(BaseModel):
    """Per-group descriptive summary so the omnibus verdict is actionable (which arm differs).

    ``mean`` / ``std`` are populated by Welch's ANOVA (the mean-based path); ``median`` / ``mean_rank``
    by Kruskal–Wallis (the rank-based path). The fields for the other path are left ``None``.
    """

    n: int
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    mean_rank: float | None = None


class OmnibusResultsResponse(BaseModel):
    """Outcome of an omnibus test across more than two groups — a single statistic, not a scalar effect.

    ``test_statistic`` is Welch's F or the Kruskal–Wallis H; ``df_numerator`` is ``k − 1`` for both,
    while ``df_denominator`` carries Welch's fractional denominator df and is ``None`` for the
    chi-square-referred Kruskal–Wallis. ``effect_size`` / ``effect_size_label`` carry η² (Welch) or ε²
    (Kruskal–Wallis). ``group_summaries`` lists the per-arm descriptives.
    """

    test_type: str
    test_statistic: float
    df_numerator: float
    df_denominator: float | None = None
    p_value: float
    is_significant: bool
    effect_size: float
    effect_size_label: str
    num_groups: int
    n_total: int
    group_summaries: list[OmnibusGroupSummary]
    verdict: str
    interpretation: str


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
    # Informational only (see execution/experiment_assignment.py); carried here purely so the
    # deterministic rules engine can warn when it is "cluster" (naive SEs assume independent units).
    randomization_unit: str | None = None
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


MAX_INGEST_BATCH = 1000


class ExposureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    # Only real exposures are recorded — a -1 ("not in experiment") assignment is never an
    # exposure, so the floor is 0.
    variation_index: int = Field(ge=0, le=MAX_SUPPORTED_VARIANTS - 1)
    # Client event time — when the exposure happened (P4.1). Optional; defaults to the server-receive
    # time when omitted. Stored distinctly from created_at; late/out-of-order attribution is P4.2.
    occurred_at: datetime | None = None


class ExposureIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exposures: list[ExposureEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class ConversionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=100)
    value: float = 1.0
    # When supplied, retries with the same key are deduped per experiment (idempotent ingest).
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    # Client event time — when the conversion happened (P4.1). Optional; defaults to the
    # server-receive time when omitted. Foundation for late-conversion attribution (P4.2).
    occurred_at: datetime | None = None


class ConversionIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversions: list[ConversionEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class PrePeriodEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    # Pre-experiment covariate X for CUPED (e.g. the user's pre-period spend / activity).
    value: float
    # Which covariate this value belongs to (multi-covariate CUPED, F3a). Single-covariate
    # ingestion omits it and lands under the reserved "__default__" name, so the one-covariate
    # path is unchanged.
    covariate_name: str = Field(default="__default__", min_length=1, max_length=100)


class PrePeriodIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_period_values: list[PrePeriodEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class StratumEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=200)
    # The user's categorical stratum, an attribute known at assignment time (e.g. "ios"/"android",
    # "US"/"EU", "new"/"returning"). Post-stratification (F3b) estimates the effect within each
    # stratum and recombines the per-stratum effects weighted by stratum size.
    stratum: str = Field(min_length=1, max_length=100)


class StratumIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strata: list[StratumEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class HoldoutEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A user held back from the rollout (recorded as a variation_index = -1 exposure). The holdout
    # is the long-lived "got nothing" group; the live read compares the pooled treated arms against
    # it to measure the cumulative effect of everything the experiment rolled out (F5).
    user_id: str = Field(min_length=1, max_length=200)


class HoldoutIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holdout: list[HoldoutEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class IdentityLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Links an anonymous_id (the id a user had before logging in) to their canonical (logged-in) id,
    # so events recorded under either are folded onto one person in the rollup — preventing a double
    # count when an anonymous user is re-exposed or converts after login (P4.3). First-write-wins per
    # anonymous_id; a self-link (anonymous_id == canonical_id) is a no-op and ignored.
    anonymous_id: str = Field(min_length=1, max_length=200)
    canonical_id: str = Field(min_length=1, max_length=200)


class IdentityIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identities: list[IdentityLink] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class ExclusionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A user to drop from every aggregate — a manual deny-list entry for the bot / fraud filter (P4.4).
    # The reason is free text (e.g. "internal_qa", "fraud_ring", "known_bot") and is kept for audit;
    # the user's raw events are never deleted, so the exclusion is a reversible read-time filter.
    user_id: str = Field(min_length=1, max_length=200)
    exclusion_reason: str = Field(default="manual", min_length=1, max_length=200)


class ExclusionIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exclusions: list[ExclusionEvent] = Field(min_length=1, max_length=MAX_INGEST_BATCH)


class IngestResultResponse(BaseModel):
    received: int
    recorded: int
    deduplicated: int


class ExposureCountBucket(BaseModel):
    variation_index: int
    count: int


class ConversionCountBucket(BaseModel):
    metric: str
    count: int
    value_sum: float


class IngestionSummaryResponse(BaseModel):
    experiment_id: str
    exposures_total: int
    exposure_counts: list[ExposureCountBucket]
    conversions_total: int
    conversion_counts: list[ConversionCountBucket]


# --- Phase D: live experiment statistics over ingested exposures/conversions ----------


class LiveSrmBlock(BaseModel):
    # status: "ok" (balanced) | "srm_detected" | "insufficient_data" (no/one arm with data)
    status: str
    chi_square: float | None = None
    p_value: float | None = None
    is_srm: bool = False
    observed_counts: list[int] = Field(default_factory=list)
    expected_counts: list[float] = Field(default_factory=list)
    verdict: str


class LiveArmStat(BaseModel):
    variation_index: int
    exposed_users: int
    converted_users: int
    conversion_rate: float | None = None  # binary metrics
    mean: float | None = None  # continuous metrics
    std: float | None = None  # continuous metrics
    ratio: float | None = None  # ratio metrics (R̂ = sum numerator / sum denominator)


class LiveAlwaysValidBlock(BaseModel):
    # Anytime-valid (mSPRT) readout: the p-value and confidence sequence stay valid under
    # continuous monitoring (peek at any time, stop whenever), unlike the fixed-horizon test.
    # status: "ok" | "not_evaluable" (degenerate variance in an arm)
    status: str
    always_valid_p_value: float | None = None
    confidence_level: float | None = None  # 1 - alpha used for the sequence (FWER-adjusted)
    ci_sequence_lower: float | None = None  # confidence-sequence bounds on the effect
    ci_sequence_upper: float | None = None
    is_significant: bool | None = None  # sequence excludes 0 == always-valid p < alpha
    mixture_variance: float | None = None  # tau^2 mixing variance (from the design MDE)
    note: str | None = None


class LiveComparison(BaseModel):
    # status: "ok" | "insufficient_data" (an arm has <2 exposed users or a degenerate stat)
    treatment_index: int
    status: str
    control: LiveArmStat
    treatment: LiveArmStat
    analysis: ResultsResponse | None = None  # reuses the frequentist /results response shape
    probability_treatment_beats_control: float | None = None  # Bayesian P(B>A), binary only
    sequential_significant: bool | None = None  # |z| crosses the current O'Brien-Fleming boundary
    always_valid: LiveAlwaysValidBlock | None = None  # anytime-valid mSPRT view, null until "ok"
    note: str | None = None


class LiveSequentialBlock(BaseModel):
    # status: "fixed_horizon" (n_looks==1) | "active" | "insufficient_data"
    status: str
    n_looks: int
    # Planned size and information fraction are populated for both "active" (O'Brien-Fleming
    # boundary placement) and "fixed_horizon" (planned-read progress feeding the decision
    # readout's peeking guard); None when sizing is unavailable for the stored design.
    planned_sample_size_per_variant: int | None = None
    total_exposed: int = 0
    information_fraction: float | None = None
    current_boundary_z: float | None = None
    note: str


class LiveCupedCovariate(BaseModel):
    # One pre-period covariate and its fitted CUPED coefficient (the regression weight from the
    # pooled normal equations theta = Sigma_xx^-1 Sigma_xy).
    name: str
    theta: float


class LiveCupedArmStat(BaseModel):
    variation_index: int
    # Exposed users that also have the complete pre-period covariate vector (CUPED-eligible subset).
    covariate_users: int
    unadjusted_mean: float | None = None  # mean(Y) over the covered subset
    adjusted_mean: float | None = None  # mean(Y_adj) = mean(Y) - theta·(mean(X) - global mean(X))
    adjusted_std: float | None = None


class LiveCupedComparison(BaseModel):
    # status: "ok" | "insufficient_data" (an arm has <2 covariate users or degenerate variance)
    treatment_index: int
    status: str
    control: LiveCupedArmStat
    treatment: LiveCupedArmStat
    analysis: ResultsResponse | None = None  # CUPED-adjusted continuous t-test (reuses /results)
    note: str | None = None


class LiveCupedBlock(BaseModel):
    # status: "available" (pre-period covariate(s) ingested + continuous metric) |
    #         "unavailable" (no covariate ingested) |
    #         "too_many_covariates" (more distinct covariates than the supported cap) |
    #         "not_applicable" (binary metric — live CUPED routes through the continuous estimator)
    status: str
    note: str
    # Single-covariate convenience: the lone coefficient when exactly one covariate is used, else
    # null (the full coefficient vector is in `covariates`). Kept for backward compatibility.
    theta: float | None = None
    num_covariates: int | None = None
    covariates: list["LiveCupedCovariate"] = Field(default_factory=list)
    variance_reduction_pct: float | None = None  # pooled (1 - var_adjusted / var_unadjusted) * 100
    covariate_users_total: int | None = None
    exposed_users_total: int | None = None
    comparisons: list["LiveCupedComparison"] = Field(default_factory=list)


class LiveStratumEffect(BaseModel):
    # One stratum's within-stratum effect that feeds the size-weighted post-stratified combine.
    stratum: str
    users: int  # stratum size across both arms (the combine weight numerator n_s)
    control_users: int
    treatment_users: int
    effect: float | None = None  # within-stratum Δ_s (treatment − control); null if an arm is sparse


class LiveStratifiedComparison(BaseModel):
    # status: "ok" | "insufficient_data" (no stratum has both arms with >=2 users)
    treatment_index: int
    status: str
    effect: float | None = None  # post-stratified Δ = Σ (n_s/N)·Δ_s
    standard_error: float | None = None
    test_statistic: float | None = None
    p_value: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    ci_level: float | None = None  # 1 - alpha (FWER-adjusted), mirroring the other live blocks
    is_significant: bool | None = None
    variance_reduction_pct: float | None = None  # vs the naive pooled estimate; may be negative
    num_strata: int | None = None  # strata that contributed (both arms populated with >=2 users)
    strata: list["LiveStratumEffect"] = Field(default_factory=list)
    note: str | None = None


class LiveStratifiedBlock(BaseModel):
    # status: "available" (strata ingested + a usable comparison) |
    #         "unavailable" (no stratum ingested / no covered users) |
    #         "too_many_strata" (more distinct strata than the supported cap)
    status: str
    note: str
    num_strata: int | None = None
    stratified_users_total: int | None = None  # exposed users that carry a stratum
    exposed_users_total: int | None = None
    comparisons: list["LiveStratifiedComparison"] = Field(default_factory=list)


class LiveGuardrailArmStat(BaseModel):
    variation_index: int
    exposed_users: int
    point_estimate: float | None = None  # guardrail rate (binary) or mean (continuous) for the arm


class LiveGuardrailComparison(BaseModel):
    # status: "ok" (no harmful move) | "warning" (degrades past the margin but not significantly) |
    #         "breached" (significant degradation beyond the margin) |
    #         "insufficient_data" (an arm has <2 exposed users or degenerate variance)
    treatment_index: int
    status: str
    control: LiveGuardrailArmStat
    treatment: LiveGuardrailArmStat
    effect: float | None = None  # Δ = treatment − control in the metric's natural units
    harm: float | None = None  # signed degradation in the harmful direction (+ is worse)
    harm_lower_bound: float | None = None  # one-sided (1−α) lower confidence bound on the harm
    margin: float | None = None  # tolerated degradation in natural units (0 ⇒ any significant harm)
    p_value: float | None = None  # one-sided breach p-value (H1: harm > margin)
    is_breached: bool | None = None
    note: str | None = None


class LiveGuardrailMetricResult(BaseModel):
    # status = the worst comparison status across treatments (breached > warning > ok)
    name: str
    metric_type: str  # "binary" | "continuous"
    direction: str  # "increase_is_bad" | "decrease_is_bad"
    margin_pct: float | None = None  # non-inferiority margin as a percent of the design baseline
    status: str
    comparisons: list["LiveGuardrailComparison"] = Field(default_factory=list)


class LiveGuardrailBlock(BaseModel):
    # status: "ok" | "warning" | "breached" | "unavailable" (no guardrails declared, or no data yet)
    status: str
    note: str
    any_breached: bool = False
    metrics: list["LiveGuardrailMetricResult"] = Field(default_factory=list)


class LiveHoldoutArmStat(BaseModel):
    # One side of the cumulative comparison: the pooled treated arms or the held-back holdout group.
    label: str  # "treated" (union of variation_index >= 1) | "holdout" (variation_index = -1)
    exposed_users: int
    converted_users: int
    conversion_rate: float | None = None  # binary metrics
    mean: float | None = None  # continuous metrics
    std: float | None = None  # continuous metrics


class LiveHoldoutBlock(BaseModel):
    # Cumulative held-back readout (F5): pooled treated arms vs the long-lived holdout group on the
    # primary metric, measuring the standing effect of everything the experiment rolled out — apart
    # from the per-variant primary test. Reuses the primary path's frequentist + Bayesian + anytime-
    # valid views; no new statistic.
    # status: "ok" | "insufficient_data" (a side has <2 users / degenerate variance) |
    #         "unavailable" (no holdout users ingested, or a ratio metric)
    status: str
    note: str
    treated: LiveHoldoutArmStat | None = None
    holdout: LiveHoldoutArmStat | None = None
    analysis: ResultsResponse | None = None  # treated-vs-holdout effect (reuses the /results shape)
    probability_treated_beats_holdout: float | None = None  # Bayesian P(treated > holdout), binary only
    always_valid: LiveAlwaysValidBlock | None = None  # anytime-valid mSPRT view, null until "ok"
    treated_users_total: int | None = None
    holdout_users_total: int | None = None


class LiveEventTimingBlock(BaseModel):
    # Late / out-of-order conversion indicator (P4.2). Classifies each conversion on the primary
    # metric by its event time (occurred_at) relative to the converting user's exposure: in_window
    # (attributed), late (after the attribution horizon), out_of_order (before the exposure).
    # Informational data-quality signal only — never alters a comparison or the decision verdict.
    # status: "ok" | "unavailable" (no summary computed, e.g. no exposures yet).
    status: str
    metric: str | None = None
    horizon_days: float | None = None
    in_window: int | None = None
    late: int | None = None
    out_of_order: int | None = None
    total: int | None = None


class LiveIdentityResolutionBlock(BaseModel):
    # Identity-resolution indicator (P4.3). Surfaces how many anonymous → canonical links are active
    # and how much they touched the rollup, which folds each user's events onto their canonical id so
    # an anonymous-then-login user is counted once (no SRM inflation, no double conversion).
    # Informational only — the resolution already happened in the primary rollup; this block reports it.
    # status: "active" (links exist) | "inactive" (no links — block hidden by the frontend).
    status: str
    linked_identities: int | None = None
    canonicalized_events: int | None = None
    merged_users: int | None = None


class LiveExclusionBlock(BaseModel):
    # Bot / fraud filter indicator (P4.4). Reports how many exposed users the rollup removed, split by
    # reason: manual deny-list vs rate-spike (more than the conversion-event threshold). Informational
    # only — the exclusion already happened in the primary rollup; this block reports it so the filter
    # is never silent. status: "active" (something filtered) | "inactive" (nothing — block hidden).
    status: str
    total_filtered: int | None = None
    manual_filtered: int | None = None
    rate_spike_filtered: int | None = None


class LiveStatsResponse(BaseModel):
    experiment_id: str
    metric_type: str
    primary_metric_name: str
    exposures_total: int
    conversions_total: int
    disclaimer: str
    srm: LiveSrmBlock
    comparisons: list[LiveComparison]
    sequential: LiveSequentialBlock
    cuped: LiveCupedBlock
    stratified: LiveStratifiedBlock
    guardrail: LiveGuardrailBlock
    holdout: LiveHoldoutBlock
    event_timing: LiveEventTimingBlock
    identity_resolution: LiveIdentityResolutionBlock
    exclusions: LiveExclusionBlock


class DecisionReason(BaseModel):
    # A machine code (e.g. "significant_win", "srm_mismatch") rendered through the frontend
    # results.decision i18n namespace, plus numeric params for interpolation/formatting.
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class DecisionReadoutResponse(BaseModel):
    # Synthesized ship/no-ship verdict over the live-stats signals. No new statistics — see
    # services/decision_service.py. ``blockers`` are hard problems (e.g. SRM) that force no_ship.
    experiment_id: str
    verdict: Literal["ship", "no_ship", "keep_running"]
    confidence: Literal["high", "medium", "low"]
    reasons: list[DecisionReason] = Field(default_factory=list)
    blockers: list[DecisionReason] = Field(default_factory=list)


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


class AnalysisResponse(BaseModel):
    calculations: CalculationResponse
    report: ExperimentReport
    advice: LlmAdviceResponse


class AnalysisRunSummary(BaseModel):
    metric_type: str | None = None
    sample_size_per_variant: int | None = None
    total_sample_size: int | None = None
    estimated_duration_days: int | None = None
    warnings_count: int = 0
    advice_available: bool = False


class AnalysisRunRecord(BaseModel):
    id: str
    project_id: str
    created_at: str
    summary: AnalysisRunSummary
    analysis: AnalysisResponse


class ExportEventRecord(BaseModel):
    id: str
    project_id: str
    analysis_run_id: str | None = None
    format: Literal["markdown", "html", "pdf"]
    created_at: str


class ProjectRevisionRecord(BaseModel):
    id: str
    project_id: str
    source: Literal["create", "update", "workspace_import"]
    created_at: str
    payload: ExperimentInput


class ProjectHistoryResponse(BaseModel):
    project_id: str
    analysis_total: int
    analysis_limit: int
    analysis_offset: int
    export_total: int
    export_limit: int
    export_offset: int
    analysis_runs: list[AnalysisRunRecord]
    export_events: list[ExportEventRecord]


class ProjectRevisionHistoryResponse(BaseModel):
    project_id: str
    total: int
    limit: int
    offset: int
    revisions: list[ProjectRevisionRecord]


class ProjectComparisonItem(BaseModel):
    id: str
    project_name: str
    updated_at: str
    analysis_created_at: str
    last_analysis_at: str | None = None
    analysis_run_id: str
    metric_type: str
    primary_metric: str
    sample_size_per_variant: int
    total_sample_size: int
    estimated_duration_days: int
    warnings_count: int
    warning_codes: list[str]
    risk_highlights: list[str]
    assumptions: list[str]
    advice_available: bool
    executive_summary: str
    warning_severity: str
    recommendation_highlights: list[str]
    sensitivity: SensitivityResponse | None = None
    observed_results: ResultsResponse | None = None


class ProjectComparisonDelta(BaseModel):
    sample_size_per_variant: int
    total_sample_size: int
    estimated_duration_days: int
    warnings_count: int


class ProjectComparisonResponse(BaseModel):
    base_project: ProjectComparisonItem
    candidate_project: ProjectComparisonItem
    deltas: ProjectComparisonDelta
    shared_warning_codes: list[str]
    base_only_warning_codes: list[str]
    candidate_only_warning_codes: list[str]
    shared_assumptions: list[str]
    base_only_assumptions: list[str]
    candidate_only_assumptions: list[str]
    shared_risk_highlights: list[str]
    base_only_risk_highlights: list[str]
    candidate_only_risk_highlights: list[str]
    metric_alignment_note: str
    highlights: list[str]
    summary: str


class MultiProjectComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ids: list[str] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_project_ids(self) -> "MultiProjectComparisonRequest":
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for project_id in self.project_ids:
            cleaned = project_id.strip()
            if not cleaned:
                raise ValueError("project_ids must not contain empty values")
            if cleaned in seen:
                raise ValueError("project_ids must be unique")
            seen.add(cleaned)
            normalized_ids.append(cleaned)
        self.project_ids = normalized_ids
        return self


class ComparisonRangeSummary(BaseModel):
    min: int
    max: int
    median: float


class ProjectUniqueInsights(BaseModel):
    warnings: list[str]
    risks: list[str]
    assumptions: list[str]


class MonteCarloSimulationResponse(BaseModel):
    num_simulations: int
    percentiles: dict[str, float]
    probability_uplift_positive: float
    probability_uplift_above_threshold: dict[str, float]
    simulated_uplifts: list[float]


class MultiProjectComparisonResponse(BaseModel):
    projects: list[ProjectComparisonItem]
    shared_warnings: list[str]
    shared_risks: list[str]
    shared_assumptions: list[str]
    unique_per_project: dict[str, ProjectUniqueInsights]
    sample_size_range: ComparisonRangeSummary
    duration_range: ComparisonRangeSummary
    metric_types_used: list[str]
    recommendation_highlights: list[str]
    monte_carlo_distribution: dict[str, MonteCarloSimulationResponse] | None = None


class DiagnosticsStorageSummary(BaseModel):
    db_path: str
    db_parent_path: str
    db_exists: bool
    db_size_bytes: int
    disk_free_bytes: int
    schema_version: int
    sqlite_user_version: int
    busy_timeout_ms: int
    journal_mode: str
    synchronous: str
    write_probe_ok: bool
    write_probe_detail: str
    projects_total: int
    archived_projects_total: int
    analysis_runs_total: int
    export_events_total: int
    project_revisions_total: int
    workspace_bundle_schema_version: int
    workspace_signature_enabled: bool
    latest_project_updated_at: str | None = None


class DiagnosticsFrontendSummary(BaseModel):
    serve_frontend_dist: bool
    dist_path: str
    dist_exists: bool


class DiagnosticsLlmSummary(BaseModel):
    provider: str
    base_url: str
    timeout_seconds: float
    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float


class DiagnosticsLoggingSummary(BaseModel):
    level: str
    format: str


class DiagnosticsAuthSummary(BaseModel):
    enabled: bool
    mode: str
    write_enabled: bool
    readonly_enabled: bool
    legacy_tokens_enabled: bool = False
    api_keys_enabled: bool = False
    admin_token_enabled: bool = False
    public_demo: bool = False
    session_scope: Literal["read", "write", "admin"] | None = None
    session_source: Literal["legacy", "api_key", "admin_token", "anonymous"] | None = None
    session_can_write: bool = False
    session_admin_authenticated: bool = False
    accepted_headers: list[str]
    read_only_methods: list[str]


class DiagnosticsGuardsSummary(BaseModel):
    security_headers_enabled: bool
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    auth_failure_limit: int
    auth_failure_window_seconds: int
    max_request_body_bytes: int
    max_workspace_body_bytes: int


class DiagnosticsRuntimeSummary(BaseModel):
    total_requests: int
    success_responses: int
    client_error_responses: int
    server_error_responses: int
    auth_rejections: int
    rate_limited_responses: int = 0
    request_body_rejections: int = 0
    last_request_at: str | None = None
    last_error_at: str | None = None
    last_error_code: str | None = None


class DiagnosticsResponse(BaseModel):
    status: str
    generated_at: str
    started_at: str
    uptime_seconds: float
    environment: str
    app_version: str
    request_timing_headers_enabled: bool
    storage: DiagnosticsStorageSummary
    frontend: DiagnosticsFrontendSummary
    llm: DiagnosticsLlmSummary
    logging: DiagnosticsLoggingSummary
    auth: DiagnosticsAuthSummary
    guards: DiagnosticsGuardsSummary
    runtime: DiagnosticsRuntimeSummary


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    generated_at: str
    checks: list[ReadinessCheck]


class WorkspaceProjectRecord(BaseModel):
    id: str
    project_name: str
    payload_schema_version: int
    archived_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    created_at: str
    updated_at: str
    payload: ExperimentInput


class WorkspaceAnalysisRunRecord(BaseModel):
    id: str
    project_id: str
    created_at: str
    analysis: AnalysisResponse


class WorkspaceExportEventRecord(BaseModel):
    id: str
    project_id: str
    analysis_run_id: str | None = None
    format: Literal["markdown", "html", "pdf"]
    created_at: str


class WorkspaceProjectRevisionRecord(BaseModel):
    id: str
    project_id: str
    source: Literal["create", "update", "workspace_import"]
    created_at: str
    payload: ExperimentInput


class WorkspaceIntegrityCounts(BaseModel):
    projects: int
    analysis_runs: int
    export_events: int
    project_revisions: int


class WorkspaceIntegrity(BaseModel):
    counts: WorkspaceIntegrityCounts
    checksum_sha256: str
    signature_hmac_sha256: str | None = None


class WorkspaceValidationResponse(BaseModel):
    status: Literal["valid"]
    schema_version: int
    counts: WorkspaceIntegrityCounts
    checksum_sha256: str
    signature_verified: bool = False


class WorkspaceBundle(BaseModel):
    schema_version: int = 3
    generated_at: str
    projects: list[WorkspaceProjectRecord]
    analysis_runs: list[WorkspaceAnalysisRunRecord]
    export_events: list[WorkspaceExportEventRecord]
    project_revisions: list[WorkspaceProjectRevisionRecord] = Field(default_factory=list)
    integrity: WorkspaceIntegrity | None = None


class WorkspaceImportResponse(BaseModel):
    status: str
    imported_projects: int
    imported_analysis_runs: int
    imported_export_events: int
    imported_project_revisions: int = 0


class ProjectRecord(BaseModel):
    id: str
    project_name: str
    payload_schema_version: int
    archived_at: str | None = None
    is_archived: bool = False
    revision_count: int = 0
    last_revision_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    has_analysis_snapshot: bool = False
    created_at: str
    updated_at: str
    payload: ExperimentInput


class ProjectListItem(BaseModel):
    id: str
    project_name: str
    hypothesis: str | None = None
    metric_type: Literal["binary", "continuous", "ratio"] | None = None
    duration_days: int | None = None
    payload_schema_version: int
    archived_at: str | None = None
    is_archived: bool = False
    revision_count: int = 0
    last_revision_at: str | None = None
    last_analysis_at: str | None = None
    last_analysis_run_id: str | None = None
    last_exported_at: str | None = None
    has_analysis_snapshot: bool = False
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False


class ProjectArchiveResponse(BaseModel):
    id: str
    archived: bool
    archived_at: str | None = None


class ProjectDeleteResponse(BaseModel):
    id: str
    deleted: bool


class AuditLogEntry(BaseModel):
    id: int
    ts: str
    action: str
    project_id: str | None = None
    project_name: str | None = None
    key_id: str | None = None
    actor: str | None = None
    request_id: str | None = None
    payload_diff: dict[str, list[Any]] | None = None
    ip_address: str | None = None


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int = 0


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    scope: Literal["read", "write", "admin"]
    rate_limit_requests: int | None = Field(default=None, ge=1)
    rate_limit_window_seconds: int | None = Field(default=None, ge=1)


class ApiKeyRecord(BaseModel):
    id: str
    name: str
    scope: Literal["read", "write", "admin"]
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
    rate_limit_requests: int | None = None
    rate_limit_window_seconds: int | None = None


class ApiKeyCreateResponse(ApiKeyRecord):
    plaintext_key: str


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyRecord]
    total: int = 0


class ApiKeyDeleteResponse(BaseModel):
    id: str
    deleted: bool


class WebhookSubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    target_url: str = Field(min_length=1, max_length=2000)
    secret: str = Field(min_length=1, max_length=200)
    format: Literal["generic", "slack"]
    event_filter: list[str] = Field(default_factory=list)
    scope: Literal["global", "api_key"]
    api_key_id: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "WebhookSubscriptionCreateRequest":
        self.event_filter = [value.strip() for value in self.event_filter if value.strip()]
        if self.scope == "api_key" and not self.api_key_id:
            raise ValueError("api_key_id is required for api_key scope")
        if self.scope == "global" and self.api_key_id is not None:
            raise ValueError("api_key_id is not allowed for global scope")
        return self


class WebhookSubscriptionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    event_filter: list[str] | None = None
    target_url: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def normalize_event_filter(self) -> "WebhookSubscriptionUpdateRequest":
        if self.event_filter is not None:
            self.event_filter = [value.strip() for value in self.event_filter if value.strip()]
        return self


class WebhookSubscriptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    target_url: str
    secret: str | None = None
    format: Literal["generic", "slack"]
    event_filter: list[str] = Field(default_factory=list)
    scope: Literal["global", "api_key"]
    api_key_id: str | None = None
    created_at: str
    updated_at: str
    last_delivered_at: str | None = None
    last_error_at: str | None = None
    enabled: bool = True


class WebhookDeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    subscription_id: str
    event_id: int
    status: Literal["pending", "delivered", "failed", "retrying"]
    attempt_count: int
    last_attempt_at: str | None = None
    delivered_at: str | None = None
    response_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None


class WebhookListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriptions: list[WebhookSubscriptionRecord]
    total: int = 0


class WebhookDeliveryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deliveries: list[WebhookDeliveryRecord]
    total: int = 0


class WebhookTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: str
    status: Literal["delivered", "failed", "retrying", "pending"]
    response_code: int | None = None


class WebhookDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    deleted: bool


class ProjectExportMarkRequest(BaseModel):
    format: Literal["markdown", "html", "pdf"]
    analysis_run_id: str | None = None


class StandaloneExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    hypothesis: str | None = None
    calculation: dict[str, Any]
    design: dict[str, Any]
    ai_advice: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None
    results: dict[str, Any] | None = None


class ExportResponse(BaseModel):
    content: str


class ComparisonExportRequest(MultiProjectComparisonRequest):
    format: Literal["pdf", "markdown"]


__all__ = [
    "ApiKeyCreateRequest",
    "ApiKeyCreateResponse",
    "ApiKeyDeleteResponse",
    "ApiKeyListResponse",
    "ApiKeyRecord",
    "AuditLogEntry",
    "AuditLogResponse",
    "AnalysisResponse",
    "CalculationRequest",
    "CalculationResponse",
    "DiagnosticsResponse",
    "ErrorResponse",
    "ExperimentInput",
    "ExperimentReport",
    "ComparisonExportRequest",
    "ComparisonRangeSummary",
    "MonteCarloSimulationResponse",
    "ExportResponse",
    "GuardrailMetricInput",
    "MultiProjectComparisonRequest",
    "MultiProjectComparisonResponse",
    "ProjectArchiveResponse",
    "ProjectComparisonResponse",
    "ProjectHistoryResponse",
    "ProjectRevisionHistoryResponse",
    "ProjectUniqueInsights",
    "LlmAdviceRequest",
    "LlmAdviceResponse",
    "ProjectDeleteResponse",
    "ProjectExportMarkRequest",
    "ProjectListResponse",
    "ProjectRecord",
    "ReadinessResponse",
    "ResultsRequest",
    "ResultsResponse",
    "SensitivityCell",
    "SensitivityRequest",
    "SensitivityResponse",
    "SrmCheckRequest",
    "SrmCheckResponse",
    "StandaloneExportRequest",
    "WebhookDeleteResponse",
    "WebhookDeliveryListResponse",
    "WebhookDeliveryRecord",
    "WebhookListResponse",
    "WebhookSubscriptionCreateRequest",
    "WebhookSubscriptionRecord",
    "WebhookSubscriptionUpdateRequest",
    "WebhookTestResponse",
    "WorkspaceBundle",
    "WorkspaceImportResponse",
    "WorkspaceValidationResponse",
]
