/** Project list CRUD: load/save/archive/delete/restore. */
import { t } from "../../../i18n";
import {
  archiveProjectRequest,
  deleteProjectRequest,
  listProjectsRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  restoreProjectRequest,
  saveProjectRequest
} from "../../../lib/api";
import { buildApiPayload } from "../../../lib/experiment";
import {
  resolveErrorMessage,
  toSavedProject,
  upsertSavedProject
} from "../helpers";
import {
  initialProjectHistoryWindow,
  initialProjectRevisionWindow,
  type ApplyStoreUpdate,
  type ProjectStoreActions,
  type ProjectStoreGet,
  type SyncPersistedProject
} from "../types";

export function createCrudActions(
  applyStoreUpdate: ApplyStoreUpdate,
  get: ProjectStoreGet,
  syncPersistedProject: SyncPersistedProject
): Pick<
  ProjectStoreActions,
  | "refreshProjects"
  | "loadProjects"
  | "loadProject"
  | "saveProject"
  | "persistAnalysisSnapshot"
  | "archiveProject"
  | "deleteProject"
  | "restoreProject"
> {
  return {
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
          projectMultiComparison: null,
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

      if (get().isReadOnlySession) {
        // Read-only session (public demo): analysis itself is allowed, but the
        // snapshot POST would 403 — skip it quietly instead of surfacing an error.
        return {
          message: t("wizardPanel.status.analysisCompletedGeneric"),
          projectId: null,
          analysisRunId: null
        };
      }

      const snapshotEligibleProjectId =
        get().activeProjectId !== null && !get().hasUnsavedChanges
          ? get().activeProjectId
          : null;

      if (!snapshotEligibleProjectId) {
        return {
          message: get().activeProjectId
            ? t("wizardPanel.status.analysisCompletedUnsavedDraft")
            : t("wizardPanel.status.analysisCompletedGeneric"),
          projectId: null,
          analysisRunId: null
        };
      }

      try {
        const updatedProject = await recordProjectAnalysisRequest(snapshotEligibleProjectId, analysisResult);
        syncPersistedProject(updatedProject, JSON.stringify(buildApiPayload(draft)));
        await get().refreshProjectHistory(snapshotEligibleProjectId, true);
        return {
          message: t("wizardPanel.status.analysisCompletedSnapshotSaved"),
          projectId: snapshotEligibleProjectId,
          analysisRunId: updatedProject.last_analysis_run_id ?? null
        };
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected analysis snapshot error")
        });
        return {
          message: t("wizardPanel.status.analysisCompletedSnapshotFailed"),
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

  };
}
