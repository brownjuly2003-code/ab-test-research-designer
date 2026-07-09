"""Observed-results inputs and the analyzer responses built from them."""

from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.backend.app.constants import (
    MAX_CONTINGENCY_DIM,
    MAX_OBSERVED_SAMPLE_SIZE,
    MAX_OMNIBUS_GROUPS,
    MAX_SURVIVAL_ARMS,
)
from app.backend.app.i18n import translate


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
        "barnard_exact",
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
        if self.metric_type == "barnard_exact":
            # Barnard's unconditional exact test reuses the same 2x2 binary shape as Fisher / Boschloo —
            # same counts, a different (pooled Wald z) ordering of the extreme tables.
            if self.binary is None:
                raise ValueError(translate("errors.schemas.barnard_exact_requires_binary_data"))
            if self.continuous is not None or self.ranked is not None:
                raise ValueError(translate("errors.schemas.barnard_exact_rejects_other_data"))
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


class SurvivalArm(BaseModel):
    """One arm of a time-to-event experiment: parallel per-subject durations + censoring flags.

    ``durations[i]`` is subject ``i``'s observed follow-up time (non-negative, finite) and
    ``events_observed[i]`` is ``True`` when the event was observed at that time or ``False`` when the
    subject was right-censored (still event-free at last follow-up). The two arrays are paired by index,
    so they must have the same length — a mismatch is a 422 (malformed input), not a statistical
    degeneracy. Per-arm counts reuse ``MAX_OBSERVED_SAMPLE_SIZE``.
    """

    model_config = ConfigDict(extra="forbid")

    durations: list[float] = Field(min_length=1, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    events_observed: list[bool] = Field(min_length=1, max_length=MAX_OBSERVED_SAMPLE_SIZE)

    @model_validator(mode="after")
    def validate_arm(self) -> "SurvivalArm":
        if len(self.durations) != len(self.events_observed):
            raise ValueError(translate("errors.schemas.survival_length_mismatch"))
        if any(not isfinite(value) for value in self.durations):
            raise ValueError(translate("errors.schemas.survival_durations_finite"))
        if any(value < 0 for value in self.durations):
            raise ValueError(translate("errors.schemas.survival_durations_non_negative"))
        return self


class SurvivalResultsRequest(BaseModel):
    """Survival arms (control + treatment + optional extra arms) for the log-rank test family.

    Separate from ``ResultsRequest`` because the input is time-to-event — a duration plus a censoring
    flag per subject, not a scalar outcome — and the response carries per-arm survival curves rather
    than a single scalar effect, exactly as the omnibus and categorical analyzers have their own
    request / response shapes. ``additional_arms`` extends the comparison beyond two arms (the
    k-sample log-rank, χ² on k−1 df); ``test_type`` picks the unweighted log-rank (default, most
    powerful under proportional hazards), the Fleming–Harrington ``G(ρ, γ)`` weighted variant —
    whose exponents ``fh_rho`` / ``fh_gamma`` up-weight early / late differences respectively and
    are consumed only on that branch — or the Cox proportional-hazards fit of the treatment effect,
    which turns the comparison into an effect size (a hazard ratio with a Wald CI). Cox is a
    two-arm regression on the treatment indicator, so it rejects ``additional_arms`` at the schema.
    A fully censored comparison (no events in any arm) is a statistical degeneracy surfaced by the
    service as a 400, not a schema error.
    """

    model_config = ConfigDict(extra="forbid")

    control_arm: SurvivalArm
    treatment_arm: SurvivalArm
    additional_arms: list[SurvivalArm] = Field(
        default_factory=list, max_length=MAX_SURVIVAL_ARMS - 2
    )
    test_type: Literal["log_rank", "fleming_harrington", "cox"] = "log_rank"
    # Fleming-Harrington exponents (w(t) = S(t-)^rho * (1 - S(t-))^gamma). The (1, 0) default is the
    # classic early-difference G^rho test; bounded to keep the weights numerically tame.
    fh_rho: float = Field(default=1.0, ge=0.0, le=4.0)
    fh_gamma: float = Field(default=0.0, ge=0.0, le=4.0)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

    @model_validator(mode="after")
    def validate_cox_is_two_arm(self) -> "SurvivalResultsRequest":
        if self.test_type == "cox" and self.additional_arms:
            raise ValueError(translate("errors.schemas.survival_cox_two_arms_only"))
        return self


class SurvivalCurvePoint(BaseModel):
    """One step of a Kaplan–Meier product-limit survival curve, at a distinct event time.

    ``survival`` is S(t); ``at_risk`` the number of subjects with observed time ``>= time``; ``n_events``
    the events at that time; ``std_error`` the Greenwood standard error and ``ci_lower`` / ``ci_upper``
    the normal-approximation confidence bounds (clamped to ``[0, 1]``, collapsed to the point estimate
    where S(t) reaches 0 and Greenwood's variance is undefined).
    """

    time: float
    survival: float
    at_risk: int
    n_events: int
    std_error: float
    ci_lower: float
    ci_upper: float


class SurvivalArmSummary(BaseModel):
    """Per-arm readout of a k-sample survival comparison, in request arm order.

    ``observed`` / ``expected`` are the observed and risk-set-expected event counts (an arm with
    fewer events than expected is surviving longer); ``expected`` is always the unweighted risk-set
    expectation even for the Fleming–Harrington branch (the weights enter the statistic, not the
    descriptive counts).
    """

    n: int
    observed: int
    expected: float


class SurvivalResultsResponse(BaseModel):
    """Outcome of a survival comparison: a log-rank-family test plus the Kaplan–Meier curves.

    ``chi_square`` is the (possibly weighted) log-rank statistic on ``degrees_of_freedom = k − 1``
    — or, on the Cox branch, the Wald chi-square ``z²`` on 1 df; ``test_type`` echoes the analyzer
    branch, ``fh_rho`` / ``fh_gamma`` are populated only for ``fleming_harrington``, and the
    ``hazard_ratio*`` / ``log_hazard_ratio*`` effect-size fields only for ``cox`` (``HR < 1``:
    treatment lowers the event hazard). ``arm_summaries`` lists every arm in request order (control,
    treatment, then the additional arms); the flat ``observed_* / expected_* / n_*`` fields duplicate
    its first two entries for backward compatibility. ``control_curve`` / ``treatment_curve`` carry
    the first two Kaplan–Meier curves and ``additional_arm_curves`` the rest, in the same order.
    """

    chi_square: float
    degrees_of_freedom: int
    p_value: float
    is_significant: bool
    test_type: str = "log_rank"
    fh_rho: float | None = None
    fh_gamma: float | None = None
    hazard_ratio: float | None = None
    hazard_ratio_ci_lower: float | None = None
    hazard_ratio_ci_upper: float | None = None
    log_hazard_ratio: float | None = None
    log_hazard_ratio_se: float | None = None
    observed_control: int
    expected_control: float
    observed_treatment: int
    expected_treatment: float
    n_control: int
    n_treatment: int
    arm_summaries: list[SurvivalArmSummary] = Field(default_factory=list)
    control_curve: list[SurvivalCurvePoint]
    treatment_curve: list[SurvivalCurvePoint]
    additional_arm_curves: list[list[SurvivalCurvePoint]] = Field(default_factory=list)
    verdict: str
    interpretation: str


class RatioArm(BaseModel):
    """One arm of a ratio metric: parallel per-user numerator and denominator totals.

    ``numerators[i]`` / ``denominators[i]`` are user ``i``'s totals of the numerator and denominator
    events (e.g. clicks and impressions for a click-through ratio), paired by index — hence the two
    arrays must have the same length. The delta method needs the within-user covariance between the
    two, which is exactly why a ratio cannot be analyzed from marginal summaries alone and the arm
    carries raw pairs. At least 2 users are needed for a sample (co)variance.
    """

    model_config = ConfigDict(extra="forbid")

    numerators: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)
    denominators: list[float] = Field(min_length=2, max_length=MAX_OBSERVED_SAMPLE_SIZE)

    @model_validator(mode="after")
    def validate_arm(self) -> "RatioArm":
        if len(self.numerators) != len(self.denominators):
            raise ValueError(translate("errors.schemas.ratio_pairs_length_mismatch"))
        if any(not isfinite(value) for value in self.numerators) or any(
            not isfinite(value) for value in self.denominators
        ):
            raise ValueError(translate("errors.schemas.ratio_values_finite"))
        return self


class RatioResultsRequest(BaseModel):
    """Two ratio-metric arms (control + treatment) for the post-hoc delta-method z-test.

    Separate from ``ResultsRequest`` because a ratio metric ``R = sum(numerator) / sum(denominator)``
    cannot be reconstructed from the marginal summaries that request carries — the delta-method
    variance needs the per-user numerator/denominator covariance, so the input is raw per-user pairs
    per arm. The response reuses ``ResultsResponse`` (the outcome *is* a scalar effect with a
    confidence interval), assembled by the same ``build_ratio_results_response`` the live executor
    uses, so post-hoc and live ratio readouts agree by construction. A degenerate comparison (zero
    denominator mean or zero pooled variance) is a statistical degeneracy surfaced by the service as
    a 400, not a schema error.
    """

    model_config = ConfigDict(extra="forbid")

    control_arm: RatioArm
    treatment_arm: RatioArm
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)
