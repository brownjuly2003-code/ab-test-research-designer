import { hasApiSessionToken } from "../../lib/api";
import { deriveProjectState } from "./helpers";
import {
  initialProjectHistoryWindow,
  initialProjectRevisionWindow,
  type ProjectStoreValues
} from "./types";

export function createInitialProjectValues(): ProjectStoreValues {
  const baseState: Omit<
    ProjectStoreValues,
    | "activeProject"
    | "activeSavedProjects"
    | "archivedProjects"
    | "hasUnsavedChanges"
    | "selectedHistoryRun"
    | "canMutateBackend"
    | "isReadOnlySession"
    | "canUseCompute"
    | "backendMutationMessage"
  > = {
    loadingHealth: false,
    loadingDiagnostics: false,
    loadingProjects: false,
    deletingProjectId: null,
    restoringProjectId: null,
    isSavingProject: false,
    importingWorkspace: false,
    exportingWorkspace: false,
    backendHealth: null,
    backendDiagnostics: null,
    healthError: "",
    diagnosticsError: "",
    projectError: "",
    savedProjects: [],
    activeProjectId: null,
    savedProjectSnapshot: null,
    dirtyState: {
      currentSerializedForm: null,
      savedSerializedForm: null
    },
    projectHistory: null,
    projectHistoryError: "",
    loadingProjectHistory: false,
    projectHistoryWindow: initialProjectHistoryWindow,
    projectRevisions: null,
    projectRevisionsError: "",
    loadingProjectRevisions: false,
    projectRevisionWindow: initialProjectRevisionWindow,
    selectedHistoryRunId: null,
    projectComparison: null,
    projectMultiComparison: null,
    projectComparisonError: "",
    loadingProjectComparison: false,
    comparingProjectId: null,
    apiTokenDraft: "",
    apiTokenConfigured: hasApiSessionToken(),
    apiTokenStatus: ""
  };

  return {
    ...baseState,
    ...deriveProjectState(baseState)
  };
}
