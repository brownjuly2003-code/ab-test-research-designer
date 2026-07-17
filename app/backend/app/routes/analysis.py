from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.backend.app.errors import ApiError
from app.backend.app.execution.bucketer import preview_assignment_distribution
from app.backend.app.execution.experiment_assignment import build_experiment_assignment
from app.backend.app.i18n import translate
from app.backend.app.llm.adapter import (
    LLMAuthError,
    LLMTransientError,
    LocalOrchestratorAdapter,
)
from app.backend.app.llm.anthropic_adapter import AnthropicAdapter
from app.backend.app.llm.mistral_adapter import MistralAdapter
from app.backend.app.llm.openai_adapter import OpenAIAdapter
from app.backend.app.schemas.api import (
    AnalysisResponse,
    AssignmentPreviewRequest,
    AssignmentPreviewResponse,
    BanditSimulationRequest,
    BanditSimulationResponse,
    CalculationRequest,
    CalculationResponse,
    CategoricalResultsRequest,
    CategoricalResultsResponse,
    ExperimentAssignmentRequest,
    ExperimentAssignmentResponse,
    ExperimentInput,
    ExperimentReport,
    HypothesisIdeationRequest,
    HypothesisIdeationResponse,
    LlmAdviceRequest,
    LlmAdviceResponse,
    MultipleTestingMetricResult,
    MultipleTestingRequest,
    MultipleTestingResponse,
    OmnibusResultsRequest,
    OmnibusResultsResponse,
    PairedResultsRequest,
    PairedResultsResponse,
    RatioResultsRequest,
    ResultsRequest,
    ResultsResponse,
    SensitivityCell,
    SensitivityRequest,
    SensitivityResponse,
    SrmCheckRequest,
    SrmCheckResponse,
    SurvivalResultsRequest,
    SurvivalResultsResponse,
)
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.monte_carlo_service import simulate_thompson_sampling
from app.backend.app.services.results_service import (
    analyze_categorical_results,
    analyze_omnibus_results,
    analyze_paired_results,
    analyze_ratio_results,
    analyze_results,
    analyze_survival_results,
)
from app.backend.app.stats.binary import calculate_binary_sample_size
from app.backend.app.stats.continuous import calculate_continuous_sample_size
from app.backend.app.stats.duration import estimate_experiment_duration_days
from app.backend.app.stats.multiple_testing import benjamini_hochberg, holm_bonferroni
from app.backend.app.stats.srm import chi_square_srm

if TYPE_CHECKING:
    from app.backend.app.config import Settings
    from app.backend.app.http_utils import SlidingWindowRateLimiter
    from app.backend.app.repository import ProjectRepository


def _build_calculation_payload(payload: ExperimentInput) -> CalculationRequest:
    metric_type = payload.metrics.metric_type
    if metric_type == "ratio" and payload.metrics.std_dev is None:
        # Ratio sample-size planning uses the delta-method linearization (the per-user value
        # numerator - R*denominator treated as a continuous metric), which needs the per-user
        # standard deviation. Without it we cannot plan a sample size — but the live execution stats
        # still analyze the ratio directly via the delta method. When std_dev is present the planning
        # path proceeds exactly like a continuous metric (see calculate_experiment_metrics).
        raise HTTPException(
            status_code=422,
            detail=(
                "Ratio sample-size planning needs the metric's per-user standard deviation (std_dev) "
                "for the delta-method linearization. Add it to the metric, or run the experiment and "
                "read its live delta-method execution stats."
            ),
        )
    return CalculationRequest(
        metric_type=metric_type,
        baseline_value=payload.metrics.baseline_value,
        std_dev=payload.metrics.std_dev,
        exposure_per_user=payload.metrics.exposure_per_user,
        cuped_pre_experiment_std=payload.metrics.cuped_pre_experiment_std,
        cuped_correlation=payload.metrics.cuped_correlation,
        planned_test=payload.metrics.planned_test,
        equivalence_margin_pct=payload.metrics.equivalence_margin_pct,
        mde_pct=payload.metrics.mde_pct,
        alpha=payload.metrics.alpha,
        power=payload.metrics.power,
        expected_daily_traffic=payload.setup.expected_daily_traffic,
        audience_share_in_test=payload.setup.audience_share_in_test,
        traffic_split=payload.setup.traffic_split,
        variants_count=payload.setup.variants_count,
        randomization_unit=payload.setup.randomization_unit,
        avg_cluster_size=payload.setup.avg_cluster_size,
        icc=payload.setup.icc,
        seasonality_present=payload.constraints.seasonality_present,
        active_campaigns_present=payload.constraints.active_campaigns_present,
        long_test_possible=payload.constraints.long_test_possible,
        n_looks=payload.constraints.n_looks,
        analysis_mode=payload.constraints.analysis_mode,
        desired_precision=payload.constraints.desired_precision,
        credibility=payload.constraints.credibility,
        holdout_fraction=payload.constraints.holdout_fraction,
        mutually_exclusive_experiments=payload.constraints.mutually_exclusive_experiments,
    )


