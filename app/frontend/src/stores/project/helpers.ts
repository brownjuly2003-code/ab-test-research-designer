import type { MetricType, SavedProject } from "../../lib/experiment";
import type { ProjectStoreValues } from "./types";

export function toSavedProject(project: {
  id?: string;
  project_name?: string;
  hypothesis?: string | null;
  metric_type?: MetricType | null;
  duration_days?: number | null;
  created_at?: string;
  updated_at?: string;
  payload_schema_version?: number;
  revision_count?: number;
  last_revision_at?: string | null;
  archived_at?: string | null;
  is_archived?: boolean;
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
    hypothesis: project.hypothesis ?? null,
    metric_type: project.metric_type ?? null,
    duration_days: project.duration_days ?? null,
    created_at: project.created_at,
    updated_at: project.updated_at,
    payload_schema_version: project.payload_schema_version ?? 1,
    archived_at: project.archived_at ?? null,
    is_archived: project.is_archived ?? false,
    revision_count: project.revision_count ?? 0,
    last_revision_at: project.last_revision_at ?? null,
    last_analysis_at: project.last_analysis_at ?? null,
    last_analysis_run_id: project.last_analysis_run_id ?? null,
    last_exported_at: project.last_exported_at ?? null,
    has_analysis_snapshot: project.has_analysis_snapshot ?? false
  };
}

export function resolveErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function downloadFile(content: BlobPart, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function upsertSavedProject(projects: SavedProject[], project: SavedProject): SavedProject[] {
  return [project, ...projects.filter((candidate) => candidate.id !== project.id)].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at)
  );
}

export function deriveProjectState(
  state: Pick<
    ProjectStoreValues,
    | "savedProjects"
    | "activeProjectId"
    | "dirtyState"
    | "projectHistory"
    | "selectedHistoryRunId"
    | "backendHealth"
    | "backendDiagnostics"
  >
): Pick<
  ProjectStoreValues,
  | "activeProject"
  | "activeSavedProjects"
  | "archivedProjects"
  | "hasUnsavedChanges"
  | "selectedHistoryRun"
  | "canMutateBackend"
  | "isReadOnlySession"
  | "canUseCompute"
  | "backendMutationMessage"
> {
  const activeProject =
    state.activeProjectId !== null
      ? state.savedProjects.find((project) => project.id === state.activeProjectId) ?? null
      : null;
  const activeSavedProjects = state.savedProjects.filter((project) => !project.is_archived);
  const archivedProjects = state.savedProjects.filter((project) => project.is_archived);
  const hasUnsavedChanges =
    state.activeProjectId !== null &&
    state.dirtyState.savedSerializedForm !== null &&
    state.dirtyState.currentSerializedForm !== state.dirtyState.savedSerializedForm;
  const selectedHistoryRun =
    state.selectedHistoryRunId && state.projectHistory
      ? state.projectHistory.analysis_runs.find((run) => run.id === state.selectedHistoryRunId) ?? null
      : null;
  const backendAuth = state.backendDiagnostics?.auth ?? null;
  const diagnosticsKnown = backendAuth !== null;
  const canMutateBackend: boolean = Boolean(
    diagnosticsKnown && (!backendAuth.enabled || backendAuth.session_can_write)
  );
  const isReadOnlySession: boolean = Boolean(
    state.backendHealth && diagnosticsKnown && backendAuth.enabled && !backendAuth.session_can_write
  );
  const canUseCompute: boolean = Boolean(state.backendHealth && diagnosticsKnown) &&
    (canMutateBackend || isReadOnlySession);
  const backendMutationMessage =
    !state.backendHealth
      ? "Backend is unavailable. Mutating actions stay disabled until health and diagnostics recover."
      : !diagnosticsKnown
        ? "Backend auth state is not confirmed yet. Refresh diagnostics or provide a browser-session API token."
        : backendAuth.enabled && !canMutateBackend
          ? "Backend is running in read-only mode for this session. Calculators, analysis, and report exports stay available; saving, workspace import, and project changes need a write-capable token."
          : "";

  return {
    activeProject,
    activeSavedProjects,
    archivedProjects,
    hasUnsavedChanges,
    selectedHistoryRun,
    canMutateBackend,
    isReadOnlySession,
    canUseCompute,
    backendMutationMessage
  };
}
