// @vitest-environment jsdom

import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    exportAuditLogRequest: vi.fn(),
    listAuditLogRequest: vi.fn()
  };
});

import { listAuditLogRequest } from "../../lib/api";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import { changeValue, click, findButton, flushEffects, renderIntoDocument } from "../../test/dom";
import SidebarPanel from "../SidebarPanel";

const initialAnalysisState = useAnalysisStore.getState();
const initialProjectState = useProjectStore.getState();

// ProjectListFilters debounces the search box before it lifts the query up.
const SEARCH_DEBOUNCE_MS = 300;

function baseProject(id: string, name: string) {
  return {
    id,
    project_name: name,
    hypothesis: "Checkout speed improves conversion.",
    metric_type: "binary" as const,
    duration_days: 12,
    payload_schema_version: 1,
    created_at: "2026-03-07T10:00:00Z",
    updated_at: "2026-03-07T12:00:00Z",
    archived_at: null,
    is_archived: false,
    revision_count: 2,
    last_revision_at: "2026-03-07T11:00:00Z",
    last_analysis_at: "2026-03-07T12:10:00Z",
    last_analysis_run_id: "run-1",
    last_exported_at: null,
    has_analysis_snapshot: true
  };
}

function seedProjects() {
  const savedProjects = [baseProject("p-1", "Stored checkout test"), baseProject("p-2", "Pricing layout test")];
  useProjectStore.setState({
    ...useProjectStore.getState(),
    loadingProjects: false,
    savedProjects,
    activeSavedProjects: savedProjects,
    archivedProjects: [],
    canMutateBackend: true
  });
}

async function advanceDebounce() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 50));
  });
}

function searchInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector("#saved-projects-search");
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("Saved-project search box was not rendered");
  }
  return input;
}

function auditFilter(container: HTMLElement): HTMLSelectElement {
  const select = container.querySelector("#audit-project-filter");
  if (!(select instanceof HTMLSelectElement)) {
    throw new Error("Audit-log project filter was not rendered");
  }
  return select;
}

/**
 * The sidebar renders exactly one tab at a time, so a tab's component unmounts the moment the
 * operator visits another one. Anything the operator typed has to outlive that unmount, which is
 * why the filter and audit-log state sits in the shell rather than inside the tab components.
 */
describe("SidebarPanel tab state", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    window.sessionStorage.setItem("ab-test:admin", "1");
    useAnalysisStore.setState(initialAnalysisState, true);
    useProjectStore.setState(initialProjectState, true);
    seedProjects();
    vi.mocked(listAuditLogRequest).mockResolvedValue({ total: 0, entries: [] });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    useAnalysisStore.setState(initialAnalysisState, true);
    useProjectStore.setState(initialProjectState, true);
    vi.clearAllMocks();
  });

  it("keeps the saved-project search query across a trip to the System tab", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      await changeValue(searchInput(view.container), "checkout");
      await advanceDebounce();
      expect(searchInput(view.container).value).toBe("checkout");

      await click(findButton(view.container, "System"));
      await flushEffects();
      expect(view.container.querySelector("#saved-projects-search")).toBeNull();

      await click(findButton(view.container, "Projects"));
      await flushEffects();

      expect(searchInput(view.container).value).toBe("checkout");
    } finally {
      await view.unmount();
    }
  }, 15000);

  it("keeps the audit-log project filter across a trip to the Projects tab", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      await click(findButton(view.container, "System"));
      await flushEffects();

      await changeValue(auditFilter(view.container), "p-1");
      await flushEffects();
      expect(vi.mocked(listAuditLogRequest)).toHaveBeenCalledWith({ projectId: "p-1" });

      await click(findButton(view.container, "Projects"));
      await flushEffects();

      await click(findButton(view.container, "System"));
      await flushEffects();

      expect(auditFilter(view.container).value).toBe("p-1");
    } finally {
      await view.unmount();
    }
  }, 15000);
});

/**
 * The hidden <input type="file"> is rendered once, by the shell. Both tabs expose an "Import"
 * button, and both must reach that one input — a ref created per tab would point at nothing.
 */
describe("SidebarPanel workspace import", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    window.sessionStorage.setItem("ab-test:admin", "1");
    useAnalysisStore.setState(initialAnalysisState, true);
    useProjectStore.setState(initialProjectState, true);
    seedProjects();
    vi.mocked(listAuditLogRequest).mockResolvedValue({ total: 0, entries: [] });
  });

  afterEach(() => {
    window.sessionStorage.clear();
    useAnalysisStore.setState(initialAnalysisState, true);
    useProjectStore.setState(initialProjectState, true);
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it.each([
    ["Projects", false],
    ["System", true]
  ])("opens the file picker from the %s tab", async (tabLabel, switchTab) => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      if (switchTab) {
        await click(findButton(view.container, tabLabel));
        await flushEffects();
      }

      const fileInput = view.container.querySelector('input[type="file"]');
      if (!(fileInput instanceof HTMLInputElement)) {
        throw new Error("Hidden workspace-import file input was not rendered");
      }
      const openPicker = vi.spyOn(fileInput, "click").mockImplementation(() => {});

      await click(findButton(view.container, "Import workspace JSON"));

      expect(openPicker).toHaveBeenCalledTimes(1);
    } finally {
      await view.unmount();
    }
  }, 15000);
});
