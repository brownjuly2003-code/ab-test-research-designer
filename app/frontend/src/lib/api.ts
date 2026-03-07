import {
  apiUrl,
  type ApiHealthResponse,
  type ExperimentInputPayload,
  buildApiPayload,
  buildCalculationPayload,
  type AdviceResponse,
  type ApiErrorResponse,
  type CalculationResponse,
  type ExportFormat,
  type FullPayload,
  type ReportResponse,
  type SavedProject
} from "./experiment";

export type ProjectRecordResponse = {
  id: string;
  project_name: string;
  created_at: string;
  updated_at: string;
  payload: ExperimentInputPayload;
};

type ProjectListResponse = {
  projects?: SavedProject[];
};

type ExportResponse = {
  content?: string;
};

export type SaveProjectResponse = {
  id?: string;
  project_name?: string;
  created_at?: string;
  updated_at?: string;
  payload?: ExperimentInputPayload;
  detail?: string;
};

export type DeleteProjectResponse = {
  id?: string;
  deleted?: boolean;
  detail?: string;
};

export type AnalysisResponse = {
  calculations: CalculationResponse;
  report: ReportResponse;
  advice: AdviceResponse;
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

export async function requestAnalysis(form: FullPayload): Promise<AnalysisResponse> {
  const payload = buildApiPayload(form);
  const calculationPayload = buildCalculationPayload(form);

  const [calculationsRes, reportRes, adviceRes] = await Promise.all([
    fetch(apiUrl("/api/v1/calculate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(calculationPayload)
    }),
    fetch(apiUrl("/api/v1/design"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
    fetch(apiUrl("/api/v1/llm/advice"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_context: payload.project,
        hypothesis: payload.hypothesis,
        setup: payload.setup,
        metrics: payload.metrics,
        constraints: payload.constraints,
        additional_context: payload.additional_context
      })
    })
  ]);

  const calculations = await readJson<CalculationResponse | ApiErrorResponse>(calculationsRes);
  const report = await readJson<ReportResponse | ApiErrorResponse>(reportRes);
  const advice = await readJson<AdviceResponse>(adviceRes);

  if (!calculationsRes.ok) {
    throw new Error(getErrorMessage(calculations as ApiErrorResponse, "Calculation request failed"));
  }
  if (!reportRes.ok) {
    throw new Error(getErrorMessage(report as ApiErrorResponse, "Design request failed"));
  }

  return {
    calculations: calculations as CalculationResponse,
    report: report as ReportResponse,
    advice
  };
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
  const data = await readJson<ProjectListResponse & ApiErrorResponse>(response);

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
