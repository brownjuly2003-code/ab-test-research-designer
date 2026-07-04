// @vitest-environment jsdom

import "../i18n";

import { afterEach, describe, expect, it, vi } from "vitest";

import EmptyState from "./EmptyState";
import { listProjectsRequest } from "../lib/api";
import type { SavedProject } from "../lib/experiment";
import { useProjectStore } from "../stores/projectStore";
import { click, flushEffects, renderIntoDocument } from "../test/dom";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    listProjectsRequest: vi.fn()
  };
});

const initialProjectState = useProjectStore.getState();

function buildDemoProject(overrides: Partial<SavedProject> = {}): SavedProject {
  return {
    id: "demo-1",
    project_name: "Demo - Checkout Conversion",
    hypothesis: "If we simplify checkout, conversion will increase.",
    metric_type: "binary",
    duration_days: 41,
    payload_schema_version: 1,
    archived_at: null,
    is_archived: false,
    revision_count: 1,
    last_revision_at: null,
    last_analysis_at: "2026-07-01T10:00:00Z",
    last_analysis_run_id: "run-1",
    last_exported_at: null,
    has_analysis_snapshot: true,
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    ...overrides
  };
}

function renderProps(overrides: Partial<Parameters<typeof EmptyState>[0]> = {}) {
  return {
    onNewExperiment: vi.fn(),
    onLoadExample: vi.fn(),
    onImportProject: vi.fn(),
    onOpenDemo: vi.fn(),
    ...overrides
  };
}

afterEach(() => {
  useProjectStore.setState(initialProjectState, true);
  window.sessionStorage.removeItem("ab-test:admin");
  vi.mocked(listProjectsRequest).mockReset();
});

describe("EmptyState landing", () => {
  it("renders demo project cards from the backend list and opens one on click", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([
      buildDemoProject(),
      buildDemoProject({
        id: "demo-2",
        project_name: "Demo - Feed Ad Click-Through Ratio",
        metric_type: "ratio",
        has_analysis_snapshot: false
      }),
      buildDemoProject({ id: "not-a-demo", project_name: "My private project" }),
      buildDemoProject({ id: "demo-archived", project_name: "Demo - Old", is_archived: true })
    ]);
    const props = renderProps();

    const view = await renderIntoDocument(<EmptyState {...props} />);
    try {
      await flushEffects();

      expect(view.container.textContent).toContain("Checkout Conversion");
      expect(view.container.textContent).toContain("Feed Ad Click-Through Ratio");
      // Non-demo and archived projects never surface on the public landing.
      expect(view.container.textContent).not.toContain("My private project");
      expect(view.container.textContent).not.toContain("Demo - Old");
      expect(view.container.textContent).toContain("41 days");
      expect(view.container.textContent).toContain("Saved analysis");

      const card = Array.from(view.container.querySelectorAll("button")).find((candidate) =>
        candidate.textContent?.includes("Checkout Conversion")
      );
      expect(card).toBeDefined();
      await click(card as HTMLButtonElement);
      expect(props.onOpenDemo).toHaveBeenCalledWith("demo-1", "Demo - Checkout Conversion");
    } finally {
      await view.unmount();
    }
  });

  it("falls back to the decorative preview when no demos are available", async () => {
    vi.mocked(listProjectsRequest).mockRejectedValueOnce(new Error("Unauthorized"));
    const props = renderProps();

    const view = await renderIntoDocument(<EmptyState {...props} />);
    try {
      await flushEffects();

      expect(view.container.textContent).not.toContain("Open demo");
      expect(view.container.textContent).toContain("4,317");
    } finally {
      await view.unmount();
    }
  });

  it("hides the workspace import link for a read-only session", async () => {
    vi.mocked(listProjectsRequest).mockResolvedValueOnce([]);
    useProjectStore.setState({ isReadOnlySession: true });
    const props = renderProps();

    const view = await renderIntoDocument(<EmptyState {...props} />);
    try {
      await flushEffects();

      expect(view.container.textContent).not.toContain("Import project");
      expect(view.container.textContent).toContain("New experiment");
    } finally {
      await view.unmount();
    }
  });

  it("does not fetch the demo list in operator mode", async () => {
    window.sessionStorage.setItem("ab-test:admin", "1");
    const props = renderProps();

    const view = await renderIntoDocument(<EmptyState {...props} />);
    try {
      await flushEffects();

      expect(listProjectsRequest).not.toHaveBeenCalled();
    } finally {
      await view.unmount();
    }
  });
});
