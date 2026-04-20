import { memo, useRef, useState, type ChangeEvent } from "react";

import { hydrateLoadedPayload, stepLabels } from "../lib/experiment";
import type { ToastType } from "../hooks/useToast";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import Icon from "./Icon";
import InlineConfirmButton from "./InlineConfirmButton";
import ProjectListSkeleton from "./ProjectListSkeleton";
import StatusDot from "./StatusDot";
import styles from "./SidebarPanel.module.css";

function formatProjectTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function formatOptionalTimestamp(timestamp: string | null | undefined): string {
  return timestamp ? formatProjectTimestamp(timestamp) : "Not recorded yet";
}

function formatUptime(seconds: number): string {
  if (!(seconds >= 0)) {
    return "0s";
  }

  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

function formatBytes(bytes: number): string {
  if (!(bytes >= 0)) {
    return "n/a";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const digits = unitIndex === 0 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function formatRevisionSource(source: string): string {
  if (source === "workspace_import") {
    return "Imported workspace snapshot";
  }
  return source === "update" ? "Project update" : "Initial save";
}

const SidebarPanel = memo(function SidebarPanel() {
  const analysis = useAnalysisStore();
  const draftStore = useDraftStore();
  const project = useProjectStore();
  const openWizard = useWizardStore((state) => state.openWizard);
  const workspaceImportRef = useRef<HTMLInputElement | null>(null);
  const {
    loadingHealth,
    loadingDiagnostics,
    loadingProjects,
    importingWorkspace,
    exportingWorkspace,
    deletingProjectId,
    restoringProjectId,
    backendHealth,
    backendDiagnostics,
    healthError,
    diagnosticsError,
    activeSavedProjects: savedProjects,
    archivedProjects,
    activeProjectId,
    activeProject,
    projectHistory,
    projectRevisions,
    projectHistoryError,
    projectRevisionsError,
    loadingProjectHistory,
    loadingProjectRevisions,
    selectedHistoryRunId,
    projectComparison,
    projectComparisonError,
    loadingProjectComparison,
    comparingProjectId,
    hasUnsavedChanges,
    canMutateBackend,
    backendMutationMessage,
    apiTokenDraft,
    apiTokenConfigured,
    apiTokenStatus
  } = project;
  const [activeTab, setActiveTab] = useState<"projects" | "system">("projects");
  const [projectQuery, setProjectQuery] = useState("");
  const onRefreshHealth = () => void project.loadBackendHealth();
  const onRefreshDiagnostics = () => void project.loadBackendDiagnostics();
  const onApiTokenDraftChange = (value: string) => project.updateApiTokenDraft(value);
  const onRefreshProjectHistory = (projectId: string) => void project.refreshProjectHistory(projectId);
  const onRefreshProjectRevisions = (projectId: string) => void project.refreshProjectRevisions(projectId);
  const onLoadMoreAnalysisHistory = (projectId: string) => void project.loadMoreAnalysisHistory(projectId);
  const onLoadMoreExportHistory = (projectId: string) => void project.loadMoreExportHistory(projectId);
  const onLoadMoreProjectRevisions = (projectId: string) => void project.loadMoreProjectRevisions(projectId);
  const onLoadProjects = () => void project.refreshProjects();
  const normalizedQuery = projectQuery.trim().toLowerCase();

  async function showAsyncStatus(action: Promise<string | null>, type: ToastType) {
    const message = await action;
    if (message) {
      analysis.showStatus(message, type);
    }
  }

  function blockMutations(): boolean {
    if (canMutateBackend) {
      return false;
    }
    analysis.clearFeedback();
    analysis.showError(backendMutationMessage || "Backend is running in read-only mode.", "warning");
    return true;
  }

  async function onSaveApiToken() {
    analysis.clearFeedback();
    await showAsyncStatus(project.saveRuntimeApiToken(), "info");
  }

  async function onClearApiToken() {
    analysis.clearFeedback();
    await showAsyncStatus(project.clearRuntimeApiToken(), "info");
    analysis.clearAnalysis();
  }

  function onClearHistoryRunSelection() {
    if (!project.clearHistoryRunSelection()) {
      return;
    }
    analysis.clearFeedback();
    analysis.showStatus(
      analysis.results.report
        ? "Returned to the current in-memory analysis results."
        : "Closed the saved snapshot preview.",
      "info"
    );
  }

  async function onOpenHistoryRun(runId: string) {
    if (!project.openHistoryRun(runId)) {
      return;
    }
    analysis.clearFeedback();
    analysis.showStatus("Opened a saved analysis snapshot from project history.", "info");
    openWizard(stepLabels.length - 1);
  }

  function onLoadProjectRevision(revisionId: string) {
    const revision = project.loadProjectRevision(revisionId);
    if (!revision) {
      return;
    }
    draftStore.replaceDraft(revision.draft, { markDirty: true });
    analysis.clearAnalysis();
    analysis.showStatus(revision.message, "info");
    openWizard();
  }

  async function onCompareProject(projectId: string) {
    const message = await project.compareProject(projectId);
    if (message) {
      analysis.showStatus(message, "info");
    }
  }

  async function onExportWorkspace() {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    await showAsyncStatus(project.exportWorkspace(), "success");
  }

  function onImportWorkspace() {
    workspaceImportRef.current?.click();
  }

  async function handleWorkspaceImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    event.target.value = "";
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    await showAsyncStatus(project.importWorkspace(await file.text()), "success");
  }

  async function onLoadProject(projectId: string) {
    analysis.clearFeedback();
    const loaded = await project.loadProject(projectId);
    if (!loaded) {
      return;
    }
    draftStore.replaceDraft(hydrateLoadedPayload(loaded.payload), { markDirty: true });
    analysis.clearAnalysis();
    analysis.showStatus(`Loaded project ${String(loaded.project_name)} into the wizard.`, "info");
    openWizard();
  }

  async function onDeleteProject(projectId: string, projectName: string) {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    const result = await project.archiveProject(projectId);
    if (!result.deleted) {
      return;
    }
    if (result.deletedActive) {
      analysis.clearAnalysis();
      analysis.showStatus(`Project ${projectName} archived. Current form remains as a new local draft.`, "success");
      return;
    }
    analysis.showStatus(`Project ${projectName} archived.`, "success");
  }

  async function onRestoreProject(projectId: string, _projectName: string) {
    analysis.clearFeedback();
    const restored = await project.restoreProject(projectId);
    if (!restored) {
      return;
    }
    if (useProjectStore.getState().activeProjectId === projectId) {
      draftStore.replaceDraft(hydrateLoadedPayload(restored.payload), { markDirty: true });
    }
    analysis.showStatus(`Project ${String(restored.project_name)} restored from archive.`, "success");
  }

  async function onPermanentlyDeleteProject(projectId: string, projectName: string) {
    if (blockMutations()) {
      return;
    }
    analysis.clearFeedback();
    const result = await project.deleteProject(projectId);
    if (!result.deleted) {
      return;
    }
    if (result.deletedActive) {
      analysis.clearAnalysis();
      analysis.showStatus(`Project ${projectName} deleted permanently. Current form remains as a new local draft.`, "success");
      return;
    }
    analysis.showStatus(`Project ${projectName} deleted permanently.`, "success");
  }
  const compareEnabled = Boolean(activeProjectId && activeProject?.has_analysis_snapshot);
  const archivedProjectsTotal = archivedProjects.length;
  const filteredProjects =
    normalizedQuery.length > 0
      ? savedProjects.filter((project) => project.project_name.toLowerCase().includes(normalizedQuery))
      : savedProjects;
  const savedProjectsTotal = savedProjects.length;
  const projectsWithSnapshots = savedProjects.filter((project) => project.has_analysis_snapshot).length;
  const projectsWithoutSnapshots = savedProjectsTotal - projectsWithSnapshots;
  const projectsWithExports = savedProjects.filter((project) => Boolean(project.last_exported_at)).length;
  const projectsWithMultipleRevisions = savedProjects.filter((project) => (project.revision_count ?? 0) > 1).length;
  const latestWorkspaceUpdate =
    backendDiagnostics?.storage.latest_project_updated_at ??
    (savedProjects[0]?.updated_at ?? null);
  const hasMoreAnalysisHistory = Boolean(
    projectHistory && projectHistory.analysis_runs.length < projectHistory.analysis_total
  );
  const hasMoreExportHistory = Boolean(
    projectHistory && projectHistory.export_events.length < projectHistory.export_total
  );
  const hasMoreProjectRevisions = Boolean(
    projectRevisions && projectRevisions.revisions.length < projectRevisions.total
  );

  return (
    <aside className={`panel ${styles.sidebar}`}>
      <input
        ref={workspaceImportRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label="Import workspace file"
        onChange={handleWorkspaceImport}
      />
      <div
        style={{
          display: "inline-flex",
          gap: 8,
          padding: 6,
          borderRadius: 999,
          background: "rgba(255, 255, 255, 0.65)",
          border: "1px solid var(--line)",
          alignSelf: "flex-start"
        }}
      >
        <button
          type="button"
          className="btn"
          style={{
            background: activeTab === "projects" ? "var(--color-secondary)" : "transparent",
            color: activeTab === "projects" ? "#ffffff" : "var(--muted)",
            boxShadow: activeTab === "projects" ? "0 10px 24px rgba(79, 70, 229, 0.2)" : "none"
          }}
          onClick={() => setActiveTab("projects")}
        >
          Projects
        </button>
        <button
          type="button"
          className="btn"
          style={{
            background: activeTab === "system" ? "var(--color-secondary)" : "transparent",
            color: activeTab === "system" ? "#ffffff" : "var(--muted)",
            boxShadow: activeTab === "system" ? "0 10px 24px rgba(79, 70, 229, 0.2)" : "none"
          }}
          onClick={() => setActiveTab("system")}
        >
          System
        </button>
      </div>

      {activeTab === "system" ? (
        <>
      <div className="card">
        <div className="section-heading">
          <div className={styles["status-heading"]}>
            <StatusDot online={Boolean(backendHealth)} />
            <div>
              <h3>Backend status</h3>
              <p className={`muted ${styles["compact-text"]}`}>
                Live health for the FastAPI runtime that serves calculations, storage, and optional AI advice.
              </p>
            </div>
          </div>
          <button className="btn ghost" disabled={loadingHealth} onClick={onRefreshHealth}>
            {loadingHealth ? "Checking..." : "Refresh backend status"}
          </button>
        </div>
        {backendHealth ? (
          <>
            <span className="pill">API online</span>
            <ul className="list">
              <li>
                <strong>Service:</strong> {backendHealth.service}
              </li>
              <li>
                <strong>Version:</strong> {backendHealth.version}
              </li>
              <li>
                <strong>Environment:</strong> {backendHealth.environment}
              </li>
            </ul>
          </>
        ) : healthError ? (
          <div className="status">API unavailable. {healthError}</div>
        ) : (
          <p className="muted">No backend status loaded yet.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>API session token</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              Optional token stored only in this browser session. It is not baked into the frontend build or Docker image.
            </p>
          </div>
        </div>
        <div className="field">
          <label htmlFor="api-session-token">Session token</label>
          <input
            id="api-session-token"
            type="password"
            placeholder={apiTokenConfigured ? "Token stored in current browser session" : "Paste read-only or write token"}
            value={apiTokenDraft}
            onChange={(event) => onApiTokenDraftChange(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="btn secondary" disabled={apiTokenDraft.trim().length === 0} onClick={onSaveApiToken}>
            Save token
          </button>
          <button className="btn ghost" disabled={!apiTokenConfigured && apiTokenDraft.trim().length === 0} onClick={onClearApiToken}>
            Clear token
          </button>
        </div>
        <div className="actions">
          <span className="pill">{apiTokenConfigured ? "Token configured" : "No token stored"}</span>
        </div>
        {apiTokenStatus ? <div className="status">{apiTokenStatus}</div> : null}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Workspace backup</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              Export or import the full SQLite workspace, including saved projects, history, exports, and revisions.
            </p>
          </div>
        </div>
        <div className="actions">
          <button className="btn ghost" disabled={exportingWorkspace} onClick={onExportWorkspace}>
            {exportingWorkspace ? "Exporting..." : "Export workspace JSON"}
          </button>
          <button className="btn secondary" disabled={!canMutateBackend || importingWorkspace} onClick={onImportWorkspace}>
            {importingWorkspace ? "Importing..." : "Import workspace JSON"}
          </button>
        </div>
      </div>

      {savedProjects.length > 0 ? (
        <div className="card">
          <h3>Saved projects</h3>
          <div className="actions">
            {savedProjects.map((project) => (
              deletingProjectId === project.id ? (
                <button
                  key={project.id}
                  className="btn secondary"
                  disabled={true}
                  aria-label={`Archive ${project.project_name}`}
                >
                  Archiving...
                </button>
              ) : (
                <InlineConfirmButton
                  key={project.id}
                  label="Archive"
                  disabled={!canMutateBackend}
                  ariaLabel={`Archive ${project.project_name}`}
                  onConfirm={() => onDeleteProject(project.id, project.project_name)}
                />
              )
            ))}
          </div>
        </div>
      ) : null}

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Runtime diagnostics</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              Lightweight observability for storage, frontend serving, orchestrator settings, and uptime.
            </p>
          </div>
          <button className="btn ghost" disabled={loadingDiagnostics} onClick={onRefreshDiagnostics}>
            {loadingDiagnostics ? "Refreshing..." : "Refresh diagnostics"}
          </button>
        </div>
        {backendDiagnostics ? (
          <>
            <span className="pill">Diagnostics online</span>
            <ul className="list">
              <li>
                <strong>Uptime:</strong> {formatUptime(backendDiagnostics.uptime_seconds)}
              </li>
              <li>
                <strong>Storage:</strong> {String(backendDiagnostics.storage.projects_total)} projects,{" "}
                {String(backendDiagnostics.storage.analysis_runs_total)} analysis runs,{" "}
                {String(backendDiagnostics.storage.export_events_total)} export events,{" "}
                {String(backendDiagnostics.storage.project_revisions_total)} revisions
              </li>
              <li>
                <strong>Latest project update:</strong> {formatOptionalTimestamp(backendDiagnostics.storage.latest_project_updated_at)}
              </li>
              <li>
                <strong>SQLite path:</strong> <code>{backendDiagnostics.storage.db_path}</code>
              </li>
              <li>
                <strong>SQLite parent:</strong> <code>{backendDiagnostics.storage.db_parent_path}</code>
              </li>
              <li>
                <strong>Storage footprint:</strong> db {formatBytes(backendDiagnostics.storage.db_size_bytes)}
                {" | free disk "}
                {formatBytes(backendDiagnostics.storage.disk_free_bytes)}
              </li>
              <li>
                <strong>SQLite mode:</strong> schema v{String(backendDiagnostics.storage.schema_version)}
                {" | user_version "}
                {String(backendDiagnostics.storage.sqlite_user_version)}
                {" | "}
                {backendDiagnostics.storage.journal_mode}
                {" | "}
                {backendDiagnostics.storage.synchronous}
                {" | busy timeout "}
                {String(backendDiagnostics.storage.busy_timeout_ms)}ms
              </li>
              <li>
                <strong>SQLite write probe:</strong> {backendDiagnostics.storage.write_probe_ok ? "pass" : "fail"}
                {" | "}
                {backendDiagnostics.storage.write_probe_detail}
              </li>
              <li>
                <strong>Workspace backups:</strong> schema v{String(backendDiagnostics.storage.workspace_bundle_schema_version)}
                {" | "}
                {backendDiagnostics.storage.workspace_signature_enabled ? "HMAC signed" : "checksum only"}
              </li>
              <li>
                <strong>Frontend dist:</strong> {backendDiagnostics.frontend.serve_frontend_dist ? "enabled" : "disabled"}
                {" | "}
                {backendDiagnostics.frontend.dist_exists ? "present" : "missing"}
              </li>
              <li>
                <strong>Timing headers:</strong> {backendDiagnostics.request_timing_headers_enabled ? "enabled" : "disabled"}
              </li>
              <li>
                <strong>LLM adapter:</strong> {backendDiagnostics.llm.provider}
                {" | timeout "}
                {String(backendDiagnostics.llm.timeout_seconds)}s
                {" | attempts "}
                {String(backendDiagnostics.llm.max_attempts)}
              </li>
              <li>
                <strong>Logging:</strong> {backendDiagnostics.logging.level}
                {" | "}
                {backendDiagnostics.logging.format}
              </li>
              <li>
                <strong>Runtime counters:</strong> {String(backendDiagnostics.runtime.total_requests)} requests
                {" | ok "}
                {String(backendDiagnostics.runtime.success_responses)}
                {" | 4xx "}
                {String(backendDiagnostics.runtime.client_error_responses)}
                {" | 5xx "}
                {String(backendDiagnostics.runtime.server_error_responses)}
                {" | 429 "}
                {String(backendDiagnostics.runtime.rate_limited_responses)}
              </li>
              <li>
                <strong>Last runtime error:</strong> {backendDiagnostics.runtime.last_error_code ?? "none"}
                {" | auth rejects "}
                {String(backendDiagnostics.runtime.auth_rejections)}
                {" | body rejects "}
                {String(backendDiagnostics.runtime.request_body_rejections)}
              </li>
              <li>
                <strong>API auth:</strong> {backendDiagnostics.auth.enabled ? backendDiagnostics.auth.mode : "disabled"}
                {" | "}
                {backendDiagnostics.auth.write_enabled ? "write token" : "no write token"}
                {" | "}
                {backendDiagnostics.auth.readonly_enabled ? "read-only token" : "no read-only token"}
              </li>
              <li>
                <strong>Auth headers:</strong> {backendDiagnostics.auth.accepted_headers.join(", ")}
                {" | read methods "}
                {backendDiagnostics.auth.read_only_methods.join(", ")}
              </li>
              <li>
                <strong>Security guards:</strong> {backendDiagnostics.guards.security_headers_enabled ? "headers on" : "headers off"}
                {" | rate limit "}
                {backendDiagnostics.guards.rate_limit_enabled
                  ? `${String(backendDiagnostics.guards.rate_limit_requests)}/${String(backendDiagnostics.guards.rate_limit_window_seconds)}s`
                  : "disabled"}
                {" | auth throttle "}
                {String(backendDiagnostics.guards.auth_failure_limit)}/{String(backendDiagnostics.guards.auth_failure_window_seconds)}s
              </li>
              <li>
                <strong>Body limits:</strong> general {formatBytes(backendDiagnostics.guards.max_request_body_bytes)}
                {" | workspace "}
                {formatBytes(backendDiagnostics.guards.max_workspace_body_bytes)}
              </li>
            </ul>
          </>
        ) : diagnosticsError ? (
          <div className="status">Diagnostics unavailable. {diagnosticsError}</div>
        ) : (
          <p className="muted">No diagnostics loaded yet.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Workspace status board</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              One-glance summary of saved-project coverage, snapshot depth, and whether the current draft is in sync.
            </p>
          </div>
        </div>
        <div className="actions">
          <span className="pill">{savedProjectsTotal} saved</span>
          <span className="pill">{projectsWithSnapshots} with snapshots</span>
          {hasUnsavedChanges ? <span className="pill">Draft changed</span> : null}
          {backendDiagnostics?.storage.write_probe_ok ? <span className="pill">SQLite writable</span> : null}
          {!canMutateBackend ? <span className="pill">Read-only API</span> : null}
        </div>
        <ul className="list">
          <li>
            <strong>Saved projects:</strong> {String(savedProjectsTotal)}
          </li>
          <li>
            <strong>Archived projects:</strong> {String(archivedProjectsTotal)}
          </li>
          <li>
            <strong>Snapshot coverage:</strong> {String(projectsWithSnapshots)} ready
            {" | "}
            {String(projectsWithoutSnapshots)} without saved analysis
          </li>
          <li>
            <strong>Export coverage:</strong> {String(projectsWithExports)} exported at least once
          </li>
          <li>
            <strong>Revision depth:</strong> {String(projectsWithMultipleRevisions)} project(s) with more than one saved revision
          </li>
          <li>
            <strong>Current draft:</strong> {activeProjectId ? (hasUnsavedChanges ? "loaded project with unsaved changes" : "loaded project in sync") : "new local draft"}
          </li>
          <li>
            <strong>Latest workspace update:</strong> {formatOptionalTimestamp(latestWorkspaceUpdate)}
          </li>
        </ul>
        {!canMutateBackend ? (
          <div className="callout">
            <Icon name="info" className="icon icon-inline" />
            <span>{backendMutationMessage}</span>
          </div>
        ) : null}
      </div>

        </>
      ) : null}

      {activeTab === "projects" ? (
        <>
      <div className="card">
        <h3>Active project</h3>
        {activeProjectId ? (
          <>
            <div className="actions">
              <span className="pill">{hasUnsavedChanges ? "Unsaved changes" : "Saved locally"}</span>
            </div>
            <ul className="list">
              <li>
                <strong>Project name:</strong> {activeProject?.project_name ?? "Unknown project"}
              </li>
              <li>
                <strong>Project id:</strong> {activeProjectId}
              </li>
              <li>
                <strong>Status:</strong> {hasUnsavedChanges ? "Needs local update" : "In sync with SQLite"}
              </li>
              <li>
                <strong>Payload schema:</strong> {String(activeProject?.payload_schema_version ?? 1)}
              </li>
              <li>
                <strong>Saved revisions:</strong> {String(activeProject?.revision_count ?? 0)}
              </li>
              <li>
                <strong>Last save:</strong> {formatOptionalTimestamp(activeProject?.last_revision_at)}
              </li>
              <li>
                <strong>Last analysis:</strong> {formatOptionalTimestamp(activeProject?.last_analysis_at)}
              </li>
              <li>
                <strong>Last export:</strong> {formatOptionalTimestamp(activeProject?.last_exported_at)}
              </li>
              <li>
                <strong>Snapshot stored:</strong> {activeProject?.has_analysis_snapshot ? "Yes" : "No"}
              </li>
            </ul>
          </>
        ) : (
          <p className="muted">No saved project is loaded. You can still work in a local draft and save it when ready.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Recent project history</h3>
            <p className={`muted ${styles["compact-text"]}`}>Timeline of saved analysis runs and export events for the loaded project.</p>
          </div>
          <button
            className="btn ghost"
            disabled={loadingProjectHistory || !activeProjectId}
            onClick={() => {
              if (activeProjectId) {
                onRefreshProjectHistory(activeProjectId);
              }
            }}
          >
            {loadingProjectHistory ? "Refreshing..." : "Refresh project history"}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">Load a saved project to inspect recent analysis runs and export events.</p>
        ) : projectHistoryError ? (
          <div className="status">Project history unavailable. {projectHistoryError}</div>
        ) : loadingProjectHistory && !projectHistory ? (
          <p className="muted">Loading saved-project history...</p>
        ) : projectHistory ? (
          <>
            <p className="muted">
              Showing {projectHistory.analysis_runs.length} of {projectHistory.analysis_total} analysis run(s)
              {" and "}
              {projectHistory.export_events.length} of {projectHistory.export_total} export event(s).
            </p>
            {selectedHistoryRunId ? (
              <div className="actions">
                <button className="btn secondary" onClick={onClearHistoryRunSelection}>
                  Close opened snapshot
                </button>
              </div>
            ) : null}
            <div className={styles["timeline-card"]}>
              <h3>Analysis runs</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.analysis_runs.length > 0 ? (
                  projectHistory.analysis_runs.map((run) => (
                    <div key={run.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(run.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {String(run.summary.metric_type ?? "unknown metric")}
                        {" | "}n={String(run.summary.total_sample_size ?? "-")}
                        {" | "}{String(run.summary.estimated_duration_days ?? "-")}d
                        {" | "}warnings {String(run.summary.warnings_count)}
                        {run.summary.advice_available ? " | AI advice" : ""}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onOpenHistoryRun(run.id)}>
                          {selectedHistoryRunId === run.id ? "Opened" : "Open snapshot"}
                        </button>
                        {selectedHistoryRunId === run.id ? <span className="pill">Viewing</span> : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>No analysis history recorded yet.</div>
                  </div>
                )}
              </div>
              {hasMoreAnalysisHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreAnalysisHistory(activeProjectId)}>
                    Load older analysis runs
                  </button>
                </div>
              ) : null}
            </div>
            <div className={styles["timeline-card"]}>
              <h3>Export events</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.export_events.length > 0 ? (
                  projectHistory.export_events.map((event) => (
                    <div key={event.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(event.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {event.format.toUpperCase()}
                        {event.analysis_run_id ? " | linked snapshot" : " | unlinked export"}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>No export history recorded yet.</div>
                  </div>
                )}
              </div>
              {hasMoreExportHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreExportHistory(activeProjectId)}>
                    Load older export events
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">No project history loaded yet.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Saved revisions</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              Payload snapshots captured on create, update, and workspace import. Loading a revision keeps the current project selected but marks the wizard as changed until you save.
            </p>
          </div>
          <button
            className="btn ghost"
            disabled={loadingProjectRevisions || !activeProjectId}
            onClick={() => {
              if (activeProjectId) {
                onRefreshProjectRevisions(activeProjectId);
              }
            }}
          >
            {loadingProjectRevisions ? "Refreshing..." : "Refresh revisions"}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">Load a saved project to inspect or restore earlier payload revisions.</p>
        ) : projectRevisionsError ? (
          <div className="status">Project revisions unavailable. {projectRevisionsError}</div>
        ) : loadingProjectRevisions && !projectRevisions ? (
          <p className="muted">Loading saved revisions...</p>
        ) : projectRevisions ? (
          <>
            <p className="muted">
              Showing {projectRevisions.revisions.length} of {projectRevisions.total} revision(s).
            </p>
            <div className={styles["timeline-card"]}>
              <div className={styles["timeline-list"]}>
                {projectRevisions.revisions.length > 0 ? (
                  projectRevisions.revisions.map((revision) => (
                    <div key={revision.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(revision.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {formatRevisionSource(revision.source)}
                        {" | "}
                        {revision.payload.project.project_name}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onLoadProjectRevision(revision.id)}>
                          Load into wizard
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>No saved revisions recorded yet.</div>
                  </div>
                )}
              </div>
              {hasMoreProjectRevisions && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreProjectRevisions(activeProjectId)}>
                    Load older revisions
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">No project revisions loaded yet.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Saved projects</h3>
            <p className={`muted ${styles["compact-text"]}`}>Load, compare, and archive SQLite-backed drafts from the local workspace.</p>
          </div>
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? "Loading..." : "Load saved projects"}
          </button>
        </div>
        <div className="actions">
          <span className="pill">{savedProjectsTotal} saved</span>
          <span className="pill">{projectsWithoutSnapshots} without saved analysis</span>
        </div>
        {loadingProjects ? (
          <ProjectListSkeleton />
        ) : savedProjects.length > 0 ? (
          <>
            <div className={`field ${styles["search-field"]}`}>
              <label htmlFor="saved-projects-search">Search projects</label>
              <div className={styles["input-with-icon"]}>
                <Icon name="search" className="icon icon-inline" />
                <input
                  id="saved-projects-search"
                  type="text"
                  placeholder="Filter by project name"
                  value={projectQuery}
                  onChange={(event) => setProjectQuery(event.target.value)}
                />
              </div>
            </div>
            <p className="muted">
              Showing {filteredProjects.length} of {savedProjects.length} saved projects.
            </p>
            {compareEnabled ? (
              <>
                <p className="muted">
                  Compare buttons use the opened snapshot for the loaded project when one is selected; otherwise they use the latest saved snapshot.
                </p>
                {projectComparison ? (
                  <p className="muted">
                    Current comparison: {projectComparison.base_project.project_name} vs {projectComparison.candidate_project.project_name}.
                  </p>
                ) : null}
                {projectComparisonError ? (
                  <div className="status">Project comparison unavailable. {projectComparisonError}</div>
                ) : null}
              </>
            ) : activeProjectId ? (
              <p className="muted">Save at least one analysis snapshot before comparing saved projects.</p>
            ) : null}
            <div className={styles["project-card-list"]}>
              {filteredProjects.map((project) => (
                <div
                  key={project.id}
                  className={[styles["project-card"], project.id === activeProjectId ? styles.active : ""].filter(Boolean).join(" ")}
                >
                  <div className={styles["project-card-head"]}>
                    <button className={`btn ghost ${styles["project-load-btn"]}`} onClick={() => onLoadProject(project.id)}>
                      {project.project_name}
                    </button>
                    <div className={styles["project-badges"]}>
                      {project.id === activeProjectId ? <span className="pill">Loaded</span> : null}
                      {project.has_analysis_snapshot ? <span className="pill">Snapshot</span> : null}
                    </div>
                  </div>
                  <div className={styles["project-meta"]}>
                    <div className="muted">
                      Updated {formatProjectTimestamp(project.updated_at)}
                      {project.last_revision_at ? ` | Saved ${formatProjectTimestamp(project.last_revision_at)}` : ""}
                      {project.last_analysis_at ? ` | Analyzed ${formatProjectTimestamp(project.last_analysis_at)}` : ""}
                    </div>
                    <div className="muted">
                      {`Revisions ${String(project.revision_count ?? 0)}`}
                      {" | "}
                      {project.last_exported_at ? `Exported ${formatProjectTimestamp(project.last_exported_at)}` : "No exports yet"}
                      {project.id === activeProjectId ? " | Loaded in wizard" : ""}
                    </div>
                  </div>
                  <div className="actions">
                    {compareEnabled && project.id !== activeProjectId && project.has_analysis_snapshot ? (
                      <button
                        className="btn secondary"
                        disabled={loadingProjectComparison || deletingProjectId === project.id}
                        onClick={() => onCompareProject(project.id)}
                      >
                        {comparingProjectId === project.id ? "Comparing..." : "Compare"}
                      </button>
                    ) : null}
                    <InlineConfirmButton
                      label="Archive"
                      disabled={!canMutateBackend || deletingProjectId === project.id}
                      ariaLabel={`Archive ${project.project_name}`}
                      onConfirm={() => onDeleteProject(project.id, project.project_name)}
                    />
                    <InlineConfirmButton
                      label="Delete"
                      disabled={!canMutateBackend || deletingProjectId === project.id}
                      ariaLabel={`Delete ${project.project_name}`}
                      onConfirm={() => onPermanentlyDeleteProject(project.id, project.project_name)}
                    />
                  </div>
                </div>
              ))}
            </div>
            {filteredProjects.length === 0 ? (
              <p className="muted">No saved projects match the current search.</p>
            ) : null}
          </>
        ) : (
          <p className="muted">No saved projects available.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Archived projects</h3>
            <p className={`muted ${styles["compact-text"]}`}>Archived projects stay here until they are restored.</p>
          </div>
        </div>
        {archivedProjects.length > 0 ? (
          <div className={styles["project-card-list"]}>
            {archivedProjects.map((project) => (
              <div key={project.id} className={styles["project-card"]}>
                <div className={styles["project-card-head"]}>
                  <strong>{project.project_name}</strong>
                  <div className={styles["project-badges"]}>
                    <span className="pill">Archived</span>
                  </div>
                </div>
                <div className={styles["project-meta"]}>
                  <div className="muted">
                    Archived {formatOptionalTimestamp(project.archived_at)}
                    {project.last_analysis_at ? ` | Last analysis ${formatProjectTimestamp(project.last_analysis_at)}` : ""}
                  </div>
                  <div className="muted">
                    {`Revisions ${String(project.revision_count ?? 0)}`}
                    {" | "}
                    {project.last_exported_at ? `Exported ${formatProjectTimestamp(project.last_exported_at)}` : "No exports yet"}
                  </div>
                </div>
                <div className="actions">
                  <button
                    className="btn secondary"
                    disabled={!canMutateBackend || restoringProjectId === project.id}
                    onClick={() => onRestoreProject(project.id, project.project_name)}
                  >
                    {restoringProjectId === project.id ? "Restoring..." : "Restore"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No archived projects.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Workspace backup</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              Export or import the full SQLite workspace, including saved projects, analysis history, export events, and saved revisions. Imports run checksum, optional signature, and reference validation before SQLite writes begin.
            </p>
          </div>
        </div>
        <div className="actions">
          <button className="btn ghost" disabled={exportingWorkspace} onClick={onExportWorkspace}>
            {exportingWorkspace ? "Exporting..." : "Export workspace JSON"}
          </button>
          <button className="btn secondary" disabled={!canMutateBackend || importingWorkspace} onClick={onImportWorkspace}>
            {importingWorkspace ? "Importing..." : "Import workspace JSON"}
          </button>
        </div>
      </div>

        </>
      ) : null}

      {activeTab === "system" ? (
      <div className="card">
        <h3>Backend endpoints</h3>
        <ul className="list">
          <li><code>POST /api/v1/analyze</code></li>
          <li><code>GET /api/v1/diagnostics</code></li>
          <li><code>GET /readyz</code></li>
          <li><code>GET /api/v1/workspace/export</code></li>
          <li><code>POST /api/v1/workspace/validate</code></li>
          <li><code>POST /api/v1/workspace/import</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/analysis</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/archive</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/exports</code></li>
          <li><code>GET /api/v1/projects/compare</code></li>
          <li><code>GET /api/v1/projects/{'{id}'}/history</code></li>
          <li><code>GET /api/v1/projects/{'{id}'}/revisions</code></li>
          <li><code>GET/POST/PUT /api/v1/projects</code></li>
          <li><code>DELETE /api/v1/projects/{'{id}'}</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/restore</code></li>
        </ul>
      </div>
      ) : null}
    </aside>
  );
});

export default SidebarPanel;
