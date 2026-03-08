import { useEffect, useState } from "react";

import {
  compareProjectsRequest,
  deleteProjectRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRequest,
  requestDiagnostics,
  requestHealth,
  type ProjectHistoryRequestOptions,
  type ProjectRecordResponse
} from "../lib/api";
import type {
  ApiDiagnosticsResponse,
  ApiHealthResponse,
  ProjectAnalysisRun,
  ProjectComparison,
  ProjectHistory,
  SavedProject
} from "../lib/experiment";

export const initialProjectHistoryWindow = {
  analysisLimit: 3,
  exportLimit: 3
};

function toSavedProject(project: {
  id?: string;
  project_name?: string;
  created_at?: string;
  updated_at?: string;
  payload_schema_version?: number;
  last_analysis_at?: string | null;
  last_analysis_run_id?: string | null;
  last_exported_at?: string | null;
  has_analysis_snapshot?: boolean;
}): SavedProject | null {
  if (
    typeof project.id !== "string" ||
    typeof project.project_name !== "string" ||
    typeof project.created_at !== "string" ||
    typeof project.updated_at !== "string"
  ) {
    return null;
  }

  return {
    id: project.id,
    project_name: project.project_name,
    created_at: project.created_at,
    updated_at: project.updated_at,
    payload_schema_version: project.payload_schema_version ?? 1,
    last_analysis_at: project.last_analysis_at ?? null,
    last_analysis_run_id: project.last_analysis_run_id ?? null,
    last_exported_at: project.last_exported_at ?? null,
    has_analysis_snapshot: project.has_analysis_snapshot ?? false
  };
}

