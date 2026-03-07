import type { SavedProject } from "../lib/experiment";

type SidebarPanelProps = {
  loadingProjects: boolean;
  deletingProjectId: string | null;
  savedProjects: SavedProject[];
  onLoadProjects: () => void;
  onLoadProject: (projectId: string) => void;
  onDeleteProject: (projectId: string, projectName: string) => void;
};

export default function SidebarPanel({
  loadingProjects,
  deletingProjectId,
  savedProjects,
  onLoadProjects,
  onLoadProject,
  onDeleteProject
}: SidebarPanelProps) {
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
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? "Loading..." : "Load saved projects"}
          </button>
        </div>
        <h3>Saved projects</h3>
        {savedProjects.length > 0 ? (
          <ul className="list">
            {savedProjects.map((project) => (
              <li key={project.id}>
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadProject(project.id)}>
                    {project.project_name}
                  </button>
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
