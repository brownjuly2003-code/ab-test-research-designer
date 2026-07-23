from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.backend.app.constants import ATTRIBUTION_HORIZON_DAYS
from app.backend.app.schemas.api import (
    ConversionIngestRequest,
    DecisionReadoutResponse,
    ExclusionIngestRequest,
    ExposureIngestRequest,
    HoldoutIngestRequest,
    IdentityIngestRequest,
    IngestionSummaryResponse,
    IngestResultResponse,
    LiveStatsResponse,
    PrePeriodIngestRequest,
    StratumIngestRequest,
)
from app.backend.app.services.decision_service import synthesize_decision
from app.backend.app.services.live_stats_service import build_live_stats

if TYPE_CHECKING:
    from app.backend.app.config import Settings
    from app.backend.app.http_utils import SlidingWindowRateLimiter
    from app.backend.app.repository import ProjectRepository


def create_execution_router(
    settings: "Settings",
    repository: "ProjectRepository",
    rate_limiter: "SlidingWindowRateLimiter",
    require_auth: Callable[[Request], None],
    require_write_auth: Callable[[Request], None],
) -> APIRouter:
    """Execution layer (Phase C) — raw exposure/conversion ingestion + a summary read.

    Ingestion writes require write auth; the summary read requires read auth. Dedup
    (first-exposure-wins exposures, idempotency-keyed conversions) lives in the repository.
    """
    router = APIRouter(tags=["execution"])

    @router.post(
        "/api/v1/experiments/{experiment_id}/exposures",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_exposures(experiment_id: str, payload: ExposureIngestRequest) -> IngestResultResponse:
        result = repository.record_exposures(
            experiment_id,
            [event.model_dump() for event in payload.exposures],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/conversions",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_conversions(experiment_id: str, payload: ConversionIngestRequest) -> IngestResultResponse:
        result = repository.record_conversions(
            experiment_id,
            [event.model_dump() for event in payload.conversions],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/pre-period",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_pre_period_values(
        experiment_id: str, payload: PrePeriodIngestRequest
    ) -> IngestResultResponse:
        """Ingest per-user pre-experiment covariate values for CUPED (E5). First-write-wins
        per user; the covariate enables variance reduction on the continuous live-stats."""
        result = repository.record_pre_period_values(
            experiment_id,
            [event.model_dump() for event in payload.pre_period_values],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/strata",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_strata(experiment_id: str, payload: StratumIngestRequest) -> IngestResultResponse:
        """Ingest one categorical stratum per user for post-stratification (F3b). First-write-wins
        per user; the stratum lets the live-stats read estimate the effect within each stratum and
        recombine it, reducing variance when the stratum explains outcome variation."""
        result = repository.record_strata(
            experiment_id,
            [event.model_dump() for event in payload.strata],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/holdout",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_holdout(experiment_id: str, payload: HoldoutIngestRequest) -> IngestResultResponse:
        """Ingest holdout members — users held back from the rollout (F5). Recorded as
        ``variation_index = -1`` exposures (first-write-wins per user); the live-stats read compares
        the pooled treated arms against this held-back group to measure the rollout's cumulative
        effect. Holdout outcomes ride the ordinary conversion stream under the primary metric name."""
        result = repository.record_holdout(
            experiment_id,
            [event.model_dump() for event in payload.holdout],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/identities",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_identities(experiment_id: str, payload: IdentityIngestRequest) -> IngestResultResponse:
        """Ingest anonymous → canonical identity links (P4.3). First-write-wins per anonymous id;
        the live-stats rollup folds each user's exposures and conversions onto their canonical id, so
        a person exposed while anonymous and re-exposed / converting after login is counted once
        instead of inflating SRM and the conversion rate. A self-link is a no-op and is skipped."""
        result = repository.record_identities(
            experiment_id,
            [event.model_dump() for event in payload.identities],
        )
        return IngestResultResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/exclusions",
        response_model=IngestResultResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def ingest_exclusions(experiment_id: str, payload: ExclusionIngestRequest) -> IngestResultResponse:
        """Ingest manual deny-list exclusions for the bot / fraud filter (P4.4). First-write-wins per
        user (the first reason sticks); the live-stats rollup drops excluded users — resolved to their
        canonical id — from every aggregate, alongside the automatic rate-spike heuristic. The raw
        events are never deleted, so an exclusion is a reversible read-time filter."""
        result = repository.record_exclusions(
            experiment_id,
            [event.model_dump() for event in payload.exclusions],
        )
        return IngestResultResponse.model_validate(result)

    @router.get(
        "/api/v1/experiments/{experiment_id}/ingestion",
        response_model=IngestionSummaryResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_ingestion_summary(experiment_id: str) -> IngestionSummaryResponse:
        summary = repository.get_ingestion_summary(experiment_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return IngestionSummaryResponse.model_validate(summary)

    def _compute_live_stats(experiment_id: str) -> dict[str, Any]:
        """Shared live-stats build path for the live-stats and decision reads. Raises 404 when the
        experiment (or its aggregates) is missing."""
        project = repository.get_project(experiment_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        metrics = project["payload"].get("metrics", {})
        metric_name = metrics.get("primary_metric_name", "")
        aggregates = repository.get_experiment_analysis_aggregates(experiment_id, metric_name)
        if aggregates is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        cuped_aggregates = repository.get_cuped_aggregates(experiment_id, metric_name)
        # Post-stratification (F3b): per-(stratum, variation) rollup over users that carry a stratum.
        stratified_aggregates = repository.get_stratified_aggregates(experiment_id, metric_name)
        # Ratio metrics (R = numerator/denominator) roll up two ingested conversion metrics per
        # user; the executor reads them only when the design's metric_type is "ratio".
        ratio_aggregates = None
        if metrics.get("metric_type") == "ratio":
            numerator = metrics.get("numerator_metric_name")
            denominator = metrics.get("denominator_metric_name")
            if numerator and denominator:
                ratio_aggregates = repository.get_ratio_aggregates(
                    experiment_id, numerator, denominator
                )
        # Guardrail metrics (F4): each declared guardrail's outcome rides the ordinary conversion
        # stream under its own metric name, so it rolls up through the same per-variation analysis
        # aggregates as the primary — one lookup per guardrail, keyed by name for the live block.
        guardrail_aggregates = {
            name: repository.get_experiment_analysis_aggregates(experiment_id, name)
            for metric in (metrics.get("guardrail_metrics") or [])
            if (name := metric.get("name"))
        }
        # Holdout groups (F5): the held-back (variation_index = -1) rollup feeds the cumulative
        # treated-vs-holdout read on the primary metric; the pooled treated arms come from the main
        # aggregates above, so this is a single extra lookup for the held-back tail.
        holdout_aggregates = repository.get_holdout_aggregates(experiment_id, metric_name)
        # Event-time diagnostics (P4.2): classify conversions on the primary metric as in-window /
        # late / out-of-order relative to each user's exposure, using the P4.1 occurred_at column.
        event_timing_summary = repository.get_event_timing_summary(
            experiment_id, metric_name, ATTRIBUTION_HORIZON_DAYS
        )
        # Identity resolution (P4.3): counts for the indicator. The resolution itself already happened
        # inside the primary rollup above (anonymous → canonical fold); this is just the informational
        # summary of how many links are active and how much they touched the data.
        identity_resolution_summary = repository.get_identity_resolution_summary(experiment_id)
        # Bot / fraud filter (P4.4): counts for the indicator. The exclusion (manual deny-list +
        # rate-spike) already happened inside the primary rollup above; this is the informational
        # summary of how many exposed users were filtered, split by reason.
        exclusion_summary = repository.get_exclusion_summary(experiment_id, metric_name)
        population_diagnostics = repository.get_analytical_population_diagnostics(
            experiment_id, metric_name
        )
        return build_live_stats(
            experiment_id,
            project["payload"],
            aggregates,
            cuped_aggregates,
            ratio_aggregates,
            stratified_aggregates,
            guardrail_aggregates,
            holdout_aggregates,
            event_timing_summary,
            identity_resolution_summary,
            exclusion_summary,
            population_diagnostics,
        )

    @router.get(
        "/api/v1/experiments/{experiment_id}/live-stats",
        response_model=LiveStatsResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_live_stats(experiment_id: str) -> LiveStatsResponse:
        """Phase D — live SRM / frequentist / Bayesian / sequential read over the current
        deduplicated exposures and conversions. Recomputed on demand (the dashboard polls);
        there is no separate scheduler process in the local-first MVP."""
        return LiveStatsResponse.model_validate(_compute_live_stats(experiment_id))

    @router.get(
        "/api/v1/experiments/{experiment_id}/decision",
        response_model=DecisionReadoutResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_decision(experiment_id: str) -> DecisionReadoutResponse:
        """Decision Readout — one synthesized ship / no-ship / keep-running verdict over the same
        live-stats signals (SRM, frequentist effect/CI, Bayesian P(B>A), sequential crossing). No
        new statistics; see services/decision_service.py."""
        decision = synthesize_decision(_compute_live_stats(experiment_id))
        return DecisionReadoutResponse.model_validate(decision)

    return router
