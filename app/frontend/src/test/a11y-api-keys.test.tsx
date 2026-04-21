// @vitest-environment jsdom

import "vitest-axe/extend-expect";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import * as matchers from "vitest-axe/matchers";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    createApiKeyRequest: vi.fn(),
    deleteApiKeyRequest: vi.fn(),
    exportAuditLogRequest: vi.fn(),
    listApiKeysRequest: vi.fn(),
    listAuditLogRequest: vi.fn(),
    listTemplatesRequest: vi.fn(),
    revokeApiKeyRequest: vi.fn(),
    useTemplateRequest: vi.fn()
  };
});

import SidebarPanel from "../components/SidebarPanel";
import { listApiKeysRequest, setAdminSessionToken, clearAdminSessionToken } from "../lib/api";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import { click, flushEffects, renderIntoDocument } from "./dom";

expect.extend(matchers);

type AxeMatcher = {
  toHaveNoViolations: () => void;
};

const initialAnalysisState = useAnalysisStore.getState();
const initialDraftState = useDraftStore.getState();
const initialProjectState = useProjectStore.getState();
const initialWizardState = useWizardStore.getState();

function seedSidebarState() {
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
      version: "1.0.0",
      environment: "local"
    },
    backendDiagnostics: null,
    healthError: "",
    diagnosticsError: "",
    projectError: "",
    savedProjects: [],
    activeSavedProjects: [],
    archivedProjects: [],
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
}

describe("API keys accessibility", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
    seedSidebarState();
    setAdminSessionToken("admin-secret");
    vi.mocked(listApiKeysRequest).mockResolvedValue({
      keys: [
        {
          id: "key-1",
          name: "Partner read key",
          scope: "read",
          created_at: "2026-04-21T07:00:00Z",
          last_used_at: null,
          revoked_at: null,
          rate_limit_requests: null,
          rate_limit_window_seconds: null
        }
      ],
      total: 1
    });
  });

  afterEach(() => {
    clearAdminSessionToken();
    useAnalysisStore.setState(initialAnalysisState, true);
    useDraftStore.setState(initialDraftState, true);
    useProjectStore.setState(initialProjectState, true);
    useWizardStore.setState(initialWizardState, true);
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it("has no critical or serious accessibility violations on the API keys tab", async () => {
    const view = await renderIntoDocument(<SidebarPanel />);
    try {
      await flushEffects();

      const apiKeysButton = Array.from(view.container.querySelectorAll("button")).find(
        (button) => button.textContent?.trim() === "API keys"
      );
      if (!(apiKeysButton instanceof HTMLButtonElement)) {
        throw new Error("API keys tab button was not rendered");
      }

      await click(apiKeysButton);
      await flushEffects();
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
  }, 15000);
});
