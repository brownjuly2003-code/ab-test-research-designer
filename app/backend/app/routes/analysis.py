from fastapi import APIRouter, Depends, Request

from app.backend.app.errors import ApiError
from app.backend.app.i18n import translate
from app.backend.app.llm.adapter import LLMAuthError, LLMTransientError, LocalOrchestratorAdapter
from app.backend.app.llm.anthropic_adapter import AnthropicAdapter
from app.backend.app.llm.openai_adapter import OpenAIAdapter
from app.backend.app.schemas.api import (
    AnalysisResponse,
    CalculationRequest,
    CalculationResponse,
    ExperimentInput,
    ExperimentReport,
    LlmAdviceRequest,
    LlmAdviceResponse,
    ResultsRequest,
    ResultsResponse,
    SensitivityCell,
    SensitivityRequest,
    SensitivityResponse,
    SrmCheckRequest,
    SrmCheckResponse,
)
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.results_service import analyze_results
from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days
from app.backend.app.stats.srm import chi_square_srm


def _build_calculation_payload(payload: ExperimentInput) -> CalculationRequest:
    return CalculationRequest(
        metric_type=payload.metrics.metric_type,
        baseline_value=payload.metrics.baseline_value,
        std_dev=payload.metrics.std_dev,
        cuped_pre_experiment_std=payload.metrics.cuped_pre_experiment_std,
        cuped_correlation=payload.metrics.cuped_correlation,
        mde_pct=payload.metrics.mde_pct,
        alpha=payload.metrics.alpha,
        power=payload.metrics.power,
        expected_daily_traffic=payload.setup.expected_daily_traffic,
        audience_share_in_test=payload.setup.audience_share_in_test,
        traffic_split=payload.setup.traffic_split,
        variants_count=payload.setup.variants_count,
        seasonality_present=payload.constraints.seasonality_present,
        active_campaigns_present=payload.constraints.active_campaigns_present,
        long_test_possible=payload.constraints.long_test_possible,
        n_looks=payload.constraints.n_looks,
        analysis_mode=payload.constraints.analysis_mode,
        desired_precision=payload.constraints.desired_precision,
        credibility=payload.constraints.credibility,
    )


def _build_llm_advice_payload(payload: ExperimentInput, calculation_result: dict) -> dict:
    normalized_payload = payload.model_dump()
    return {
        "project_context": normalized_payload["project"],
        "hypothesis": normalized_payload["hypothesis"],
        "setup": normalized_payload["setup"],
        "metrics": normalized_payload["metrics"],
        "constraints": normalized_payload["constraints"],
        "additional_context": normalized_payload["additional_context"],
        "calculation_results": calculation_result["results"],
        "warnings": calculation_result.get("warnings", []),
    }


def pick_adapter(
    request: Request,
    *,
    local_adapter: LocalOrchestratorAdapter,
    openai_adapter: OpenAIAdapter,
    anthropic_adapter: AnthropicAdapter,
) -> tuple[LocalOrchestratorAdapter | OpenAIAdapter | AnthropicAdapter, str]:
    provider = request.headers.get("X-AB-LLM-Provider", "").strip().lower()
    token = request.headers.get("X-AB-LLM-Token", "").strip()
    if provider == "openai" and token:
        return openai_adapter, token
    if provider == "anthropic" and token:
        return anthropic_adapter, token
    return local_adapter, ""


