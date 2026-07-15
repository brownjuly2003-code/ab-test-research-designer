/** Full workspace backup export / import. */
import {
  exportWorkspaceRequest,
  importWorkspaceRequest,
  validateWorkspaceRequest
} from "../../../lib/api";
import { downloadFile, resolveErrorMessage } from "../helpers";
import type {
  ApplyStoreUpdate,
  ProjectStoreActions,
  ProjectStoreGet
} from "../types";

export function createWorkspaceActions(
  applyStoreUpdate: ApplyStoreUpdate,
  get: ProjectStoreGet
): Pick<ProjectStoreActions, "exportWorkspace" | "importWorkspace"> {
  return {
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

  };
}
