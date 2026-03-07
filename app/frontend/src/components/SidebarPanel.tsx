import { useState } from "react";

import type { ApiHealthResponse, SavedProject } from "../lib/experiment";

type SidebarPanelProps = {
  loadingHealth: boolean;
  loadingProjects: boolean;
  deletingProjectId: string | null;
  backendHealth: ApiHealthResponse | null;
  healthError: string;
  savedProjects: SavedProject[];
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  onRefreshHealth: () => void;
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

export default function SidebarPanel({
  loadingHealth,
  loadingProjects,
  deletingProjectId,
  backendHealth,
  healthError,
  savedProjects,
  activeProjectId,
  hasUnsavedChanges,
  onRefreshHealth,
  onLoadProjects,
  onLoadProject,
  onDeleteProject
}: SidebarPanelProps) {
  const [projectQuery, setProjectQuery] = useState("");
  const normalizedQuery = projectQuery.trim().toLowerCase();
  const filteredProjects =
    normalizedQuery.length > 0
      ? savedProjects.filter((project) => project.project_name.toLowerCase().includes(normalizedQuery))
      : savedProjects;

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
            </ul>
          </>
        ) : (
          <p className="muted">You are working in a new local draft until you save it as a project.</p>
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
          <ul className="list">
            {filteredProjects.map((project) => (
              <li key={project.id}>
                <div className="muted">
                  Updated {formatProjectTimestamp(project.updated_at)}
                  {project.id === activeProjectId ? " | Loaded in wizard" : ""}
                </div>
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadProject(project.id)}>
                    {project.project_name}
                  </button>
                  {project.id === activeProjectId ? <span className="pill">Loaded</span> : null}
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
          <li>`POST /api/v1/calculate`</li>
          <li>`POST /api/v1/design`</li>
          <li>`POST /api/v1/llm/advice`</li>
          <li>`GET/POST/PUT/DELETE /api/v1/projects`</li>
        </ul>
      </div>
    </aside>
  );
}
