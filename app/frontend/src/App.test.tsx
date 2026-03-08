// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./lib/api", () => ({
  compareProjectsRequest: vi.fn(),
  deleteProjectRequest: vi.fn(),
  exportWorkspaceRequest: vi.fn(),
  exportReportRequest: vi.fn(),
  importWorkspaceRequest: vi.fn(),
  listProjectsRequest: vi.fn(),
  loadProjectHistoryRequest: vi.fn(),
  loadProjectRevisionsRequest: vi.fn(),
  loadProjectRequest: vi.fn(),
  recordProjectAnalysisRequest: vi.fn(),
  recordProjectExportRequest: vi.fn(),
  requestDiagnostics: vi.fn(),
  requestHealth: vi.fn(),
  requestAnalysis: vi.fn(),
  saveProjectRequest: vi.fn()
}));

import App from "./App";
import {
  type AnalysisResponse,
  compareProjectsRequest,
  deleteProjectRequest,
  exportWorkspaceRequest,
  exportReportRequest,
  importWorkspaceRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRevisionsRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestDiagnostics,
  requestHealth,
  requestAnalysis,
  saveProjectRequest
} from "./lib/api";
import {
  buildApiPayload,
  buildDraftTransferFile,
  browserDraftStorageKey,
  cloneInitialState,
  type FullPayload
} from "./lib/experiment";
import { changeFiles, changeValue, click, findButton, findButtonByAriaLabel, flushEffects, renderIntoDocument } from "./test/dom";

function buildAnalysisResult(adviceAvailable = false): AnalysisResponse {
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
      available: adviceAvailable,
      provider: "local_orchestrator",
      model: adviceAvailable ? "Claude Sonnet 4.6" : "offline",
      advice: adviceAvailable
        ? {
            brief_assessment: "The experiment is feasible with careful monitoring.",
            key_risks: ["Tracking quality may skew results."],
            design_improvements: ["Validate assignment logging before launch."],
            metric_recommendations: ["Track checkout step completion by segment."],
            interpretation_pitfalls: ["Do not over-read the first 48 hours."],
            additional_checks: ["Verify exposure balance by traffic source."]
          }
        : null,
      raw_text: null,
      error: adviceAvailable ? null : "offline",
      error_code: adviceAvailable ? null : "request_error"
    }
  };
}

function buildLoadedPayload(): FullPayload {
  const state = cloneInitialState();
  state.project.project_name = "Loaded experiment";
  state.constraints.legal_or_ethics_constraints = "legal review required";
  state.constraints.deadline_pressure = "high";
  return state;
}

function buildProjectHistory(projectId = "p-1") {
  return {
    project_id: projectId,
    analysis_total: 1,
    analysis_limit: 3,
    analysis_offset: 0,
    export_total: 1,
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
          warnings_count: 1,
          advice_available: false
        },
        analysis: buildAnalysisResult()
      }
    ],
    export_events: [
      {
        id: "export-1",
        project_id: projectId,
        analysis_run_id: "run-1",
        format: "markdown" as const,
        created_at: "2026-03-07T12:45:00Z"
      }
    ]
  };
}

function buildProjectRevisions(projectId = "p-1") {
  return {
    project_id: projectId,
    total: 2,
    limit: 3,
    offset: 0,
    revisions: [
      {
        id: "rev-2",
        project_id: projectId,
        source: "update" as const,
        created_at: "2026-03-07T12:10:00Z",
        payload: buildApiPayload({
          ...buildLoadedPayload(),
          project: {
            ...buildLoadedPayload().project,
            project_name: "Loaded experiment v2"
          }
        })
      },
      {
        id: "rev-1",
        project_id: projectId,
        source: "create" as const,
        created_at: "2026-03-07T10:00:00Z",
        payload: buildApiPayload(buildLoadedPayload())
      }
    ]
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
      db_exists: true,
      schema_version: 2,
      sqlite_user_version: 2,
      busy_timeout_ms: 5000,
      journal_mode: "WAL",
      synchronous: "NORMAL",
      projects_total: 2,
      analysis_runs_total: 3,
      export_events_total: 1,
      project_revisions_total: 2,
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
      accepted_headers: ["Authorization: Bearer", "X-API-Key"]
    }
  };
}

