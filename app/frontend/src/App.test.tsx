// @vitest-environment jsdom

import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("./lib/api", () => ({
  archiveProjectRequest: vi.fn(),
  clearAdminSessionToken: vi.fn(),
  clearApiSessionToken: vi.fn(),
  compareMultipleProjectsRequest: vi.fn(),
  compareProjectsRequest: vi.fn(),
  createApiKeyRequest: vi.fn(),
  deleteApiKeyRequest: vi.fn(),
  exportAuditLogRequest: vi.fn(),
  downloadProjectReportDataRequest: vi.fn(),
  downloadProjectReportPdfRequest: vi.fn(),
  deleteProjectRequest: vi.fn(),
  exportWorkspaceRequest: vi.fn(),
  exportReportRequest: vi.fn(),
  hasAdminSessionToken: vi.fn(),
  hasApiSessionToken: vi.fn(),
  importWorkspaceRequest: vi.fn(),
  listApiKeysRequest: vi.fn(),
  listAuditLogRequest: vi.fn(),
  listTemplatesRequest: vi.fn(),
  revokeApiKeyRequest: vi.fn(),
  restoreProjectRequest: vi.fn(),
  setAdminSessionToken: vi.fn(),
  setApiSessionToken: vi.fn(),
  useTemplateRequest: vi.fn(),
  validateWorkspaceRequest: vi.fn(),
  listProjectsRequest: vi.fn(),
  loadProjectHistoryRequest: vi.fn(),
  loadProjectRevisionsRequest: vi.fn(),
  loadProjectRequest: vi.fn(),
  recordProjectAnalysisRequest: vi.fn(),
  recordProjectExportRequest: vi.fn(),
  requestCalculation: vi.fn(),
  requestDiagnostics: vi.fn(),
  requestHealth: vi.fn(),
  requestAnalysis: vi.fn(),
  saveProjectRequest: vi.fn()
}));

import App from "./App";
import Accordion from "./components/Accordion";
import WizardDraftStep from "./components/WizardDraftStep";
import {
  type AnalysisResponse,
  archiveProjectRequest,
  clearAdminSessionToken,
  clearApiSessionToken,
  compareProjectsRequest,
  createApiKeyRequest,
  deleteApiKeyRequest,
  exportAuditLogRequest,
  downloadProjectReportDataRequest,
  downloadProjectReportPdfRequest,
  deleteProjectRequest,
  exportWorkspaceRequest,
  exportReportRequest,
  importWorkspaceRequest,
  hasAdminSessionToken,
  listAuditLogRequest,
  listApiKeysRequest,
  listTemplatesRequest,
  hasApiSessionToken,
  revokeApiKeyRequest,
  restoreProjectRequest,
  setAdminSessionToken,
  setApiSessionToken,
  useTemplateRequest,
  validateWorkspaceRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRevisionsRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestCalculation,
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
  sections,
  type FullPayload
} from "./lib/experiment";
import { changeFiles, changeValue, click, findButton, findButtonByAriaLabel, flushEffects, renderIntoDocument } from "./test/dom";

const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";
const themeStorageKey = "ab-test-research-designer:theme:v1";

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
      guardrail_metrics: [
        {
          name: "Payment error rate",
          metric_type: "binary",
          baseline: 2.4,
          detectable_mde_pp: 0.321,
          note: "With N=100 per variant, can detect >= 0.32 pp change at 80% power"
        }
      ],
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

