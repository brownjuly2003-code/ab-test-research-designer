/** Report/data exports and project comparison. */
import {
  compareMultipleProjectsRequest,
  compareProjectsRequest,
  downloadProjectReportDataRequest,
  downloadProjectReportPdfRequest,
  exportReportRequest,
  recordProjectExportRequest
} from "../../../lib/api";
import { downloadFile, resolveErrorMessage } from "../helpers";
import type {
  ApplyStoreUpdate,
  ProjectStoreActions,
  ProjectStoreGet,
  SyncPersistedProject
} from "../types";

export function createExportsActions(
  applyStoreUpdate: ApplyStoreUpdate,
  get: ProjectStoreGet,
  syncPersistedProject: SyncPersistedProject
): Pick<
  ProjectStoreActions,
  | "compareProjects"
  | "compareProject"
  | "exportReport"
  | "exportProjectPdf"
  | "exportProjectData"
> {
  return {
    compareProjects: async (projectIds) => {
      if (projectIds.length < 2) {
        return null;
      }

      applyStoreUpdate({
        loadingProjectComparison: true,
        comparingProjectId: null,
        projectComparisonError: ""
      });

      try {
        const comparison = await compareMultipleProjectsRequest(projectIds);
        applyStoreUpdate({
          projectComparison: null,
          projectMultiComparison: comparison
        });
        return `Loaded comparison dashboard for ${projectIds.length} projects.`;
      } catch (error) {
        applyStoreUpdate({
          projectMultiComparison: null,
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
          projectComparison: comparison,
          projectMultiComparison: null
        });
        return `Loaded saved-project comparison against ${candidateName}.`;
      } catch (error) {
        applyStoreUpdate({
          projectComparison: null,
          projectMultiComparison: null,
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

        if (!exportProjectId || get().isReadOnlySession) {
          // Read-only sessions can render exports but not record export metadata.
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
    },
    exportProjectPdf: async (projectId, linkedAnalysisRunId) => {
      get().clearProjectError();

      try {
        const { blob, filename } = await downloadProjectReportPdfRequest(projectId);
        downloadFile(blob, filename, "application/pdf");

        if (get().isReadOnlySession) {
          return "Exported report as PDF.";
        }

        try {
          const updatedProject = await recordProjectExportRequest(projectId, "pdf", linkedAnalysisRunId);
          syncPersistedProject(
            updatedProject,
            get().savedProjectSnapshot ?? get().dirtyState.currentSerializedForm ?? ""
          );
          await get().refreshProjectHistory(projectId, true);
          return "Exported report as PDF and updated project export metadata.";
        } catch (error) {
          applyStoreUpdate({
            projectError: resolveErrorMessage(error, "Unexpected PDF export metadata error")
          });
          return "Exported report as PDF, but project export metadata was not updated.";
        }
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, "Unexpected PDF export error")
        });
        return null;
      }
    },
    exportProjectData: async (projectId, format) => {
      get().clearProjectError();

      try {
        const { blob, filename } = await downloadProjectReportDataRequest(projectId, format);
        downloadFile(
          blob,
          filename,
          format === "csv"
            ? "text/csv"
            : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        );
        return `Exported project data as ${format.toUpperCase()}.`;
      } catch (error) {
        applyStoreUpdate({
          projectError: resolveErrorMessage(error, `Unexpected ${format.toUpperCase()} export error`)
        });
        return null;
      }
    },

  };
}