function buildProjectComparison() {
  return {
    base_project: {
      id: "p-1",
      project_name: "Stored checkout test",
      updated_at: "2026-03-07T10:00:00Z",
      analysis_created_at: "2026-03-07T12:30:00Z",
      last_analysis_at: "2026-03-07T12:30:00Z",
      analysis_run_id: "run-1",
      metric_type: "binary",
      primary_metric: "purchase_conversion",
      sample_size_per_variant: 100,
      total_sample_size: 300,
      estimated_duration_days: 12,
      warnings_count: 1,
      warning_codes: ["SEASONALITY_PRESENT"],
      risk_highlights: ["tracking quality"],
      assumptions: ["Baseline is stable"],
      advice_available: false,
      executive_summary: "Stored checkout summary",
      warning_severity: "medium",
      recommendation_highlights: ["Verify tracking", "Watch SRM"]
    },
    candidate_project: {
      id: "p-2",
      project_name: "Pricing challenger",
      updated_at: "2026-03-07T11:00:00Z",
      analysis_created_at: "2026-03-07T13:00:00Z",
      last_analysis_at: "2026-03-07T13:00:00Z",
      analysis_run_id: "run-2",
      metric_type: "binary",
      primary_metric: "purchase_conversion",
      sample_size_per_variant: 140,
      total_sample_size: 360,
      estimated_duration_days: 15,
      warnings_count: 2,
      warning_codes: ["LONG_DURATION", "LOW_TRAFFIC"],
      risk_highlights: ["tracking quality"],
      assumptions: ["Baseline is stable"],
      advice_available: false,
      executive_summary: "Pricing challenger summary",
      warning_severity: "high",
      recommendation_highlights: ["Validate traffic quality", "Watch SRM"]
    },
    deltas: {
      sample_size_per_variant: 40,
      total_sample_size: 60,
      estimated_duration_days: 3,
      warnings_count: 1
    },
    shared_warning_codes: [],
    base_only_warning_codes: ["SEASONALITY_PRESENT"],
    candidate_only_warning_codes: ["LONG_DURATION", "LOW_TRAFFIC"],
    shared_assumptions: ["Baseline is stable"],
    base_only_assumptions: [],
    candidate_only_assumptions: [],
    shared_risk_highlights: ["tracking quality"],
    base_only_risk_highlights: [],
    candidate_only_risk_highlights: [],
    metric_alignment_note: "Both snapshots evaluate the same primary metric and metric family.",
    highlights: [
      "Pricing challenger changes total sample size by +60 and estimated duration by +3 days versus Stored checkout test.",
      "Both snapshots evaluate the same primary metric and metric family."
    ],
    summary: "Pricing challenger needs larger total sample size and a longer test window than Stored checkout test."
  };
}

function buildWorkspaceBundle() {
  return {
    schema_version: 1,
    generated_at: "2026-03-09T00:30:00Z",
    projects: [
      {
        id: "project-1",
        project_name: "Workspace project",
        payload_schema_version: 1,
        last_analysis_at: "2026-03-09T00:20:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: "2026-03-09T00:25:00Z",
        created_at: "2026-03-09T00:10:00Z",
        updated_at: "2026-03-09T00:25:00Z",
        payload: buildApiPayload(cloneInitialState())
      }
    ],
    analysis_runs: [
      {
        id: "run-1",
        project_id: "project-1",
        created_at: "2026-03-09T00:20:00Z",
        analysis: buildAnalysisResult()
      }
    ],
    export_events: [
      {
        id: "export-1",
        project_id: "project-1",
        analysis_run_id: "run-1",
        format: "markdown" as const,
        created_at: "2026-03-09T00:25:00Z"
      }
    ],
    project_revisions: [
      {
        id: "rev-1",
        project_id: "project-1",
        source: "create" as const,
        created_at: "2026-03-09T00:10:00Z",
        payload: buildApiPayload(cloneInitialState())
      }
    ]
  };
}

