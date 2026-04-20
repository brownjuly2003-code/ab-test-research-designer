import { create } from "zustand";

import {
  archiveProjectRequest,
  clearApiSessionToken,
  compareProjectsRequest,
  deleteProjectRequest,
  exportReportRequest,
  exportWorkspaceRequest,
  hasApiSessionToken,
  importWorkspaceRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRevisionsRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestDiagnostics,
  requestHealth,
  restoreProjectRequest,
  saveProjectRequest,
  setApiSessionToken,
  validateWorkspaceRequest,
  type ProjectHistoryRequestOptions,
  type ProjectRecordResponse,
  type ProjectRevisionRequestOptions
} from "../lib/api";
import {
  buildApiPayload,
  hydrateLoadedPayload,
  type AnalysisResponsePayload,
  type ApiDiagnosticsResponse,
  type ApiHealthResponse,
  type ExportFormat,
  type FullPayload,
  type ProjectComparison,
  type ProjectHistory,
  type ProjectRevisionHistory,
  type SavedProject
} from "../lib/experiment";

export const initialProjectHistoryWindow = {
  analysisLimit: 3,
  exportLimit: 3
};

export const initialProjectRevisionWindow = {
  limit: 3
};

type ProjectHistoryWindow = typeof initialProjectHistoryWindow;
type ProjectRevisionWindow = typeof initialProjectRevisionWindow;
type ProjectDirtyState = {
  currentSerializedForm: string | null;
  savedSerializedForm: string | null;
};

type ProjectStoreValues = {
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
  backendMutationMessage: string;
};

type ProjectStoreActions = {
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
  compareProject: (candidateProjectId: string) => Promise<string | null>;
  openHistoryRun: (runId: string) => boolean;
  clearHistoryRunSelection: () => boolean;
  loadProjectRevision: (revisionId: string) => { draft: FullPayload; message: string } | null;
};

export type ProjectStoreState = ProjectStoreValues & ProjectStoreActions;

function toSavedProject(project: {
  id?: string;
  project_name?: string;
  created_at?: string;
  updated_at?: string;
  payload_schema_version?: number;
  revision_count?: number;
  last_revision_at?: string | null;
  archived_at?: string | null;
  is_archived?: boolean;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
}): SavedProject | null {
  if (
    typeof project.id !== "string" ||
    typeof project.project_name !== "string" ||
    typeof project.created_at !== "string" ||
    typeof project.updated_at !== "string"
  ) {
    return null;
  }

  return {
    id: project.id,
    project_name: project.project_name,
    created_at: project.created_at,
    updated_at: project.updated_at,
    payload_schema_version: project.payload_schema_version ?? 1,
    archived_at: project.archived_at ?? null,
    is_archived: project.is_archived ?? false,
    revision_count: project.revision_count ?? 0,
    last_revision_at: project.last_revision_at ?? null,
    last_analysis_at: project.last_analysis_at ?? null,
    last_analysis_run_id: project.last_analysis_run_id ?? null,
    last_exported_at: project.last_exported_at ?? null,
    has_analysis_snapshot: project.has_analysis_snapshot ?? false
  };
}

function resolveErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function downloadFile(content: BlobPart, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function upsertSavedProject(projects: SavedProject[], project: SavedProject): SavedProject[] {
  return [project, ...projects.filter((candidate) => candidate.id !== project.id)].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at)
  );
}

function deriveProjectState(
  state: Pick<
    ProjectStoreValues,
    | "savedProjects"
    | "activeProjectId"
    | "dirtyState"
    | "projectHistory"
    | "selectedHistoryRunId"
    | "backendHealth"
    | "backendDiagnostics"
  >
): Pick<
  ProjectStoreValues,
  | "activeProject"
  | "activeSavedProjects"
  | "archivedProjects"
  | "hasUnsavedChanges"
  | "selectedHistoryRun"
  | "canMutateBackend"
  | "backendMutationMessage"
