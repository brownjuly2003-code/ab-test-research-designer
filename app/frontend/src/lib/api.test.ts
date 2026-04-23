import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  archiveProjectRequest,
  clearApiSessionToken,
  clearLlmSessionConfig,
  compareProjectsRequest,
  deleteProjectRequest,
  exportWorkspaceRequest,
  exportReportRequest,
  hasApiSessionToken,
  importWorkspaceRequest,
  restoreProjectRequest,
  setApiSessionToken,
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
  saveProjectRequest,
  setLlmSessionProvider,
  setLlmSessionToken
} from "./api";
import { buildApiPayload, buildCalculationPayload, cloneInitialState } from "./experiment";

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

function buildReportPayload() {
  return {
    executive_summary: "summary",
    calculations: {
      sample_size_per_variant: 100,
      total_sample_size: 200,
      estimated_duration_days: 10,
      assumptions: []
    },
    experiment_design: {
      variants: [
        { name: "A", description: "current experience" },
        { name: "B", description: "new experience" }
      ],
      randomization_unit: "user",
      traffic_split: [50, 50],
      target_audience: "new users",
      inclusion_criteria: "new users only",
      exclusion_criteria: "internal staff",
      recommended_duration_days: 10,
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
      product: ["Expected result depends on user behavior."],
      technical: ["legacy event logging"],
      operational: ["tracking quality"]
    },
    recommendations: { before_launch: [], during_test: [], after_test: [] },
    open_questions: []
  };
}

function buildWorkspaceBundle() {
  return {
    schema_version: 3,
    generated_at: "2026-03-09T00:30:00Z",
    projects: [
      {
        id: "project-1",
        project_name: "Workspace project",
        payload_schema_version: 1,
        archived_at: null,
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
        analysis: {
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
              total_sample_size: 200,
              effective_daily_traffic: 5000,
              estimated_duration_days: 10
            },
            assumptions: [],
            warnings: []
          },
          report: buildReportPayload(),
          advice: {
            available: false,
            provider: "local_orchestrator",
            model: "offline",
            advice: null,
            raw_text: null,
            error: "offline",
            error_code: "request_error"
          }
        }
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
      checksum_sha256: "a".repeat(64)
    }
  };
}

