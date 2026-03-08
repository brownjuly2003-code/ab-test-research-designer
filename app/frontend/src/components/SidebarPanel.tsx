import { memo, useState } from "react";

import type {
  ApiDiagnosticsResponse,
  ApiHealthResponse,
  ProjectComparison,
  ProjectHistory,
  SavedProject
} from "../lib/experiment";
import Icon from "./Icon";
import StatusDot from "./StatusDot";

type SidebarPanelProps = {
  loadingHealth: boolean;
  loadingDiagnostics: boolean;
  loadingProjects: boolean;
  importingWorkspace: boolean;
  exportingWorkspace: boolean;
  deletingProjectId: string | null;
  backendHealth: ApiHealthResponse | null;
  backendDiagnostics: ApiDiagnosticsResponse | null;
  healthError: string;
  diagnosticsError: string;
  savedProjects: SavedProject[];
  activeProjectId: string | null;
  activeProject: SavedProject | null;
  projectHistory: ProjectHistory | null;
  projectHistoryError: string;
  loadingProjectHistory: boolean;
  selectedHistoryRunId: string | null;
  projectComparison: ProjectComparison | null;
  projectComparisonError: string;
  loadingProjectComparison: boolean;
  comparingProjectId: string | null;
  hasUnsavedChanges: boolean;
  onRefreshHealth: () => void;
  onRefreshDiagnostics: () => void;
  onRefreshProjectHistory: (projectId: string) => void;
  onLoadMoreAnalysisHistory: (projectId: string) => void;
  onLoadMoreExportHistory: (projectId: string) => void;
  onOpenHistoryRun: (runId: string) => void;
  onClearHistoryRunSelection: () => void;
  onCompareProject: (projectId: string) => void;
  onLoadProjects: () => void;
  onExportWorkspace: () => void;
  onImportWorkspace: () => void;
  onLoadProject: (projectId: string) => void;
  onDeleteProject: (projectId: string, projectName: string) => void;
};

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

