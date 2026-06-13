from fastapi import APIRouter, Depends, HTTPException

from app.backend.app.schemas.api import (
    ConversionIngestRequest,
    ExposureIngestRequest,
    IngestionSummaryResponse,
    IngestResultResponse,
    LiveStatsResponse,
)
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

    @router.get(
        "/api/v1/experiments/{experiment_id}/live-stats",
        response_model=LiveStatsResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_live_stats(experiment_id: str) -> LiveStatsResponse:
        """Phase D — live SRM / frequentist / Bayesian / sequential read over the current
        deduplicated exposures and conversions. Recomputed on demand (the dashboard polls);
        there is no separate scheduler process in the local-first MVP."""
        project = repository.get_project(experiment_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        metric_name = project["payload"].get("metrics", {}).get("primary_metric_name", "")
        aggregates = repository.get_experiment_analysis_aggregates(experiment_id, metric_name)
        if aggregates is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        result = build_live_stats(experiment_id, project["payload"], aggregates)
        return LiveStatsResponse.model_validate(result)

    return router
