from fastapi import APIRouter, Depends, HTTPException

from app.backend.app.schemas.api import (
    ConversionIngestRequest,
    DecisionReadoutResponse,
    ExposureIngestRequest,
    IngestionSummaryResponse,
    IngestResultResponse,
    LiveStatsResponse,
    PrePeriodIngestRequest,
)
from app.backend.app.services.decision_service import synthesize_decision
from app.backend.app.services.live_stats_service import build_live_stats


def create_execution_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
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

    def _compute_live_stats(experiment_id: str) -> dict:
        """Shared live-stats build path for the live-stats and decision reads. Raises 404 when the
        experiment (or its aggregates) is missing."""
        project = repository.get_project(experiment_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        metric_name = project["payload"].get("metrics", {}).get("primary_metric_name", "")
        aggregates = repository.get_experiment_analysis_aggregates(experiment_id, metric_name)
        if aggregates is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        cuped_aggregates = repository.get_cuped_aggregates(experiment_id, metric_name)
        return build_live_stats(experiment_id, project["payload"], aggregates, cuped_aggregates)

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
