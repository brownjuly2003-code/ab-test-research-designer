/**
 * Workspace backup import/export/validate client.
 */

import type {
  WorkspaceBundle,
  WorkspaceBundleInput,
  WorkspaceImportResponse,
  WorkspaceValidationResponse
} from "../experiment";
import { apiJsonRequest } from "./client";

export type WorkspaceExportResponse = WorkspaceBundle;
export type WorkspaceValidationSummary = WorkspaceValidationResponse;
export type WorkspaceImportSummary = WorkspaceImportResponse;

export async function exportWorkspaceRequest(): Promise<WorkspaceBundle> {
  return apiJsonRequest<WorkspaceBundle>("/api/v1/workspace/export", {
    errorFallback: "Workspace export failed"
  });
}

export async function importWorkspaceRequest(
  bundle: WorkspaceBundleInput | WorkspaceBundle
): Promise<WorkspaceImportResponse> {
  return apiJsonRequest<WorkspaceImportResponse>("/api/v1/workspace/import", {
    method: "POST",
    body: bundle,
    errorFallback: "Workspace import failed"
  });
}

export async function validateWorkspaceRequest(
  bundle: WorkspaceBundleInput | WorkspaceBundle
): Promise<WorkspaceValidationResponse> {
  return apiJsonRequest<WorkspaceValidationResponse>("/api/v1/workspace/validate", {
    method: "POST",
    body: bundle,
    errorFallback: "Workspace validation failed"
  });
}
