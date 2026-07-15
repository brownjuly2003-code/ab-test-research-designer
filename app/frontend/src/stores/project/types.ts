import type {
  ProjectHistoryRequestOptions,
  ProjectRecordResponse,
  ProjectRevisionRequestOptions
} from "../../lib/api";
import type {
  AnalysisResponsePayload,
  ApiDiagnosticsResponse,
  ApiHealthResponse,
  ExportFormat,
  FullPayload,
  ProjectComparison,
  ProjectHistory,
  ProjectRevisionHistory,
  MultiProjectComparison,
  SavedProject
} from "../../lib/experiment";

export const initialProjectHistoryWindow = {
  analysisLimit: 3,
  exportLimit: 3
};

export const initialProjectRevisionWindow = {
  limit: 3
};

export type ProjectHistoryWindow = typeof initialProjectHistoryWindow;
export type ProjectRevisionWindow = typeof initialProjectRevisionWindow;
export type ProjectDirtyState = {
  currentSerializedForm: string | null;
  savedSerializedForm: string | null;
};

export type ProjectStoreValues = {
  loadingHealth: boolean;
  loadingDiagnostics: boolean;
  loadingProjects: boolean;
  deletingProjectId: string | null;
  restoringProjectId: string | null;
  isSavingProject: boolean;
  importingWorkspace: boolean;
  exportingWorkspace: boolean;
  backendHealth: ApiHealthResponse | null;
  backendDiagnostics: ApiDiagnosticsResponse | null;
  healthError: string;
  diagnosticsError: string;
  projectError: string;
  savedProjects: SavedProject[];
  activeProjectId: string | null;
  savedProjectSnapshot: string | null;
  dirtyState: ProjectDirtyState;
  projectHistory: ProjectHistory | null;
  projectHistoryError: string;
  loadingProjectHistory: boolean;
  projectHistoryWindow: ProjectHistoryWindow;
  projectRevisions: ProjectRevisionHistory | null;
  projectRevisionsError: string;
  loadingProjectRevisions: boolean;
  projectRevisionWindow: ProjectRevisionWindow;
  selectedHistoryRunId: string | null;
  projectComparison: ProjectComparison | null;
  projectMultiComparison: MultiProjectComparison | null;
  projectComparisonError: string;
  loadingProjectComparison: boolean;
  comparingProjectId: string | null;
  apiTokenDraft: string;
  apiTokenConfigured: boolean;
  apiTokenStatus: string;
  activeProject: SavedProject | null;
  activeSavedProjects: SavedProject[];
  archivedProjects: SavedProject[];
  hasUnsavedChanges: boolean;
  selectedHistoryRun: ProjectHistory["analysis_runs"][number] | null;
  canMutateBackend: boolean;
  // Confirmed read-scope session against an auth-enabled backend (e.g. the anonymous
  // public-demo scope). Write surfaces should be hidden — not merely disabled.
  isReadOnlySession: boolean;
  // Stateless calculators (/calculate, /analyze, /results/*, exports…) stay available
  // to read-scope sessions; they only need a confirmed reachable backend.
  canUseCompute: boolean;
  backendMutationMessage: string;
};

export type ProjectStoreActions = {
  clearProjectError: () => void;
  clearComparison: () => void;
  markDraftChanged: (serializedForm?: string) => void;
  resetProjectSelection: () => void;
  loadBackendHealth: () => Promise<ApiHealthResponse | null>;
  loadBackendDiagnostics: () => Promise<ApiDiagnosticsResponse | null>;
  refreshBackendState: (options?: { suppressProjectErrors?: boolean }) => Promise<ApiDiagnosticsResponse | null>;
  refreshProjects: () => Promise<boolean>;
  loadProjects: () => Promise<boolean>;
  refreshProjectHistory: (
    projectId: string,
    silent?: boolean,
    overrides?: Partial<ProjectHistoryWindow>,
    offsets?: Pick<ProjectHistoryRequestOptions, "analysisOffset" | "exportOffset">
  ) => Promise<boolean>;
  refreshProjectRevisions: (
    projectId: string,
    silent?: boolean,
    overrides?: Partial<ProjectRevisionWindow>,
    options?: Pick<ProjectRevisionRequestOptions, "offset">
  ) => Promise<boolean>;
  loadMoreAnalysisHistory: (projectId: string) => Promise<boolean>;
  loadMoreExportHistory: (projectId: string) => Promise<boolean>;
  loadMoreProjectRevisions: (projectId: string) => Promise<boolean>;
  saveProject: (
    draft: FullPayload,
    persistedAnalysis: AnalysisResponsePayload | null,
    currentAnalysisRunId: string | null
  ) => Promise<{
    message: string;
    savedProjectId: string | null;
    analysisRunId: string | null;
  } | null>;
  persistAnalysisSnapshot: (
    draft: FullPayload,
    analysisResult: AnalysisResponsePayload
  ) => Promise<{
    message: string;
    projectId: string | null;
    analysisRunId: string | null;
  }>;
  loadProject: (projectId: string) => Promise<ProjectRecordResponse | null>;
  archiveProject: (projectId: string) => Promise<{ deleted: boolean; deletedActive: boolean }>;
  deleteProject: (projectId: string) => Promise<{ deleted: boolean; deletedActive: boolean }>;
  restoreProject: (projectId: string) => Promise<ProjectRecordResponse | null>;
  exportWorkspace: () => Promise<string | null>;
  importWorkspace: (raw: string) => Promise<string | null>;
  updateApiTokenDraft: (value: string) => void;
  saveRuntimeApiToken: () => Promise<string | null>;
  clearRuntimeApiToken: () => Promise<string | null>;
  exportReport: (
    report: AnalysisResponsePayload["report"],
    format: ExportFormat,
    exportProjectId: string | null,
    linkedAnalysisRunId: string | null
  ) => Promise<string | null>;
  exportProjectPdf: (
    projectId: string,
    linkedAnalysisRunId: string | null
  ) => Promise<string | null>;
  exportProjectData: (
    projectId: string,
    format: "csv" | "xlsx"
  ) => Promise<string | null>;
  compareProjects: (projectIds: string[]) => Promise<string | null>;
  compareProject: (candidateProjectId: string) => Promise<string | null>;
  openHistoryRun: (runId: string) => boolean;
  clearHistoryRunSelection: () => boolean;
  loadProjectRevision: (revisionId: string) => { draft: FullPayload; message: string } | null;
};

export type ProjectStoreState = ProjectStoreValues & ProjectStoreActions;


export type ApplyStoreUpdate = (
  update:
    | Partial<ProjectStoreValues>
    | ((state: ProjectStoreState) => Partial<ProjectStoreValues>)
) => void;

export type SyncPersistedProject = (
  record: ProjectRecordResponse,
  serializedPayloadFallback: string
) => { savedProjectId: string | null; savedProject: SavedProject | null };

export type ProjectStoreGet = () => ProjectStoreState;
