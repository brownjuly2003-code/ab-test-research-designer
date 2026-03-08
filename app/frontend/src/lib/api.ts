import {
  apiUrl,
  type ProjectHistory,
  type ProjectComparison,
  type ApiHealthResponse,
  type ApiDiagnosticsResponse,
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
export type ProjectHistoryRequestOptions = {
  analysisLimit?: number;
  analysisOffset?: number;
  exportLimit?: number;
  exportOffset?: number;
};

async function readJson<T>(response: Response): Promise<T> {
  return await response.json() as T;
}

function getErrorMessage(payload: ApiErrorResponse, fallback: string): string {
  return typeof payload.detail === "string" ? payload.detail : fallback;
}

export async function requestHealth(): Promise<ApiHealthResponse> {
  const response = await fetch(apiUrl("/health"));
  const data = await readJson<ApiHealthResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Health check failed"));
  }

  return data;
}

export async function requestDiagnostics(): Promise<ApiDiagnosticsResponse> {
  const response = await fetch(apiUrl("/api/v1/diagnostics"));
  const data = await readJson<ApiDiagnosticsResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Diagnostics request failed"));
  }

  return data;
}

export async function requestAnalysis(form: FullPayload): Promise<AnalysisResponse> {
  const payload = buildApiPayload(form);
  const response = await fetch(apiUrl("/api/v1/analyze"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
      headers: { "Content-Type": "application/json" },
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
  const response = await fetch(apiUrl("/api/v1/projects"));
  const data = await readJson<GeneratedProjectListResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project list request failed"));
  }

  return Array.isArray(data.projects) ? data.projects : [];
}

export async function loadProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`));
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
  const response = await fetch(apiUrl(path));
  const data = await readJson<ProjectHistory & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project history load failed"));
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
  const response = await fetch(apiUrl(`/api/v1/projects/compare?${params.toString()}`));
  const data = await readJson<ProjectComparison & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Project comparison failed"));
  }

  return data;
}

export async function deleteProjectRequest(projectId: string): Promise<DeleteProjectResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    method: "DELETE"
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
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report)
  });
  const data = await readJson<ExportResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, "Export failed"));
  }

  return String(data.content ?? "");
}
