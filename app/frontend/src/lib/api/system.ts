/**
 * System / operator surfaces: health, diagnostics, templates, audit log.
 */

import type {
  ApiDiagnosticsResponse,
  ApiHealthResponse,
  AuditLogResponse,
  TemplateDeleteResponse,
  TemplateRecord
} from "../experiment";
import { apiBlobRequest, apiJsonRequest } from "./client";

export type DiagnosticsResponse = ApiDiagnosticsResponse;

export type AuditLogRequestOptions = {
  projectId?: string;
  action?: string;
};

type TemplateListResponse = {
  templates?: TemplateRecord[];
  total?: number;
};

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

export async function exportAuditLogRequest(
  options: AuditLogRequestOptions = {}
): Promise<{ blob: Blob; filename: string }> {
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
