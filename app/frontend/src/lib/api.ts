import {
  apiUrl,
  type CalculationRequestPayload,
  type CalculationResponse,
  type ProjectHistory,
  type ProjectComparison,
  type MultiProjectComparison,
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
  type MetricType,
  type ProjectRecordPayload,
  type ReportResponse,
  type AuditLogResponse,
  type SavedProject,
  type TemplateDeleteResponse,
  type TemplateRecord
} from "./experiment";
import type {
  BanditRegretPoint,
  BanditSimulationRequest,
  BanditSimulationResponse,
  ProjectArchiveResponse as GeneratedProjectArchiveResponse,
  DecisionReadoutResponse,
  DecisionReason,
  ExperimentAssignmentRequest,
  ExperimentAssignmentResponse,
  ExportResponse,
  HypothesisCandidate,
  HypothesisIdeationRequest,
  HypothesisIdeationResponse,
  LiveArmStat,
  LiveComparison,
  LiveCupedArmStat,
  LiveCupedBlock,
  LiveCupedComparison,
  LiveEventTimingBlock,
  LiveExclusionBlock,
  LiveGuardrailArmStat,
  LiveGuardrailBlock,
  LiveGuardrailComparison,
  LiveGuardrailMetricResult,
  LiveHoldoutArmStat,
  LiveHoldoutBlock,
  LiveIdentityResolutionBlock,
  LiveSequentialBlock,
  LiveSrmBlock,
  LiveStatsResponse,
  LiveStratifiedBlock,
  LiveStratifiedComparison,
  LiveStratumEffect,
  MetricPValue,
  MultipleTestingMetricResult,
  MultipleTestingRequest,
  MultipleTestingResponse,
  ProjectDeleteResponse as GeneratedProjectDeleteResponse,
  ProjectListResponse as GeneratedProjectListResponse,
  SensitivityRequest,
  SensitivityResponse
} from "./generated/api-contract";

export type { HypothesisCandidate, HypothesisIdeationRequest, HypothesisIdeationResponse };
export type { BanditRegretPoint, BanditSimulationRequest, BanditSimulationResponse };
export type { ExperimentAssignmentRequest, ExperimentAssignmentResponse };
export type { DecisionReadoutResponse, DecisionReason };
export type { MetricPValue, MultipleTestingMetricResult, MultipleTestingRequest, MultipleTestingResponse };
export type {
  LiveArmStat,
  LiveComparison,
  LiveCupedArmStat,
  LiveCupedBlock,
  LiveCupedComparison,
  LiveEventTimingBlock,
  LiveExclusionBlock,
  LiveGuardrailArmStat,
  LiveGuardrailBlock,
  LiveGuardrailComparison,
  LiveGuardrailMetricResult,
  LiveHoldoutArmStat,
  LiveHoldoutBlock,
  LiveIdentityResolutionBlock,
  LiveSequentialBlock,
  LiveSrmBlock,
  LiveStatsResponse,
  LiveStratifiedBlock,
  LiveStratifiedComparison,
  LiveStratumEffect
};

const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";
const adminSessionTokenStorageKey = "ab-test-research-designer:admin-token:v1";
const llmProviderSessionStorageKey = "ab_llm_provider";
const llmTokenSessionStorageKey = "ab_llm_token";

