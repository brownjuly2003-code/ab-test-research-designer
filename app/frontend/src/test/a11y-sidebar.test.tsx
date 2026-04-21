// @vitest-environment jsdom

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    exportAuditLogRequest: vi.fn(),
    listAuditLogRequest: vi.fn(),
    listTemplatesRequest: vi.fn(),
    useTemplateRequest: vi.fn()
  };
});

import ShortcutHelp from "../components/ShortcutHelp";
import SidebarPanel from "../components/SidebarPanel";
import TemplateGallery from "../components/TemplateGallery";
import { listAuditLogRequest, listTemplatesRequest } from "../lib/api";
import { buildApiPayload, cloneInitialState } from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import { click, flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

const initialAnalysisState = useAnalysisStore.getState();
const initialDraftState = useDraftStore.getState();
const initialProjectState = useProjectStore.getState();
const initialWizardState = useWizardStore.getState();

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

function seedSidebarState() {
  const savedProjects = [
    {
      id: "p-1",
      project_name: "Stored checkout test",
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
      last_exported_at: "2026-03-07T12:20:00Z",
      has_analysis_snapshot: true
    },
    {
      id: "p-2",
      project_name: "Archived pricing test",
      hypothesis: "Pricing layout changes conversion.",
      metric_type: "continuous" as const,
      duration_days: 15,
      payload_schema_version: 1,
      created_at: "2026-03-05T10:00:00Z",
      updated_at: "2026-03-06T12:00:00Z",
      archived_at: "2026-03-08T09:00:00Z",
      is_archived: true,
      revision_count: 1,
      last_revision_at: "2026-03-06T11:00:00Z",
      last_analysis_at: null,
      last_analysis_run_id: null,
      last_exported_at: null,
      has_analysis_snapshot: false
    }
  ];

  useProjectStore.setState({
    ...useProjectStore.getState(),
    loadingHealth: false,
    loadingDiagnostics: false,
    loadingProjects: false,
    deletingProjectId: null,
    restoringProjectId: null,
    importingWorkspace: false,
    exportingWorkspace: false,
    backendHealth: {
      status: "ok",
      service: "AB Test Research Designer API",
      version: "0.1.0",
      environment: "local"
    },
    backendDiagnostics: null,
    healthError: "",
    diagnosticsError: "",
    projectError: "",
    savedProjects,
    activeSavedProjects: savedProjects.filter((project) => !project.is_archived),
    archivedProjects: savedProjects.filter((project) => project.is_archived),
    activeProjectId: null,
    activeProject: null,
    savedProjectSnapshot: null,
    hasUnsavedChanges: false,
    projectHistory: null,
    projectHistoryError: "",
    loadingProjectHistory: false,
    projectRevisions: null,
    projectRevisionsError: "",
    loadingProjectRevisions: false,
    selectedHistoryRunId: null,
    selectedHistoryRun: null,
    projectComparison: null,
    projectComparisonError: "",
    loadingProjectComparison: false,
    comparingProjectId: null,
    apiTokenDraft: "",
    apiTokenConfigured: false,
    apiTokenStatus: "",
    canMutateBackend: true,
    backendMutationMessage: ""
  });
  useAnalysisStore.setState({
    ...useAnalysisStore.getState(),
    statusMessage: "",
    analysisError: ""
  });
}

describe("Sidebar and modal accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
    seedSidebarState();
    vi.mocked(listAuditLogRequest).mockResolvedValue({
      total: 0,
      entries: []
    });
    vi.mocked(listTemplatesRequest).mockResolvedValue([
      {
        id: "checkout_conversion",
        name: "Checkout Conversion",
        category: "Revenue",
        description: "Test checkout changes against conversion.",
        built_in: true,
        payload: buildApiPayload(cloneInitialState()),
        tags: ["binary", "checkout"],
        usage_count: 3
      }
    ]);
  });

  afterEach(() => {
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("has no critical or serious accessibility violations on the Projects tab", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations on the System tab", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      const systemButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "System"
      );
      if (!(systemButton instanceof HTMLButtonElement)) {
        throw new Error("System tab button was not rendered");
      }

      await click(systemButton);
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations when the template gallery is open", async () => {
    const view = await renderIntoDocument(
      <TemplateGallery
        onClose={vi.fn()}
        onApplyTemplate={vi.fn()}
      />
    );
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations when shortcut help is open", async () => {
    const view = await renderIntoDocument(<ShortcutHelp onClose={vi.fn()} />);
    try {
      await flushEffects();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations when project filters are visible", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      expect(view.container.querySelector("#saved-projects-search")).not.toBeNull();

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });

  it("has no critical or serious accessibility violations for workspace backup controls", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      const systemButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "System"
      );
      if (!(systemButton instanceof HTMLButtonElement)) {
        throw new Error("System tab button was not rendered");
      }

      await click(systemButton);
      await flushEffects();

      expect(view.container.textContent).toContain("Workspace backup");

      const results = await axe(view.container);

      (expect({
        ...results,
        violations: results.violations.filter(
          (violation) => violation.impact === "critical" || violation.impact === "serious"
        )
      }) as unknown as AxeMatcher).toHaveNoViolations();
    } finally {
      await view.unmount();
    }
  });
});