> {
  const activeProject =
    state.activeProjectId !== null
      ? state.savedProjects.find((project) => project.id === state.activeProjectId) ?? null
      : null;
  const activeSavedProjects = state.savedProjects.filter((project) => !project.is_archived);
  const archivedProjects = state.savedProjects.filter((project) => project.is_archived);
  const hasUnsavedChanges =
    state.activeProjectId !== null &&
    state.dirtyState.savedSerializedForm !== null &&
    state.dirtyState.currentSerializedForm !== state.dirtyState.savedSerializedForm;
  const selectedHistoryRun =
    state.selectedHistoryRunId && state.projectHistory
      ? state.projectHistory.analysis_runs.find((run) => run.id === state.selectedHistoryRunId) ?? null
      : null;
  const backendAuth = state.backendDiagnostics?.auth ?? null;
  const diagnosticsKnown = backendAuth !== null;
  const canMutateBackend =
    diagnosticsKnown &&
    (
      !backendAuth.enabled ||
      backendAuth.write_enabled
    );
  const backendMutationMessage =
    !state.backendHealth
      ? "Backend is unavailable. Mutating actions stay disabled until health and diagnostics recover."
      : !diagnosticsKnown
        ? "Backend auth state is not confirmed yet. Refresh diagnostics or provide a browser-session API token."
        : backendAuth.enabled && !canMutateBackend
          ? "Backend is running in read-only API mode for this session. Save, analysis, report export, workspace import, and project archiving are disabled until a write-capable token is configured."
          : "";

  return {
    activeProject,
    activeSavedProjects,
    archivedProjects,
    hasUnsavedChanges,
    selectedHistoryRun,
    canMutateBackend,
    backendMutationMessage
  };
}

