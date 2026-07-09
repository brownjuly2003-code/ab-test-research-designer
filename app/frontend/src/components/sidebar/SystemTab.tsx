import { useTranslation } from "react-i18next";

import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import InlineConfirmButton from "../InlineConfirmButton";
import LlmProviderSettings from "../Settings/llm-provider";
import styles from "../SidebarPanel.module.css";
import StatusDot from "../StatusDot";
import { formatBytes, formatProjectTimestamp, formatUptime } from "./formatters";
import type { AdminToken } from "./useAdminToken";
import type { AuditLog } from "./useAuditLog";
import { useProjectStats } from "./useProjectStats";
import { useSidebarActions } from "./useSidebarActions";

type SystemTabProps = {
  auditLog: AuditLog;
  adminToken: AdminToken;
  onImportWorkspace: () => void;
};

export default function SystemTab({ auditLog, adminToken, onImportWorkspace }: SystemTabProps) {
  const { t } = useTranslation();
  const {
    loadingHealth,
    loadingDiagnostics,
    backendHealth,
    backendDiagnostics,
    healthError,
    diagnosticsError,
    savedProjects: allSavedProjects,
    activeSavedProjects: savedProjects,
    activeProjectId,
    deletingProjectId,
    importingWorkspace,
    exportingWorkspace,
    hasUnsavedChanges,
    canMutateBackend,
    backendMutationMessage,
    apiTokenDraft,
    apiTokenConfigured,
    apiTokenStatus
  } = useProjectStore();
  const {
    onRefreshHealth,
    onRefreshDiagnostics,
    onApiTokenDraftChange,
    onSaveApiToken,
    onClearApiToken,
    onExportWorkspace,
    onDeleteProject
  } = useSidebarActions();
  const {
    savedProjectsTotal,
    archivedProjectsTotal,
    projectsWithSnapshots,
    projectsWithoutSnapshots,
    projectsWithExports,
    projectsWithMultipleRevisions,
    latestWorkspaceUpdate,
    formatOptionalProjectTimestamp
  } = useProjectStats();

  return (
    <>
      <div className="card">
        <div className="section-heading">
          <div className={styles["status-heading"]}>
            <StatusDot online={Boolean(backendHealth)} />
            <div>
              <h3>{t("sidebarPanel.backendStatus.title")}</h3>
              <p className={`muted ${styles["compact-text"]}`}>
                {t("sidebarPanel.backendStatus.description")}
              </p>
            </div>
          </div>
          <button className="btn ghost" disabled={loadingHealth} onClick={onRefreshHealth}>
            {loadingHealth ? t("sidebarPanel.backendStatus.checking") : t("sidebarPanel.backendStatus.refresh")}
          </button>
        </div>
        {backendHealth ? (
          <>
            <span className="pill">{t("sidebarPanel.backendStatus.online")}</span>
            <ul className="list">
              <li>
                <strong>{t("sidebarPanel.backendStatus.labels.service")}:</strong> {backendHealth.service}
              </li>
              <li>
                <strong>{t("sidebarPanel.backendStatus.labels.version")}:</strong> {backendHealth.version}
              </li>
              <li>
                <strong>{t("sidebarPanel.backendStatus.labels.environment")}:</strong> {backendHealth.environment}
              </li>
            </ul>
          </>
        ) : healthError ? (
          <div className="status">{t("sidebarPanel.backendStatus.unavailable")} {healthError}</div>
        ) : (
          <p className="muted">{t("sidebarPanel.backendStatus.notLoaded")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.apiSessionToken.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.apiSessionToken.description")}
            </p>
          </div>
        </div>
        <div className="field">
          <label htmlFor="api-session-token">{t("sidebarPanel.apiSessionToken.label")}</label>
          <input
            id="api-session-token"
            type="password"
            placeholder={apiTokenConfigured
              ? t("sidebarPanel.apiSessionToken.placeholderConfigured")
              : t("sidebarPanel.apiSessionToken.placeholderEmpty")}
            value={apiTokenDraft}
            onChange={(event) => onApiTokenDraftChange(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="btn secondary" disabled={apiTokenDraft.trim().length === 0} onClick={onSaveApiToken}>
            {t("sidebarPanel.apiSessionToken.save")}
          </button>
          <button className="btn ghost" disabled={!apiTokenConfigured && apiTokenDraft.trim().length === 0} onClick={onClearApiToken}>
            {t("sidebarPanel.apiSessionToken.clear")}
          </button>
        </div>
        <div className="actions">
          <span className="pill">
            {apiTokenConfigured
              ? t("sidebarPanel.apiSessionToken.configured")
              : t("sidebarPanel.apiSessionToken.notStored")}
          </span>
        </div>
        {apiTokenStatus ? <div className="status">{apiTokenStatus}</div> : null}
      </div>

      <LlmProviderSettings />

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.adminToken.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.adminToken.description")}
            </p>
          </div>
        </div>
        <div className="field">
          <label htmlFor="api-admin-token">{t("sidebarPanel.adminToken.label")}</label>
          <input
            id="api-admin-token"
            type="password"
            placeholder={adminToken.configured
              ? t("sidebarPanel.adminToken.placeholderConfigured")
              : t("sidebarPanel.adminToken.placeholderEmpty")}
            value={adminToken.draft}
            onChange={(event) => adminToken.setDraft(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="btn secondary" disabled={adminToken.draft.trim().length === 0} onClick={adminToken.onSave}>
            {t("sidebarPanel.adminToken.save")}
          </button>
          <button
            className="btn ghost"
            disabled={!adminToken.configured && adminToken.draft.trim().length === 0}
            onClick={adminToken.onClear}
          >
            {t("sidebarPanel.adminToken.clear")}
          </button>
        </div>
        <div className="actions">
          <span className="pill">
            {adminToken.configured
              ? t("sidebarPanel.adminToken.configured")
              : t("sidebarPanel.adminToken.disabled")}
          </span>
        </div>
        {adminToken.status ? <div className="status">{adminToken.status}</div> : null}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.workspaceBackup.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.workspaceBackup.systemDescription")}
            </p>
          </div>
        </div>
        <div className="actions">
          <button className="btn ghost" disabled={exportingWorkspace} onClick={onExportWorkspace}>
            {exportingWorkspace ? t("sidebarPanel.workspaceBackup.exporting") : t("sidebarPanel.workspaceBackup.export")}
          </button>
          <button className="btn secondary" disabled={!canMutateBackend || importingWorkspace} onClick={onImportWorkspace}>
            {importingWorkspace ? t("sidebarPanel.workspaceBackup.importing") : t("sidebarPanel.workspaceBackup.import")}
          </button>
        </div>
      </div>

      {savedProjects.length > 0 ? (
        <div className="card">
          <h3>{t("sidebarPanel.quickArchive.title")}</h3>
          <div className="actions">
            {savedProjects.map((project) => (
              deletingProjectId === project.id ? (
                <button
                  key={project.id}
                  className="btn secondary"
                  disabled={true}
                  aria-label={t("sidebarPanel.quickArchive.archiveAriaLabel", { projectName: project.project_name })}
                >
                  {t("sidebarPanel.quickArchive.archiving")}
                </button>
              ) : (
                <InlineConfirmButton
                  key={project.id}
                  label={t("sidebarPanel.savedProjects.actions.archive")}
                  disabled={!canMutateBackend}
                  ariaLabel={t("sidebarPanel.quickArchive.archiveAriaLabel", { projectName: project.project_name })}
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
            <h3>{t("sidebarPanel.diagnostics.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.diagnostics.description")}
            </p>
          </div>
          <button className="btn ghost" disabled={loadingDiagnostics} onClick={onRefreshDiagnostics}>
            {loadingDiagnostics ? t("sidebarPanel.diagnostics.refreshing") : t("sidebarPanel.diagnostics.refresh")}
          </button>
        </div>
        {backendDiagnostics ? (
          <>
            <span className="pill">{t("sidebarPanel.diagnostics.online")}</span>
            <ul className="list">
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.uptime")}:</strong> {formatUptime(backendDiagnostics.uptime_seconds)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.storage")}:</strong>{" "}
                {t("sidebarPanel.diagnostics.storageSummary", {
                  projects: String(backendDiagnostics.storage.projects_total),
                  analysisRuns: String(backendDiagnostics.storage.analysis_runs_total),
                  exportEvents: String(backendDiagnostics.storage.export_events_total),
                  revisions: String(backendDiagnostics.storage.project_revisions_total)
                })}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.latestProjectUpdate")}:</strong>{" "}
                {formatOptionalProjectTimestamp(backendDiagnostics.storage.latest_project_updated_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.sqlitePath")}:</strong> <code>{backendDiagnostics.storage.db_path}</code>
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.sqliteParent")}:</strong> <code>{backendDiagnostics.storage.db_parent_path}</code>
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.storageFootprint")}:</strong>{" "}
                {t("sidebarPanel.diagnostics.values.db")} {formatBytes(backendDiagnostics.storage.db_size_bytes)}
                {" | "}
                {t("sidebarPanel.diagnostics.values.freeDisk")}{" "}
                {formatBytes(backendDiagnostics.storage.disk_free_bytes)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.sqliteMode")}:</strong> schema v{String(backendDiagnostics.storage.schema_version)}
                {" | "}
                {t("sidebarPanel.diagnostics.values.userVersion")}{" "}
                {String(backendDiagnostics.storage.sqlite_user_version)}
                {" | "}
                {backendDiagnostics.storage.journal_mode}
                {" | "}
                {backendDiagnostics.storage.synchronous}
                {" | "}
                {t("sidebarPanel.diagnostics.values.busyTimeout")}{" "}
                {String(backendDiagnostics.storage.busy_timeout_ms)}ms
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.sqliteWriteProbe")}:</strong>{" "}
                {backendDiagnostics.storage.write_probe_ok
                  ? t("sidebarPanel.diagnostics.values.pass")
                  : t("sidebarPanel.diagnostics.values.fail")}
                {" | "}
                {backendDiagnostics.storage.write_probe_detail}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.workspaceBackups")}:</strong> schema v{String(backendDiagnostics.storage.workspace_bundle_schema_version)}
                {" | "}
                {backendDiagnostics.storage.workspace_signature_enabled
                  ? t("sidebarPanel.diagnostics.values.hmacSigned")
                  : t("sidebarPanel.diagnostics.values.checksumOnly")}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.frontendDist")}:</strong>{" "}
                {backendDiagnostics.frontend.serve_frontend_dist
                  ? t("sidebarPanel.diagnostics.values.enabled")
                  : t("sidebarPanel.diagnostics.values.disabled")}
                {" | "}
                {backendDiagnostics.frontend.dist_exists
                  ? t("sidebarPanel.diagnostics.values.present")
                  : t("sidebarPanel.diagnostics.values.missing")}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.timingHeaders")}:</strong>{" "}
                {backendDiagnostics.request_timing_headers_enabled
                  ? t("sidebarPanel.diagnostics.values.enabled")
                  : t("sidebarPanel.diagnostics.values.disabled")}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.llmAdapter")}:</strong> {backendDiagnostics.llm.provider}
                {" | "}
                {t("sidebarPanel.diagnostics.values.timeout")}{" "}
                {String(backendDiagnostics.llm.timeout_seconds)}s
                {" | "}
                {t("sidebarPanel.diagnostics.values.attempts")}{" "}
                {String(backendDiagnostics.llm.max_attempts)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.logging")}:</strong> {backendDiagnostics.logging.level}
                {" | "}
                {backendDiagnostics.logging.format}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.runtimeCounters")}:</strong>{" "}
                {String(backendDiagnostics.runtime.total_requests)} {t("sidebarPanel.diagnostics.values.requests")}
                {" | "}
                {t("sidebarPanel.diagnostics.values.ok")}{" "}
                {String(backendDiagnostics.runtime.success_responses)}
                {" | 4xx "}
                {String(backendDiagnostics.runtime.client_error_responses)}
                {" | 5xx "}
                {String(backendDiagnostics.runtime.server_error_responses)}
                {" | 429 "}
                {String(backendDiagnostics.runtime.rate_limited_responses)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.lastRuntimeError")}:</strong>{" "}
                {backendDiagnostics.runtime.last_error_code ?? t("sidebarPanel.diagnostics.values.none")}
                {" | "}
                {t("sidebarPanel.diagnostics.values.authRejects")}{" "}
                {String(backendDiagnostics.runtime.auth_rejections)}
                {" | "}
                {t("sidebarPanel.diagnostics.values.bodyRejects")}{" "}
                {String(backendDiagnostics.runtime.request_body_rejections)}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.apiAuth")}:</strong>{" "}
                {backendDiagnostics.auth.enabled ? backendDiagnostics.auth.mode : t("sidebarPanel.diagnostics.values.disabled")}
                {" | "}
                {backendDiagnostics.auth.write_enabled
                  ? t("sidebarPanel.diagnostics.values.writeToken")
                  : t("sidebarPanel.diagnostics.values.noWriteToken")}
                {" | "}
                {backendDiagnostics.auth.readonly_enabled
                  ? t("sidebarPanel.diagnostics.values.readOnlyToken")
                  : t("sidebarPanel.diagnostics.values.noReadOnlyToken")}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.authHeaders")}:</strong> {backendDiagnostics.auth.accepted_headers.join(", ")}
                {" | "}
                {t("sidebarPanel.diagnostics.values.readMethods")}{" "}
                {backendDiagnostics.auth.read_only_methods.join(", ")}
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.securityGuards")}:</strong>{" "}
                {backendDiagnostics.guards.security_headers_enabled
                  ? t("sidebarPanel.diagnostics.values.headersOn")
                  : t("sidebarPanel.diagnostics.values.headersOff")}
                {" | "}
                {t("sidebarPanel.diagnostics.values.rateLimit")}{" "}
                {backendDiagnostics.guards.rate_limit_enabled
                  ? `${String(backendDiagnostics.guards.rate_limit_requests)}/${String(backendDiagnostics.guards.rate_limit_window_seconds)}s`
                  : t("sidebarPanel.diagnostics.values.disabled")}
                {" | "}
                {t("sidebarPanel.diagnostics.values.authThrottle")}{" "}
                {String(backendDiagnostics.guards.auth_failure_limit)}/{String(backendDiagnostics.guards.auth_failure_window_seconds)}s
              </li>
              <li>
                <strong>{t("sidebarPanel.diagnostics.labels.bodyLimits")}:</strong>{" "}
                {t("sidebarPanel.diagnostics.values.general")} {formatBytes(backendDiagnostics.guards.max_request_body_bytes)}
                {" | "}
                {t("sidebarPanel.diagnostics.values.workspace")}{" "}
                {formatBytes(backendDiagnostics.guards.max_workspace_body_bytes)}
              </li>
            </ul>
          </>
        ) : diagnosticsError ? (
          <div className="status">{t("sidebarPanel.diagnostics.unavailable")} {diagnosticsError}</div>
        ) : (
          <p className="muted">{t("sidebarPanel.diagnostics.notLoaded")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.workspaceStatus.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.workspaceStatus.description")}
            </p>
          </div>
        </div>
        <div className="actions">
          <span className="pill">{t("sidebarPanel.workspaceStatus.savedCount", { count: savedProjectsTotal })}</span>
          <span className="pill">{t("sidebarPanel.workspaceStatus.withSnapshotsCount", { count: projectsWithSnapshots })}</span>
          {hasUnsavedChanges ? <span className="pill">{t("sidebarPanel.workspaceStatus.draftChanged")}</span> : null}
          {backendDiagnostics?.storage.write_probe_ok ? <span className="pill">{t("sidebarPanel.workspaceStatus.sqliteWritable")}</span> : null}
          {!canMutateBackend ? <span className="pill">{t("sidebarPanel.workspaceStatus.readOnlyApi")}</span> : null}
        </div>
        <ul className="list">
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.savedProjects")}:</strong> {String(savedProjectsTotal)}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.archivedProjects")}:</strong> {String(archivedProjectsTotal)}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.snapshotCoverage")}:</strong>{" "}
            {t("sidebarPanel.workspaceStatus.snapshotCoverage", {
              ready: String(projectsWithSnapshots),
              withoutSavedAnalysis: String(projectsWithoutSnapshots)
            })}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.exportCoverage")}:</strong>{" "}
            {t("sidebarPanel.workspaceStatus.exportCoverage", { count: projectsWithExports })}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.revisionDepth")}:</strong>{" "}
            {t("sidebarPanel.workspaceStatus.revisionDepth", { count: projectsWithMultipleRevisions })}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.currentDraft")}:</strong>{" "}
            {activeProjectId
              ? (hasUnsavedChanges
                ? t("sidebarPanel.workspaceStatus.currentDraft.loadedProjectWithUnsavedChanges")
                : t("sidebarPanel.workspaceStatus.currentDraft.loadedProjectInSync"))
              : t("sidebarPanel.workspaceStatus.currentDraft.newLocalDraft")}
          </li>
          <li>
            <strong>{t("sidebarPanel.workspaceStatus.labels.latestWorkspaceUpdate")}:</strong>{" "}
            {formatOptionalProjectTimestamp(latestWorkspaceUpdate)}
          </li>
        </ul>
        {!canMutateBackend ? (
          <div className="callout">
            <Icon name="info" className="icon icon-inline" />
            <span>{backendMutationMessage}</span>
          </div>
        ) : null}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.auditLog.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.auditLog.description")}
            </p>
          </div>
          <div className="actions">
            <button className="btn ghost" disabled={auditLog.loading} onClick={auditLog.reload}>
              {auditLog.loading ? t("sidebarPanel.auditLog.refreshing") : t("sidebarPanel.auditLog.refresh")}
            </button>
            <button className="btn secondary" disabled={!canMutateBackend} onClick={() => void auditLog.onExport()}>
              {t("sidebarPanel.auditLog.export")}
            </button>
          </div>
        </div>
        <div className="field">
          <label htmlFor="audit-project-filter">{t("sidebarPanel.auditLog.projectFilter")}</label>
          <select
            id="audit-project-filter"
            value={auditLog.projectId}
            onChange={(event) => auditLog.setProjectId(event.target.value)}
          >
            <option value="">{t("sidebarPanel.auditLog.allProjects")}</option>
            {allSavedProjects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </div>
        {auditLog.error ? (
          <div className="status">{t("sidebarPanel.auditLog.unavailable")} {auditLog.error}</div>
        ) : auditLog.loading && auditLog.entries.length === 0 ? (
          <p className="muted">{t("sidebarPanel.auditLog.loading")}</p>
        ) : (
          <>
            <p className="muted">
              {t("sidebarPanel.auditLog.showingEntries", {
                count: auditLog.total,
                visible: auditLog.entries.length,
                total: auditLog.total
              })}
            </p>
            <table>
              <thead>
                <tr>
                  <th>{t("sidebarPanel.auditLog.columns.time")}</th>
                  <th>{t("sidebarPanel.auditLog.columns.action")}</th>
                  <th>{t("sidebarPanel.auditLog.columns.project")}</th>
                  <th>{t("sidebarPanel.auditLog.columns.actor")}</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.entries.length > 0 ? (
                  auditLog.entries.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatProjectTimestamp(entry.ts)}</td>
                      <td>{entry.action}</td>
                      <td>{entry.project_name ?? entry.project_id ?? t("sidebarPanel.auditLog.workspace")}</td>
                      <td>{entry.actor ?? t("sidebarPanel.auditLog.unknownActor")}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4}>{t("sidebarPanel.auditLog.noEntries")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h3>{t("sidebarPanel.backendEndpoints.title")}</h3>
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
    </>
  );
}
