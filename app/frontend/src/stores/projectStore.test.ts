// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  archiveProjectRequest: vi.fn(),
  clearApiSessionToken: vi.fn(),
  compareProjectsRequest: vi.fn(),
  downloadProjectReportPdfRequest: vi.fn(),
  deleteProjectRequest: vi.fn(),
  exportReportRequest: vi.fn(),
  exportWorkspaceRequest: vi.fn(),
  hasApiSessionToken: vi.fn(),
  importWorkspaceRequest: vi.fn(),
  listProjectsRequest: vi.fn(),
  loadProjectHistoryRequest: vi.fn(),
  loadProjectRevisionsRequest: vi.fn(),
  loadProjectRequest: vi.fn(),
  recordProjectAnalysisRequest: vi.fn(),
  recordProjectExportRequest: vi.fn(),
  requestDiagnostics: vi.fn(),
  requestHealth: vi.fn(),
  restoreProjectRequest: vi.fn(),
  saveProjectRequest: vi.fn(),
  setApiSessionToken: vi.fn(),
  validateWorkspaceRequest: vi.fn()
}));

import {
  archiveProjectRequest,
  compareProjectsRequest,
  deleteProjectRequest,
  hasApiSessionToken,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRevisionsRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  requestDiagnostics,
  requestHealth,
  restoreProjectRequest,
  saveProjectRequest
} from "../lib/api";
import {
  buildApiPayload,
  cloneInitialState,
  type AnalysisResponsePayload
} from "../lib/experiment";

function buildAnalysisResult(): AnalysisResponsePayload {
  return {
    calculations: {
      calculation_summary: {
        metric_type: "binary",
        baseline_value: 0.042,
        mde_pct: 5,
        mde_absolute: 0.0021,
        alpha: 0.05,
        power: 0.8
      },
      results: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        effective_daily_traffic: 5000,
        estimated_duration_days: 12
      },
      assumptions: [],
      warnings: []
    },
    report: {
      executive_summary: "Deterministic summary",
      calculations: {
        sample_size_per_variant: 100,
        total_sample_size: 300,
        estimated_duration_days: 12,
        assumptions: []
      },
      experiment_design: {
        variants: [
          { name: "A", description: "current experience" },
          { name: "B", description: "new checkout" }
        ],
        randomization_unit: "user",
        traffic_split: [50, 50],
        target_audience: "new users on web",
        inclusion_criteria: "new users only",
        exclusion_criteria: "internal staff",
        recommended_duration_days: 12,
        stopping_conditions: ["planned duration reached"]
      },
      metrics_plan: {
        primary: ["purchase_conversion"],
        secondary: ["add_to_cart_rate"],
        guardrail: ["payment_error_rate"],
        diagnostic: ["assignment_rate"]
      },
      guardrail_metrics: [],
      risks: {
        statistical: ["No major deterministic warnings identified at this stage."],
        product: ["Expected result depends on the hypothesis."],
        technical: ["legacy event logging"],
        operational: ["tracking quality"]
      },
      recommendations: {
        before_launch: ["Verify tracking"],
        during_test: ["Watch SRM"],
        after_test: ["Segment the result"]
      },
      open_questions: ["Will mobile respond differently?"]
    },
    advice: {
      available: false,
      provider: "offline",
      model: "offline",
      advice: null,
      raw_text: null,
      error: "offline",
      error_code: "request_error"
    }
  };
}

function buildSavedProject(id = "p-1", projectName = "Stored checkout test") {
  return {
    id,
    project_name: projectName,
    payload_schema_version: 1,
    revision_count: 1,
    last_revision_at: "2026-03-07T10:05:00Z",
    archived_at: null,
    is_archived: false,
    last_analysis_at: null,
    last_analysis_run_id: null,
    last_exported_at: null,
    has_analysis_snapshot: false,
    created_at: "2026-03-07T10:00:00Z",
    updated_at: "2026-03-07T10:00:00Z"
  };
}

function buildProjectRecord(id = "p-1", projectName = "Stored checkout test") {
  return {
    ...buildSavedProject(id, projectName),
    payload: buildApiPayload(cloneInitialState())
  };
}

function buildHealth() {
  return {
    status: "ok",
    service: "AB Test Research Designer API",
    version: "0.1.0",
    environment: "local"
  };
}

