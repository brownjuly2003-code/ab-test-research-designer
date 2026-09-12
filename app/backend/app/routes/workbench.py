from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.backend.app.errors import ApiError
from app.backend.app.evidence.abx import BUNDLE_MEDIA_TYPE, BUNDLE_SUFFIX
from app.backend.app.evidence.decisions import (
    ApprovalQuorumUnmetError,
    EvidenceFindingNotFoundError,
    RoleNotPermittedError,
    record_finding_state,
    record_human_decision,
)
from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
from app.backend.app.evidence.persisted_workbench import (
    PersistedDecisionRequest,
    PersistedOverrideRequest,
    PersistedRunPortfolio,
    PersistedRunView,
    summarize_persisted_run,
    view_persisted_run,
)
from app.backend.app.evidence.run_abx import (
    EvidenceRunNotFoundError,
    publish_completed_run_abx,
)
from app.backend.app.evidence.runs import CompletedEvidenceRun
from app.backend.app.evidence.sql_run_store import EvidenceRunConflictError
from app.backend.app.http_runtime import Principal
from app.backend.app.repository import ProjectRepository


def _role_not_permitted(error: RoleNotPermittedError) -> ApiError:
    return ApiError(
        str(error),
        error_code="role_not_permitted",
        status_code=403,
    )


def _approval_quorum_unmet(error: ApprovalQuorumUnmetError) -> ApiError:
    # 409, not 403: the caller is allowed to decide, and the frozen policy is
    # what cannot be satisfied. Nothing about this request would make it succeed.
    return ApiError(
        str(error),
        error_code="approval_quorum_unmet",
        status_code=409,
    )


def create_workbench_router(
    repository: ProjectRepository,
    require_auth: Callable[[Request], None],
    require_write_auth: Callable[[Request], Principal],
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(tags=["evidence"])

    def run_store() -> LifecycleEvidenceRunStore:
        return LifecycleEvidenceRunStore(repository, artifact_root)

    def require_run(
        store: LifecycleEvidenceRunStore,
        run_id: str,
    ) -> CompletedEvidenceRun:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Completed evidence run not found.")
        return run

    @router.get(
        "/api/v2/runs",
        response_model=PersistedRunPortfolio,
        dependencies=[Depends(require_auth)],
    )
    def list_runs() -> PersistedRunPortfolio:
        store = run_store()
        runs = []
        for run_id in store.list_run_ids():
            runs.append(summarize_persisted_run(require_run(store, run_id)))
        return PersistedRunPortfolio(runs=runs)

    @router.get(
        "/api/v2/runs/{run_id}:bundle",
        dependencies=[Depends(require_auth)],
    )
    def download_persisted_bundle(run_id: str) -> Response:
        store = run_store()
        require_run(store, run_id)
        with TemporaryDirectory(prefix="trialmark-api-bundle-") as temporary_name:
            destination = Path(temporary_name) / f"{run_id}{BUNDLE_SUFFIX}"
            publish_completed_run_abx(store, run_id=run_id, destination=destination)
            archive = destination.read_bytes()
        return Response(
            content=archive,
            media_type=BUNDLE_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{run_id}{BUNDLE_SUFFIX}"',
                "Cache-Control": "no-store",
            },
        )

    @router.post(
        "/api/v2/runs/{run_id}/decisions",
        response_model=PersistedRunView,
        status_code=201,
    )
    def record_persisted_decision(
        run_id: str,
        payload: PersistedDecisionRequest,
        principal: Principal = Depends(require_write_auth),  # noqa: B008
    ) -> PersistedRunView:
        store = run_store()
        try:
            child = record_human_decision(
                run_id,
                principal,
                payload.verdict,
                payload.rationale,
                out_store=store,
            )
        except EvidenceRunNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="Completed evidence run not found.",
            ) from error
        except RoleNotPermittedError as error:
            raise _role_not_permitted(error) from error
        except ApprovalQuorumUnmetError as error:
            raise _approval_quorum_unmet(error) from error
        except EvidenceRunConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        view = view_persisted_run(child)
        store.complete(
            child,
            bundle_id=view.bundle.bundle_id,
            artifact_ref=f"/api/v2/runs/{child.run_id}:bundle",
        )
        return view

    @router.post(
        "/api/v2/runs/{run_id}/findings/{finding_id}:remediate",
        response_model=PersistedRunView,
        status_code=201,
    )
    def remediate_persisted_finding(
        run_id: str,
        finding_id: str,
        principal: Principal = Depends(require_write_auth),  # noqa: B008
    ) -> PersistedRunView:
        return persist_finding_action(
            run_id,
            finding_id,
            principal,
            action="remediate",
        )

    @router.post(
        "/api/v2/runs/{run_id}/findings/{finding_id}:override",
        response_model=PersistedRunView,
        status_code=201,
    )
    def override_persisted_finding(
        run_id: str,
        finding_id: str,
        payload: PersistedOverrideRequest,
        principal: Principal = Depends(require_write_auth),  # noqa: B008
    ) -> PersistedRunView:
        return persist_finding_action(
            run_id,
            finding_id,
            principal,
            action="override",
            reason=payload.reason,
        )

    def persist_finding_action(
        run_id: str,
        finding_id: str,
        principal: Principal,
        *,
        action: Literal["remediate", "override"],
        reason: str | None = None,
    ) -> PersistedRunView:
        store = run_store()
        try:
            child = record_finding_state(
                run_id,
                finding_id,
                principal,
                action,
                reason=reason,
                out_store=store,
            )
        except (EvidenceRunNotFoundError, EvidenceFindingNotFoundError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        # Before the conflict/ValueError arm: an unauthorized role is neither a
        # conflict with the run's state nor a malformed request.
        except RoleNotPermittedError as error:
            raise _role_not_permitted(error) from error
        except (EvidenceRunConflictError, ValueError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        view = view_persisted_run(child)
        store.complete(
            child,
            bundle_id=view.bundle.bundle_id,
            artifact_ref=f"/api/v2/runs/{child.run_id}:bundle",
        )
        return view

    @router.get(
        "/api/v2/runs/{run_id}",
        response_model=PersistedRunView,
        dependencies=[Depends(require_auth)],
    )
    def get_run(run_id: str) -> PersistedRunView:
        store = run_store()
        return view_persisted_run(require_run(store, run_id))

    return router
