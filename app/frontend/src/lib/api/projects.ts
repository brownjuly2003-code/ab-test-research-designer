/**
 * Project CRUD, history, revisions, comparison, and report download client.
 */

import {
  buildApiPayload,
  type ExportFormat,
  type FullPayload,
  type MetricType,
  type MultiProjectComparison,
  type ProjectComparison,
  type ProjectHistory,
  type ProjectRecordPayload,
  type ProjectRevisionHistory,
  type SavedProject
} from "../experiment";
import type {
  ExportResponse,
  ProjectArchiveResponse as GeneratedProjectArchiveResponse,
  ProjectDeleteResponse as GeneratedProjectDeleteResponse,
  ProjectListResponse as GeneratedProjectListResponse
} from "../generated/api-contract";
import { apiBlobRequest, apiJsonRequest } from "./client";
import type { AnalysisResponse } from "./analysis";

export type ProjectRecordResponse = ProjectRecordPayload;
export type SaveProjectResponse = ProjectRecordPayload;
export type ArchiveProjectResponse = GeneratedProjectArchiveResponse;
export type DeleteProjectResponse = GeneratedProjectDeleteResponse;

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

  const path =
    params.size > 0
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

  const path =
    params.size > 0
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