export type LlmProvider = "local" | "openai" | "anthropic";
export type LlmSessionConfig = {
  provider: LlmProvider;
  token: string;
};

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
export type WebhookFormat = "generic" | "slack";
export type WebhookScope = "global" | "api_key";
export type WebhookDeliveryStatus = "pending" | "delivered" | "failed" | "retrying";
export type WebhookSubscriptionRecord = {
  id: string;
  name: string;
  target_url: string;
  secret?: string | null;
  format: WebhookFormat;
  event_filter: string[];
  scope: WebhookScope;
  api_key_id?: string | null;
  created_at: string;
  updated_at: string;
  last_delivered_at?: string | null;
  last_error_at?: string | null;
  enabled: boolean;
};
export type WebhookCreateRequest = {
  name: string;
  target_url: string;
  secret: string;
  format: WebhookFormat;
  event_filter?: string[];
  scope: WebhookScope;
  api_key_id?: string | null;
};
export type WebhookListResponse = {
  subscriptions: WebhookSubscriptionRecord[];
  total?: number;
};
export type WebhookDeliveryRecord = {
  id: string;
  subscription_id: string;
  event_id: number;
  status: WebhookDeliveryStatus;
  attempt_count: number;
  last_attempt_at?: string | null;
  delivered_at?: string | null;
  response_code?: number | null;
  response_body?: string | null;
  error_message?: string | null;
};
export type WebhookDeliveryListResponse = {
  deliveries: WebhookDeliveryRecord[];
  total?: number;
};
export type WebhookTestResponse = {
  delivery_id: string;
  status: WebhookDeliveryStatus;
  response_code?: number | null;
};
export type SlackStatusResponse = {
  configured: boolean;
  installed: boolean;
  team_id?: string | null;
  team_name?: string | null;
  installed_at?: string | null;
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
  metricType?: MetricType | "all";
  sortBy?: "created_at" | "updated_at" | "name" | "duration_days";
  sortDir?: "asc" | "desc";
  limit?: number;
  offset?: number;
};
export type ProjectRevisionRequestOptions = {
  limit?: number;
  offset?: number;
};
export type CompareMultipleProjectsRequestOptions = {
  includeMonteCarlo?: boolean;
  monteCarloSimulations?: number;
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

function readLlmSessionProvider(): LlmProvider {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "local";
  }

  try {
    const provider = String(storage.getItem(llmProviderSessionStorageKey) ?? "").trim().toLowerCase();
    return provider === "openai" || provider === "anthropic" ? provider : "local";
  } catch {
    return "local";
  }
}

function readLlmSessionToken(): string {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return "";
  }

  try {
    return String(storage.getItem(llmTokenSessionStorageKey) ?? "").trim();
  } catch {
    return "";
  }
}

export function getLlmSessionConfig(): LlmSessionConfig {
  return {
    provider: readLlmSessionProvider(),
    token: readLlmSessionToken()
  };
}

export function setLlmSessionProvider(provider: LlmProvider): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  if (provider === "local") {
    clearLlmSessionConfig();
    return;
  }

  storage.setItem(llmProviderSessionStorageKey, provider);
}

export function setLlmSessionToken(token: string): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  const normalized = token.trim();
  if (!normalized) {
    storage.removeItem(llmTokenSessionStorageKey);
    return;
  }

  storage.setItem(llmTokenSessionStorageKey, normalized);
}

export function clearLlmSessionConfig(): void {
  const storage = typeof globalThis !== "undefined" ? globalThis.sessionStorage : undefined;
  if (!storage) {
    return;
  }

  storage.removeItem(llmProviderSessionStorageKey);
  storage.removeItem(llmTokenSessionStorageKey);
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

function currentLanguageHeader(): Record<string, string> {
  if (typeof document === "undefined") {
    return {};
  }
  const language = document.documentElement.lang?.trim();
  return language ? { "Accept-Language": language } : {};
}

function buildHeaders(
  additionalHeaders: Record<string, string> = {},
  token: string = readApiSessionToken()
): Record<string, string> {
  const headers = { ...currentLanguageHeader(), ...additionalHeaders };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function buildAdminHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
  return buildHeaders(additionalHeaders, readAdminSessionToken());
}

function buildLlmHeaders(path: string): Record<string, string> {
  if (
    path !== "/api/v1/analyze" &&
    path !== "/api/v1/hypotheses/generate" &&
    !path.startsWith("/api/v1/llm/")
  ) {
    return {};
  }

  const config = getLlmSessionConfig();
  if ((config.provider === "openai" || config.provider === "anthropic") && config.token) {
    return {
      "X-AB-LLM-Provider": config.provider,
      "X-AB-LLM-Token": config.token
    };
  }

  return {};
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

type ApiAuthMode = "session" | "admin";

type ApiJsonRequestOptions = {
  method?: string;
  /** Object/array is JSON.stringified; string body is sent as-is. */
  body?: unknown;
  headers?: Record<string, string>;
  auth?: ApiAuthMode;
  signal?: AbortSignal;
  errorFallback: string;
};

/**
 * Shared typed JSON request primitive for the frontend API client.
 * All JSON endpoints go through here so auth headers, error parsing,
 * and response typing stay in one place (audit F-11).
 */
async function apiJsonRequest<T>(path: string, options: ApiJsonRequestOptions): Promise<T> {
  const {
    method = "GET",
    body,
    headers: extraHeaders = {},
    auth = "session",
    signal,
    errorFallback
  } = options;

  const withContentType =
    body !== undefined && !("Content-Type" in extraHeaders)
      ? { "Content-Type": "application/json", ...extraHeaders }
      : extraHeaders;

  const headers =
    auth === "admin" ? buildAdminHeaders(withContentType) : buildHeaders(withContentType);

  const init: RequestInit = { method, headers, signal };
  if (body !== undefined) {
    init.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  const response = await fetch(apiUrl(path), init);
  const data = await readJson<T & ApiErrorResponse>(response);

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response, errorFallback));
  }

  return data;
}

