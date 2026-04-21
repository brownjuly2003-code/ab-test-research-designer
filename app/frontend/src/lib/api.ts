import {
  apiUrl,
  type CalculationRequestPayload,
  type CalculationResponse,
  type ProjectHistory,
  type ProjectComparison,
  type ProjectRevisionHistory,
  type ApiHealthResponse,
  type ApiDiagnosticsResponse,
  type WorkspaceBundle,
  type WorkspaceBundleInput,
  type WorkspaceImportResponse,
  type WorkspaceValidationResponse,
  buildApiPayload,
  type AnalysisResponsePayload,
  type ApiErrorResponse,
  type ExportFormat,
  type FullPayload,
  type ProjectRecordPayload,
  type ReportResponse,
  type AuditLogResponse,
  type SavedProject,
  type TemplateDeleteResponse,
  type TemplateRecord
} from "./experiment";
import type {
  ProjectArchiveResponse as GeneratedProjectArchiveResponse,
  ExportResponse,
  ProjectDeleteResponse as GeneratedProjectDeleteResponse,
  ProjectListResponse as GeneratedProjectListResponse,
  SensitivityRequest,
  SensitivityResponse
} from "./generated/api-contract";

const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";
const adminSessionTokenStorageKey = "ab-test-research-designer:admin-token:v1";

export type ProjectRecordResponse = ProjectRecordPayload;
export type SaveProjectResponse = ProjectRecordPayload;
export type ArchiveProjectResponse = GeneratedProjectArchiveResponse;
export type DeleteProjectResponse = GeneratedProjectDeleteResponse;
export type AnalysisResponse = AnalysisResponsePayload;
export type DiagnosticsResponse = ApiDiagnosticsResponse;
export type WorkspaceExportResponse = WorkspaceBundle;
export type WorkspaceValidationSummary = WorkspaceValidationResponse;
export type WorkspaceImportSummary = WorkspaceImportResponse;
export type ApiKeyScope = "read" | "write" | "admin";
export type ApiKeyRecord = {
  id: string;
  name: string;
  scope: ApiKeyScope;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
  rate_limit_requests?: number | null;
  rate_limit_window_seconds?: number | null;
};
export type ApiKeyCreateRequest = {
  name: string;
  scope: ApiKeyScope;
  rate_limit_requests?: number | null;
  rate_limit_window_seconds?: number | null;
};
export type ApiKeyCreateResponse = ApiKeyRecord & {
  plaintext_key: string;
};
export type ApiKeyListResponse = {
  keys: ApiKeyRecord[];
  total?: number;
};
export type SrmCheckRequest = {
  observed_counts: number[];
  expected_fractions: number[];
};
export type SrmCheckResponse = {
  chi_square: number;
  p_value: number;
  is_srm: boolean;
  verdict: string;
  observed_counts: number[];
  expected_counts: number[];
};
export type ProjectHistoryRequestOptions = {
  analysisLimit?: number;
  analysisOffset?: number;
  exportLimit?: number;
  exportOffset?: number;
};
export type ProjectListRequestOptions = {
  includeArchived?: boolean;
  q?: string;
  status?: "active" | "archived" | "all";
  metricType?: "binary" | "continuous" | "all";
  sortBy?: "created_at" | "updated_at" | "name" | "duration_days";
  sortDir?: "asc" | "desc";
  limit?: number;
  offset?: number;
};
export type ProjectRevisionRequestOptions = {
  limit?: number;
  offset?: number;
};
type TemplateListResponse = {
  templates?: TemplateRecord[];
  total?: number;
};
export type AuditLogRequestOptions = {
  projectId?: string;
  action?: string;
};
type RequestOptions = {
  signal?: AbortSignal;
};

function readApiSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(apiSessionTokenStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

function readAdminSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(adminSessionTokenStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

export function hasApiSessionToken(): boolean {
  return readApiSessionToken().length > 0;
}

export function hasAdminSessionToken(): boolean {
  return readAdminSessionToken().length > 0;
}

export function setApiSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    clearApiSessionToken();
    return;
  }

  storage.setItem(apiSessionTokenStorageKey, normalized);
}

export function clearApiSessionToken(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(apiSessionTokenStorageKey);
}

export function setAdminSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    clearAdminSessionToken();
    return;
  }

  storage.setItem(adminSessionTokenStorageKey, normalized);
}

export function clearAdminSessionToken(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(adminSessionTokenStorageKey);
}

function buildHeaders(
  additionalHeaders: Record<string, string> = {},
  token: string = readApiSessionToken()
): Record<string, string> {
  const headers = { ...additionalHeaders };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function buildAdminHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
  return buildHeaders(additionalHeaders, readAdminSessionToken());
}

async function readJson<T>(response: Response): Promise<T> {
  const data: T = await response.json();
  return data;
}