export function useProjectManager(serializedForm: string) {
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [loadingDiagnostics, setLoadingDiagnostics] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [backendHealth, setBackendHealth] = useState<ApiHealthResponse | null>(null);
  const [backendDiagnostics, setBackendDiagnostics] = useState<ApiDiagnosticsResponse | null>(null);
  const [healthError, setHealthError] = useState("");
  const [diagnosticsError, setDiagnosticsError] = useState("");
  const [savedProjects, setSavedProjects] = useState<SavedProject[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [savedProjectSnapshot, setSavedProjectSnapshot] = useState<string | null>(null);
  const [projectHistory, setProjectHistory] = useState<ProjectHistory | null>(null);
  const [projectHistoryError, setProjectHistoryError] = useState("");
  const [loadingProjectHistory, setLoadingProjectHistory] = useState(false);
  const [projectHistoryWindow, setProjectHistoryWindow] = useState(initialProjectHistoryWindow);
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(null);
  const [projectComparison, setProjectComparison] = useState<ProjectComparison | null>(null);
  const [projectComparisonError, setProjectComparisonError] = useState("");
  const [loadingProjectComparison, setLoadingProjectComparison] = useState(false);
  const [comparingProjectId, setComparingProjectId] = useState<string | null>(null);

  const activeProject =
    activeProjectId !== null
      ? savedProjects.find((project) => project.id === activeProjectId) ?? null
      : null;
  const hasUnsavedChanges =
    activeProjectId !== null && savedProjectSnapshot !== null && savedProjectSnapshot !== serializedForm;
  const selectedHistoryRun =
    selectedHistoryRunId && projectHistory
      ? projectHistory.analysis_runs.find((run) => run.id === selectedHistoryRunId) ?? null
      : null;

  useEffect(() => {
    if (selectedHistoryRunId && projectHistory && !projectHistory.analysis_runs.some((run) => run.id === selectedHistoryRunId)) {
      setSelectedHistoryRunId(null);
    }
  }, [projectHistory, selectedHistoryRunId]);

  function upsertSavedProject(project: SavedProject) {
    setSavedProjects((current) =>
      [project, ...current.filter((candidate) => candidate.id !== project.id)].sort((left, right) =>
        right.updated_at.localeCompare(left.updated_at)
      )
    );
  }

  function clearProjectComparison() {
    setProjectComparison(null);
    setProjectComparisonError("");
    setLoadingProjectComparison(false);
    setComparingProjectId(null);
  }

  function resetProjectSelection() {
    setActiveProjectId(null);
    setSavedProjectSnapshot(null);
    setProjectHistory(null);
    setProjectHistoryWindow(initialProjectHistoryWindow);
    setProjectHistoryError("");
    setLoadingProjectHistory(false);
    setSelectedHistoryRunId(null);
    clearProjectComparison();
  }

  async function loadBackendHealth() {
    setLoadingHealth(true);

    try {
      setBackendHealth(await requestHealth());
      setHealthError("");
    } catch (requestError) {
      setBackendHealth(null);
      setHealthError(requestError instanceof Error ? requestError.message : "Unexpected backend health error");
    } finally {
      setLoadingHealth(false);
    }
  }

  async function loadBackendDiagnostics() {
    setLoadingDiagnostics(true);

    try {
      setBackendDiagnostics(await requestDiagnostics());
      setDiagnosticsError("");
    } catch (requestError) {
      setBackendDiagnostics(null);
      setDiagnosticsError(requestError instanceof Error ? requestError.message : "Unexpected backend diagnostics error");
    } finally {
      setLoadingDiagnostics(false);
    }
  }

  async function loadProjects() {
    setLoadingProjects(true);

    try {
      setSavedProjects(await listProjectsRequest());
    } finally {
      setLoadingProjects(false);
    }
  }

  async function refreshProjectHistory(
    projectId: string,
    silent = false,
    overrides?: Partial<typeof initialProjectHistoryWindow>,
    offsets?: Pick<ProjectHistoryRequestOptions, "analysisOffset" | "exportOffset">
  ) {
    const nextWindow = {
      analysisLimit: overrides?.analysisLimit ?? projectHistoryWindow.analysisLimit,
      exportLimit: overrides?.exportLimit ?? projectHistoryWindow.exportLimit
    };

    if (overrides) {
      setProjectHistoryWindow(nextWindow);
    }
    if (!silent) {
      setLoadingProjectHistory(true);
    }
    setProjectHistoryError("");

    try {
      setProjectHistory(
        await loadProjectHistoryRequest(projectId, {
          analysisLimit: nextWindow.analysisLimit,
          exportLimit: nextWindow.exportLimit,
          analysisOffset: offsets?.analysisOffset,
          exportOffset: offsets?.exportOffset
        })
      );
    } catch (requestError) {
      setProjectHistory(null);
      setProjectHistoryError(requestError instanceof Error ? requestError.message : "Unexpected project history error");
    } finally {
      if (!silent) {
        setLoadingProjectHistory(false);
      }
    }
  }

  async function compareProject(candidateProjectId: string) {
    if (!activeProjectId) {
      return;
    }

    const candidateName = savedProjects.find((project) => project.id === candidateProjectId)?.project_name ?? candidateProjectId;
    setLoadingProjectComparison(true);
    setComparingProjectId(candidateProjectId);
    setProjectComparisonError("");

    try {
      const comparison = await compareProjectsRequest(
        activeProjectId,
        candidateProjectId,
        selectedHistoryRunId ?? undefined
      );
      setProjectComparison(comparison);
      return `Loaded saved-project comparison against ${candidateName}.`;
    } catch (requestError) {
      setProjectComparison(null);
      setProjectComparisonError(
        requestError instanceof Error ? requestError.message : "Unexpected project comparison error"
      );
      return null;
    } finally {
      setLoadingProjectComparison(false);
      setComparingProjectId(null);
    }
  }

  async function loadProject(projectId: string): Promise<ProjectRecordResponse> {
    const data = await loadProjectRequest(projectId);
    const savedProject = toSavedProject(data);
    const resolvedProjectId = typeof data.id === "string" ? data.id : projectId;

    setActiveProjectId(resolvedProjectId);
    setSavedProjectSnapshot(JSON.stringify(data.payload));
    setProjectHistory(null);
    setProjectHistoryWindow(initialProjectHistoryWindow);
    setProjectHistoryError("");
    setSelectedHistoryRunId(null);
    clearProjectComparison();
    if (savedProject) {
      upsertSavedProject(savedProject);
    }
    await refreshProjectHistory(resolvedProjectId, false, initialProjectHistoryWindow);

    return data;
  }

  function syncPersistedProject(
    record: ProjectRecordResponse,
    serializedPayloadFallback: string
  ): { savedProjectId: string | null; savedProject: SavedProject | null } {
    const savedProjectId = typeof record.id === "string" ? record.id : null;
    const savedProject = toSavedProject(record);

    setActiveProjectId(savedProjectId);
    setSavedProjectSnapshot(
      record.payload ? JSON.stringify(record.payload) : serializedPayloadFallback
    );
    if (savedProject) {
      upsertSavedProject(savedProject);
    }

    return { savedProjectId, savedProject };
  }

  async function deleteProject(projectId: string, projectName: string) {
    if (!window.confirm(`Delete project "${projectName}" from local storage?`)) {
      return { deleted: false, deletedActive: false };
    }

    setDeletingProjectId(projectId);

    try {
      await deleteProjectRequest(projectId);
      setSavedProjects((current) => current.filter((project) => project.id !== projectId));

      const deletedActive = activeProjectId === projectId;
      if (deletedActive) {
        resetProjectSelection();
      }

      return { deleted: true, deletedActive };
    } finally {
      setDeletingProjectId(null);
    }
  }

  function openHistoryRun(runId: string) {
    if (!projectHistory) {
      return false;
    }

    const targetRun = projectHistory.analysis_runs.find((run) => run.id === runId);
    if (!targetRun) {
      return false;
    }

    setSelectedHistoryRunId(targetRun.id);
    clearProjectComparison();
    return true;
  }

  function clearHistoryRunSelection() {
    if (!selectedHistoryRunId) {
      return false;
    }

    setSelectedHistoryRunId(null);
    return true;
  }

  return {
    loadingHealth,
    loadingDiagnostics,
    loadingProjects,
    deletingProjectId,
    backendHealth,
    backendDiagnostics,
    healthError,
    diagnosticsError,
    savedProjects,
    activeProjectId,
    savedProjectSnapshot,
    projectHistory,
    projectHistoryError,
    loadingProjectHistory,
    projectHistoryWindow,
    selectedHistoryRunId,
    selectedHistoryRun,
    projectComparison,
    projectComparisonError,
    loadingProjectComparison,
    comparingProjectId,
    activeProject,
    hasUnsavedChanges,
    setSavedProjects,
    setActiveProjectId,
    setSavedProjectSnapshot,
    setProjectHistory,
    setProjectHistoryError,
    setLoadingProjectHistory,
    setProjectHistoryWindow,
    setSelectedHistoryRunId,
    upsertSavedProject,
    clearProjectComparison,
    resetProjectSelection,
    loadBackendHealth,
    loadBackendDiagnostics,
    loadProjects,
    refreshProjectHistory,
    compareProject,
    loadProject,
    syncPersistedProject,
    deleteProject,
    openHistoryRun,
    clearHistoryRunSelection
  };
}