def _build_llm_advice_payload(payload: ExperimentInput, calculation_result: dict[str, Any]) -> dict[str, Any]:
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


AdviceAdapter = LocalOrchestratorAdapter | OpenAIAdapter | AnthropicAdapter | MistralAdapter

PUBLIC_DEMO_LLM_ERROR_CODE = "public_demo_llm_requires_key"


def server_llm_allowed(request: Request) -> bool:
    """Whether this session may spend server-funded LLM resources.

    The default local-orchestrator path and the server-side Mistral insurance key
    are reserved for write/admin sessions. When auth is disabled entirely (private
    local instance, ``auth_scope`` is ``None``) they stay available. A read-scope
    session (readonly token or the anonymous public-demo scope) must bring its own
    provider via the ``X-AB-LLM-Provider`` / ``X-AB-LLM-Token`` headers instead.
    """
    return getattr(request.state, "auth_scope", None) in {None, "write", "admin"}


def _public_demo_llm_stub(*, method: str) -> dict[str, Any]:
    stub: dict[str, Any] = {
        "available": False,
        "provider": "none",
        "model": "none",
        "raw_text": None,
        "error": "Server-side AI is reserved for authenticated sessions. Bring your own API key to enable it.",
        "error_code": PUBLIC_DEMO_LLM_ERROR_CODE,
    }
    if method == "hypotheses":
        stub["hypotheses"] = []
    else:
        stub["advice"] = None
    return stub


def pick_adapter(
    request: Request,
    *,
    local_adapter: LocalOrchestratorAdapter,
    openai_adapter: OpenAIAdapter,
    anthropic_adapter: AnthropicAdapter,
    mistral_adapter: MistralAdapter | None = None,
) -> tuple[AdviceAdapter, str]:
    provider = request.headers.get("X-AB-LLM-Provider", "").strip().lower()
    token = request.headers.get("X-AB-LLM-Token", "").strip()
    if provider == "openai" and token:
        return openai_adapter, token
    if provider == "anthropic" and token:
        return anthropic_adapter, token
    if provider == "mistral" and token and mistral_adapter is not None:
        return mistral_adapter, token
    return local_adapter, ""