function getErrorMessage(payload: ApiErrorResponse, response: Response, fallback: string): string {
  const retryAfter = response.headers.get("Retry-After")?.trim();
  if (payload.error_code === "rate_limited" || payload.error_code === "auth_rate_limited") {
    const detail = typeof payload.detail === "string" && payload.detail.length > 0 ? payload.detail : "Too many requests";
    return retryAfter ? `${detail}. Retry after ${retryAfter}s.` : detail;
  }
  if (payload.error_code === "request_body_too_large") {
    if (typeof payload.detail === "string" && payload.detail.length > 0) {
      return `${payload.detail}. Reduce the payload size or raise the backend limit.`;
    }
    return "Request payload is too large for the current backend limit.";
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (typeof payload.error_code === "string" && payload.error_code.length > 0) {
    return `${fallback} (${payload.error_code})`;
  }
  return fallback;
}

export async function requestHealth(): Promise<ApiHealthResponse> {
  const response = await fetch(apiUrl("/health"), {
    headers: buildHeaders()
  });
  const data = await readJson<ApiHealthResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Health check failed"));
  }

  return data;
}

export async function requestDiagnostics(): Promise<ApiDiagnosticsResponse> {
  const response = await fetch(apiUrl("/api/v1/diagnostics"), {
    headers: buildHeaders()
  });
  const data = await readJson<ApiDiagnosticsResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Diagnostics request failed"));
  }

  return data;
}

export async function exportWorkspaceRequest(): Promise<WorkspaceBundle> {
  const response = await fetch(apiUrl("/api/v1/workspace/export"), {
    headers: buildHeaders()
  });
  const data = await readJson<WorkspaceBundle & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Workspace export failed"));
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
    throw new Error(getErrorMessage(data, response, "Workspace import failed"));
  }

  return data;
}

export async function validateWorkspaceRequest(
  bundle: WorkspaceBundleInput | WorkspaceBundle
): Promise<WorkspaceValidationResponse> {
  const response = await fetch(apiUrl("/api/v1/workspace/validate"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(bundle)
  });
  const data = await readJson<WorkspaceValidationResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Workspace validation failed"));
  }

  return data;
}

export async function requestAnalysis(form: FullPayload, options: RequestOptions = {}): Promise<AnalysisResponse> {
  const payload = buildApiPayload(form);
  const response = await fetch(apiUrl("/api/v1/analyze"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    signal: options.signal
  });
  const data = await readJson<AnalysisResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Analysis request failed"));
  }

  return data;
}

export async function requestCalculation(
  payload: CalculationRequestPayload,
  options: RequestOptions = {}
): Promise<CalculationResponse> {
  const response = await fetch(apiUrl("/api/v1/calculate"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    signal: options.signal
  });
  const data = await readJson<CalculationResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Calculation request failed"));
  }

  return data;
}

export async function requestSensitivity(
  payload: SensitivityRequest,
  options: RequestOptions = {}
): Promise<SensitivityResponse> {
  const response = await fetch(apiUrl("/api/v1/sensitivity"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    signal: options.signal
  });
  const data = await readJson<SensitivityResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Sensitivity request failed"));
  }

  return data;
}

export async function requestSrmCheck(
  payload: SrmCheckRequest,
  options: RequestOptions = {}
): Promise<SrmCheckResponse> {
  const response = await fetch(apiUrl("/api/v1/srm-check"), {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
    signal: options.signal
  });
  const data = await readJson<SrmCheckResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "SRM check request failed"));
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
    throw new Error(getErrorMessage(data, response, "Project save failed"));
  }

  return data;
}

export async function listProjectsRequest(options: ProjectListRequestOptions = {}): Promise<SavedProject[]> {
  const params = new URLSearchParams();
  if (options.includeArchived) {
    params.set("include_archived", "true");
  }
  if (options.q && options.q.trim().length > 0) {
    params.set("q", options.q.trim());
  }
  if (options.status) {
    params.set("status", options.status);
  }
  if (options.metricType) {
    params.set("metric_type", options.metricType);
  }
  if (options.sortBy) {
    params.set("sort_by", options.sortBy);
  }
  if (options.sortDir) {
    params.set("sort_dir", options.sortDir);
  }
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(options.offset));
  }

  const path = params.size > 0 ? `/api/v1/projects?${params.toString()}` : "/api/v1/projects";
  const response = await fetch(apiUrl(path), {
    headers: buildHeaders()
  });
  const data = await readJson<GeneratedProjectListResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Project list request failed"));
  }

  return Array.isArray(data.projects) ? data.projects : [];
}

export async function listTemplatesRequest(): Promise<TemplateRecord[]> {
  const response = await fetch(apiUrl("/api/v1/templates"), {
    headers: buildHeaders()
  });
  const data = await readJson<TemplateListResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Template list request failed"));
  }

  return Array.isArray(data.templates) ? data.templates : [];
}

export async function useTemplateRequest(templateId: string): Promise<TemplateRecord> {
  const response = await fetch(apiUrl(`/api/v1/templates/${templateId}/use`), {
    method: "POST",
    headers: buildHeaders()
  });
  const data = await readJson<TemplateRecord & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Template apply failed"));
  }

  return data;
}