type ApiBlobRequestOptions = {
  auth?: ApiAuthMode;
  headers?: Record<string, string>;
  errorFallback: string;
  fallbackFilename: string;
};

/** Download endpoints that return a binary body + optional Content-Disposition filename. */
async function apiBlobRequest(
  path: string,
  options: ApiBlobRequestOptions
): Promise<{ blob: Blob; filename: string }> {
  const { auth = "session", headers: extraHeaders = {}, errorFallback, fallbackFilename } = options;
  const headers =
    auth === "admin" ? buildAdminHeaders(extraHeaders) : buildHeaders(extraHeaders);

  const response = await fetch(apiUrl(path), { headers });

  if (!response.ok) {
    const data = await response.json().catch(() => ({} as ApiErrorResponse));
    throw new Error(getErrorMessage(data, response, errorFallback));
  }

  const blob = await response.blob();
  const filename =
    /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ??
    fallbackFilename;
  return { blob, filename };
}

export async function requestHealth(): Promise<ApiHealthResponse> {
  return apiJsonRequest<ApiHealthResponse>("/health", {
    errorFallback: "Health check failed"
  });
}

export async function requestDiagnostics(): Promise<ApiDiagnosticsResponse> {
  return apiJsonRequest<ApiDiagnosticsResponse>("/api/v1/diagnostics", {
    errorFallback: "Diagnostics request failed"
  });
}

export async function exportWorkspaceRequest(): Promise<WorkspaceBundle> {
  return apiJsonRequest<WorkspaceBundle>("/api/v1/workspace/export", {
    errorFallback: "Workspace export failed"
  });
}

export async function importWorkspaceRequest(bundle: WorkspaceBundleInput | WorkspaceBundle): Promise<WorkspaceImportResponse> {
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

export async function requestAnalysis(form: FullPayload, options: RequestOptions = {}): Promise<AnalysisResponse> {
  return apiJsonRequest<AnalysisResponse>("/api/v1/analyze", {
    method: "POST",
    body: buildApiPayload(form),
    headers: buildLlmHeaders("/api/v1/analyze"),
    signal: options.signal,
    errorFallback: "Analysis request failed"
  });
}

export async function requestCalculation(
  payload: CalculationRequestPayload,
  options: RequestOptions = {}
): Promise<CalculationResponse> {
  return apiJsonRequest<CalculationResponse>("/api/v1/calculate", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "Calculation request failed"
  });
}

export async function requestHypotheses(
  payload: HypothesisIdeationRequest,
  options: RequestOptions = {}
): Promise<HypothesisIdeationResponse> {
  return apiJsonRequest<HypothesisIdeationResponse>("/api/v1/hypotheses/generate", {
    method: "POST",
    body: payload,
    headers: buildLlmHeaders("/api/v1/hypotheses/generate"),
    signal: options.signal,
    errorFallback: "Hypothesis generation failed"
  });
}

export async function requestSensitivity(
  payload: SensitivityRequest,
  options: RequestOptions = {}
): Promise<SensitivityResponse> {
  return apiJsonRequest<SensitivityResponse>("/api/v1/sensitivity", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "Sensitivity request failed"
  });
}

export async function requestSrmCheck(
  payload: SrmCheckRequest,
  options: RequestOptions = {}
): Promise<SrmCheckResponse> {
  return apiJsonRequest<SrmCheckResponse>("/api/v1/srm-check", {
    method: "POST",
    body: payload,
    signal: options.signal,
    errorFallback: "SRM check request failed"
  });
}

export async function saveProjectRequest(
  form: FullPayload,
  activeProjectId: string | null
): Promise<SaveProjectResponse> {
  const isUpdate = activeProjectId !== null;
  return apiJsonRequest<SaveProjectResponse>(
    isUpdate ? `/api/v1/projects/${activeProjectId}` : "/api/v1/projects",
    {
      method: isUpdate ? "PUT" : "POST",
      body: buildApiPayload(form),
      errorFallback: "Project save failed"
    }
  );
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
  const data = await apiJsonRequest<GeneratedProjectListResponse>(path, {
    errorFallback: "Project list request failed"
  });

  return Array.isArray(data.projects) ? data.projects : [];
}