def _request_with_insurance(
    *,
    adapter: AdviceAdapter,
    token: str,
    payload: dict[str, Any],
    method: str,
    local_adapter: LocalOrchestratorAdapter,
    mistral_adapter: MistralAdapter | None,
    mistral_key: str,
) -> dict[str, Any]:
    """Run an advice/hypotheses request, with free Mistral as insurance.

    Mistral only steps in for the *default* local-orchestrator path when that path
    could not produce a result (e.g. the hosted demo has no local orchestrator, so
    the call returns ``available: False``). An explicitly chosen provider
    (openai/anthropic/mistral with a caller token) is left untouched — its errors
    propagate as before. ``method`` is ``"advice"`` or ``"hypotheses"``.
    """

    def call(active: AdviceAdapter, active_token: str) -> dict[str, Any]:
        if method == "hypotheses":
            return (
                cast("OpenAIAdapter | AnthropicAdapter | MistralAdapter", active).request_hypotheses(payload, token=active_token)
                if active_token
                else active.request_hypotheses(payload)
            )
        return (
            cast("OpenAIAdapter | AnthropicAdapter | MistralAdapter", active).request_advice(payload, token=active_token)
            if active_token
            else active.request_advice(payload)
        )

    result = call(adapter, token)
    if (
        adapter is local_adapter
        and not result.get("available")
        and mistral_adapter is not None
        and mistral_key
    ):
        try:
            insured = call(mistral_adapter, mistral_key)
            if insured.get("available"):
                return insured
        except (LLMAuthError, LLMTransientError):
            pass
    return result


