import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  compareProjectsRequest,
  deleteProjectRequest,
  exportReportRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestHealth,
  requestAnalysis,
  saveProjectRequest
} from "./api";
import { buildApiPayload, cloneInitialState } from "./experiment";

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

describe("frontend api wrapper", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
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

  it("throws the backend detail when save project fails", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ detail: "Project save failed hard" }, { status: 400 })
    );

    await expect(saveProjectRequest(cloneInitialState(), null)).rejects.toThrow("Project save failed hard");
  });

  it("lists saved projects", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        projects: [
          { id: "1", project_name: "Checkout redesign", created_at: "x", updated_at: "y" }
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
          advice_available: false
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
          advice_available: false
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
        summary: "Checkout challenger needs larger total sample size and a longer test window than Checkout baseline."
      })
    );

    const result = await compareProjectsRequest("base-1", "cand-1", "run-base-old");

    expect(result.deltas.total_sample_size).toBe(80);
    expect(result.candidate_project.project_name).toBe("Checkout challenger");
    expect(result.base_project.analysis_created_at).toBe("2026-03-07T09:30:00Z");
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain(
      "/api/v1/projects/compare?base_id=base-1&candidate_id=cand-1&base_run_id=run-base-old"
    );
  });

  it("deletes a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ id: "1", deleted: true })
    );

    const result = await deleteProjectRequest("1");

    expect(result).toEqual({ id: "1", deleted: true });
  });

  it("records an export timestamp for a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        id: "1",
        project_name: "Checkout redesign",
        payload_schema_version: 1,
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