export async function listTemplatesRequest(): Promise<TemplateRecord[]> {
  const data = await apiJsonRequest<TemplateListResponse>("/api/v1/templates", {
    errorFallback: "Template list request failed"
  });

  return Array.isArray(data.templates) ? data.templates : [];
}

export async function useTemplateRequest(templateId: string): Promise<TemplateRecord> {
  return apiJsonRequest<TemplateRecord>(`/api/v1/templates/${templateId}/use`, {
    method: "POST",
    errorFallback: "Template apply failed"
  });
}

export async function deleteTemplateRequest(templateId: string): Promise<TemplateDeleteResponse> {
  return apiJsonRequest<TemplateDeleteResponse>(`/api/v1/templates/${templateId}`, {
    method: "DELETE",
    errorFallback: "Template delete failed"
  });
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
  return apiJsonRequest<AuditLogResponse>(path, {
    errorFallback: "Audit log request failed"
  });
}

export async function listApiKeysRequest(): Promise<ApiKeyListResponse> {
  return apiJsonRequest<ApiKeyListResponse>("/api/v1/keys", {
    auth: "admin",
    errorFallback: "API key list request failed"
  });
}

export async function createApiKeyRequest(payload: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  return apiJsonRequest<ApiKeyCreateResponse>("/api/v1/keys", {
    method: "POST",
    body: payload,
    auth: "admin",
    errorFallback: "API key creation failed"
  });
}

export async function revokeApiKeyRequest(apiKeyId: string): Promise<ApiKeyRecord> {
  return apiJsonRequest<ApiKeyRecord>(`/api/v1/keys/${apiKeyId}/revoke`, {
    method: "POST",
    auth: "admin",
    errorFallback: "API key revoke failed"
  });
}

export async function deleteApiKeyRequest(apiKeyId: string): Promise<{ id: string; deleted: boolean }> {
  return apiJsonRequest<{ id: string; deleted: boolean }>(`/api/v1/keys/${apiKeyId}`, {
    method: "DELETE",
    auth: "admin",
    errorFallback: "API key delete failed"
  });
}

export async function listWebhooksRequest(): Promise<WebhookListResponse> {
  return apiJsonRequest<WebhookListResponse>("/api/v1/webhooks", {
    auth: "admin",
    errorFallback: "Webhook list request failed"
  });
}

export async function requestSlackStatus(): Promise<SlackStatusResponse> {
  return apiJsonRequest<SlackStatusResponse>("/api/v1/slack/status", {
    errorFallback: "Slack status request failed"
  });
}

export function slackInstallUrl(): string {
  return apiUrl("/slack/install");
}

export async function createWebhookRequest(payload: WebhookCreateRequest): Promise<WebhookSubscriptionRecord> {
  return apiJsonRequest<WebhookSubscriptionRecord>("/api/v1/webhooks", {
    method: "POST",
    body: payload,
    auth: "admin",
    errorFallback: "Webhook creation failed"
  });
}

export async function deleteWebhookRequest(subscriptionId: string): Promise<{ id: string; deleted: boolean }> {
  return apiJsonRequest<{ id: string; deleted: boolean }>(`/api/v1/webhooks/${subscriptionId}`, {
    method: "DELETE",
    auth: "admin",
    errorFallback: "Webhook deletion failed"
  });
}

export async function testWebhookRequest(subscriptionId: string): Promise<WebhookTestResponse> {
  return apiJsonRequest<WebhookTestResponse>(`/api/v1/webhooks/${subscriptionId}/test`, {
    method: "POST",
    auth: "admin",
    errorFallback: "Webhook test delivery failed"
  });
}

export async function listWebhookDeliveriesRequest(
  subscriptionId: string,
  options: { limit?: number; status?: WebhookDeliveryStatus } = {}
): Promise<WebhookDeliveryListResponse> {
  const params = new URLSearchParams();
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  if (options.status) {
    params.set("status", options.status);
  }

  const path = params.size > 0
    ? `/api/v1/webhooks/${subscriptionId}/deliveries?${params.toString()}`
    : `/api/v1/webhooks/${subscriptionId}/deliveries`;
  return apiJsonRequest<WebhookDeliveryListResponse>(path, {
    auth: "admin",
    errorFallback: "Webhook delivery history failed"
  });
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
  return apiBlobRequest(path, {
    errorFallback: "Audit export failed",
    fallbackFilename: "audit-log.csv"
  });
}