def create_analysis_router(
    settings: "Settings",
    repository: "ProjectRepository",
    rate_limiter: "SlidingWindowRateLimiter",
    require_auth: Callable[[Request], None],
    require_write_auth: Callable[[Request], None],
) -> APIRouter:
    router = APIRouter(tags=["calculations"])
    local_adapter = LocalOrchestratorAdapter(
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        initial_backoff_seconds=settings.llm_initial_backoff_seconds,
        backoff_multiplier=settings.llm_backoff_multiplier,
    )
    openai_adapter = OpenAIAdapter(
        model=settings.openai_model,
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
    # Free Mistral insurance: created only when a server-side key is configured.
    # When set, it backstops the default local path if the orchestrator is absent
    # (e.g. the hosted demo), so AI advice still works without a paid provider.
    mistral_adapter = (
        MistralAdapter(
            model=settings.mistral_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_attempts=settings.llm_max_attempts,
            initial_backoff_seconds=settings.llm_initial_backoff_seconds,
            backoff_multiplier=settings.llm_backoff_multiplier,
        )
        if settings.mistral_api_key
        else None
    )
    mistral_key = settings.mistral_api_key or ""

    @router.post(
        "/api/v1/calculate",
        response_model=CalculationResponse,
        dependencies=[Depends(require_auth)],
    )
    def calculate(payload: CalculationRequest) -> CalculationResponse:
        result = calculate_experiment_metrics(payload.model_dump())
        return CalculationResponse.model_validate(result)

    @router.post(
        "/api/v1/sensitivity",
        response_model=SensitivityResponse,
        dependencies=[Depends(require_auth)],
    )
    def sensitivity(payload: SensitivityRequest) -> SensitivityResponse:
        cells: list[SensitivityCell] = []

        for mde in payload.mde_values:
            for power in payload.power_values:
                if payload.metric_type == "binary":
                    # validate_metric_specific_fields guarantees baseline_rate is set for binary metrics.
                    calculation = calculate_binary_sample_size(
                        baseline_rate=float(cast("float", payload.baseline_rate)) / 100,
                        mde_pct=mde,
                        alpha=payload.alpha,
                        power=power,
                        variants_count=payload.variants,
                    )
                else:
                    # validate_metric_specific_fields guarantees baseline_mean and std_dev are set for
                    # continuous and ratio metrics alike — ratio sizing reuses this same delta-method-
                    # linearized continuous formula (baseline_mean carries the baseline ratio R), matching
                    # calculate_experiment_metrics's "continuous" / "ratio" branch in calculations_service.py.
                    baseline_mean = float(cast("float", payload.baseline_mean))
                    calculation = calculate_continuous_sample_size(
                        baseline_mean=baseline_mean,
                        std_dev=float(cast("float", payload.std_dev)),
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
        dependencies=[Depends(require_auth)],
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
        "/api/v1/multiple-testing",
        response_model=MultipleTestingResponse,
        dependencies=[Depends(require_auth)],
    )
    def multiple_testing(payload: MultipleTestingRequest) -> MultipleTestingResponse:
        pvalues = [metric.p_value for metric in payload.metrics]
        correction = (
            benjamini_hochberg(pvalues, q=payload.level)
            if payload.method == "bh"
            else holm_bonferroni(pvalues, alpha=payload.level)
        )
        results = [
            MultipleTestingMetricResult(
                label=metric.label,
                p_value=metric.p_value,
                adjusted_p_value=round(adjusted, 6),
                rejected=rejected,
            )
            for metric, adjusted, rejected in zip(
                payload.metrics, correction["adjusted_pvalues"], correction["rejected"], strict=True
            )
        ]
        return MultipleTestingResponse(
            method=correction["method"],
            level=correction["level"],
            num_tests=correction["num_tests"],
            num_rejected=correction["num_rejected"],
            threshold_rank=correction["threshold_rank"],
            critical_value=round(correction["critical_value"], 6),
            results=results,
        )

    @router.post(
        "/api/v1/results",
        response_model=ResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def results(payload: ResultsRequest) -> ResultsResponse:
        return analyze_results(payload)

    @router.post(
        "/api/v1/results/categorical",
        response_model=CategoricalResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def categorical_results(payload: CategoricalResultsRequest) -> CategoricalResultsResponse:
        return analyze_categorical_results(payload)

    @router.post(
        "/api/v1/results/paired",
        response_model=PairedResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def paired_results(payload: PairedResultsRequest) -> PairedResultsResponse:
        return analyze_paired_results(payload)

    @router.post(
        "/api/v1/results/omnibus",
        response_model=OmnibusResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def omnibus_results(payload: OmnibusResultsRequest) -> OmnibusResultsResponse:
        return analyze_omnibus_results(payload)

    @router.post(
        "/api/v1/results/survival",
        response_model=SurvivalResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def survival_results(payload: SurvivalResultsRequest) -> SurvivalResultsResponse:
        return analyze_survival_results(payload)

    @router.post(
        "/api/v1/results/ratio",
        response_model=ResultsResponse,
        dependencies=[Depends(require_auth)],
    )
    def ratio_results(payload: RatioResultsRequest) -> ResultsResponse:
        return analyze_ratio_results(payload)

    @router.post(
        "/api/v1/simulate/bandit",
        response_model=BanditSimulationResponse,
        dependencies=[Depends(require_auth)],
    )
    def simulate_bandit(payload: BanditSimulationRequest) -> BanditSimulationResponse:
        result = simulate_thompson_sampling(
            arm_rates=payload.arm_rates,
            horizon=payload.horizon,
            num_simulations=payload.num_simulations,
            seed=payload.seed,
        )
        return BanditSimulationResponse.model_validate(result)

    @router.post(
        "/api/v1/assignment/preview",
        response_model=AssignmentPreviewResponse,
        dependencies=[Depends(require_auth)],
    )
    def assignment_preview(payload: AssignmentPreviewRequest) -> AssignmentPreviewResponse:
        result = preview_assignment_distribution(
            seed=payload.seed,
            num_variations=payload.num_variations,
            coverage=payload.coverage,
            weights=payload.weights,
            sample_size=payload.sample_size,
            user_id_prefix=payload.user_id_prefix,
            hash_version=payload.hash_version,
        )
        return AssignmentPreviewResponse.model_validate(result)

    @router.post(
        "/api/v1/experiments/{experiment_id}/assign",
        response_model=ExperimentAssignmentResponse,
        dependencies=[Depends(require_write_auth)],
    )
    def assign_experiment(experiment_id: str, payload: ExperimentAssignmentRequest) -> ExperimentAssignmentResponse:
        project = repository.get_project(experiment_id, include_archived=True)
        if project is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        # Sticky bucketing: honour a previously recorded exposure so the user keeps their
        # variation even if weights/coverage changed since.
        existing_exposure = repository.get_user_exposure(experiment_id, payload.user_id)
        result = build_experiment_assignment(
            experiment_id=experiment_id,
            payload=project["payload"],
            user_id=payload.user_id,
            hash_version=payload.hash_version,
            sticky_variation_index=existing_exposure["variation_index"] if existing_exposure else None,
            attributes=payload.attributes,
        )
        return ExperimentAssignmentResponse.model_validate(result)

    @router.post(
        "/api/v1/design",
        response_model=ExperimentReport,
        dependencies=[Depends(require_auth)],
    )
    def design(payload: ExperimentInput) -> ExperimentReport:
        calculation_payload = _build_calculation_payload(payload)
        calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
        report = build_experiment_report(payload.model_dump(), calculation_result)
        return ExperimentReport.model_validate(report)

    @router.post(
        "/api/v1/analyze",
        response_model=AnalysisResponse,
        dependencies=[Depends(require_auth)],
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
            mistral_adapter=mistral_adapter,
        )
        advice_payload = _build_llm_advice_payload(payload, calculation_result)
        if adapter is local_adapter and not server_llm_allowed(request):
            return AnalysisResponse(
                calculations=CalculationResponse.model_validate(calculation_result),
                report=ExperimentReport.model_validate(report),
                advice=LlmAdviceResponse.model_validate(_public_demo_llm_stub(method="advice")),
            )
        try:
            advice = _request_with_insurance(
                adapter=adapter,
                token=token,
                payload=advice_payload,
                method="advice",
                local_adapter=local_adapter,
                mistral_adapter=mistral_adapter,
                mistral_key=mistral_key,
            )
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
        dependencies=[Depends(require_auth)],
    )
    def llm_advice(request: Request, payload: LlmAdviceRequest) -> LlmAdviceResponse:
        adapter, token = pick_adapter(
            request,
            local_adapter=local_adapter,
            openai_adapter=openai_adapter,
            anthropic_adapter=anthropic_adapter,
            mistral_adapter=mistral_adapter,
        )
        advice_payload = payload.model_dump(exclude_none=True)
        if adapter is local_adapter and not server_llm_allowed(request):
            return LlmAdviceResponse.model_validate(_public_demo_llm_stub(method="advice"))
        try:
            result = _request_with_insurance(
                adapter=adapter,
                token=token,
                payload=advice_payload,
                method="advice",
                local_adapter=local_adapter,
                mistral_adapter=mistral_adapter,
                mistral_key=mistral_key,
            )
        except LLMAuthError as exc:
            raise ApiError(str(exc), error_code="llm_auth", status_code=exc.status_code) from exc
        except LLMTransientError as exc:
            raise ApiError(str(exc), error_code="llm_transient", status_code=503) from exc
        return LlmAdviceResponse.model_validate(result)

    @router.post(
        "/api/v1/hypotheses/generate",
        response_model=HypothesisIdeationResponse,
        dependencies=[Depends(require_auth)],
    )
    def generate_hypotheses(request: Request, payload: HypothesisIdeationRequest) -> HypothesisIdeationResponse:
        adapter, token = pick_adapter(
            request,
            local_adapter=local_adapter,
            openai_adapter=openai_adapter,
            anthropic_adapter=anthropic_adapter,
            mistral_adapter=mistral_adapter,
        )
        ideation_payload = payload.model_dump(exclude_none=True)
        if adapter is local_adapter and not server_llm_allowed(request):
            return HypothesisIdeationResponse.model_validate(_public_demo_llm_stub(method="hypotheses"))
        try:
            result = _request_with_insurance(
                adapter=adapter,
                token=token,
                payload=ideation_payload,
                method="hypotheses",
                local_adapter=local_adapter,
                mistral_adapter=mistral_adapter,
                mistral_key=mistral_key,
            )
        except LLMAuthError as exc:
            raise ApiError(str(exc), error_code="llm_auth", status_code=exc.status_code) from exc
        except LLMTransientError as exc:
            raise ApiError(str(exc), error_code="llm_transient", status_code=503) from exc
        return HypothesisIdeationResponse.model_validate(result)

    return router