function createInitialProjectValues(): ProjectStoreValues {
  const baseState: Omit<
    ProjectStoreValues,
    | "activeProject"
    | "activeSavedProjects"
    | "archivedProjects"
    | "hasUnsavedChanges"
    | "selectedHistoryRun"
    | "canMutateBackend"
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

export const useProjectStore = create<ProjectStoreState>((set, get) => {
  function applyStoreUpdate(
    update:
      | Partial<ProjectStoreValues>
      | ((state: ProjectStoreState) => Partial<ProjectStoreValues>)
  ) {
    const partial = typeof update === "function" ? update(get()) : update;
    const nextState = {
      ...get(),
      ...partial
    };

    set({
      ...partial,
      ...deriveProjectState(nextState)
    });
  }

  function syncPersistedProject(
    record: ProjectRecordResponse,
    serializedPayloadFallback: string
  ): { savedProjectId: string | null; savedProject: SavedProject | null } {
    const savedProjectId = typeof record.id === "string" ? record.id : null;
    const savedProject = toSavedProject(record);
    const persistedSnapshot =
      record.payload ? JSON.stringify(record.payload) : serializedPayloadFallback;

    applyStoreUpdate((state) => ({
      activeProjectId: savedProjectId,
      savedProjectSnapshot: persistedSnapshot,
      dirtyState: {
        currentSerializedForm: persistedSnapshot,
        savedSerializedForm: persistedSnapshot
      },
      savedProjects: savedProject ? upsertSavedProject(state.savedProjects, savedProject) : state.savedProjects
    }));

    return { savedProjectId, savedProject };
  }

  return {
    ...createInitialProjectValues(),

    // Projects
    clearProjectError: () => {
      applyStoreUpdate({ projectError: "" });
    },
    clearComparison: () => {
      applyStoreUpdate({
        projectComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null
      });
    },
    markDraftChanged: (serializedForm) => {
      applyStoreUpdate((state) => ({
        selectedHistoryRunId: null,
        projectComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null,
        dirtyState:
          serializedForm === undefined
            ? state.dirtyState
            : {
                ...state.dirtyState,
                currentSerializedForm: serializedForm
              }
      }));
    },
    resetProjectSelection: () => {
      applyStoreUpdate({
        activeProjectId: null,
        savedProjectSnapshot: null,
        dirtyState: {
          currentSerializedForm: null,
          savedSerializedForm: null
        },
        projectHistory: null,
        projectHistoryWindow: initialProjectHistoryWindow,
        projectHistoryError: "",
        loadingProjectHistory: false,
        projectRevisions: null,
        projectRevisionWindow: initialProjectRevisionWindow,
        projectRevisionsError: "",
        loadingProjectRevisions: false,
        selectedHistoryRunId: null,
        projectComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null
      });
    },
    refreshProjects: async () => {
      applyStoreUpdate({
        projectError: "",
        loadingProjects: true
      });

      try {
        applyStoreUpdate({
          savedProjects: await listProjectsRequest({ includeArchived: true })
        });
        return true;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected project list error")
        });
        return false;
      } finally {
        applyStoreUpdate({ loadingProjects: false });
      }
    },
    loadProjects: async () => {
      return await get().refreshProjects();
    },
    loadProject: async (projectId) => {
      get().clearProjectError();

      try {
        const data = await loadProjectRequest(projectId);
        const savedProject = toSavedProject(data);
        const resolvedProjectId = typeof data.id === "string" ? data.id : projectId;
        const loadedSnapshot = JSON.stringify(data.payload);

        applyStoreUpdate((state) => ({
          activeProjectId: resolvedProjectId,
          savedProjectSnapshot: loadedSnapshot,
          dirtyState: {
            currentSerializedForm: loadedSnapshot,
            savedSerializedForm: loadedSnapshot
          },
          savedProjects: savedProject ? upsertSavedProject(state.savedProjects, savedProject) : state.savedProjects,
          projectHistory: null,
          projectHistoryWindow: initialProjectHistoryWindow,
          projectHistoryError: "",
          projectRevisions: null,
          projectRevisionWindow: initialProjectRevisionWindow,
          projectRevisionsError: "",
          selectedHistoryRunId: null,
          projectComparison: null,
          projectComparisonError: "",
          loadingProjectComparison: false,
          comparingProjectId: null
        }));

        await get().refreshProjectHistory(resolvedProjectId, false, initialProjectHistoryWindow);
        await get().refreshProjectRevisions(resolvedProjectId, false, initialProjectRevisionWindow);

        return data;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected project load error")
        });
        return null;
      }
    },
    saveProject: async (draft, persistedAnalysis, currentAnalysisRunId) => {
      get().clearProjectError();
      applyStoreUpdate({ isSavingProject: true });
      const isUpdate = get().activeProjectId !== null;

      try {
        const normalizedPayloadJson = JSON.stringify(buildApiPayload(draft));
        const data = await saveProjectRequest(draft, get().activeProjectId);
        const { savedProjectId, savedProject } = syncPersistedProject(data, normalizedPayloadJson);
        let message = isUpdate
          ? `Project ${String(data.project_name)} updated locally.`
          : `Project saved locally with id ${String(data.id)}.`;
        let analysisRunId = currentAnalysisRunId;

        if (savedProjectId && persistedAnalysis && currentAnalysisRunId === null) {
          try {
            const updatedProject = await recordProjectAnalysisRequest(savedProjectId, persistedAnalysis);
            syncPersistedProject(updatedProject, normalizedPayloadJson);
            analysisRunId = updatedProject.last_analysis_run_id ?? null;
            message = `${message} Latest analysis snapshot was recorded for this saved project.`;
          } catch (error) {
            applyStoreUpdate({
              projectError: resolveErrorMessage(error, "Unexpected analysis snapshot save error")
            });
            message = `${message} Current analysis is still local until the snapshot is recorded.`;
          }
        }

        if (!savedProject) {
          await get().refreshProjects();
        }
        if (savedProjectId) {
          await get().refreshProjectHistory(savedProjectId, true);
          await get().refreshProjectRevisions(savedProjectId, true);
        }
        get().clearComparison();

        return {
          message,
          savedProjectId,
          analysisRunId
        };
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected save error")
        });
        return null;
      } finally {
        applyStoreUpdate({ isSavingProject: false });
      }
    },
    persistAnalysisSnapshot: async (draft, analysisResult) => {
      get().clearProjectError();
      get().markDraftChanged();

      const snapshotEligibleProjectId =
        get().activeProjectId !== null && !get().hasUnsavedChanges
          ? get().activeProjectId
          : null;

      if (!snapshotEligibleProjectId) {
        return {
          message: get().activeProjectId
            ? "Analysis completed for draft changes. Save the project to persist this analysis snapshot."
            : "Analysis completed. Deterministic output and optional AI advice are shown below.",
          projectId: null,
          analysisRunId: null
        };
      }

      try {
        const updatedProject = await recordProjectAnalysisRequest(snapshotEligibleProjectId, analysisResult);
        syncPersistedProject(updatedProject, JSON.stringify(buildApiPayload(draft)));
        await get().refreshProjectHistory(snapshotEligibleProjectId, true);
        return {
          message: "Analysis completed and the latest snapshot was recorded for this saved project.",
          projectId: snapshotEligibleProjectId,
          analysisRunId: updatedProject.last_analysis_run_id ?? null
        };
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected analysis snapshot error")
        });
        return {
          message: "Analysis completed, but project snapshot metadata could not be persisted.",
          projectId: snapshotEligibleProjectId,
          analysisRunId: null
        };
      }
    },
    archiveProject: async (projectId) => {
      get().clearProjectError();
      applyStoreUpdate({ deletingProjectId: projectId });

      try {
        const archived = await archiveProjectRequest(projectId);
        const archivedAt = archived?.archived_at ?? new Date().toISOString();

        applyStoreUpdate((state) => ({
          savedProjects: state.savedProjects.map((project) =>
            project.id === projectId
              ? {
                  ...project,
                  archived_at: archivedAt,
                  is_archived: true,
                  updated_at: archivedAt
                }
              : project
          )
        }));

        const deletedActive = get().activeProjectId === projectId;
        if (deletedActive) {
          get().resetProjectSelection();
        }

        return {
          deleted: true,
          deletedActive
        };
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected project archive error")
        });
        return { deleted: false, deletedActive: false };
      } finally {
        applyStoreUpdate({ deletingProjectId: null });
      }
    },
    deleteProject: async (projectId) => {
      get().clearProjectError();
      applyStoreUpdate({ deletingProjectId: projectId });

      try {
        await deleteProjectRequest(projectId);
        applyStoreUpdate((state) => ({
          savedProjects: state.savedProjects.filter((project) => project.id !== projectId)
        }));

        const deletedActive = get().activeProjectId === projectId;
        if (deletedActive) {
          get().resetProjectSelection();
        }

        return {
          deleted: true,
          deletedActive
        };
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected project delete error")
        });
        return { deleted: false, deletedActive: false };
      } finally {
        applyStoreUpdate({ deletingProjectId: null });
      }
    },
    restoreProject: async (projectId) => {
      get().clearProjectError();
      applyStoreUpdate({ restoringProjectId: projectId });

      try {
        const restored = await restoreProjectRequest(projectId);
        const savedProject = toSavedProject(restored);
        if (savedProject) {
          applyStoreUpdate((state) => ({
            savedProjects: upsertSavedProject(state.savedProjects, savedProject)
          }));
        }

        return restored;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected project restore error")
        });
        return null;
      } finally {
        applyStoreUpdate({ restoringProjectId: null });
      }
    },

    // Backend state
    loadBackendHealth: async () => {
      applyStoreUpdate({ loadingHealth: true });

      try {
        const health = await requestHealth();
        applyStoreUpdate({
          backendHealth: health,
          healthError: ""
        });
        return health;
      } catch (error) {
        applyStoreUpdate({
          backendHealth: null,
          healthError: resolveErrorMessage(error, "Unexpected backend health error")
        });
        return null;
      } finally {
        applyStoreUpdate({ loadingHealth: false });
      }
    },
    loadBackendDiagnostics: async () => {
      applyStoreUpdate({ loadingDiagnostics: true });

      try {
        const diagnostics = await requestDiagnostics();
        applyStoreUpdate({
          backendDiagnostics: diagnostics,
          diagnosticsError: ""
        });
        return diagnostics;
      } catch (error) {
        applyStoreUpdate({
          backendDiagnostics: null,
          diagnosticsError: resolveErrorMessage(error, "Unexpected backend diagnostics error")
        });
        return null;
      } finally {
        applyStoreUpdate({ loadingDiagnostics: false });
      }
    },
    refreshBackendState: async (options = {}) => {
      get().clearProjectError();
      const [health, diagnostics] = await Promise.all([
        get().loadBackendHealth(),
        get().loadBackendDiagnostics()
      ]);

      if (health || diagnostics) {
        const loaded = await get().refreshProjects();
        if (!loaded && options.suppressProjectErrors) {
          get().clearProjectError();
        }
      }

      return diagnostics;
    },
    updateApiTokenDraft: (value) => {
      applyStoreUpdate({ apiTokenDraft: value });
    },
    saveRuntimeApiToken: async () => {
      get().clearProjectError();
      const normalizedToken = get().apiTokenDraft.trim();

      if (!normalizedToken) {
        return null;
      }

      setApiSessionToken(normalizedToken);
      applyStoreUpdate({
        apiTokenStatus: "Verifying token against backend diagnostics...",
        apiTokenConfigured: hasApiSessionToken(),
        apiTokenDraft: ""
      });

      const diagnostics = await get().refreshBackendState({ suppressProjectErrors: true });

      if (!diagnostics) {
        const message = "Token saved in this browser session, but backend access is still not confirmed.";
        applyStoreUpdate({ apiTokenStatus: message });
        return message;
      }

      if (!diagnostics.auth.enabled) {
        const message = "Backend is open. A session token is not required for this runtime.";
        applyStoreUpdate({ apiTokenStatus: message });
        return message;
      }

      const message = diagnostics.auth.write_enabled
        ? "Token accepted. Write-capable backend access is available in this browser session."
        : "Token accepted, but this backend session remains read-only.";

      applyStoreUpdate({ apiTokenStatus: message });
      return message;
    },
    clearRuntimeApiToken: async () => {
      get().clearProjectError();
      clearApiSessionToken();
      applyStoreUpdate({
        apiTokenConfigured: false,
        apiTokenDraft: ""
      });
      get().resetProjectSelection();
      applyStoreUpdate({
        savedProjects: []
      });
      const message = "Token cleared from this browser session.";
      applyStoreUpdate({ apiTokenStatus: message });
      await get().refreshBackendState({ suppressProjectErrors: true });
      return message;
    },
    exportWorkspace: async () => {
      get().clearProjectError();
      applyStoreUpdate({ exportingWorkspace: true });

      try {
        const bundle = await exportWorkspaceRequest();
        const safeTimestamp = bundle.generated_at.replace(/[:]/g, "-");
        downloadFile(
          JSON.stringify(bundle, null, 2),
          `ab-test-workspace-${safeTimestamp}.json`,
          "application/json"
        );
        const signedBackup = Boolean(bundle.integrity?.signature_hmac_sha256);
        return `Exported ${signedBackup ? "signed " : ""}workspace backup with ${String(bundle.projects.length)} project(s).`;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected workspace export error")
        });
        return null;
      } finally {
        applyStoreUpdate({ exportingWorkspace: false });
      }
    },
    importWorkspace: async (raw) => {
      get().clearProjectError();
      applyStoreUpdate({ importingWorkspace: true });

      try {
        const parsed = JSON.parse(raw);
        const validation = await validateWorkspaceRequest(parsed);
        const result = await importWorkspaceRequest(parsed);
        await get().refreshProjects();
        await get().loadBackendDiagnostics();
        const shortChecksum = validation.checksum_sha256.slice(0, 12);
        const validationLabel = validation.signature_verified ? "Validated signed workspace backup" : "Validated workspace backup";

        return `${validationLabel} (schema v${String(validation.schema_version)}, checksum ${shortChecksum}...). ` +
          `Imported workspace backup: ${String(result.imported_projects)} project(s), ` +
          `${String(result.imported_analysis_runs)} analysis run(s), ` +
          `${String(result.imported_export_events)} export event(s), ` +
          `${String(result.imported_project_revisions ?? 0)} revision(s).`;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected workspace import error")
        });
        return null;
      } finally {
        applyStoreUpdate({ importingWorkspace: false });
      }
    },

    // History
    refreshProjectHistory: async (projectId, silent = false, overrides, offsets) => {
      const nextWindow = {
        analysisLimit: overrides?.analysisLimit ?? get().projectHistoryWindow.analysisLimit,
        exportLimit: overrides?.exportLimit ?? get().projectHistoryWindow.exportLimit
      };

      applyStoreUpdate({
        projectHistoryWindow: nextWindow,
        projectHistoryError: "",
        ...(silent ? {} : { loadingProjectHistory: true })
      });

      try {
        applyStoreUpdate({
          projectHistory: await loadProjectHistoryRequest(projectId, {
            analysisLimit: nextWindow.analysisLimit,
            exportLimit: nextWindow.exportLimit,
            analysisOffset: offsets?.analysisOffset,
            exportOffset: offsets?.exportOffset
          })
        });
        return true;
      } catch (error) {
        applyStoreUpdate({
          projectHistory: null,
          projectHistoryError: resolveErrorMessage(error, "Unexpected project history error")
        });
        return false;
      } finally {
        if (!silent) {
          applyStoreUpdate({ loadingProjectHistory: false });
        }
      }
    },
    loadMoreAnalysisHistory: async (projectId) => {
      return await get().refreshProjectHistory(projectId, false, {
        analysisLimit: get().projectHistoryWindow.analysisLimit + 5
      });
    },
    loadMoreExportHistory: async (projectId) => {
      return await get().refreshProjectHistory(projectId, false, {
        exportLimit: get().projectHistoryWindow.exportLimit + 5
      });
    },
    openHistoryRun: (runId) => {
      if (!get().projectHistory) {
        return false;
      }

      const targetRun = get().projectHistory?.analysis_runs.find((run) => run.id === runId);
      if (!targetRun) {
        return false;
      }

      applyStoreUpdate({
        selectedHistoryRunId: targetRun.id,
        projectComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null
      });
      return true;
    },
    clearHistoryRunSelection: () => {
      if (!get().selectedHistoryRunId) {
        return false;
      }

      applyStoreUpdate({ selectedHistoryRunId: null });
      return true;
    },

    // Revisions
    refreshProjectRevisions: async (projectId, silent = false, overrides, options) => {
      const nextWindow = {
        limit: overrides?.limit ?? get().projectRevisionWindow.limit
      };

      applyStoreUpdate({
        projectRevisionWindow: nextWindow,
        projectRevisionsError: "",
        ...(silent ? {} : { loadingProjectRevisions: true })
      });

      try {
        applyStoreUpdate({
          projectRevisions: await loadProjectRevisionsRequest(projectId, {
            limit: nextWindow.limit,
            offset: options?.offset
          })
        });
        return true;
      } catch (error) {
        applyStoreUpdate({
          projectRevisions: null,
          projectRevisionsError: resolveErrorMessage(error, "Unexpected project revision error")
        });
        return false;
      } finally {
        if (!silent) {
          applyStoreUpdate({ loadingProjectRevisions: false });
        }
      }
    },
    loadMoreProjectRevisions: async (projectId) => {
      return await get().refreshProjectRevisions(projectId, false, {
        limit: get().projectRevisionWindow.limit + 5
      });
    },
    loadProjectRevision: (revisionId) => {
      get().clearProjectError();
      const revision = get().projectRevisions?.revisions.find((item) => item.id === revisionId);

      if (!revision) {
        applyStoreUpdate({
          projectError: "Saved revision not found."
        });
        return null;
      }

      const revisionSnapshot = JSON.stringify(revision.payload);
      applyStoreUpdate((state) => ({
        selectedHistoryRunId: null,
        projectComparison: null,
        projectComparisonError: "",
        loadingProjectComparison: false,
        comparingProjectId: null,
        dirtyState: {
          ...state.dirtyState,
          currentSerializedForm: revisionSnapshot
        }
      }));

      return {
        draft: hydrateLoadedPayload(revision.payload),
        message:
          `Loaded ${revision.source.replace("_", " ")} revision from ${revision.created_at}. ` +
          "Save the project to persist it as the latest local version."
      };
    },

    // Comparison
    compareProject: async (candidateProjectId) => {
      const activeProjectId = get().activeProjectId;

      if (!activeProjectId) {
        return null;
      }

      const candidateName = get().savedProjects.find((project) => project.id === candidateProjectId)?.project_name ?? candidateProjectId;
      applyStoreUpdate({
        loadingProjectComparison: true,
        comparingProjectId: candidateProjectId,
        projectComparisonError: ""
      });

      try {
        const comparison = await compareProjectsRequest(
          activeProjectId,
          candidateProjectId,
          get().selectedHistoryRunId ?? undefined
        );
        applyStoreUpdate({
          projectComparison: comparison
        });
        return `Loaded saved-project comparison against ${candidateName}.`;
      } catch (error) {
        applyStoreUpdate({
          projectComparison: null,
          projectComparisonError: resolveErrorMessage(error, "Unexpected project comparison error")
        });
        return null;
      } finally {
        applyStoreUpdate({
          loadingProjectComparison: false,
          comparingProjectId: null
        });
      }
    },

    // Snapshot
    exportReport: async (report, format, exportProjectId, linkedAnalysisRunId) => {
      get().clearProjectError();

      try {
        const extension = format === "markdown" ? "md" : "html";
        const content = await exportReportRequest(report, format);
        downloadFile(
          content,
          `experiment-report.${extension}`,
          format === "markdown" ? "text/markdown" : "text/html"
        );

        if (!exportProjectId) {
          return `Exported report as ${extension.toUpperCase()}.`;
        }

        try {
          const updatedProject = await recordProjectExportRequest(exportProjectId, format, linkedAnalysisRunId);
          syncPersistedProject(
            updatedProject,
            get().savedProjectSnapshot ?? get().dirtyState.currentSerializedForm ?? ""
          );
          await get().refreshProjectHistory(exportProjectId, true);
          return `Exported report as ${extension.toUpperCase()} and updated project export metadata.`;
        } catch (error) {
          applyStoreUpdate({
            projectError: resolveErrorMessage(error, "Unexpected export metadata error")
          });
          return `Exported report as ${extension.toUpperCase()}, but project export metadata was not updated.`;
        }
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected export error")
        });
        return null;
      }
    }
  };
});