export async function downloadProjectReportPdfRequest(
  projectId: string
): Promise<{ blob: Blob; filename: string }> {
  return apiBlobRequest(`/api/v1/projects/${projectId}/report/pdf`, {
    errorFallback: "PDF export failed",
    fallbackFilename: "experiment-report.pdf"
  });
}

export async function downloadProjectReportDataRequest(
  projectId: string,
  format: "csv" | "xlsx"
): Promise<{ blob: Blob; filename: string }> {
  const fallbackFilename = format === "csv" ? "experiment-report.csv" : "experiment-report.xlsx";
  return apiBlobRequest(`/api/v1/projects/${projectId}/report/${format}`, {
    errorFallback: `${format.toUpperCase()} export failed`,
    fallbackFilename
  });
}

export async function loadProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  return apiJsonRequest<ProjectRecordResponse>(`/api/v1/projects/${projectId}`, {
    errorFallback: "Project load failed"
  });
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
  return apiJsonRequest<ProjectHistory>(path, {
    errorFallback: "Project history load failed"
  });
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
  return apiJsonRequest<ProjectRevisionHistory>(path, {
    errorFallback: "Project revision history load failed"
  });
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
  return apiJsonRequest<ProjectComparison>(`/api/v1/projects/compare?${params.toString()}`, {
    errorFallback: "Project comparison failed"
  });
}

export async function compareMultipleProjectsRequest(
  projectIds: string[],
  options: CompareMultipleProjectsRequestOptions = {}
): Promise<MultiProjectComparison> {
  const params = new URLSearchParams();
  if (options.includeMonteCarlo) {
    params.set("include_monte_carlo", "true");
    if (typeof options.monteCarloSimulations === "number") {
      params.set("monte_carlo_simulations", String(options.monteCarloSimulations));
    }
  }
  const path = params.size > 0 ? `/api/v1/projects/compare?${params.toString()}` : "/api/v1/projects/compare";
  return apiJsonRequest<MultiProjectComparison>(path, {
    method: "POST",
    body: { project_ids: projectIds },
    errorFallback: "Project comparison failed"
  });
}

export async function exportComparisonRequest(
  projectIds: string[],
  format: "markdown" | "pdf"
): Promise<string> {
  const data = await apiJsonRequest<ExportResponse>("/api/v1/export/comparison", {
    method: "POST",
    body: { project_ids: projectIds, format },
    errorFallback: "Comparison export failed"
  });

  return String(data.content ?? "");
}

export async function archiveProjectRequest(projectId: string): Promise<ArchiveProjectResponse> {
  return apiJsonRequest<ArchiveProjectResponse>(`/api/v1/projects/${projectId}/archive`, {
    method: "POST",
    errorFallback: "Project archive failed"
  });
}

export async function deleteProjectRequest(projectId: string): Promise<DeleteProjectResponse> {
  return apiJsonRequest<DeleteProjectResponse>(`/api/v1/projects/${projectId}`, {
    method: "DELETE",
    errorFallback: "Project delete failed"
  });
}

export async function restoreProjectRequest(projectId: string): Promise<ProjectRecordResponse> {
  return apiJsonRequest<ProjectRecordResponse>(`/api/v1/projects/${projectId}/restore`, {
    method: "POST",
    errorFallback: "Project restore failed"
  });
}

export async function recordProjectAnalysisRequest(
  projectId: string,
  analysis: AnalysisResponse
): Promise<ProjectRecordResponse> {
  return apiJsonRequest<ProjectRecordResponse>(`/api/v1/projects/${projectId}/analysis`, {
    method: "POST",
    body: analysis,
    errorFallback: "Project analysis snapshot update failed"
  });
}

export async function recordProjectExportRequest(
  projectId: string,
  format: ExportFormat,
  analysisRunId: string | null = null
): Promise<ProjectRecordResponse> {
  return apiJsonRequest<ProjectRecordResponse>(`/api/v1/projects/${projectId}/exports`, {
    method: "POST",
    body: { format, analysis_run_id: analysisRunId },
    errorFallback: "Project export metadata update failed"
  });
}

export async function exportReportRequest(report: ReportResponse, format: ExportFormat): Promise<string> {
  const data = await apiJsonRequest<ExportResponse>(`/api/v1/export/${format}`, {
    method: "POST",
    body: report,
    errorFallback: "Export failed"
  });

  return String(data.content ?? "");
}