def create_analysis_router(settings, repository, rate_limiter, require_auth, require_write_auth) -> APIRouter:
    router = APIRouter(tags=["calculations"])
    local_adapter = LocalOrchestratorAdapter(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )
    openai_adapter = OpenAIAdapter(
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )
    anthropic_adapter = AnthropicAdapter(
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )

    @router.post(
        "/api/v1/calculate",
        response_model=CalculationResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def calculate(payload: CalculationRequest) -> CalculationResponse:
        result = calculate_experiment_metrics(payload.model_dump())
        return CalculationResponse.model_validate(result)

    @router.post(
        "/api/v1/sensitivity",
        response_model=SensitivityResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def sensitivity(payload: SensitivityRequest) -> SensitivityResponse:
        cells: list[SensitivityCell] = []

        for mde in payload.mde_values:
            for power in payload.power_values:
                if payload.metric_type == "binary":
                    calculation = calculate_binary_sample_size(
                        baseline_rate=float(payload.baseline_rate) / 100,
                        mde_pct=mde,
                        alpha=payload.alpha,
                        power=power,
                        variants_count=payload.variants,
                    )
                else:
                    baseline_mean = float(payload.baseline_mean)
                    calculation = calculate_continuous_sample_size(
                        baseline_mean=baseline_mean,
                        std_dev=float(payload.std_dev),
                        mde_pct=(mde / baseline_mean) * 100,
                        alpha=payload.alpha,
                        power=power,
                        variants_count=payload.variants,
                    )

                duration = estimate_experiment_duration_days(
                    sample_size_per_variant=calculation["sample_size_per_variant"],
                    expected_daily_traffic=payload.daily_traffic,
                    audience_share_in_test=payload.audience_share,
                    traffic_split=payload.traffic_split or [],
                )
                cells.append(
                    SensitivityCell(
                        mde=mde,
                        power=power,
                        sample_size_per_variant=calculation["sample_size_per_variant"],
                        duration_days=float(duration["estimated_duration_days"]),
                    )
                )

        return SensitivityResponse(cells=cells)

    @router.post(
        "/api/v1/srm-check",
        response_model=SrmCheckResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def srm_check(payload: SrmCheckRequest) -> SrmCheckResponse:
        chi_square, p_value, is_srm = chi_square_srm(
            observed_counts=payload.observed_counts,
            expected_fractions=payload.expected_fractions,
        )
        total_observed = sum(payload.observed_counts)
        expected_counts = [fraction * total_observed for fraction in payload.expected_fractions]

        return SrmCheckResponse(
            chi_square=round(chi_square, 4),
            p_value=round(p_value, 6),
            is_srm=is_srm,
            verdict=(
                translate("errors.srm_detected")
                if is_srm
                else translate("errors.srm_not_detected")
            ),
            observed_counts=payload.observed_counts,
            expected_counts=[round(count, 1) for count in expected_counts],
        )

    @router.post(
        "/api/v1/results",
        response_model=ResultsResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def results(payload: ResultsRequest) -> ResultsResponse:
        return analyze_results(payload)

    @router.post(
        "/api/v1/design",
        response_model=ExperimentReport,
        dependencies=[Depends(require_write_auth)],
    )
    def design(payload: ExperimentInput) -> ExperimentReport:
        calculation_payload = _build_calculation_payload(payload)
        calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
        report = build_experiment_report(payload.model_dump(), calculation_result)
        return ExperimentReport.model_validate(report)

    @router.post(
        "/api/v1/analyze",
        response_model=AnalysisResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def analyze(request: Request, payload: ExperimentInput) -> AnalysisResponse:
        calculation_payload = _build_calculation_payload(payload)
        calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
        report = build_experiment_report(payload.model_dump(), calculation_result)
        adapter, token = pick_adapter(
            request,
            local_adapter=local_adapter,
            openai_adapter=openai_adapter,
            anthropic_adapter=anthropic_adapter,
        )
        advice_payload = _build_llm_advice_payload(payload, calculation_result)
        try:
            advice = adapter.request_advice(advice_payload, token=token) if token else adapter.request_advice(advice_payload)
        except LLMAuthError as exc:
            raise ApiError(str(exc), error_code="llm_auth", status_code=exc.status_code) from exc
        except LLMTransientError as exc:
            raise ApiError(str(exc), error_code="llm_transient", status_code=503) from exc
        return AnalysisResponse(
            calculations=CalculationResponse.model_validate(calculation_result),
            report=ExperimentReport.model_validate(report),
            advice=LlmAdviceResponse.model_validate(advice),
        )

    @router.post(
        "/api/v1/llm/advice",
        response_model=LlmAdviceResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def llm_advice(request: Request, payload: LlmAdviceRequest) -> LlmAdviceResponse:
        adapter, token = pick_adapter(
            request,
            local_adapter=local_adapter,
            openai_adapter=openai_adapter,
            anthropic_adapter=anthropic_adapter,
        )
        advice_payload = payload.model_dump(exclude_none=True)
        try:
            result = adapter.request_advice(advice_payload, token=token) if token else adapter.request_advice(advice_payload)
        except LLMAuthError as exc:
            raise ApiError(str(exc), error_code="llm_auth", status_code=exc.status_code) from exc
        except LLMTransientError as exc:
            raise ApiError(str(exc), error_code="llm_transient", status_code=503) from exc
        return LlmAdviceResponse.model_validate(result)

    return router