const SidebarPanel = memo(function SidebarPanel({
  loadingHealth,
  loadingDiagnostics,
  loadingProjects,
  importingWorkspace,
  exportingWorkspace,
  deletingProjectId,
  backendHealth,
  backendDiagnostics,
  healthError,
  diagnosticsError,
  savedProjects,
  activeProjectId,
  activeProject,
  projectHistory,
  projectHistoryError,
  loadingProjectHistory,
  selectedHistoryRunId,
  projectComparison,
  projectComparisonError,
  loadingProjectComparison,
  comparingProjectId,
  hasUnsavedChanges,
  onRefreshHealth,
  onRefreshDiagnostics,
  onRefreshProjectHistory,
  onLoadMoreAnalysisHistory,
  onLoadMoreExportHistory,
  onOpenHistoryRun,
  onClearHistoryRunSelection,
  onCompareProject,
  onLoadProjects,
  onExportWorkspace,
  onImportWorkspace,
  onLoadProject,
  onDeleteProject
}: SidebarPanelProps) {
  const [projectQuery, setProjectQuery] = useState("");
  const normalizedQuery = projectQuery.trim().toLowerCase();
  const compareEnabled = Boolean(activeProjectId && activeProject?.has_analysis_snapshot);
  const filteredProjects =
    normalizedQuery.length > 0
      ? savedProjects.filter((project) => project.project_name.toLowerCase().includes(normalizedQuery))
      : savedProjects;
  const hasMoreAnalysisHistory = Boolean(
    projectHistory && projectHistory.analysis_runs.length < projectHistory.analysis_total
  );
  const hasMoreExportHistory = Boolean(
    projectHistory && projectHistory.export_events.length < projectHistory.export_total
  );

  return (
    <aside className="panel meta">
      <div className="note">
        <h3>How this UI is split</h3>
        <ul className="list">
          <li>Deterministic calculations come from `/api/v1/calculate`.</li>
          <li>Warnings come from the rules engine layered on top of deterministic inputs.</li>
          <li>AI advice is optional and pulled separately from the local orchestrator.</li>
        </ul>
      </div>

      <div className="card">
        <div className="section-heading">
          <div className="status-heading">
            <StatusDot online={Boolean(backendHealth)} />
            <div>
              <h3>Backend status</h3>
              <p className="muted compact-text">
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
            <h3>Runtime diagnostics</h3>
            <p className="muted compact-text">
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
                {String(backendDiagnostics.storage.export_events_total)} export events
              </li>
              <li>
                <strong>Latest project update:</strong> {formatOptionalTimestamp(backendDiagnostics.storage.latest_project_updated_at)}
              </li>
              <li>
                <strong>SQLite path:</strong> <code>{backendDiagnostics.storage.db_path}</code>
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
            </ul>
          </>
        ) : diagnosticsError ? (
          <div className="status">Diagnostics unavailable. {diagnosticsError}</div>
        ) : (
          <p className="muted">No diagnostics loaded yet.</p>
        )}
      </div>

      <div className="card">
        <h3>Current draft</h3>
        {activeProjectId ? (
          <>
            <span className="pill">{hasUnsavedChanges ? "Unsaved changes" : "Saved locally"}</span>
            <ul className="list">
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
          <p className="muted">You are working in a new local draft until you save it as a project.</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>Recent project history</h3>
            <p className="muted compact-text">Timeline of saved analysis runs and export events for the loaded project.</p>
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
            <div className="timeline-card">
              <h3>Analysis runs</h3>
              <div className="timeline-list">
                {projectHistory.analysis_runs.length > 0 ? (
                  projectHistory.analysis_runs.map((run) => (
                    <div key={run.id} className="timeline-item">
                      <div className="timeline-title">
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
                  <div className="timeline-item">
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
            <div className="timeline-card">
              <h3>Export events</h3>
              <div className="timeline-list">
                {projectHistory.export_events.length > 0 ? (
                  projectHistory.export_events.map((event) => (
                    <div key={event.id} className="timeline-item">
                      <div className="timeline-title">
                        <strong>{formatProjectTimestamp(event.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {event.format.toUpperCase()}
                        {event.analysis_run_id ? " | linked snapshot" : " | unlinked export"}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="timeline-item">
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
            <h3>Saved projects</h3>
            <p className="muted compact-text">Load, compare, and delete SQLite-backed drafts from the local workspace.</p>
          </div>
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? "Loading..." : "Load saved projects"}
          </button>
        </div>
        {savedProjects.length > 0 ? (
          <>
            <div className="field search-field">
              <label htmlFor="saved-projects-search">Search projects</label>
              <div className="input-with-icon">
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
            <div className="project-card-list">
              {filteredProjects.map((project) => (
                <div key={project.id} className={`project-card ${project.id === activeProjectId ? "active" : ""}`}>
                  <div className="project-card-head">
                    <button className="btn ghost project-load-btn" onClick={() => onLoadProject(project.id)}>
                      {project.project_name}
                    </button>
                    <div className="project-badges">
                      {project.id === activeProjectId ? <span className="pill">Loaded</span> : null}
                      {project.has_analysis_snapshot ? <span className="pill">Snapshot</span> : null}
                    </div>
                  </div>
                  <div className="meta">
                    <div className="muted">
                      Updated {formatProjectTimestamp(project.updated_at)}
                      {project.last_analysis_at ? ` | Analyzed ${formatProjectTimestamp(project.last_analysis_at)}` : ""}
                    </div>
                    <div className="muted">
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
                    <button
                      className="btn secondary"
                      disabled={deletingProjectId === project.id}
                      aria-label={`Delete ${project.project_name}`}
                      onClick={() => onDeleteProject(project.id, project.project_name)}
                    >
                      <Icon name="trash" className="icon icon-inline" />
                      {deletingProjectId === project.id ? "Deleting..." : "Delete"}
                    </button>
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
            <h3>Workspace backup</h3>
            <p className="muted compact-text">
              Export or import the full SQLite workspace, including saved projects, analysis history, and export events.
            </p>
          </div>
        </div>
        <div className="actions">
          <button className="btn ghost" disabled={exportingWorkspace} onClick={onExportWorkspace}>
            {exportingWorkspace ? "Exporting..." : "Export workspace JSON"}
          </button>
          <button className="btn secondary" disabled={importingWorkspace} onClick={onImportWorkspace}>
            {importingWorkspace ? "Importing..." : "Import workspace JSON"}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Backend endpoints</h3>
        <ul className="list">
          <li><code>POST /api/v1/analyze</code></li>
          <li><code>GET /api/v1/diagnostics</code></li>
          <li><code>GET /readyz</code></li>
          <li><code>GET /api/v1/workspace/export</code></li>
          <li><code>POST /api/v1/workspace/import</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/analysis</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/exports</code></li>
          <li><code>GET /api/v1/projects/compare</code></li>
          <li><code>GET /api/v1/projects/{'{id}'}/history</code></li>
          <li><code>GET/POST/PUT/DELETE /api/v1/projects</code></li>
        </ul>
      </div>
    </aside>
  );
});

export default SidebarPanel;