describe("App UI flow", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:test"),
      revokeObjectURL: vi.fn()
    });
    window.localStorage.clear();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(compareProjectsRequest).mockReset();
    vi.mocked(deleteProjectRequest).mockReset();
    vi.mocked(exportWorkspaceRequest).mockReset();
    vi.mocked(importWorkspaceRequest).mockReset();
    vi.mocked(listProjectsRequest).mockResolvedValue([]);
    vi.mocked(loadProjectHistoryRequest).mockReset();
    vi.mocked(loadProjectHistoryRequest).mockResolvedValue({
      project_id: "p-1",
      analysis_total: 0,
      analysis_limit: 3,
      analysis_offset: 0,
      export_total: 0,
      export_limit: 3,
      export_offset: 0,
      analysis_runs: [],
      export_events: []
    });
    vi.mocked(loadProjectRevisionsRequest).mockReset();
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValue({
      project_id: "p-1",
      total: 0,
      limit: 3,
      offset: 0,
      revisions: []
    });
    vi.mocked(loadProjectRequest).mockReset();
    vi.mocked(recordProjectAnalysisRequest).mockReset();
    vi.mocked(recordProjectExportRequest).mockReset();
    vi.mocked(requestDiagnostics).mockResolvedValue(buildDiagnostics());
    vi.mocked(requestHealth).mockResolvedValue({
      status: "ok",
      service: "AB Test Research Designer API",
      version: "0.1.0",
      environment: "local"
    });
    vi.mocked(requestAnalysis).mockReset();
    vi.mocked(saveProjectRequest).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("loads saved projects on startup and can hydrate a selected project", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        revision_count: 2,
        last_revision_at: "2026-03-07T10:15:00Z",
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      revision_count: 2,
      last_revision_at: "2026-03-07T10:15:00Z",
      last_analysis_at: "2026-03-07T10:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: "2026-03-07T11:00:00Z",
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory("p-1"));
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions("p-1"));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Backend status");
      expect(view.container.textContent).toContain("API online");
      expect(view.container.textContent).toContain("AB Test Research Designer API");
      expect(view.container.textContent).toContain("Runtime diagnostics");
      expect(view.container.textContent).toContain("Storage:");
      expect(view.container.textContent).toContain("Timing headers:");
      expect(view.container.textContent).toContain("Stored checkout test");

      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      expect(view.container.textContent).toContain("Loaded project Stored checkout test into the wizard.");
      expect((view.container.querySelector("#project-project_name") as HTMLInputElement).value).toBe("Loaded experiment");
      expect(view.container.textContent).toContain("Project id: p-1");
      expect(view.container.textContent).toContain("All changes saved locally.");
      expect(view.container.textContent).toContain("In sync with SQLite");
      expect(view.container.textContent).toContain("Last analysis:");
      expect(view.container.textContent).toContain("Last export:");
      expect(view.container.textContent).toContain("Snapshot stored:");
      expect(view.container.textContent).toContain("Saved revisions:");
      expect(view.container.textContent).toContain("Recent project history");
      expect(view.container.textContent).toContain("Saved revisions");
      expect(view.container.textContent).toContain("Showing 1 of 1 analysis run(s) and 1 of 1 export event(s).");
      expect(view.container.textContent).toContain("linked snapshot");

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "Loaded experiment v2");
      await flushEffects();

      expect(view.container.textContent).toContain("Unsaved changes pending local update.");
      expect(view.container.textContent).toContain("Needs local update");
    } finally {
      await view.unmount();
    }
  });

  it("loads saved project revisions and can restore one into the wizard", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        revision_count: 2,
        last_revision_at: "2026-03-07T12:10:00Z",
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T12:10:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      revision_count: 2,
      last_revision_at: "2026-03-07T12:10:00Z",
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T12:10:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory("p-1"));
    vi.mocked(loadProjectRevisionsRequest).mockResolvedValueOnce(buildProjectRevisions("p-1"));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      expect(view.container.textContent).toContain("Showing 2 of 2 revision(s).");

      await click(findButton(view.container, "Load into wizard"));
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Loaded experiment v2");
      expect(view.container.textContent).toContain("Loaded update revision");
      expect(view.container.textContent).toContain("Needs local update");
    } finally {
      await view.unmount();
    }
  });

  it("filters saved projects in the sidebar by search query", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      },
      {
        id: "p-2",
        project_name: "Pricing experiment",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T11:00:00Z",
        updated_at: "2026-03-07T11:00:00Z"
      }
    ]);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const searchInput = view.container.querySelector("#saved-projects-search");
      if (!(searchInput instanceof HTMLInputElement)) {
        throw new Error("Saved projects search input was not rendered");
      }

      expect(view.container.textContent).toContain("Stored checkout test");
      expect(view.container.textContent).toContain("Pricing experiment");

      await changeValue(searchInput, "pricing");
      await flushEffects();

      expect(view.container.textContent).not.toContain("Stored checkout test");
      expect(view.container.textContent).toContain("Pricing experiment");
      expect(view.container.textContent).toContain("Showing 1 of 2 saved projects.");
    } finally {
      await view.unmount();
    }
  });

  it("exports the full workspace bundle from the sidebar", async () => {
    vi.mocked(exportWorkspaceRequest).mockResolvedValueOnce(buildWorkspaceBundle());

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Export workspace JSON"));
      await flushEffects();

      expect(exportWorkspaceRequest).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("Exported workspace backup with 1 project(s).");
    } finally {
      await view.unmount();
    }
  });

  it("imports a workspace backup and refreshes saved projects", async () => {
    vi.mocked(importWorkspaceRequest).mockResolvedValueOnce({
      status: "imported",
      imported_projects: 1,
      imported_analysis_runs: 1,
      imported_export_events: 1,
      imported_project_revisions: 1
    });
    vi.mocked(listProjectsRequest)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "p-imported",
          project_name: "Imported workspace project",
          payload_schema_version: 1,
          last_analysis_at: null,
          last_analysis_run_id: null,
          last_exported_at: null,
          has_analysis_snapshot: false,
          created_at: "2026-03-09T00:10:00Z",
          updated_at: "2026-03-09T00:10:00Z"
        }
      ]);

    const file = new File([JSON.stringify(buildWorkspaceBundle())], "workspace-backup.json", {
      type: "application/json"
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const input = view.container.parentElement?.querySelector('input[type="file"][aria-label="Import workspace file"]');
      if (!(input instanceof HTMLInputElement)) {
        throw new Error("Workspace import input was not rendered");
      }

      await changeFiles(input, [file]);
      await flushEffects();

      expect(importWorkspaceRequest).toHaveBeenCalledTimes(1);
      expect(listProjectsRequest).toHaveBeenCalledTimes(2);
      expect(view.container.textContent).toContain(
        "Imported workspace backup: 1 project(s), 1 analysis run(s), 1 export event(s), 1 revision(s)."
      );
      expect(view.container.textContent).toContain("Imported workspace project");
    } finally {
      await view.unmount();
    }
  });

  it("compares the loaded project with another saved snapshot", async () => {
    const history = buildProjectHistory("p-1");
    history.analysis_total = 2;
    history.analysis_runs = [
      {
        ...history.analysis_runs[0],
        id: "run-older",
        created_at: "2026-03-07T11:15:00Z",
        summary: {
          ...history.analysis_runs[0].summary,
          total_sample_size: 260,
          estimated_duration_days: 11,
          warnings_count: 0
        }
      },
      history.analysis_runs[0]
    ];
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: "2026-03-07T12:30:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: null,
        has_analysis_snapshot: true,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      },
      {
        id: "p-2",
        project_name: "Pricing challenger",
        payload_schema_version: 1,
        last_analysis_at: "2026-03-07T13:00:00Z",
        last_analysis_run_id: "run-2",
        last_exported_at: null,
        has_analysis_snapshot: true,
        created_at: "2026-03-07T11:00:00Z",
        updated_at: "2026-03-07T11:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(history);
    vi.mocked(compareProjectsRequest).mockResolvedValueOnce(buildProjectComparison());

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();
      await click(findButton(view.container, "Open snapshot"));
      await flushEffects();

      await click(findButton(view.container, "Compare"));
      await flushEffects();

      expect(compareProjectsRequest).toHaveBeenCalledWith("p-1", "p-2", "run-older");
      expect(view.container.textContent).toContain("Viewing historical analysis");
      expect(view.container.textContent).toContain("Saved snapshot comparison");
      expect(view.container.textContent).toContain("Pricing challenger");
      expect(view.container.textContent).toContain("Candidate only: LONG_DURATION, LOW_TRAFFIC");
      expect(view.container.textContent).toContain("Assumptions overlap");
      expect(view.container.textContent).toContain("Recommendation highlights");
    } finally {
      await view.unmount();
    }
  });

  it("opens a saved analysis snapshot and exports it without rerunning analysis", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: "2026-03-07T12:30:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: null,
        has_analysis_snapshot: true,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest)
      .mockResolvedValueOnce(buildProjectHistory("p-1"))
      .mockResolvedValueOnce(buildProjectHistory("p-1"));
    vi.mocked(exportReportRequest).mockResolvedValueOnce("# Historical Experiment Report");
    vi.mocked(recordProjectExportRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: "2026-03-07T13:00:00Z",
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();
      await click(findButton(view.container, "Open snapshot"));
      await flushEffects();
      await click(findButton(view.container, "Export Markdown"));
      await flushEffects();

      expect(exportReportRequest).toHaveBeenCalledWith(
        buildProjectHistory("p-1").analysis_runs[0].analysis.report,
        "markdown"
      );
      expect(recordProjectExportRequest).toHaveBeenCalledWith("p-1", "markdown", "run-1");
      expect(view.container.textContent).toContain("Viewing historical analysis");
    } finally {
      await view.unmount();
    }
  });

  it("shows backend health errors when the API is unavailable", async () => {
    vi.mocked(requestHealth).mockRejectedValueOnce(new Error("fetch failed"));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Backend status");
      expect(view.container.textContent).toContain("API unavailable. fetch failed");
    } finally {
      await view.unmount();
    }
  });

  it("shows backend diagnostics errors when the diagnostics endpoint is unavailable", async () => {
    vi.mocked(requestDiagnostics).mockRejectedValueOnce(new Error("diagnostics failed"));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Runtime diagnostics");
      expect(view.container.textContent).toContain("Diagnostics unavailable. diagnostics failed");
    } finally {
      await view.unmount();
    }
  });

  it("restores an unsaved browser draft on startup", async () => {
    const restored = buildLoadedPayload();
    restored.project.project_name = "Browser draft";

    window.localStorage.setItem(
      browserDraftStorageKey,
      JSON.stringify(buildDraftTransferFile(restored))
    );

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Restored unsaved browser draft.");
      expect((view.container.querySelector("#project-project_name") as HTMLInputElement).value).toBe("Browser draft");
    } finally {
      await view.unmount();
    }
  });

  it("deletes a saved project from the sidebar and keeps the current form as draft", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(deleteProjectRequest).mockResolvedValueOnce({ id: "p-1", deleted: true });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Delete Stored checkout test"));
      await flushEffects();

      expect(window.confirm).toHaveBeenCalledWith('Delete project "Stored checkout test" from local storage?');
      expect(deleteProjectRequest).toHaveBeenCalledWith("p-1");
      expect(view.container.textContent).toContain("Project Stored checkout test deleted. Current form remains as a new local draft.");
      expect(view.container.textContent).not.toContain("Project id: p-1");
      expect(view.container.querySelector('button[aria-label="Delete Stored checkout test"]')).toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("does not delete a project when the confirmation dialog is rejected", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(window.confirm).mockReturnValueOnce(false);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Delete Stored checkout test"));
      await flushEffects();

      expect(deleteProjectRequest).not.toHaveBeenCalled();
      expect(view.container.querySelector('button[aria-label="Delete Stored checkout test"]')).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("autosaves form changes into browser local storage", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "Autosaved checkout");
      await flushEffects();

      const stored = window.localStorage.getItem(browserDraftStorageKey);
      expect(stored).toBeTruthy();
      expect(stored).toContain("Autosaved checkout");
    } finally {
      await view.unmount();
    }
  });

  it("surfaces localStorage persistence failures instead of swallowing them silently", async () => {
    const quotaError = new Error("Quota exceeded");
    quotaError.name = "QuotaExceededError";
    const setItemSpy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw quotaError;
      });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "Quota warning");
      await flushEffects();

      expect(setItemSpy).toHaveBeenCalled();
      expect(view.container.textContent).toContain("Storage full - draft not saved. Clear old data or use Export.");
    } finally {
      setItemSpy.mockRestore();
      await view.unmount();
    }
  });

  it("clears a localStorage warning after a later successful autosave", async () => {
    const quotaError = new Error("Quota exceeded");
    quotaError.name = "QuotaExceededError";
    let saveAttempt = 0;
    const setItemSpy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        saveAttempt += 1;
        if (saveAttempt === 2) {
          throw quotaError;
        }
      });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "First failing save");
      await flushEffects();

      expect(view.container.textContent).toContain("Storage full - draft not saved. Clear old data or use Export.");

      await changeValue(projectNameInput, "Second successful save");
      await flushEffects();

      expect(setItemSpy).toHaveBeenCalled();
      expect(view.container.textContent).not.toContain("Storage full - draft not saved. Clear old data or use Export.");
    } finally {
      setItemSpy.mockRestore();
      await view.unmount();
    }
  });

  it("keeps generic storage error details for non-quota localStorage failures", async () => {
    const setItemSpy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("Storage backend unavailable");
      });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "Generic storage warning");
      await flushEffects();

      expect(view.container.textContent).toContain(
        "Browser draft could not be saved locally: Storage backend unavailable"
      );
    } finally {
      setItemSpy.mockRestore();
      await view.unmount();
    }
  });

  it("updates the sidebar immediately after saving without reloading the project list", async () => {
    vi.mocked(saveProjectRequest).mockResolvedValueOnce({
      id: "p-new",
      project_name: "Checkout redesign",
      payload_schema_version: 1,
      last_analysis_at: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T12:00:00Z",
      updated_at: "2026-03-07T12:00:00Z",
      payload: buildApiPayload(cloneInitialState())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      await click(findButton(view.container, "Save project"));
      await flushEffects();

      expect(saveProjectRequest).toHaveBeenCalledTimes(1);
      expect(listProjectsRequest).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("Project saved locally with id p-new.");
      expect(view.container.textContent).toContain("Checkout redesign");
      expect(view.container.textContent).toContain("Project id: p-new");
    } finally {
      await view.unmount();
    }
  });

  it("keeps optional expected uplift empty instead of coercing it to zero", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 3; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      const expectedUpliftInput = view.container.querySelector("#metrics-expected_uplift_pct");
      if (!(expectedUpliftInput instanceof HTMLInputElement)) {
        throw new Error("Expected uplift input was not rendered");
      }

      await changeValue(expectedUpliftInput, "");
      await flushEffects();

      expect(expectedUpliftInput.value).toBe("");
      expect(window.localStorage.getItem(browserDraftStorageKey)).toContain('"expected_uplift_pct":null');
    } finally {
      await view.unmount();
    }
  });

  it("imports a draft json file into a new local draft", async () => {
    const imported = buildLoadedPayload();
    imported.project.project_name = "Imported checkout";
    imported.setup.traffic_split = "30,70";

    const file = new File(
      [
        JSON.stringify(buildDraftTransferFile(imported))
      ],
      "imported-draft.json",
      { type: "application/json" }
    );

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const input = view.container.parentElement?.querySelector('input[type="file"][aria-label="Import draft file"]');
      if (!(input instanceof HTMLInputElement)) {
        throw new Error("Draft import input was not rendered");
      }

      await changeFiles(input, [file]);
      await flushEffects();

      expect(view.container.textContent).toContain(
        "Imported draft from imported-draft.json. Save it to create a new local project record."
      );
      expect((view.container.querySelector("#project-project_name") as HTMLInputElement).value).toBe("Imported checkout");
      expect(view.container.textContent).toContain("Working on a new draft");
      expect(view.container.textContent).not.toContain("Project id:");
    } finally {
      await view.unmount();
    }
  });

  it("reaches the review step and renders the full deterministic report after analysis", async () => {
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult());

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      expect(view.container.textContent).toContain("Review inputs");
      expect(view.container.textContent).toContain("Legal / ethics constraints: none");
      expect(view.container.textContent).toContain("Deadline pressure: medium");

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(requestAnalysis).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("Analysis completed.");
      expect(view.container.textContent).toContain("Deterministic summary");
      expect(view.container.textContent).toContain("Variant and rollout structure");
      expect(view.container.textContent).toContain("new checkout");
      expect(view.container.textContent).toContain("Primary, secondary, and guardrail coverage");
      expect(view.container.textContent).toContain("payment_error_rate");
      expect(view.container.textContent).toContain("Statistical and operational considerations");
      expect(view.container.textContent).toContain("legacy event logging");
      expect(view.container.textContent).toContain("During test");
      expect(view.container.textContent).toContain("Watch SRM");
      expect(view.container.textContent).toContain("After test");
      expect(view.container.textContent).toContain("Segment the result");
    } finally {
      await view.unmount();
    }
  });

  it("records an analysis snapshot for a saved project that is in sync", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest)
      .mockResolvedValueOnce({
        project_id: "p-1",
        analysis_total: 0,
        analysis_limit: 3,
        analysis_offset: 0,
        export_total: 0,
        export_limit: 3,
        export_offset: 0,
        analysis_runs: [],
        export_events: []
      })
      .mockResolvedValueOnce(buildProjectHistory("p-1"));
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult());
    vi.mocked(recordProjectAnalysisRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(recordProjectAnalysisRequest).toHaveBeenCalledTimes(1);
      expect(recordProjectAnalysisRequest).toHaveBeenCalledWith("p-1", expect.any(Object));
      expect(loadProjectHistoryRequest).toHaveBeenCalledWith("p-1", { analysisLimit: 3, exportLimit: 3 });
      expect(view.container.textContent).toContain("Analysis completed and the latest snapshot was recorded for this saved project.");
      expect(view.container.textContent).toContain("Snapshot stored: Yes");
    } finally {
      await view.unmount();
    }
  });

  it("records analysis history after saving a draft that was analyzed before persistence", async () => {
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult());
    vi.mocked(saveProjectRequest).mockResolvedValueOnce({
      id: "p-new",
      project_name: "Checkout redesign",
      payload_schema_version: 1,
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T12:00:00Z",
      updated_at: "2026-03-07T12:00:00Z",
      payload: buildApiPayload(cloneInitialState())
    });
    vi.mocked(recordProjectAnalysisRequest).mockResolvedValueOnce({
      id: "p-new",
      project_name: "Checkout redesign",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T12:00:00Z",
      updated_at: "2026-03-07T12:00:00Z",
      payload: buildApiPayload(cloneInitialState())
    });
    vi.mocked(loadProjectHistoryRequest).mockResolvedValueOnce(buildProjectHistory("p-new"));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();
      await click(findButton(view.container, "Save project"));
      await flushEffects();

      expect(saveProjectRequest).toHaveBeenCalledTimes(1);
      expect(recordProjectAnalysisRequest).toHaveBeenCalledWith("p-new", expect.any(Object));
      expect(view.container.textContent).toContain("Latest analysis snapshot was recorded for this saved project.");
      expect(view.container.textContent).toContain("Project id: p-new");
    } finally {
      await view.unmount();
    }
  });

  it("links export metadata to the latest saved analysis run", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        last_analysis_at: null,
        last_analysis_run_id: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(loadProjectHistoryRequest)
      .mockResolvedValueOnce({
        project_id: "p-1",
        analysis_total: 0,
        analysis_limit: 3,
        analysis_offset: 0,
        export_total: 0,
        export_limit: 3,
        export_offset: 0,
        analysis_runs: [],
        export_events: []
      })
      .mockResolvedValueOnce(buildProjectHistory("p-1"))
      .mockResolvedValueOnce(buildProjectHistory("p-1"));
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult());
    vi.mocked(recordProjectAnalysisRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });
    vi.mocked(exportReportRequest).mockResolvedValueOnce("# Experiment Report");
    vi.mocked(recordProjectExportRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      last_analysis_at: "2026-03-07T12:30:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: "2026-03-07T12:45:00Z",
      has_analysis_snapshot: true,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:00:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();
      await click(findButton(view.container, "Export Markdown"));
      await flushEffects();

      expect(recordProjectExportRequest).toHaveBeenCalledWith("p-1", "markdown", "run-1");
      expect(view.container.textContent).toContain("updated project export metadata");
    } finally {
      await view.unmount();
    }
  });

  it("shows std dev only for continuous metrics and hides it from binary review", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 3; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      expect(view.container.querySelector("#metrics-std_dev")).toBeNull();

      const metricType = view.container.querySelector("#metrics-metric_type");
      if (!(metricType instanceof HTMLSelectElement)) {
        throw new Error("Metric type select was not rendered");
      }

      await changeValue(metricType, "continuous");
      await flushEffects();

      const stdDevInput = view.container.querySelector("#metrics-std_dev");
      if (!(stdDevInput instanceof HTMLInputElement)) {
        throw new Error("Std dev input was not rendered for continuous metrics");
      }

      await changeValue(stdDevInput, "12");
      await flushEffects();

      await changeValue(metricType, "binary");
      await flushEffects();

      expect(view.container.querySelector("#metrics-std_dev")).toBeNull();
      expect(window.localStorage.getItem(browserDraftStorageKey)).toContain('"std_dev":null');

      for (let stepIndex = 0; stepIndex < 2; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      expect(view.container.textContent).toContain("Review inputs");
      expect(view.container.textContent).not.toContain("Std dev:");
    } finally {
      await view.unmount();
    }
  });

  it("shows validation errors in review instead of calling analysis for an invalid form", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "");

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(requestAnalysis).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("Fix these fields before saving or running analysis:");
      expect(view.container.textContent).toContain("Project name is required.");
    } finally {
      await view.unmount();
    }
  });

  it("renders the full AI advice payload when the orchestrator response is available", async () => {
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult(true));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(view.container.textContent).toContain("Provider: local_orchestrator | Model: Claude Sonnet 4.6");
      expect(view.container.textContent).toContain("The experiment is feasible with careful monitoring.");
      expect(view.container.textContent).toContain("Tracking quality may skew results.");
      expect(view.container.textContent).toContain("Track checkout step completion by segment.");
      expect(view.container.textContent).toContain("Do not over-read the first 48 hours.");
      expect(view.container.textContent).toContain("Verify exposure balance by traffic source.");
    } finally {
      await view.unmount();
    }
  });
});
