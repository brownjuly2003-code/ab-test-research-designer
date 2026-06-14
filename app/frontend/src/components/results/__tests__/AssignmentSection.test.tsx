// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AssignmentSection from "../AssignmentSection";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../../test/dom";
import { resetResultsStores, seedResultsStores } from "./resultsTestUtils";
import { useAnalysisStore } from "../../../stores/analysisStore";
import { useProjectStore } from "../../../stores/projectStore";

const assignResponse = {
  experiment_id: "p-1",
  user_id: "user-99",
  seed: "p-1",
  variation_index: 1,
  in_experiment: true,
  hash: 0.8123,
  num_variations: 2,
  coverage: 1.0,
  weights: [0.5, 0.5],
  hash_version: 2,
  growthbook: {
    key: "p-1",
    variationId: 1,
    inExperiment: true,
    hashUsed: true,
    hashAttribute: "id",
    hashValue: "user-99",
    bucket: 0.8123
  }
};

describe("AssignmentSection", () => {
  beforeEach(() => {
    resetResultsStores();
    seedResultsStores();
  });

  afterEach(() => {
    resetResultsStores();
    vi.unstubAllGlobals();
  });

  it("renders the assignment form for a saved experiment", async () => {
    const view = await renderIntoDocument(<AssignmentSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Assign a user");
      expect(view.container.querySelector("#assignment-user-id")).not.toBeNull();
    } finally {
      await view.unmount();
    }
  });

  it("assigns a user and shows the resulting variation", async () => {
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => assignResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<AssignmentSection />);
    try {
      await flushEffects();
      const input = view.container.querySelector("#assignment-user-id") as HTMLInputElement;
      await changeValue(input, "user-99");
      await click(findButton(view.container, "Assign"));
      await flushEffects();
      await flushEffects();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const requestedUrl = String(fetchMock.mock.calls[0]?.[0]);
      expect(requestedUrl).toContain("/api/v1/experiments/p-1/assign");
      expect(view.container.textContent).toContain("Assigned to Treatment");
    } finally {
      await view.unmount();
    }
  });

  it("shows the sticky note when the assignment came from a recorded exposure", async () => {
    const stickyResponse = { ...assignResponse, sticky: true };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => stickyResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<AssignmentSection />);
    try {
      await flushEffects();
      const input = view.container.querySelector("#assignment-user-id") as HTMLInputElement;
      await changeValue(input, "user-99");
      await click(findButton(view.container, "Assign"));
      await flushEffects();
      await flushEffects();

      expect(view.container.textContent).toContain("Sticky:");
    } finally {
      await view.unmount();
    }
  });

  it("distinguishes a namespace exclusion from a holdout", async () => {
    const nsResponse = { ...assignResponse, in_experiment: false, variation_index: -1, namespace_excluded: true };
    const fetchMock = vi.fn(async (..._args: unknown[]) => ({ ok: true, json: async () => nsResponse }));
    vi.stubGlobal("fetch", fetchMock);

    const view = await renderIntoDocument(<AssignmentSection />);
    try {
      await flushEffects();
      const input = view.container.querySelector("#assignment-user-id") as HTMLInputElement;
      await changeValue(input, "user-99");
      await click(findButton(view.container, "Assign"));
      await flushEffects();
      await flushEffects();

      expect(view.container.textContent).toContain("Mutually excluded");
    } finally {
      await view.unmount();
    }
  });

  it("shows the save-first hint when no experiment is saved", async () => {
    useAnalysisStore.setState({ ...useAnalysisStore.getState(), resultsProjectId: null });
    useProjectStore.setState({
      ...useProjectStore.getState(),
      activeProjectId: null,
      activeProject: null,
      selectedHistoryRun: null
    });

    const view = await renderIntoDocument(<AssignmentSection />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Save this experiment first");
      expect(view.container.querySelector("#assignment-user-id")).toBeNull();
    } finally {
      await view.unmount();
    }
  });
});
