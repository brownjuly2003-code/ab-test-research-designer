/** Project analysis history and revision windows. */
import {
  loadProjectHistoryRequest,
  loadProjectRevisionsRequest
} from "../../../lib/api";
import { hydrateLoadedPayload } from "../../../lib/experiment";
import { resolveErrorMessage } from "../helpers";
import type {
  ApplyStoreUpdate,
  ProjectStoreActions,
  ProjectStoreGet
} from "../types";

export function createHistoryActions(
  applyStoreUpdate: ApplyStoreUpdate,
  get: ProjectStoreGet
): Pick<
  ProjectStoreActions,
  | "refreshProjectHistory"
  | "loadMoreAnalysisHistory"
  | "loadMoreExportHistory"
  | "openHistoryRun"
  | "clearHistoryRunSelection"
  | "refreshProjectRevisions"
  | "loadMoreProjectRevisions"
  | "loadProjectRevision"
> {
  return {
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
        projectMultiComparison: null,
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
        projectMultiComparison: null,
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

  };
}