export async function deleteTemplateRequest(templateId: string): Promise<TemplateDeleteResponse> {
  const response = await fetch(apiUrl(`/api/v1/templates/${templateId}`), {
    method: "DELETE",
    headers: buildHeaders()
  });
  const data = await readJson<TemplateDeleteResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Template delete failed"));
  }

  return data;
}

export async function listAuditLogRequest(options: AuditLogRequestOptions = {}): Promise<AuditLogResponse> {
  const params = new URLSearchParams();
  if (options.projectId) {
    params.set("project_id", options.projectId);
  }
  if (options.action) {
    params.set("action", options.action);
  }
  const path = params.size > 0 ? `/api/v1/audit?${params.toString()}` : "/api/v1/audit";
  const response = await fetch(apiUrl(path), {
    headers: buildHeaders()
  });
  const data = await readJson<AuditLogResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Audit log request failed"));
  }

  return data;
}

export async function listApiKeysRequest(): Promise<ApiKeyListResponse> {
  const response = await fetch(apiUrl("/api/v1/keys"), {
    headers: buildAdminHeaders()
  });
  const data = await readJson<ApiKeyListResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "API key list request failed"));
  }

  return data;
}

export async function createApiKeyRequest(payload: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  const response = await fetch(apiUrl("/api/v1/keys"), {
    method: "POST",
    headers: buildAdminHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload)
  });
  const data = await readJson<ApiKeyCreateResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "API key creation failed"));
  }

  return data;
}

export async function revokeApiKeyRequest(apiKeyId: string): Promise<ApiKeyRecord> {
  const response = await fetch(apiUrl(`/api/v1/keys/${apiKeyId}/revoke`), {
    method: "POST",
    headers: buildAdminHeaders()
  });
  const data = await readJson<ApiKeyRecord & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "API key revoke failed"));
  }

  return data;
}

export async function deleteApiKeyRequest(apiKeyId: string): Promise<{ id: string; deleted: boolean }> {
  const response = await fetch(apiUrl(`/api/v1/keys/${apiKeyId}`), {
    method: "DELETE",
    headers: buildAdminHeaders()
  });
  const data = await readJson<{ id: string; deleted: boolean } & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "API key delete failed"));
  }

  return data;
}

export async function exportAuditLogRequest(options: AuditLogRequestOptions = {}): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams();
  if (options.projectId) {
    params.set("project_id", options.projectId);
  }
  if (options.action) {
    params.set("action", options.action);
  }
  const path = params.size > 0 ? `/api/v1/audit/export?${params.toString()}` : "/api/v1/audit/export";
  const response = await fetch(apiUrl(path), {
    headers: buildHeaders()
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({} as ApiErrorResponse));
    throw new Error(getErrorMessage(data, response, "Audit export failed"));
  }

  const blob = await response.blob();
  const filename =
    /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    "audit-log.csv";
  return { blob, filename };
}

export async function downloadProjectReportPdfRequest(
  projectId: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/report/pdf`), {
    headers: buildHeaders()
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({} as ApiErrorResponse));
    throw new Error(getErrorMessage(data, response, "PDF export failed"));
  }

  const blob = await response.blob();
  const filename =
    /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    "experiment-report.pdf";
  return { blob, filename };
}

export async function downloadProjectReportDataRequest(
  projectId: string,
  format: "csv" | "xlsx"
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/report/${format}`), {
    headers: buildHeaders()
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({} as ApiErrorResponse));
    throw new Error(getErrorMessage(data, response, `${format.toUpperCase()} export failed`));
  }

  const blob = await response.blob();
  const fallbackFilename = format === "csv" ? "experiment-report.csv" : "experiment-report.xlsx";
  const filename =
    /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    fallbackFilename;
  return { blob, filename };
}

export async function loadProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`), {
    headers: buildHeaders()
  });
  const data = await readJson<ProjectRecordResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Project load failed"));
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
    throw new Error(getErrorMessage(data, response, "Project history load failed"));
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
    throw new Error(getErrorMessage(data, response, "Project revision history load failed"));
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
    throw new Error(getErrorMessage(data, response, "Project comparison failed"));
  }

  return data;
}

export async function archiveProjectRequest(projectId: string): Promise<ArchiveProjectResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/archive`), {
    method: "POST",
    headers: buildHeaders()
  });
  const data = await readJson<ArchiveProjectResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Project archive failed"));
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
    throw new Error(getErrorMessage(data, response, "Project delete failed"));
  }

  return data;
}

export async function restoreProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  const response = await fetch(apiUrl(`/api/v1/projects/${projectId}/restore`), {
    method: "POST",
    headers: buildHeaders()
  });
  const data = await readJson<ProjectRecordResponse & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, "Project restore failed"));
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
    throw new Error(
      getErrorMessage(data, response, "Project analysis snapshot update failed"),
    );
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
    throw new Error(
      getErrorMessage(data, response, "Project export metadata update failed"),
    );
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
    throw new Error(getErrorMessage(data, response, "Export failed"));
  }

  return String(data.content ?? "");
}
