// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./lib/api", () => ({
  deleteProjectRequest: vi.fn(),
  exportReportRequest: vi.fn(),
  listProjectsRequest: vi.fn(),
  loadProjectRequest: vi.fn(),
  requestHealth: vi.fn(),
  requestAnalysis: vi.fn(),
  saveProjectRequest: vi.fn()
}));

import App from "./App";
import {
  deleteProjectRequest,
  listProjectsRequest,
  loadProjectRequest,
  requestHealth,
  requestAnalysis
} from "./lib/api";
import { buildDraftTransferFile, browserDraftStorageKey, cloneInitialState, type FullPayload } from "./lib/experiment";
import { changeFiles, changeValue, click, findButton, findButtonByAriaLabel, flushEffects, renderIntoDocument } from "./test/dom";

function buildAnalysisResult(adviceAvailable = false) {
  return {
    calculations: {
      calculation_summary: {},
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
      error: adviceAvailable ? null : "offline"
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

describe("App UI flow", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(deleteProjectRequest).mockReset();
    vi.mocked(listProjectsRequest).mockResolvedValue([]);
    vi.mocked(loadProjectRequest).mockReset();
    vi.mocked(requestHealth).mockResolvedValue({
      status: "ok",
      service: "AB Test Research Designer API",
      version: "0.1.0",
      environment: "local"
    });
    vi.mocked(requestAnalysis).mockReset();
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("loads saved projects on startup and can hydrate a selected project", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      {
        id: "p-1",
        project_name: "Stored checkout test",
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload: buildLoadedPayload()
    });

    const view = await renderIntoDocument(<App />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Backend status");
      expect(view.container.textContent).toContain("API online");
      expect(view.container.textContent).toContain("AB Test Research Designer API");
      expect(view.container.textContent).toContain("Stored checkout test");

      await click(findButton(view.container, "Stored checkout test"));
      await flushEffects();

      expect(view.container.textContent).toContain("Loaded project Stored checkout test into the wizard.");
      expect((view.container.querySelector("#project-project_name") as HTMLInputElement).value).toBe("Loaded experiment");
      expect(view.container.textContent).toContain("Project id: p-1");
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
        created_at: "2026-03-07T10:00:00Z",
        updated_at: "2026-03-07T10:00:00Z"
      }
    ]);
    vi.mocked(loadProjectRequest).mockResolvedValueOnce({
      id: "p-1",
      project_name: "Stored checkout test",
      payload: buildLoadedPayload()
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