function buildDiagnostics() {
  return {
    status: "ok",
    generated_at: "2026-03-08T14:00:00Z",
    started_at: "2026-03-08T13:30:00Z",
    uptime_seconds: 1800,
    environment: "local",
    app_version: "0.1.0",
    request_timing_headers_enabled: true,
    storage: {
      db_path: "D:/AB_TEST/app/backend/data/projects.sqlite3",
      db_parent_path: "D:/AB_TEST/app/backend/data",
      db_exists: true,
      db_size_bytes: 24576,
      disk_free_bytes: 987654321,
      schema_version: 3,
      sqlite_user_version: 3,
      busy_timeout_ms: 5000,
      journal_mode: "WAL",
      synchronous: "NORMAL",
      write_probe_ok: true,
      write_probe_detail: "BEGIN IMMEDIATE succeeded",
      projects_total: 2,
      archived_projects_total: 0,
      analysis_runs_total: 3,
      export_events_total: 1,
      project_revisions_total: 2,
      workspace_bundle_schema_version: 3,
      workspace_signature_enabled: false,
      latest_project_updated_at: "2026-03-08T13:55:00Z"
    },
    frontend: {
      serve_frontend_dist: true,
      dist_path: "D:/AB_TEST/app/frontend/dist",
      dist_exists: true
    },
    llm: {
      provider: "local_orchestrator",
      base_url: "http://localhost:8001",
      timeout_seconds: 60,
      max_attempts: 3,
      initial_backoff_seconds: 0.1,
      backoff_multiplier: 2
    },
    logging: {
      level: "INFO",
      format: "plain"
    },
    auth: {
      enabled: false,
      mode: "open",
      write_enabled: false,
      readonly_enabled: false,
      accepted_headers: ["Authorization: Bearer", "X-API-Key"],
      read_only_methods: ["GET", "HEAD", "OPTIONS"]
    },
    guards: {
      security_headers_enabled: true,
      rate_limit_enabled: true,
      rate_limit_requests: 240,
      rate_limit_window_seconds: 60,
      auth_failure_limit: 20,
      auth_failure_window_seconds: 60,
      max_request_body_bytes: 1048576,
      max_workspace_body_bytes: 8388608
    },
    runtime: {
      total_requests: 4,
      success_responses: 4,
      client_error_responses: 0,
      server_error_responses: 0,
      auth_rejections: 0,
      rate_limited_responses: 0,
      request_body_rejections: 0,
      last_request_at: "2026-03-08T14:00:00Z",
      last_error_at: null,
      last_error_code: null
    }
  };
}

function buildProjectHistory(projectId = "p-1") {
  return {
    project_id: projectId,
    analysis_total: 1,
    analysis_limit: 3,
    analysis_offset: 0,
    export_total: 0,
    export_limit: 3,
    export_offset: 0,
    analysis_runs: [
      {
        id: "run-1",
        project_id: projectId,
        created_at: "2026-03-07T12:30:00Z",
        summary: {
          metric_type: "binary",
          sample_size_per_variant: 100,
          total_sample_size: 300,
          estimated_duration_days: 12,
          warnings_count: 0,
          advice_available: false
        },
        analysis: buildAnalysisResult()
      }
    ],
    export_events: []
  };
}

function buildProjectRevisions(projectId = "p-1") {
  return {
    project_id: projectId,
    total: 1,
    limit: 3,
    offset: 0,
    revisions: [
      {
        id: "rev-1",
        project_id: projectId,
        source: "create" as const,
        created_at: "2026-03-07T10:00:00Z",
        payload: buildApiPayload(cloneInitialState())
      }
    ]
  };
}

async function loadProjectStoreModule() {
  vi.resetModules();
  const store = await import("./projectStore");

  return {
    useProjectStore: store.useProjectStore
  };
}