describe("frontend api wrapper", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
    vi.stubGlobal("fetch", vi.fn());
    vi.stubGlobal("sessionStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      }
    });
  });

  afterEach(() => {
    clearApiSessionToken();
    clearLlmSessionConfig();
    vi.unstubAllGlobals();
  });

  it("requests analysis and returns the combined payload", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
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
              total_sample_size: 200,
              effective_daily_traffic: 5000,
              estimated_duration_days: 10
            },
            assumptions: [],
            warnings: []
          },
          report: buildReportPayload(),
          advice: {
            available: false,
            provider: "local_orchestrator",
            model: "Claude Sonnet 4.6",
            advice: null,
            raw_text: null,
            error: "offline",
            error_code: "request_error"
          }
        })
      );

    const result = await requestAnalysis(cloneInitialState());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.calculations.results.total_sample_size).toBe(200);
    expect(result.report.executive_summary).toBe("summary");
    expect(result.report.metrics_plan.secondary).toEqual(["add_to_cart_rate"]);
    expect(result.advice.available).toBe(false);
  });

  it("requests a live calculation preview and forwards the abort signal", async () => {
    const fetchMock = vi.mocked(fetch);
    const controller = new AbortController();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
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
          total_sample_size: 200,
          effective_daily_traffic: 5000,
          estimated_duration_days: 10
        },
        assumptions: [],
        warnings: [],
        bonferroni_note: "Adjusted for multiple comparisons."
      })
    );

    const payload = buildCalculationPayload(cloneInitialState());
    const result = await requestCalculation(payload, { signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/calculate"),
      expect.objectContaining({
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify(payload)
      })
    );
    expect(result.results.sample_size_per_variant).toBe(100);
    expect(result.bonferroni_note).toBe("Adjusted for multiple comparisons.");
  });

  it("loads backend health", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        status: "ok",
        service: "AB Test Research Designer API",
        version: "0.1.0",
        environment: "local"
      })
    );

    const result = await requestHealth();

    expect(result.service).toBe("AB Test Research Designer API");
    expect(result.environment).toBe("local");
  });

  it("injects bearer auth when a browser-session token is configured", async () => {
    setApiSessionToken("frontend-secret");
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        status: "ok",
        service: "AB Test Research Designer API",
        version: "0.1.0",
        environment: "local"
      })
    );

    await requestHealth();

    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      headers: {
        Authorization: "Bearer frontend-secret"
      }
    });
    expect(hasApiSessionToken()).toBe(true);
  });

  it("adds session-only LLM headers to analysis requests without leaking the token into URL or body", async () => {
    setLlmSessionProvider("openai");
    setLlmSessionToken("sk-llm-secret");
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
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
            total_sample_size: 200,
            effective_daily_traffic: 5000,
            estimated_duration_days: 10
          },
          assumptions: [],
          warnings: []
        },
        report: buildReportPayload(),
        advice: {
          available: true,
          provider: "openai",
          model: "gpt-4o-mini",
          advice: {
            brief_assessment: "Remote advice is available.",
            key_risks: ["Tracking quality"],
            design_improvements: ["Validate event schema"],
            metric_recommendations: ["Track checkout step completion"],
            interpretation_pitfalls: ["Do not stop early"],
            additional_checks: ["Verify exposure balance"]
          },
          raw_text: "{\"brief_assessment\":\"Remote advice is available.\"}",
          error: null,
          error_code: null
        }
      })
    );

    await requestAnalysis(cloneInitialState());

    const [url, options] = vi.mocked(fetch).mock.calls[0] ?? [];

    expect(options).toMatchObject({
      headers: {
        "Content-Type": "application/json",
        "X-AB-LLM-Provider": "openai",
        "X-AB-LLM-Token": "sk-llm-secret"
      }
    });
    expect(String(url)).not.toContain("sk-llm-secret");
    expect(String(options?.body ?? "")).not.toContain("sk-llm-secret");
  });

  it("does not add LLM headers when the provider is remote but no token is configured", async () => {
    setLlmSessionProvider("anthropic");
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
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
            total_sample_size: 200,
            effective_daily_traffic: 5000,
            estimated_duration_days: 10
          },
          assumptions: [],
          warnings: []
        },
        report: buildReportPayload(),
        advice: {
          available: false,
          provider: "local_orchestrator",
          model: "offline",
          advice: null,
          raw_text: null,
          error: "offline",
          error_code: "request_error"
        }
      })
    );

    await requestAnalysis(cloneInitialState());

    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      headers: {
        "Content-Type": "application/json"
      }
    });
    expect(vi.mocked(fetch).mock.calls[0]?.[1]).not.toMatchObject({
      headers: {
        "X-AB-LLM-Provider": expect.any(String),
        "X-AB-LLM-Token": expect.any(String)
      }
    });
  });

  it("loads backend diagnostics", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
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
      })
    );

    const result = await requestDiagnostics();

    expect(result.storage.projects_total).toBe(2);
    expect(result.request_timing_headers_enabled).toBe(true);
  });

  it("exports the full workspace bundle", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(buildWorkspaceBundle()));

    const result = await exportWorkspaceRequest();

    expect(result.projects).toHaveLength(1);
    expect(result.analysis_runs[0]?.id).toBe("run-1");
    expect(result.project_revisions?.[0]?.id).toBe("rev-1");
  });

  it("validates the full workspace bundle before import", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
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
      })
    );

    const result = await validateWorkspaceRequest(buildWorkspaceBundle());

    expect(result.status).toBe("valid");
    expect(result.counts.projects).toBe(1);
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain("/api/v1/workspace/validate");
  });

  it("imports the full workspace bundle", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        status: "imported",
        imported_projects: 1,
        imported_analysis_runs: 1,
        imported_export_events: 1,
        imported_project_revisions: 1
      })
    );

    const result = await importWorkspaceRequest(buildWorkspaceBundle());

    expect(result.imported_projects).toBe(1);
    expect(result.imported_export_events).toBe(1);
    expect(result.imported_project_revisions).toBe(1);
  });

  it("throws the backend detail when save project fails", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ detail: "Project save failed hard" }, { status: 400 })
    );

    await expect(saveProjectRequest(cloneInitialState(), null)).rejects.toThrow("Project save failed hard");
  });

  it("falls back to backend error_code when string detail is absent", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: "workspace_integrity_checksum_mismatch" }, { status: 400 })
    );

    await expect(importWorkspaceRequest(buildWorkspaceBundle())).rejects.toThrow(
      "Workspace import failed (workspace_integrity_checksum_mismatch)"
    );
  });

  it("surfaces retry-after guidance for rate-limited responses", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        { detail: "Too many requests", error_code: "rate_limited" },
        { status: 429, headers: { "Retry-After": "17" } }
      )
    );

    await expect(requestDiagnostics()).rejects.toThrow("Too many requests. Retry after 17s.");
  });

  it("surfaces payload-size guidance for request body limit errors", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(
        { detail: "Request body exceeds limit of 1024 bytes", error_code: "request_body_too_large" },
        { status: 413 }
      )
    );

    await expect(importWorkspaceRequest(buildWorkspaceBundle())).rejects.toThrow(
      "Request body exceeds limit of 1024 bytes. Reduce the payload size or raise the backend limit."
    );
  });

  it("surfaces workspace validation errors before import", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ error_code: "workspace_duplicate_project_id" }, { status: 400 })
    );

    await expect(validateWorkspaceRequest(buildWorkspaceBundle())).rejects.toThrow(
      "Workspace validation failed (workspace_duplicate_project_id)"
    );
  });

  it("lists saved projects", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        projects: [
          { id: "1", project_name: "Checkout redesign", archived_at: null, is_archived: false, created_at: "x", updated_at: "y" }
        ]
      })
    );

    const projects = await listProjectsRequest();

    expect(projects).toHaveLength(1);
    expect(projects[0].project_name).toBe("Checkout redesign");
  });

  it("loads a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: "1",
        project_name: "Checkout redesign",
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: null,
        last_analysis_run_id: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "x",
        updated_at: "y",
        payload: buildApiPayload(cloneInitialState())
      })
    );

    const project = await loadProjectRequest("1");

    expect(project.id).toBe("1");
    expect(project.payload.project.project_name).toBe("Checkout redesign");
  });

  it("records an analysis snapshot for a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: "1",
        project_name: "Checkout redesign",
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: "2026-03-07T12:30:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: null,
        has_analysis_snapshot: true,
        created_at: "x",
        updated_at: "y",
        payload: buildApiPayload(cloneInitialState())
      })
    );

    const result = await recordProjectAnalysisRequest("1", {
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
          total_sample_size: 200,
          effective_daily_traffic: 5000,
          estimated_duration_days: 10
        },
        assumptions: [],
        warnings: []
      },
      report: buildReportPayload(),
      advice: {
        available: false,
        provider: "local_orchestrator",
        model: "offline",
        advice: null,
        raw_text: null,
        error: "offline",
        error_code: "request_error"
      }
    });

    expect(result.has_analysis_snapshot).toBe(true);
    expect(result.last_analysis_at).toBe("2026-03-07T12:30:00Z");
    expect(result.last_analysis_run_id).toBe("run-1");
  });

  it("loads saved project history", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        project_id: "1",
        analysis_total: 1,
        analysis_limit: 3,
        analysis_offset: 0,
        export_total: 1,
        export_limit: 3,
        export_offset: 0,
        analysis_runs: [
          {
            id: "run-1",
            project_id: "1",
            created_at: "2026-03-07T12:30:00Z",
            summary: {
              metric_type: "binary",
              sample_size_per_variant: 100,
              total_sample_size: 200,
              estimated_duration_days: 10,
              warnings_count: 1,
              advice_available: false
            },
            analysis: {
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
                  total_sample_size: 200,
                  effective_daily_traffic: 5000,
                  estimated_duration_days: 10
                },
                assumptions: [],
                warnings: []
              },
              report: buildReportPayload(),
              advice: {
                available: false,
                provider: "local_orchestrator",
                model: "offline",
                advice: null,
                raw_text: null,
                error: "offline",
                error_code: "request_error"
              }
            }
          }
        ],
        export_events: [
          {
            id: "export-1",
            project_id: "1",
            analysis_run_id: "run-1",
            format: "markdown",
            created_at: "2026-03-07T12:45:00Z"
          }
        ]
      })
    );

    const result = await loadProjectHistoryRequest("1", {
      analysisLimit: 3,
      exportLimit: 3
    });

    expect(result.project_id).toBe("1");
    expect(result.analysis_total).toBe(1);
    expect(result.analysis_runs[0]?.id).toBe("run-1");
    expect(result.export_events[0]?.analysis_run_id).toBe("run-1");
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain(
      "/api/v1/projects/1/history?analysis_limit=3&export_limit=3"
    );
  });

  it("loads saved project revisions", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        project_id: "1",
        total: 2,
        limit: 3,
        offset: 0,
        revisions: [
          {
            id: "rev-2",
            project_id: "1",
            source: "update",
            created_at: "2026-03-07T12:10:00Z",
            payload: buildApiPayload(cloneInitialState())
          },
          {
            id: "rev-1",
            project_id: "1",
            source: "create",
            created_at: "2026-03-07T10:00:00Z",
            payload: buildApiPayload(cloneInitialState())
          }
        ]
      })
    );

    const result = await loadProjectRevisionsRequest("1", { limit: 3 });

    expect(result.project_id).toBe("1");
    expect(result.total).toBe(2);
    expect(result.revisions[0]?.source).toBe("update");
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain("/api/v1/projects/1/revisions?limit=3");
  });

  it("loads a comparison between saved projects", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        base_project: {
          id: "base-1",
          project_name: "Checkout baseline",
          updated_at: "2026-03-07T10:00:00Z",
          analysis_created_at: "2026-03-07T09:30:00Z",
          last_analysis_at: "2026-03-07T10:30:00Z",
          analysis_run_id: "run-base",
          metric_type: "binary",
          primary_metric: "purchase_conversion",
          sample_size_per_variant: 100,
          total_sample_size: 200,
          estimated_duration_days: 10,
          warnings_count: 1,
          warning_codes: ["SEASONALITY_PRESENT"],
          risk_highlights: ["tracking quality"],
          assumptions: ["Baseline is stable"],
          advice_available: false,
          executive_summary: "Checkout baseline summary",
          warning_severity: "medium",
          recommendation_highlights: ["Verify tracking", "Watch SRM"]
        },
        candidate_project: {
          id: "cand-1",
          project_name: "Checkout challenger",
          updated_at: "2026-03-07T11:00:00Z",
          analysis_created_at: "2026-03-07T10:45:00Z",
          last_analysis_at: "2026-03-07T11:30:00Z",
          analysis_run_id: "run-candidate",
          metric_type: "binary",
          primary_metric: "purchase_conversion",
          sample_size_per_variant: 140,
          total_sample_size: 280,
          estimated_duration_days: 14,
          warnings_count: 2,
          warning_codes: ["LONG_DURATION", "LOW_TRAFFIC"],
          risk_highlights: ["tracking quality"],
          assumptions: ["Baseline is stable"],
          advice_available: false,
          executive_summary: "Checkout challenger summary",
          warning_severity: "high",
          recommendation_highlights: ["Validate traffic quality", "Watch SRM"]
        },
        deltas: {
          sample_size_per_variant: 40,
          total_sample_size: 80,
          estimated_duration_days: 4,
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
          "Checkout challenger changes total sample size by +80 and estimated duration by +4 days versus Checkout baseline.",
          "Both snapshots evaluate the same primary metric and metric family."
        ],
        summary: "Checkout challenger needs larger total sample size and a longer test window than Checkout baseline."
      })
    );

    const result = await compareProjectsRequest("base-1", "cand-1", "run-base-old");

    expect(result.deltas.total_sample_size).toBe(80);
    expect(result.candidate_project.project_name).toBe("Checkout challenger");
    expect(result.base_project.analysis_created_at).toBe("2026-03-07T09:30:00Z");
    expect(result.metric_alignment_note).toContain("same primary metric");
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain(
      "/api/v1/projects/compare?base_id=base-1&candidate_id=cand-1&base_run_id=run-base-old"
    );
  });

  it("archives a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ id: "1", archived: true, archived_at: "2026-03-07T12:45:00Z" })
    );

    const result = await archiveProjectRequest("1");

    expect(result).toEqual({ id: "1", archived: true, archived_at: "2026-03-07T12:45:00Z" });
  });

  it("hard-deletes a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ id: "1", deleted: true })
    );

    const result = await deleteProjectRequest("1");

    expect(result).toEqual({ id: "1", deleted: true });
  });

  it("restores an archived project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: "1",
        project_name: "Checkout redesign",
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: null,
        last_analysis_run_id: null,
        last_exported_at: null,
        has_analysis_snapshot: false,
        created_at: "x",
        updated_at: "y",
        payload: buildApiPayload(cloneInitialState())
      })
    );

    const result = await restoreProjectRequest("1");

    expect(result.id).toBe("1");
    expect(result.is_archived).toBe(false);
  });

  it("records an export timestamp for a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: "1",
        project_name: "Checkout redesign",
        payload_schema_version: 1,
        archived_at: null,
        is_archived: false,
        last_analysis_at: "2026-03-07T12:30:00Z",
        last_analysis_run_id: "run-1",
        last_exported_at: "2026-03-07T12:45:00Z",
        has_analysis_snapshot: true,
        created_at: "x",
        updated_at: "y",
        payload: buildApiPayload(cloneInitialState())
      })
    );

    const result = await recordProjectExportRequest("1", "markdown", "run-1");

    expect(result.last_exported_at).toBe("2026-03-07T12:45:00Z");
    expect(result.last_analysis_run_id).toBe("run-1");
  });

  it("exports report content", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ content: "# Experiment Report" })
    );

    const content = await exportReportRequest(
      buildReportPayload(),
      "markdown"
    );

    expect(content).toBe("# Experiment Report");
  });
});
