"""Ingestion events and the live-stats read model."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.backend.app.constants import (
    MAX_SUPPORTED_VARIANTS,
)
from app.backend.app.schemas.api._results import ResultsResponse

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
