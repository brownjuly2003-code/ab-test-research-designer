import { useState } from "react";

import type { ApiHealthResponse, ProjectComparison, ProjectHistory, SavedProject } from "../lib/experiment";

type SidebarPanelProps = {
  loadingHealth: boolean;
  loadingProjects: boolean;
  deletingProjectId: string | null;
  backendHealth: ApiHealthResponse | null;
  healthError: string;
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
  onRefreshProjectHistory: (projectId: string) => void;
  onLoadMoreAnalysisHistory: (projectId: string) => void;
  onLoadMoreExportHistory: (projectId: string) => void;
  onOpenHistoryRun: (runId: string) => void;
  onClearHistoryRunSelection: () => void;
  onCompareProject: (projectId: string) => void;
  onLoadProjects: () => void;
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

export default function SidebarPanel({
  loadingHealth,
  loadingProjects,
  deletingProjectId,
  backendHealth,
  healthError,
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
  onRefreshProjectHistory,
  onLoadMoreAnalysisHistory,
  onLoadMoreExportHistory,
  onOpenHistoryRun,
  onClearHistoryRunSelection,
  onCompareProject,
  onLoadProjects,
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
        <div className="actions">
          <button className="btn ghost" disabled={loadingHealth} onClick={onRefreshHealth}>
            {loadingHealth ? "Checking..." : "Refresh backend status"}
          </button>
        </div>
        <h3>Backend status</h3>
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
          <div className="status">
            API unavailable. {healthError}
          </div>
        ) : (
          <p className="muted">No backend status loaded yet.</p>
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
        <div className="actions">
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
        <h3>Recent project history</h3>
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
            <div className="card">
              <h3>Analysis runs</h3>
              <ul className="list">
                {projectHistory.analysis_runs.length > 0 ? (
                  projectHistory.analysis_runs.map((run) => (
                    <li key={run.id}>
                      <div>
                        <strong>{formatProjectTimestamp(run.created_at)}</strong>
                        {" | "}
                        {String(run.summary.metric_type ?? "unknown metric")}
                        {" | "}
                        n={String(run.summary.total_sample_size ?? "-")}
                        {" | "}
                        {String(run.summary.estimated_duration_days ?? "-")}d
                        {" | "}
                        warnings {String(run.summary.warnings_count)}
                        {run.summary.advice_available ? " | AI advice" : ""}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onOpenHistoryRun(run.id)}>
                          {selectedHistoryRunId === run.id ? "Opened" : "Open snapshot"}
                        </button>
                        {selectedHistoryRunId === run.id ? <span className="pill">Viewing</span> : null}
                      </div>
                    </li>
                  ))
                ) : (
                  <li>No analysis history recorded yet.</li>
                )}
              </ul>
              {hasMoreAnalysisHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreAnalysisHistory(activeProjectId)}>
                    Load older analysis runs
                  </button>
                </div>
              ) : null}
            </div>
            <div className="card">
              <h3>Export events</h3>
              <ul className="list">
                {projectHistory.export_events.length > 0 ? (
                  projectHistory.export_events.map((event) => (
                    <li key={event.id}>
                      <strong>{formatProjectTimestamp(event.created_at)}</strong>
                      {" | "}
                      {event.format.toUpperCase()}
                      {event.analysis_run_id ? " | linked snapshot" : " | unlinked export"}
                    </li>
                  ))
                ) : (
                  <li>No export history recorded yet.</li>
                )}
              </ul>
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
        <div className="actions">
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? "Loading..." : "Load saved projects"}
          </button>
        </div>
        <h3>Saved projects</h3>
        {savedProjects.length > 0 ? (
          <>
            <div className="field">
              <label htmlFor="saved-projects-search">Search projects</label>
              <input
                id="saved-projects-search"
                type="text"
                placeholder="Filter by project name"
                value={projectQuery}
                onChange={(event) => setProjectQuery(event.target.value)}
              />
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
          <ul className="list">
            {filteredProjects.map((project) => (
              <li key={project.id}>
                <div className="muted">
                  Updated {formatProjectTimestamp(project.updated_at)}
                  {project.last_analysis_at ? ` | Analyzed ${formatProjectTimestamp(project.last_analysis_at)}` : ""}
                  {project.last_exported_at ? ` | Exported ${formatProjectTimestamp(project.last_exported_at)}` : ""}
                  {project.id === activeProjectId ? " | Loaded in wizard" : ""}
                </div>
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadProject(project.id)}>
                    {project.project_name}
                  </button>
                  {project.id === activeProjectId ? <span className="pill">Loaded</span> : null}
                  {project.has_analysis_snapshot ? <span className="pill">Snapshot</span> : null}
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
                    {deletingProjectId === project.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
            {filteredProjects.length === 0 ? (
              <p className="muted">No saved projects match the current search.</p>
            ) : null}
          </>
        ) : (
          <p className="muted">No saved projects available.</p>
        )}
      </div>
      <div className="card">
        <h3>Current phase</h3>
        <p className="muted">
          Use the wizard to define experiment context first. Results stay visible below the form after the run.
        </p>
      </div>
      <div className="card">
        <h3>Backend endpoints</h3>
        <ul className="list">
          <li><code>POST /api/v1/calculate</code></li>
          <li><code>POST /api/v1/design</code></li>
          <li><code>POST /api/v1/llm/advice</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/analysis</code></li>
          <li><code>POST /api/v1/projects/{'{id}'}/exports</code></li>
          <li><code>GET /api/v1/projects/compare</code></li>
          <li><code>GET /api/v1/projects/{'{id}'}/history</code></li>
          <li><code>GET/POST/PUT/DELETE /api/v1/projects</code></li>
        </ul>
      </div>
    </aside>
  );
}