describe("projectStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.mocked(hasApiSessionToken).mockReturnValue(false);
    vi.mocked(requestHealth).mockReset();
    vi.mocked(requestDiagnostics).mockReset();
    vi.mocked(listProjectsRequest).mockReset();
    vi.mocked(loadProjectRequest).mockReset();
    vi.mocked(loadProjectHistoryRequest).mockReset();
    vi.mocked(loadProjectRevisionsRequest).mockReset();
    vi.mocked(saveProjectRequest).mockReset();
    vi.mocked(recordProjectAnalysisRequest).mockReset();
    vi.mocked(archiveProjectRequest).mockReset();
    vi.mocked(restoreProjectRequest).mockReset();
    vi.mocked(compareProjectsRequest).mockReset();
    vi.mocked(deleteProjectRequest).mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("refreshes the saved-project list when health succeeds even if diagnostics fail", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(requestHealth).mockResolvedValueOnce(buildHealth());
    vi.mocked(requestDiagnostics).mockRejectedValueOnce(new Error("diagnostics failed"));
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([buildSavedProject()]);

    await useProjectStore.getState().refreshBackendState();

    expect(requestHealth).toHaveBeenCalledTimes(1);
    expect(requestDiagnostics).toHaveBeenCalledTimes(1);
    expect(listProjectsRequest).toHaveBeenCalledWith({ includeArchived: true });
    expect(useProjectStore.getState().savedProjects).toHaveLength(1);
    expect(useProjectStore.getState().diagnosticsError).toBe("diagnostics failed");
  });

  it("loads a project together with history and revisions", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(loadProjectRequest).mockResolvedValueOnce(buildProjectRecord());
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory());
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions());

    const loaded = await useProjectStore.getState().loadProject("p-1");

    expect(loaded?.id).toBe("p-1");
    expect(useProjectStore.getState().activeProjectId).toBe("p-1");
    expect(useProjectStore.getState().activeProject?.project_name).toBe("Stored checkout test");
    expect(useProjectStore.getState().savedProjectSnapshot).toBe(
      JSON.stringify(buildApiPayload(cloneInitialState()))
    );
    expect(useProjectStore.getState().projectHistory?.project_id).toBe("p-1");
    expect(useProjectStore.getState().projectRevisions?.project_id).toBe("p-1");
  });

  it("marks loaded projects as dirty and clears history selection on draft edits", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(loadProjectRequest).mockResolvedValueOnce(buildProjectRecord());
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory());
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions());

    await useProjectStore.getState().loadProject("p-1");
    expect(useProjectStore.getState().openHistoryRun("run-1")).toBe(true);
    expect(useProjectStore.getState().selectedHistoryRunId).toBe("run-1");

    const changedDraft = cloneInitialState();
    changedDraft.project.project_name = "Loaded experiment v2";
    useProjectStore.getState().markDraftChanged(JSON.stringify(buildApiPayload(changedDraft)));

    expect(useProjectStore.getState().selectedHistoryRunId).toBeNull();
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);
  });

  it("saves a new project and records the latest analysis snapshot", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(saveProjectRequest).mockResolvedValueOnce(buildProjectRecord("p-new", "Checkout redesign"));
    vi.mocked(recordProjectAnalysisRequest).mockResolvedValueOnce({
      ...buildProjectRecord("p-new", "Checkout redesign"),
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      has_analysis_snapshot: true
    });
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory("p-new"));
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions("p-new"));

    const draft = cloneInitialState();
    const outcome = await useProjectStore.getState().saveProject(draft, buildAnalysisResult(), null);

    expect(saveProjectRequest).toHaveBeenCalledWith(draft, null);
    expect(recordProjectAnalysisRequest).toHaveBeenCalledWith("p-new", expect.any(Object));
    expect(outcome?.savedProjectId).toBe("p-new");
    expect(outcome?.analysisRunId).toBe("run-1");
    expect(outcome?.message).toContain("Latest analysis snapshot was recorded");
    expect(useProjectStore.getState().activeProjectId).toBe("p-new");
    expect(useProjectStore.getState().projectHistory?.project_id).toBe("p-new");
  });

  it("updates an existing project and clears the dirty state", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(loadProjectRequest).mockResolvedValueOnce(buildProjectRecord());
    vi.mocked(loadProjectHistoryRequest).mockResolvedValue(buildProjectHistory());
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValue(buildProjectRevisions());

    const updatedDraft = cloneInitialState();
    updatedDraft.project.project_name = "Loaded experiment v2";
    vi.mocked(saveProjectRequest).mockResolvedValueOnce({
      ...buildProjectRecord("p-1", "Loaded experiment v2"),
      updated_at: "2026-03-07T11:15:00Z",
      payload: buildApiPayload(updatedDraft)
    });

    await useProjectStore.getState().loadProject("p-1");
    useProjectStore.getState().markDraftChanged(JSON.stringify(buildApiPayload(updatedDraft)));
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(true);

    const outcome = await useProjectStore.getState().saveProject(updatedDraft, null, null);

    expect(saveProjectRequest).toHaveBeenCalledWith(updatedDraft, "p-1");
    expect(outcome?.message).toContain("updated locally");
    expect(useProjectStore.getState().activeProject?.project_name).toBe("Loaded experiment v2");
    expect(useProjectStore.getState().savedProjectSnapshot).toBe(
      JSON.stringify(buildApiPayload(updatedDraft))
    );
    expect(useProjectStore.getState().hasUnsavedChanges).toBe(false);
  });

  it("persists analysis snapshots once the project has been saved", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(saveProjectRequest).mockResolvedValueOnce(buildProjectRecord("p-new", "Checkout redesign"));
    vi.mocked(loadProjectHistoryRequest).mockResolvedValue(buildProjectHistory("p-new"));
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValue(buildProjectRevisions("p-new"));
    vi.mocked(recordProjectAnalysisRequest).mockResolvedValueOnce({
      ...buildProjectRecord("p-new", "Checkout redesign"),
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-2",
      has_analysis_snapshot: true
    });

    const draft = cloneInitialState();
    await useProjectStore.getState().saveProject(draft, null, null);
    const outcome = await useProjectStore.getState().persistAnalysisSnapshot(draft, buildAnalysisResult());

    expect(recordProjectAnalysisRequest).toHaveBeenCalledWith("p-new", expect.any(Object));
    expect(outcome).toEqual({
      message: "Analysis completed and the latest snapshot was recorded for this saved project.",
      projectId: "p-new",
      analysisRunId: "run-2"
    });
    expect(useProjectStore.getState().activeProjectId).toBe("p-new");
    expect(useProjectStore.getState().activeProject?.has_analysis_snapshot).toBe(true);
    expect(useProjectStore.getState().projectHistory?.project_id).toBe("p-new");
  });

  it("archives the active project and resets the current selection", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(loadProjectRequest).mockResolvedValueOnce(buildProjectRecord());
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory());
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions());
    vi.mocked(archiveProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      archived: true,
      archived_at: "2026-03-07T13:00:00Z"
    });

    await useProjectStore.getState().loadProject("p-1");
    const outcome = await useProjectStore.getState().archiveProject("p-1");

    expect(outcome).toEqual({ deleted: true, deletedActive: true });
    expect(useProjectStore.getState().activeProjectId).toBeNull();
    expect(useProjectStore.getState().projectHistory).toBeNull();
    expect(useProjectStore.getState().projectRevisions).toBeNull();
  });

  it("deletes the active project instead of archiving it", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(loadProjectRequest).mockResolvedValueOnce(buildProjectRecord());
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory());
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions());
    vi.mocked(deleteProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      deleted: true
    });

    await useProjectStore.getState().loadProject("p-1");
    const outcome = await useProjectStore.getState().deleteProject("p-1");

    expect(deleteProjectRequest).toHaveBeenCalledWith("p-1");
    expect(archiveProjectRequest).not.toHaveBeenCalled();
    expect(outcome).toEqual({ deleted: true, deletedActive: true });
    expect(useProjectStore.getState().activeProjectId).toBeNull();
    expect(useProjectStore.getState().savedProjects).toHaveLength(0);
    expect(useProjectStore.getState().projectHistory).toBeNull();
    expect(useProjectStore.getState().projectRevisions).toBeNull();
  });

  it("restores an archived project back into the saved-project list", async () => {
    const { useProjectStore } = await loadProjectStoreModule();
    vi.mocked(restoreProjectRequest).mockResolvedValueOnce({
      ...buildProjectRecord("p-archived", "Archived experiment"),
      archived_at: null,
      is_archived: false
    });

    const restored = await useProjectStore.getState().restoreProject("p-archived");

    expect(restored?.id).toBe("p-archived");
    expect(useProjectStore.getState().savedProjects.some((project) => project.id === "p-archived")).toBe(true);
  });
});