function buildReadonlyDiagnostics() {
  return {
    ...buildDiagnostics(),
    auth: {
      enabled: true,
      mode: "readonly",
      write_enabled: false,
      readonly_enabled: true,
      accepted_headers: ["Authorization: Bearer", "X-API-Key"],
      read_only_methods: ["GET", "HEAD", "OPTIONS"]
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

function buildWorkspaceBundle(options: { signed?: boolean } = {}) {
  return {
    schema_version: 3,
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
    ],
    integrity: {
      counts: {
        projects: 1,
        analysis_runs: 1,
        export_events: 1,
        project_revisions: 1
      },
      checksum_sha256: "a".repeat(64),
      signature_hmac_sha256: options.signed ? "b".repeat(64) : undefined
    }
  };
}

function buildTemplateRecord(
  overrides: Partial<{
    id: string;
    name: string;
    category: string;
    description: string;
    built_in: boolean;
    tags: string[];
    usage_count: number;
  }> = {}
) {
  const payload = buildApiPayload(cloneInitialState());
  payload.project.project_name = "";

  return {
    id: overrides.id ?? "checkout_conversion",
    name: overrides.name ?? "Checkout Conversion",
    category: overrides.category ?? "Revenue",
    description: overrides.description ?? "Test checkout changes against conversion.",
    built_in: overrides.built_in ?? true,
    payload,
    tags: overrides.tags ?? ["binary", "checkout"],
    usage_count: overrides.usage_count ?? 0
  };
}

function buildAuditLogResponse(projectId = "p-1") {
  return {
    total: 2,
    entries: [
      {
        id: 2,
        ts: "2026-03-07T12:45:00Z",
        action: "project.update",
        project_id: projectId,
        project_name: "Stored checkout test",
        actor: "api_key:rw",
        request_id: "req-2",
        payload_diff: {
          "metrics.mde_pct": [5, 7] as [number, number]
        },
        ip_address: "127.0.0.1"
      },
      {
        id: 1,
        ts: "2026-03-07T12:30:00Z",
        action: "project.create",
        project_id: projectId,
        project_name: "Stored checkout test",
        actor: "api_key:rw",
        request_id: "req-1",
        payload_diff: null,
        ip_address: "127.0.0.1"
      }
    ]
  };
}

type AppView = Awaited<ReturnType<typeof renderIntoDocument>>;

async function startNewExperiment(view: AppView) {
  await click(findButton(view.container, "New experiment"));
  await flushEffects();
}

async function loadExample(view: AppView) {
  await click(findButton(view.container, "Load example"));
  await flushEffects();
}

async function openSystemTab(view: AppView) {
  await click(findButton(view.container, "System"));
  await flushEffects();
}

describe("App UI flow", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:test"),
      revokeObjectURL: vi.fn()
    });
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.mocked(hasAdminSessionToken).mockImplementation(
      () => window.sessionStorage.getItem("ab-test-research-designer:admin-token:v1") !== null
    );
    vi.mocked(hasApiSessionToken).mockImplementation(
      () => window.sessionStorage.getItem(apiSessionTokenStorageKey) !== null
    );
    vi.mocked(setAdminSessionToken).mockImplementation((token: string) => {
      window.sessionStorage.setItem("ab-test-research-designer:admin-token:v1", token.trim());
    });
    vi.mocked(setApiSessionToken).mockImplementation((token: string) => {
      window.sessionStorage.setItem(apiSessionTokenStorageKey, token.trim());
    });
    vi.mocked(clearAdminSessionToken).mockImplementation(() => {
      window.sessionStorage.removeItem("ab-test-research-designer:admin-token:v1");
    });
    vi.mocked(clearApiSessionToken).mockImplementation(() => {
      window.sessionStorage.removeItem(apiSessionTokenStorageKey);
    });
    vi.mocked(compareProjectsRequest).mockReset();
    vi.mocked(createApiKeyRequest).mockReset();
    vi.mocked(deleteApiKeyRequest).mockReset();
    vi.mocked(exportAuditLogRequest).mockReset();
    vi.mocked(downloadProjectReportDataRequest).mockReset();
    vi.mocked(archiveProjectRequest).mockReset();
    vi.mocked(downloadProjectReportPdfRequest).mockReset();
    vi.mocked(deleteProjectRequest).mockReset();
    vi.mocked(exportWorkspaceRequest).mockReset();
    vi.mocked(importWorkspaceRequest).mockReset();
    vi.mocked(listApiKeysRequest).mockReset();
    vi.mocked(listAuditLogRequest).mockResolvedValue(buildAuditLogResponse());
    vi.mocked(listTemplatesRequest).mockResolvedValue([]);
    vi.mocked(revokeApiKeyRequest).mockReset();
    vi.mocked(restoreProjectRequest).mockReset();
    vi.mocked(validateWorkspaceRequest).mockReset();
    vi.mocked(useTemplateRequest).mockReset();
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
    vi.mocked(requestCalculation).mockReset();
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
    window.sessionStorage.clear();
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("shows onboarding first, keeps Projects active by default, and moves diagnostics behind the System tab", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Plan your A/B experiment");
      expect(view.container.textContent).toContain("Deterministic calculations. Local-first. No cloud required.");
      expect(view.container.textContent).toContain("New experiment");
      expect(view.container.textContent).toContain("Load example");
      expect(view.container.textContent).toContain("Import project");
      expect(view.container.textContent).toContain("Saved projects");
      expect(view.container.textContent).not.toContain("Runtime diagnostics");
      expect(view.container.textContent).not.toContain("How this UI is split");

      await openSystemTab(view);

      expect(view.container.textContent).toContain("Backend status");
      expect(view.container.textContent).toContain("Runtime diagnostics");
      expect(view.container.textContent).toContain("API session token");
    } finally {
      await view.unmount();
    }
  });

  it("renders a skip link before the app shell and exposes the main region", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const firstElement = view.container.firstElementChild;
      if (!(firstElement instanceof HTMLAnchorElement)) {
        throw new Error("Skip link was not rendered as the first element");
      }

      expect(firstElement.getAttribute("href")).toBe("#main-content");
      expect(firstElement.textContent).toBe("Skip to main content");

      const mainRegion = view.container.querySelector("#main-content");
      if (!(mainRegion instanceof HTMLElement)) {
        throw new Error("Main region was not rendered");
      }

      expect(mainRegion.tagName).toBe("MAIN");
      expect(mainRegion.getAttribute("tabindex")).toBe("-1");
    } finally {
      await view.unmount();
    }
  });

  it("moves focus to the current step heading when the wizard step changes", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      let stepHeading = view.container.querySelector("h2");
      if (!(stepHeading instanceof HTMLHeadingElement)) {
        throw new Error("Step heading was not rendered");
      }

      expect(document.activeElement).toBe(stepHeading);

      await click(findButton(view.container, "Next"));
      await flushEffects();

      stepHeading = view.container.querySelector("h2");
      if (!(stepHeading instanceof HTMLHeadingElement)) {
        throw new Error("Updated step heading was not rendered");
      }

      expect(stepHeading.textContent).toBe("Hypothesis");
      expect(document.activeElement).toBe(stepHeading);
    } finally {
      await view.unmount();
    }
  });

  it("opens the template gallery and applies a built-in template to the wizard", async () => {
    vi.mocked(listTemplatesRequest).mockResolvedValueOnce([
      buildTemplateRecord(),
      buildTemplateRecord({ id: "onboarding_completion", name: "Onboarding Completion", category: "Engagement" }),
      buildTemplateRecord({ id: "pricing_sensitivity", name: "Pricing Sensitivity" }),
      buildTemplateRecord({ id: "feature_adoption", name: "Feature Adoption" }),
      buildTemplateRecord({ id: "latency_impact", name: "Latency Impact", category: "Performance" })
    ]);
    vi.mocked(useTemplateRequest).mockResolvedValueOnce(buildTemplateRecord({ usage_count: 1 }));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await startNewExperiment(view);

      const initialProjectName = view.container.querySelector("#project-project_name");
      if (!(initialProjectName instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(initialProjectName.value).toBe("Checkout redesign");

      await click(findButton(view.container, "Start from template"));
      await flushEffects();

      expect(document.body.textContent).toContain("Experiment templates");
      expect(document.body.textContent).toContain("Checkout Conversion");
      expect(document.body.textContent).toContain("Onboarding Completion");
      expect(document.body.textContent).toContain("Pricing Sensitivity");
      expect(document.body.textContent).toContain("Feature Adoption");
      expect(document.body.textContent).toContain("Latency Impact");

      await click(findButtonByAriaLabel(view.container, "Use template Checkout Conversion"));
      await flushEffects();

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered after template apply");
      }

      expect(projectNameInput.value).toBe("");
      expect(document.querySelector('[role="dialog"]')).toBeNull();
      expect(view.container.textContent).toContain("Template Checkout Conversion loaded into the wizard.");
    } finally {
      await view.unmount();
    }
  });

  it("exposes accordion state with linked ARIA attributes", async () => {
    const view = await renderIntoDocument(
      <Accordion title="Example section">
        <p>Accordion body</p>
      </Accordion>
    );
    try {
      await flushEffects();

      const toggle = view.container.querySelector("button");
      if (!(toggle instanceof HTMLButtonElement)) {
        throw new Error("Accordion toggle was not rendered");
      }

      expect(toggle.getAttribute("aria-expanded")).toBe("false");
      expect(toggle.id).not.toBe("");

      const panelId = toggle.getAttribute("aria-controls");
      if (!panelId) {
        throw new Error("Accordion toggle is missing aria-controls");
      }

      const panel = view.container.querySelector(`#${panelId}`);
      if (!(panel instanceof HTMLDivElement)) {
        throw new Error("Accordion panel was not rendered");
      }

      expect(panel.getAttribute("role")).toBe("region");
      expect(panel.getAttribute("aria-labelledby")).toBe(toggle.id);
      expect(panel.getAttribute("aria-hidden")).toBe("true");

      await click(toggle);
      await flushEffects();

      expect(toggle.getAttribute("aria-expanded")).toBe("true");
      expect(panel.getAttribute("aria-hidden")).toBe("false");
    } finally {
      await view.unmount();
    }
  });

  it("has no critical accessibility violations on initial render", async () => {
    document.documentElement.lang = "en";

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await flushEffects();

      const results = await axe(view.container, {
        runOnly: {
          type: "rule",
          values: ["button-name", "label", "aria-required-attr"]
        }
      });

      expect(results.violations).toHaveLength(0);
    } finally {
      await view.unmount();
    }
  });

  it("persists the selected theme and reapplies it on reload", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Dark theme"));
      await flushEffects();

      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
      expect(window.localStorage.getItem(themeStorageKey)).toBe("dark");
    } finally {
      await view.unmount();
    }

    const reloadedView = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
      expect(findButtonByAriaLabel(reloadedView.container, "Dark theme").getAttribute("aria-pressed")).toBe("true");

      await click(findButtonByAriaLabel(reloadedView.container, "System theme"));
      await flushEffects();

      expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
      expect(window.localStorage.getItem(themeStorageKey)).toBe("system");
    } finally {
      await reloadedView.unmount();
    }
  });

  it("loads the example payload from onboarding without creating a saved project", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      expect(saveProjectRequest).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("Example loaded - click Run analysis to see results");
      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Checkout redesign");
      expect(view.container.textContent).toContain("Working on a new draft");
      expect(view.container.textContent).not.toContain("Project id:");
    } finally {
      await view.unmount();
    }
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

      expect(view.container.textContent).toContain("Plan your A/B experiment");
      expect(view.container.textContent).toContain("Projects");
      expect(view.container.textContent).toContain("System");
      expect(view.container.textContent).toContain("1 saved");
      expect(view.container.textContent).toContain("1 without saved analysis");
      expect(view.container.textContent).not.toContain("Runtime diagnostics");
      expect(view.container.textContent).toContain("Stored checkout test");

      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      expect(view.container.textContent).toContain("Loaded project Stored checkout test into the wizard.");
      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Loaded experiment");
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

  it("disables mutating actions when diagnostics report a read-only api session", async () => {
    vi.mocked(requestDiagnostics).mockResolvedValueOnce(buildReadonlyDiagnostics());
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        revision_count: 2,
        last_revision_at: "2026-03-07T10:15:00Z",
        last_analysis_at: "2026-03-07T10:30:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: null,
        has_analysis_snapshot: true,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);
      await openSystemTab(view);

      expect(view.container.textContent).toContain("Read-only API");
      expect(view.container.textContent).toContain("read-only API mode for this session");
      expect(findButton(view.container, "Save project").disabled).toBe(true);
      expect(findButton(view.container, "Import workspace JSON").disabled).toBe(true);
      expect(findButton(view.container, "Export workspace JSON").disabled).toBe(false);
      expect(findButtonByAriaLabel(view.container, "Archive Stored checkout test").disabled).toBe(true);
      await click(findButton(view.container, "Save project"));
      await flushEffects();
      expect(saveProjectRequest).not.toHaveBeenCalled();

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }
      await flushEffects();

      expect(findButton(view.container, "Run analysis").disabled).toBe(true);
      await click(findButton(view.container, "Run analysis"));
      await flushEffects();
      expect(requestAnalysis).not.toHaveBeenCalled();
    } finally {
      await view.unmount();
    }
  });

  it("stores a browser-session token and rechecks backend access", async () => {
    vi.mocked(requestDiagnostics)
      .mockRejectedValueOnce(new Error("Unauthorized"))
      .mockResolvedValueOnce(buildReadonlyDiagnostics());
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([]);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await openSystemTab(view);

      const tokenInput = view.container.querySelector("#api-session-token");
      if (!(tokenInput instanceof HTMLInputElement)) {
        throw new Error("API session token input was not rendered");
      }

      await changeValue(tokenInput, "readonly-secret");
      await click(findButton(view.container, "Save token"));
      await flushEffects();

      expect(hasApiSessionToken()).toBe(true);
      expect(view.container.textContent).toContain("Token accepted, but this backend session remains read-only.");
      expect(view.container.textContent).toContain("Token configured");
    } finally {
      await view.unmount();
    }
  });

  it("filters saved projects in the sidebar by search query", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 14,
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
        hypothesis: "Pricing copy refresh will improve checkout intent.",
        metric_type: "continuous",
        duration_days: 9,
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
      await act(async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 350));
      });
      await flushEffects();

      expect(view.container.textContent).not.toContain("Stored checkout test");
      expect(view.container.textContent).toContain("Pricing experiment");
      expect(view.container.textContent).toContain("1 experiment shown.");
    } finally {
      await view.unmount();
    }
  });

  it("filters saved projects by status and metric type, then sorts by duration", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 14,
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      },
      {
        id: "p-2",
        project_name: "Pricing experiment",
        hypothesis: "Pricing copy refresh will improve checkout intent.",
        metric_type: "continuous",
        duration_days: 9,
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T11:00:00Z",
        updated_at: "2026-03-07T11:00:00Z"
      },
      {
        id: "p-3",
        project_name: "Archived checkout",
        hypothesis: "Archived hypothesis",
        metric_type: "binary",
        duration_days: 6,
        payload_schema_version: 1,
        archived_at: "2026-03-07T12:00:00Z",
        is_archived: true,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T12:00:00Z",
        updated_at: "2026-03-07T12:00:00Z"
      }
    ]);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const statusSelect = view.container.querySelector("#saved-projects-status");
      const metricTypeSelect = view.container.querySelector("#saved-projects-metric-type");
      const sortSelect = view.container.querySelector("#saved-projects-sort");
      if (!(statusSelect instanceof HTMLSelectElement) || !(metricTypeSelect instanceof HTMLSelectElement) || !(sortSelect instanceof HTMLSelectElement)) {
        throw new Error("Project filter controls were not rendered");
      }

      await changeValue(statusSelect, "all");
      await changeValue(metricTypeSelect, "binary");
      await changeValue(sortSelect, "duration_asc");
      await flushEffects();

      const projectButtons = Array.from(view.container.querySelectorAll("button"))
        .map((button) => button.textContent?.trim())
        .filter((label) => label === "Stored checkout test" || label === "Pricing experiment");
      expect(projectButtons).toEqual(["Stored checkout test"]);
      expect(view.container.textContent).toContain("Archived checkout");
      expect(view.container.textContent).not.toContain("Pricing experiment");
    } finally {
      await view.unmount();
    }
  });

  it("loads the audit log in the system tab, filters by project, and exports CSV", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 12,
        payload_schema_version: 1,
        last_analysis_at: null,
        last_analysis_run_id: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(listAuditLogRequest)
      .mockResolvedValueOnce(buildAuditLogResponse())
      .mockResolvedValueOnce(buildAuditLogResponse("p-1"));
    vi.mocked(exportAuditLogRequest).mockResolvedValueOnce({
      blob: new Blob(["ts,action"], { type: "text/csv" }),
      filename: "audit-log.csv"
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await openSystemTab(view);

      expect(view.container.textContent).toContain("Audit log");
      expect(view.container.textContent).toContain("project.update");
      expect(view.container.textContent).toContain("project.create");

      const filter = view.container.querySelector("#audit-project-filter");
      if (!(filter instanceof HTMLSelectElement)) {
        throw new Error("Audit project filter was not rendered");
      }

      await changeValue(filter, "p-1");
      await flushEffects();
      await click(findButton(view.container, "Export audit CSV"));
      await flushEffects();

      expect(listAuditLogRequest).toHaveBeenLastCalledWith({ projectId: "p-1" });
      expect(exportAuditLogRequest).toHaveBeenCalledWith({ projectId: "p-1" });
    } finally {
      await view.unmount();
    }
  });

  it("shows a project list skeleton while saved projects are loading", async () => {
    let resolveProjects: ((value: Awaited<ReturnType<typeof listProjectsRequest>>) => void) | undefined;
    const projectsPromise = new Promise<Awaited<ReturnType<typeof listProjectsRequest>>>((resolve) => {
      resolveProjects = resolve;
    });

    vi.mocked(listProjectsRequest).mockReturnValueOnce(projectsPromise);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await flushEffects();

      expect(view.container.querySelector(".project-list-skeleton")).not.toBeNull();
      expect(view.container.textContent).not.toContain("No saved projects available.");

      resolveProjects?.([]);
      await flushEffects();
      await flushEffects();
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

  it("surfaces when an exported workspace backup is signed", async () => {
    vi.mocked(exportWorkspaceRequest).mockResolvedValueOnce(buildWorkspaceBundle({ signed: true }));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Export workspace JSON"));
      await flushEffects();

      expect(view.container.textContent).toContain("Exported signed workspace backup with 1 project(s).");
    } finally {
      await view.unmount();
    }
  });

  it("imports a workspace backup and refreshes saved projects", async () => {
    vi.mocked(validateWorkspaceRequest).mockResolvedValueOnce({
      status: "valid",
      schema_version: 3,
      counts: {
        projects: 1,
        analysis_runs: 1,
        export_events: 1,
        project_revisions: 1
      },
      checksum_sha256: "a".repeat(64),
      signature_verified: false
    });
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

      expect(validateWorkspaceRequest).toHaveBeenCalledTimes(1);
      expect(importWorkspaceRequest).toHaveBeenCalledTimes(1);
      expect(listProjectsRequest).toHaveBeenCalledTimes(2);
      expect(view.container.textContent).toContain(
        "Validated workspace backup (schema v3, checksum aaaaaaaaaaaa...). Imported workspace backup: 1 project(s), 1 analysis run(s), 1 export event(s), 1 revision(s)."
      );
      expect(view.container.textContent).toContain("Imported workspace project");
    } finally {
      await view.unmount();
    }
  });

  it("mentions signature verification when importing a signed workspace backup", async () => {
    vi.mocked(validateWorkspaceRequest).mockResolvedValueOnce({
      status: "valid",
      schema_version: 3,
      counts: {
        projects: 1,
        analysis_runs: 1,
        export_events: 1,
        project_revisions: 1
      },
      checksum_sha256: "a".repeat(64),
      signature_verified: true
    });
    vi.mocked(importWorkspaceRequest).mockResolvedValueOnce({
      status: "imported",
      imported_projects: 1,
      imported_analysis_runs: 1,
      imported_export_events: 1,
      imported_project_revisions: 1
    });
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([]).mockResolvedValueOnce([]);

    const file = new File([JSON.stringify(buildWorkspaceBundle({ signed: true }))], "workspace-backup.json", {
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

      expect(view.container.textContent).toContain("Validated signed workspace backup (schema v3, checksum aaaaaaaaaaaa...).");
    } finally {
      await view.unmount();
    }
  });

  it("blocks workspace import when validation fails before SQLite writes begin", async () => {
    vi.mocked(validateWorkspaceRequest).mockRejectedValueOnce(
      new Error("Workspace validation failed (workspace_duplicate_project_id)")
    );

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

      expect(validateWorkspaceRequest).toHaveBeenCalledTimes(1);
      expect(importWorkspaceRequest).not.toHaveBeenCalled();
      expect(view.container.textContent).toContain("Workspace validation failed (workspace_duplicate_project_id)");
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
      await openSystemTab(view);

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
      await openSystemTab(view);

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
      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Browser draft");
    } finally {
      await view.unmount();
    }
  });

  it("deletes a saved project from the sidebar and keeps the current form as draft after inline confirmation", async () => {
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
    vi.mocked(archiveProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      archived: true,
      archived_at: "2026-03-07T10:30:00Z"
    });

    vi.useFakeTimers();
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Archive Stored checkout test"));
      await flushEffects();

      expect(findButtonByAriaLabel(view.container, "Archive Stored checkout test").textContent).toContain("Sure? (3)");
      expect(archiveProjectRequest).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });

      await click(findButtonByAriaLabel(view.container, "Archive Stored checkout test"));
      await flushEffects();

      expect(archiveProjectRequest).toHaveBeenCalledWith("p-1");
      expect(view.container.textContent).toContain("Project Stored checkout test archived. Current form remains as a new local draft.");
      expect(view.container.textContent).not.toContain("Project id: p-1");
      expect(view.container.textContent).toContain("Archived projects");
      expect(view.container.textContent).toContain("Restore");
    } finally {
      vi.useRealTimers();
      await view.unmount();
    }
  });

  it("cancels archive confirmation after the countdown expires", async () => {
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

    vi.useFakeTimers();
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Archive Stored checkout test"));
      await flushEffects();

      expect(findButtonByAriaLabel(view.container, "Archive Stored checkout test").textContent).toContain("Sure? (3)");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3100);
      });
      await flushEffects();

      expect(archiveProjectRequest).not.toHaveBeenCalled();
      expect(findButtonByAriaLabel(view.container, "Archive Stored checkout test").textContent).toContain("Archive");
    } finally {
      vi.useRealTimers();
      await view.unmount();
    }
  });

  it("restores an archived project back into the active saved list", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        payload_schema_version: 1,
        archived_at: "2026-03-07T10:30:00Z",
        is_archived: true,
        last_analysis_at: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:30:00Z"
      }
    ]);
    vi.mocked(restoreProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload_schema_version: 1,
      archived_at: null,
      is_archived: false,
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false,
      created_at: "2026-03-07T10:00:00Z",
      updated_at: "2026-03-07T10:35:00Z",
      payload: buildApiPayload(buildLoadedPayload())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Archived projects");
      await click(findButton(view.container, "Restore"));
      await flushEffects();

      expect(restoreProjectRequest).toHaveBeenCalledWith("p-1");
      expect(view.container.textContent).toContain("Project Stored checkout test restored from archive.");
      expect(view.container.textContent).toContain("Saved projects");
    } finally {
      await view.unmount();
    }
  });

  it("permanently deletes a saved project from the sidebar", async () => {
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
    vi.mocked(deleteProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      deleted: true
    });

    vi.useFakeTimers();
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      await click(findButtonByAriaLabel(view.container, "Delete Stored checkout test"));
      await flushEffects();

      expect(findButtonByAriaLabel(view.container, "Delete Stored checkout test").textContent).toContain("Sure? (3)");
      expect(deleteProjectRequest).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });

      await click(findButtonByAriaLabel(view.container, "Delete Stored checkout test"));
      await flushEffects();

      expect(deleteProjectRequest).toHaveBeenCalledWith("p-1");
      expect(view.container.textContent).toContain("Project Stored checkout test deleted permanently.");
      expect(view.container.querySelector('button[aria-label="Delete Stored checkout test"]')).toBeNull();
      expect(view.container.querySelector('button[aria-label="Archive Stored checkout test"]')).toBeNull();
    } finally {
      vi.useRealTimers();
      await view.unmount();
    }
  });

  it("autosaves form changes into browser local storage", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await startNewExperiment(view);

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
      await startNewExperiment(view);

      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      await changeValue(projectNameInput, "Quota warning");
      await flushEffects();

      expect(setItemSpy).toHaveBeenCalled();
      expect(view.container.textContent).toContain("Storage full - draft not saved. Clear old data or use Export.");
      expect(Array.from(view.container.querySelectorAll('[role="alert"]')).some(
        (alert) => alert.textContent?.includes("Draft not saved - browser storage full") ?? false
      )).toBe(true);
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
      await startNewExperiment(view);

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
      await startNewExperiment(view);

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
      await loadExample(view);

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

  it("shows a save toast and auto-dismisses it after a successful save", async () => {
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

    vi.useFakeTimers();
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      await click(findButton(view.container, "Save project"));
      await flushEffects();

      expect(Array.from(view.container.querySelectorAll('[role="alert"]')).some(
        (alert) => alert.textContent?.includes("Project saved") ?? false
      )).toBe(true);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });
      await flushEffects();

      expect(Array.from(view.container.querySelectorAll('[role="alert"]')).some(
        (alert) => alert.textContent?.includes("Project saved") ?? false
      )).toBe(false);
    } finally {
      vi.useRealTimers();
      await view.unmount();
    }
  });

  it("keeps optional expected uplift empty instead of coercing it to zero", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

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

  it("renders focusable tooltip guidance for setup and metric inputs", async () => {
    const setupSection = sections.find((section) => section.section === "setup");
    const metricsSection = sections.find((section) => section.section === "metrics");
    const constraintsSection = sections.find((section) => section.section === "constraints");
    if (!setupSection || !metricsSection || !constraintsSection) {
      throw new Error("Wizard sections were not configured");
    }

    const form = cloneInitialState();
    const view = await renderIntoDocument(
      <WizardDraftStep
        current={setupSection}
        form={form}
        canGoBack={true}
        activeProjectId={null}
        hasUnsavedChanges={false}
        canMutateBackend={true}
        backendMutationMessage=""
        validationErrors={[]}
        importingDraft={false}
        loading={false}
        saving={false}
        onUpdateSection={() => {}}
        onBack={() => {}}
        onNext={() => {}}
        onSave={() => {}}
        onStartNew={() => {}}
        onOpenTemplateGallery={() => {}}
        onImportDraft={() => {}}
        onExportDraft={() => {}}
      />
    );
    try {
      await flushEffects();

      for (const fieldId of [
        "setup-traffic_split",
        "setup-expected_daily_traffic",
        "setup-audience_share_in_test",
        "setup-variants_count"
      ]) {
        const label = view.container.querySelector(`label[for="${fieldId}"]`);
        if (!(label instanceof HTMLLabelElement)) {
          throw new Error(`Label was not rendered for ${fieldId}`);
        }

        expect(label.querySelector('[role="note"][tabindex="0"]')).not.toBeNull();
      }

      await view.rerender(
        <WizardDraftStep
          current={metricsSection}
          form={form}
          canGoBack={true}
          activeProjectId={null}
          hasUnsavedChanges={false}
          canMutateBackend={true}
          backendMutationMessage=""
          validationErrors={[]}
          importingDraft={false}
          loading={false}
          saving={false}
          onUpdateSection={() => {}}
          onBack={() => {}}
          onNext={() => {}}
          onSave={() => {}}
          onStartNew={() => {}}
          onOpenTemplateGallery={() => {}}
          onImportDraft={() => {}}
          onExportDraft={() => {}}
        />
      );
      await flushEffects();

      for (const fieldId of [
        "metrics-baseline_value",
        "metrics-expected_uplift_pct",
        "metrics-mde_pct"
      ]) {
        const label = view.container.querySelector(`label[for="${fieldId}"]`);
        if (!(label instanceof HTMLLabelElement)) {
          throw new Error(`Label was not rendered for ${fieldId}`);
        }

        expect(label.querySelector('[role="note"][tabindex="0"]')).not.toBeNull();
      }

      await view.rerender(
        <WizardDraftStep
          current={constraintsSection}
          form={form}
          canGoBack={true}
          activeProjectId={null}
          hasUnsavedChanges={false}
          canMutateBackend={true}
          backendMutationMessage=""
          validationErrors={[]}
          importingDraft={false}
          loading={false}
          saving={false}
          onUpdateSection={() => {}}
          onBack={() => {}}
          onNext={() => {}}
          onSave={() => {}}
          onStartNew={() => {}}
          onOpenTemplateGallery={() => {}}
          onImportDraft={() => {}}
          onExportDraft={() => {}}
        />
      );
      await flushEffects();

      for (const fieldId of ["metrics-alpha", "metrics-power"]) {
        const label = view.container.querySelector(`label[for="${fieldId}"]`);
        if (!(label instanceof HTMLLabelElement)) {
          throw new Error(`Label was not rendered for ${fieldId}`);
        }

        expect(label.querySelector('[role="note"][tabindex="0"]')).not.toBeNull();
      }

      await view.rerender(
        <WizardDraftStep
          current={metricsSection}
          form={{
            ...form,
            metrics: {
              ...form.metrics,
              metric_type: "continuous"
            }
          }}
          canGoBack={true}
          activeProjectId={null}
          hasUnsavedChanges={false}
          canMutateBackend={true}
          backendMutationMessage=""
          validationErrors={[]}
          importingDraft={false}
          loading={false}
          saving={false}
          onUpdateSection={() => {}}
          onBack={() => {}}
          onNext={() => {}}
          onSave={() => {}}
          onStartNew={() => {}}
          onOpenTemplateGallery={() => {}}
          onImportDraft={() => {}}
          onExportDraft={() => {}}
        />
      );
      await flushEffects();

      const stdDevLabel = view.container.querySelector('label[for="metrics-std_dev"]');
      if (!(stdDevLabel instanceof HTMLLabelElement)) {
        throw new Error("Std dev label was not rendered");
      }

      const baselineLabel = view.container.querySelector('label[for="metrics-baseline_value"]');
      if (!(baselineLabel instanceof HTMLLabelElement)) {
        throw new Error("Baseline value label was not rendered");
      }

      const baselineTrigger = baselineLabel.querySelector('[role="note"][tabindex="0"]');
      if (!(baselineTrigger instanceof HTMLElement)) {
        throw new Error("Baseline tooltip trigger was not rendered");
      }

      expect(stdDevLabel.querySelector('[role="note"][tabindex="0"]')).not.toBeNull();

      await act(async () => {
        baselineTrigger.focus();
      });
      await flushEffects();

      const tooltip = document.body.querySelector('[role="tooltip"]');
      expect(tooltip?.textContent).toContain("0.042 for 4.2%");

      await act(async () => {
        baselineTrigger.blur();
      });
      await flushEffects();

      expect(document.body.querySelector('[role="tooltip"]')).toBeNull();
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
      const projectNameInput = view.container.querySelector("#project-project_name");
      if (!(projectNameInput instanceof HTMLInputElement)) {
        throw new Error("Project name input was not rendered");
      }

      expect(projectNameInput.value).toBe("Imported checkout");
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
      await loadExample(view);

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      expect(view.container.textContent).toContain("Review inputs");
      expect(view.container.textContent).toContain("Legal / ethics constraints: none");
      expect(view.container.textContent).toContain("Deadline pressure: medium");
      expect(view.container.textContent).toContain("Payment error rate");

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(requestAnalysis).toHaveBeenCalledTimes(1);
      expect(view.container.textContent).toContain("Analysis completed.");
      expect(view.container.textContent).toContain("Deterministic summary");
      expect(view.container.textContent).toContain("Variant and rollout structure");
      expect(view.container.textContent).toContain("new checkout");
      expect(view.container.textContent).toContain("Primary, secondary, and guardrail coverage");
      expect(view.container.textContent).toContain("payment_error_rate");
      expect(view.container.textContent).toContain("Guardrail metrics");
      expect(view.container.textContent).toContain("Payment error rate");
      expect(view.container.textContent).toContain("0.321 pp");
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

  it("shows a results skeleton while analysis is running", async () => {
    let resolveAnalysis: ((value: AnalysisResponse) => void) | undefined;
    const analysisPromise = new Promise<AnalysisResponse>((resolve) => {
      resolveAnalysis = resolve;
    });

    vi.mocked(requestAnalysis).mockReturnValueOnce(analysisPromise);

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      for (let stepIndex = 0; stepIndex < 5; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      await click(findButton(view.container, "Run analysis"));
      await flushEffects();

      expect(view.container.querySelector(".results-skeleton")).not.toBeNull();
      expect(view.container.textContent).not.toContain("No analysis yet.");

      resolveAnalysis?.(buildAnalysisResult());
      await flushEffects();
      await flushEffects();

      expect(view.container.querySelector(".results-skeleton")).toBeNull();
      expect(view.container.textContent).toContain("Deterministic summary");
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
      await loadExample(view);

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

  it("exports a saved analysis snapshot as PDF", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 12,
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
    vi.mocked(downloadProjectReportPdfRequest).mockResolvedValueOnce({
      blob: new Blob(["pdf"], { type: "application/pdf" }),
      filename: "stored-checkout-test-report.pdf"
    });
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
      await click(findButton(view.container, "Export PDF"));
      await flushEffects();

      expect(downloadProjectReportPdfRequest).toHaveBeenCalledWith("p-1");
      expect(recordProjectExportRequest).toHaveBeenCalledWith("p-1", "pdf", "run-1");
      expect(view.container.textContent).toContain("Exported report as PDF and updated project export metadata.");
    } finally {
      await view.unmount();
    }
  });

  it("exports saved project data as CSV and XLSX from the unified export control", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 12,
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
    vi.mocked(downloadProjectReportDataRequest)
      .mockResolvedValueOnce({
        blob: new Blob(["csv"], { type: "text/csv" }),
        filename: "stored-checkout-test-report.csv"
      })
      .mockResolvedValueOnce({
        blob: new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
        filename: "stored-checkout-test-report.xlsx"
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
      await click(findButton(view.container, "Export"));
      await flushEffects();
      await click(findButton(view.container, "CSV Data"));
      await flushEffects();
      await click(findButton(view.container, "Excel Workbook"));
      await flushEffects();

      expect(downloadProjectReportDataRequest).toHaveBeenNthCalledWith(1, "p-1", "csv");
      expect(downloadProjectReportDataRequest).toHaveBeenNthCalledWith(2, "p-1", "xlsx");
    } finally {
      await view.unmount();
    }
  });

  it("shows std dev only for continuous metrics and hides it from binary review", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

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
      await loadExample(view);

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

  it("shows inline field validation on blur and marks the step tab", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      for (let stepIndex = 0; stepIndex < 3; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      const baselineInput = view.container.querySelector("#metrics-baseline_value");
      if (!(baselineInput instanceof HTMLInputElement)) {
        throw new Error("Baseline input was not rendered");
      }

      await changeValue(baselineInput, "-5");
      await act(async () => {
        baselineInput.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
      });

      expect(view.container.textContent).toContain("Binary baseline value must be between 0 and 1.");
      expect(baselineInput.getAttribute("aria-invalid")).toBe("true");
      expect(view.container.querySelector('.step[data-step-index="3"] [aria-label="This step has errors"]')).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("keeps the error indicator on the step that actually contains the invalid field", async () => {
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      for (let stepIndex = 0; stepIndex < 3; stepIndex += 1) {
        await click(findButton(view.container, "Next"));
      }

      const baselineInput = view.container.querySelector("#metrics-baseline_value");
      if (!(baselineInput instanceof HTMLInputElement)) {
        throw new Error("Baseline input was not rendered");
      }

      await changeValue(baselineInput, "-5");
      await act(async () => {
        baselineInput.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
      });
      await flushEffects();

      await click(findButton(view.container, "Back"));
      await flushEffects();

      expect(view.container.querySelector('.step[data-step-index="3"] [aria-label="This step has errors"]')).not.toBeNull();
      expect(view.container.querySelector('.step[data-step-index="2"] [aria-label="This step has errors"]')).toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("supports keyboard shortcuts for navigation, analysis, export, and save", async () => {
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult());
    vi.mocked(exportReportRequest).mockResolvedValueOnce("# exported");
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
      last_analysis_at: "2026-03-07T12:05:00Z",
      last_analysis_run_id: "run-1",
      last_exported_at: null,
      has_analysis_snapshot: true,
      created_at: "2026-03-07T12:00:00Z",
      updated_at: "2026-03-07T12:05:00Z",
      payload: buildApiPayload(cloneInitialState())
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

      expect(findButton(view.container, "Save project").title).toBe("Save project (Ctrl+S)");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
      });
      expect(view.container.querySelector(".step.active")?.textContent).toContain("2. Hypothesis");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
      });
      expect(view.container.querySelector(".step.active")?.textContent).toContain("1. Project");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true }));
      });
      await flushEffects();

      expect(requestAnalysis).toHaveBeenCalledTimes(1);
      expect(findButton(view.container, "Export Markdown").title).toBe("Export report (Ctrl+E)");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "e", ctrlKey: true, bubbles: true }));
      });
      await flushEffects();

      expect(exportReportRequest).toHaveBeenCalledWith(buildAnalysisResult().report, "markdown");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true }));
      });
      await flushEffects();

      expect(saveProjectRequest).toHaveBeenCalledTimes(1);
    } finally {
      await view.unmount();
    }
  });

  it("opens shortcut help, focuses project search, closes on escape, and toggles theme from the keyboard", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        hypothesis: "Checkout speed will improve with a shorter flow.",
        metric_type: "binary",
        duration_days: 12,
        payload_schema_version: 1,
        last_analysis_at: null,
        last_analysis_run_id: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      const searchInput = view.container.querySelector("#saved-projects-search");
      if (!(searchInput instanceof HTMLInputElement)) {
        throw new Error("Saved projects search input was not rendered");
      }

      const initialTheme = document.documentElement.getAttribute("data-theme");

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "/", bubbles: true }));
      });
      expect(document.activeElement).toBe(searchInput);

      searchInput.blur();

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "?", bubbles: true }));
      });
      expect(document.body.textContent).toContain("Keyboard shortcuts");
      expect(document.querySelector('[role="dialog"]')).not.toBeNull();

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      });
      expect(document.querySelector('[role="dialog"]')).toBeNull();

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "D", ctrlKey: true, shiftKey: true, bubbles: true }));
      });
      expect(document.documentElement.getAttribute("data-theme")).not.toBe(initialTheme);
    } finally {
      await view.unmount();
    }
  });

  it("renders the full AI advice payload when the orchestrator response is available", async () => {
    vi.mocked(requestAnalysis).mockResolvedValueOnce(buildAnalysisResult(true));

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();
      await loadExample(view);

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
