import {
  apiUrl,
  type ProjectHistory,
  type ProjectComparison,
  type ProjectRevisionHistory,
  type ApiHealthResponse,
  type ApiDiagnosticsResponse,
  type WorkspaceBundle,
  type WorkspaceBundleInput,
  type WorkspaceImportResponse,
  buildApiPayload,
  type AnalysisResponsePayload,
  type ApiErrorResponse,
  type ExportFormat,
  type FullPayload,
  type ProjectRecordPayload,
  type ReportResponse,
  type SavedProject
} from "./experiment";
import type {
  ExportResponse,
  ProjectDeleteResponse as GeneratedProjectDeleteResponse,
  ProjectListResponse as GeneratedProjectListResponse
} from "./generated/api-contract";

export type ProjectRecordResponse = ProjectRecordPayload;
export type SaveProjectResponse = ProjectRecordPayload;
export type DeleteProjectResponse = GeneratedProjectDeleteResponse;
export type AnalysisResponse = AnalysisResponsePayload;
export type DiagnosticsResponse = ApiDiagnosticsResponse;
export type WorkspaceExportResponse = WorkspaceBundle;
export type WorkspaceImportSummary = WorkspaceImportResponse;
export type ProjectHistoryRequestOptions = {
  analysisLimit?: number;
  analysisOffset?: number;
  exportLimit?: number;
  exportOffset?: number;
};
export type ProjectRevisionRequestOptions = {
  limit?: number;
  offset?: number;
};

function buildHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
  const headers = { ...additionalHeaders };
  const apiToken = String(import.meta.env.VITE_API_TOKEN ?? "").trim();
  if (apiToken) {
    headers.Authorization = `Bearer ${apiToken}`;
  }
  return headers;
}

async function readJson<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

function getErrorMessage(payload: ApiErrorResponse, fallback: string): string {
  return typeof payload.detail === "string" ? payload.detail : fallback;
}

export async function requestHealth(): Promise<ApiHealthResponse> {
  const response = await fetch(apiUrl("/health"), {
    headers: buildHeaders()
  });
  const data = await readJson<ApiHealthResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Health check failed"));
  }

  return data;
}

export async function requestDiagnostics(): Promise<ApiDiagnosticsResponse> {
  const response = await fetch(apiUrl("/api/v1/diagnostics"), {
    headers: buildHeaders()
  });
  const data = await readJson<ApiDiagnosticsResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Diagnostics request failed"));
  }

  return data;
}

export async function exportWorkspaceRequest(): Promise<WorkspaceBundle> {
  const response = await fetch(apiUrl("/api/v1/workspace/export"), {
    headers: buildHeaders()
  });
  const data = await readJson<WorkspaceBundle & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Workspace export failed"));
  }

  return data;
}

export async function importWorkspaceRequest(bundle: WorkspaceBundleInput | WorkspaceBundle): Promise<WorkspaceImportResponse> {
  const response = await fetch(apiUrl("/api/v1/workspace/import"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(bundle)
  });
  const data = await readJson<WorkspaceImportResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Workspace import failed"));
  }

  return data;
}

export async function requestAnalysis(form: FullPayload): Promise<AnalysisResponse> {
  const payload = buildApiPayload(form);
  const response = await fetch(apiUrl("/api/v1/analyze"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload)
  });
  const data = await readJson<AnalysisResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Analysis request failed"));
  }

  return data;
}

export async function saveProjectRequest(
  form: FullPayload,
  activeProjectId: string | null
): Promise<SaveProjectResponse> {
  const isUpdate = activeProjectId !== null;
  const response = await fetch(
    isUpdate ? apiUrl(`/api/v1/projects/${activeProjectId}`) : apiUrl("/api/v1/projects"),
    {
      method: isUpdate ? "PUT" : "POST",
      headers: buildHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(buildApiPayload(form))
    }
  );
  const data = await readJson<SaveProjectResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project save failed"));
  }

  return data;
}

export async function listProjectsRequest(): Promise<SavedProject[]> {
  const response = await fetch(apiUrl("/api/v1/projects"), {
    headers: buildHeaders()
  });
  const data = await readJson<GeneratedProjectListResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project list request failed"));
  }

  return Array.isArray(data.projects) ? data.projects : [];
}

export async function loadProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    headers: buildHeaders()
  });
  const data = await readJson<ProjectRecordResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project load failed"));
  }

  return data;
}

export async function loadProjectHistoryRequest(
  projectId: string,
  options: ProjectHistoryRequestOptions = {}
): Promise<ProjectHistory> {
  const params = new URLSearchParams();

  if (typeof options.analysisLimit === "number") {
    params.set("analysis_limit", String(options.analysisLimit));
  }
  if (typeof options.analysisOffset === "number") {
    params.set("analysis_offset", String(options.analysisOffset));
  }
  if (typeof options.exportLimit === "number") {
    params.set("export_limit", String(options.exportLimit));
  }
  if (typeof options.exportOffset === "number") {
    params.set("export_offset", String(options.exportOffset));
  }

  const path = params.size > 0
    ? `/api/v1/projects/${projectId}/history?${params.toString()}`
    : `/api/v1/projects/${projectId}/history`;
  const response = await fetch(apiUrl(path), {
    headers: buildHeaders()
  });
  const data = await readJson<ProjectHistory & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project history load failed"));
  }

  return data;
}

export async function loadProjectRevisionsRequest(
  projectId: string,
  options: ProjectRevisionRequestOptions = {}
): Promise<ProjectRevisionHistory> {
  const params = new URLSearchParams();

  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(options.offset));
  }

  const path = params.size > 0
    ? `/api/v1/projects/${projectId}/revisions?${params.toString()}`
    : `/api/v1/projects/${projectId}/revisions`;
  const response = await fetch(apiUrl(path), {
    headers: buildHeaders()
  });
  const data = await readJson<ProjectRevisionHistory & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project revision history load failed"));
  }

  return data;
}

export async function compareProjectsRequest(
  baseProjectId: string,
  candidateProjectId: string,
  baseRunId?: string,
  candidateRunId?: string
): Promise<ProjectComparison> {
  const params = new URLSearchParams({
    base_id: baseProjectId,
    candidate_id: candidateProjectId
  });
  if (baseRunId) {
    params.set("base_run_id", baseRunId);
  }
  if (candidateRunId) {
    params.set("candidate_run_id", candidateRunId);
  }
  const response = await fetch(apiUrl(`/api/v1/projects/compare?${params.toString()}`), {
    headers: buildHeaders()
  });
  const data = await readJson<ProjectComparison & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project comparison failed"));
  }

  return data;
}

export async function deleteProjectRequest(projectId: string): Promise<DeleteProjectResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    method: "DELETE",
    headers: buildHeaders()
  });
  const data = await readJson<DeleteProjectResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project delete failed"));
  }

  return data;
}

export async function recordProjectAnalysisRequest(
  projectId: string,
  analysis: AnalysisResponse
): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/analysis`), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(analysis)
  });
  const data = await readJson<ProjectRecordResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project analysis snapshot update failed"));
  }

  return data;
}

export async function recordProjectExportRequest(
  projectId: string,
  format: ExportFormat,
  analysisRunId: string | null = null
): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/exports`), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ format, analysis_run_id: analysisRunId })
  });
  const data = await readJson<ProjectRecordResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project export metadata update failed"));
  }

  return data;
}

export async function exportReportRequest(report: ReportResponse, format: ExportFormat): Promise<string> {
  const response = await fetch(apiUrl(`/api/v1/export/${format}`), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(report)
  });
  const data = await readJson<ExportResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Export failed"));
  }

  return String(data.content ?? "");
}
