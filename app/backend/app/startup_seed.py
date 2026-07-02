from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

from app.backend.app.config import Settings
from app.backend.app.demo_execution import seed_demo_execution
from app.backend.app.logging_utils import log_event
from app.backend.app.repository import ProjectRepository
from app.backend.app.routes.analysis import _build_calculation_payload
from app.backend.app.schemas.api import AnalysisResponse, ExperimentInput
from app.backend.app.services.calculations_service import calculate_experiment_metrics
from app.backend.app.services.design_service import build_experiment_report
from app.backend.app.services.export_service import export_report_to_markdown
from app.backend.app.services.template_service import (
    load_built_in_templates,
    sync_built_in_templates,
)

logger = logging.getLogger(__name__)

DEMO_PROJECT_PREFIX = "Demo - "
# ``metrics_overrides`` retune a demo *instance* without touching the user-facing template. The
# seeded execution data is far smaller than the stock templates' planned samples, and the decision
# readout now refuses to confirm a fixed-horizon result read before the planned sample (the
# peeking guard) — so the demos that are meant to showcase a "ship" verdict are sized for the
# effect their seeded data actually demonstrates, making the demo read the *planned* read:
# - Checkout seeds ~2,000 users/arm with a deliberately large (~+44%) uplift; the stock 5% MDE
#   plans ~147k/arm (the demo read would sit at ~1.4% of plan). A 50% MDE plans ~1,770/arm.
# - Pricing seeds 400/arm; the stock 4.5% MDE plans ~552/arm. A 5.5% MDE plans ~370/arm.
# The ratio demo is left early on purpose: its anytime-valid view is significant, so it showcases
# the legitimate early-ship path; the onboarding demo stays honestly inconclusive.
SAMPLE_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "template_id": "checkout_conversion",
        "project_name": "Demo - Checkout Conversion",
        "metrics_overrides": {"mde_pct": 50, "expected_uplift_pct": 45},
    },
    {
        "template_id": "pricing_sensitivity",
        "project_name": "Demo - Pricing Sensitivity",
        "metrics_overrides": {"mde_pct": 5.5},
    },
    {
        "template_id": "onboarding_completion",
        "project_name": "Demo - Onboarding Completion",
    },
    {
        "template_id": "ad_ctr_ratio",
        "project_name": "Demo - Feed Ad Click-Through Ratio",
    },
)


@dataclass
class SeedResult:
    created_projects: int = 0
    analyzed_projects: int = 0
    exported_projects: int = 0
    skipped_projects: int = 0


def _demo_advice_payload() -> dict[str, Any]:
    return {
        "available": False,
        "provider": "local_orchestrator",
        "model": "offline",
        "advice": None,
        "raw_text": None,
        "error": "Demo seed skips live LLM advice.",
        "error_code": "seed_demo_disabled_llm",
    }


def _build_seed_payload(
    template_payload: dict[str, Any],
    project_name: str,
    metrics_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = copy.deepcopy(template_payload)
    payload["project"]["project_name"] = project_name
    payload["project"]["project_description"] = (
        f"{payload['project']['project_description']} Seeded demo sample."
    )
    payload["additional_context"]["llm_context"] = (
        f"{payload['additional_context'].get('llm_context', '').strip()} Seeded demo sample."
    ).strip()
    for key, value in (metrics_overrides or {}).items():
        payload["metrics"][key] = value
    return payload


def _build_analysis_payload(project_payload: dict[str, Any]) -> dict[str, Any]:
    payload = ExperimentInput.model_validate(project_payload)
    calculation_payload = _build_calculation_payload(payload)
    calculation_result = calculate_experiment_metrics(calculation_payload.model_dump())
    report = build_experiment_report(payload.model_dump(), calculation_result)
    return AnalysisResponse.model_validate(
        {
            "calculations": calculation_result,
            "report": report,
            "advice": _demo_advice_payload(),
        }
    ).model_dump()


def seed_demo_workspace(settings: Settings, repository: ProjectRepository) -> SeedResult:
    del settings
    sync_built_in_templates(repository)

    existing_projects = repository.query_projects(
        q=DEMO_PROJECT_PREFIX,
        status="all",
        sort_by="name",
        sort_dir="asc",
        limit=200,
        offset=0,
    )["projects"]
    demo_projects = [
        project
        for project in existing_projects
        if project["project_name"].startswith(DEMO_PROJECT_PREFIX)
    ]
    # Demo project name -> id, kept current through both the create path and the already-populated
    # path so the execution seed below can resolve every demo regardless of how it got here.
    project_id_by_name: dict[str, str] = {
        project["project_name"]: project["id"] for project in demo_projects
    }

    if len(demo_projects) >= len(SAMPLE_PROJECTS):
        log_event(
            logger,
            logging.INFO,
            "demo-seed: already populated, skipping design seed",
            existing_demo_projects=len(demo_projects),
        )
        result = SeedResult(skipped_projects=len(SAMPLE_PROJECTS))
    else:
        templates_by_id = {template["id"]: template for template in load_built_in_templates()}
        existing_by_name = {project["project_name"]: project for project in demo_projects}
        result = SeedResult()

        for index, sample in enumerate(SAMPLE_PROJECTS):
            project = None
            existing = existing_by_name.get(sample["project_name"])
            if existing is None:
                template = templates_by_id[sample["template_id"]]
                project = repository.create_project(
                    _build_seed_payload(
                        template["payload"],
                        sample["project_name"],
                        sample.get("metrics_overrides"),
                    )
                )
                result.created_projects += 1
            else:
                project = repository.get_project(existing["id"], include_archived=True)

            if project is None:
                raise RuntimeError(f"Failed to load demo project {sample['project_name']}")

            if project["last_analysis_run_id"] is None:
                project = repository.record_analysis(project["id"], _build_analysis_payload(project["payload"]))
                result.analyzed_projects += 1

            if project is None:
                raise RuntimeError(f"Failed to record analysis for {sample['project_name']}")

            if index == 0:
                history = repository.get_project_history(
                    project["id"],
                    analysis_limit=1,
                    analysis_offset=0,
                    export_limit=1,
                    export_offset=0,
                )
                if history is None:
                    raise RuntimeError(f"Failed to load history for {sample['project_name']}")
                if history["export_total"] == 0:
                    analysis_run = repository.get_latest_analysis_run(project["id"])
                    if analysis_run is None:
                        raise RuntimeError(f"Missing analysis run for {sample['project_name']}")
                    export_report_to_markdown(analysis_run["analysis"]["report"])
                    project = repository.record_export(project["id"], "markdown", analysis_run["id"])
                    result.exported_projects += 1
                    if project is None:
                        raise RuntimeError(f"Failed to record export for {sample['project_name']}")

            if existing is not None and project["last_analysis_run_id"] is not None and index != 0:
                result.skipped_projects += 1

            project_id_by_name[sample["project_name"]] = project["id"]

        log_event(
            logger,
            logging.INFO,
            "demo-seed: completed",
            created_projects=result.created_projects,
            analyzed_projects=result.analyzed_projects,
            exported_projects=result.exported_projects,
            skipped_projects=result.skipped_projects,
        )

    # Execution data (Phase 5 / T5.1): make the live-stats surface visible on the demo path without
    # manual ingest. Idempotent (skips demos that already carry exposures), so it is safe on every
    # startup and tops up the upgrade path where the design projects already exist but have no events.
    demo_for_execution = [
        (sample["template_id"], project_id_by_name[sample["project_name"]])
        for sample in SAMPLE_PROJECTS
        if sample["project_name"] in project_id_by_name
    ]
    seed_demo_execution(repository, demo_for_execution)
    return result
