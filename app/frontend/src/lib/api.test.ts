import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  exportReportRequest,
  listProjectsRequest,
  loadProjectRequest,
  requestAnalysis,
  saveProjectRequest
} from "./api";
import { cloneInitialState } from "./experiment";

function jsonResponse(payload: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "Content-Type": "application/json" },
    ...init
  });
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
          calculation_summary: {},
          results: {
            sample_size_per_variant: 100,
            total_sample_size: 200,
            effective_daily_traffic: 5000,
            estimated_duration_days: 10
          },
          assumptions: [],
          warnings: []
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          executive_summary: "summary",
          recommendations: { before_launch: [], during_test: [], after_test: [] },
          open_questions: []
        })
      )
      .mockResolvedValueOnce(
        jsonResponse({
          available: false,
          provider: "local_orchestrator",
          model: "Claude Sonnet 4.6",
          advice: null,
          raw_text: null,
          error: "offline"
        })
      );

    const result = await requestAnalysis(cloneInitialState());

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(result.calculations.results.total_sample_size).toBe(200);
    expect(result.report.executive_summary).toBe("summary");
    expect(result.advice.available).toBe(false);
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
        payload: cloneInitialState()
      })
    );

    const project = await loadProjectRequest("1");

    expect(project.id).toBe("1");
    expect(project.payload.project.project_name).toBe("Checkout redesign");
  });

  it("exports report content", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ content: "# Experiment Report" })
    );

    const content = await exportReportRequest(
      {
        executive_summary: "summary",
        recommendations: { before_launch: [], during_test: [], after_test: [] },
        open_questions: []
      },
      "markdown"
    );

    expect(content).toBe("# Experiment Report");
  });
});
