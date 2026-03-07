import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteProjectRequest,
  exportReportRequest,
  listProjectsRequest,
  loadProjectRequest,
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
            error: "offline"
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
        created_at: "x",
        updated_at: "y",
        payload: buildApiPayload(cloneInitialState())
      })
    );

    const project = await loadProjectRequest("1");

    expect(project.id).toBe("1");
    expect(project.payload.project.project_name).toBe("Checkout redesign");
  });

  it("deletes a saved project", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ id: "1", deleted: true })
    );

    const result = await deleteProjectRequest("1");

    expect(result).toEqual({ id: "1", deleted: true });
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
