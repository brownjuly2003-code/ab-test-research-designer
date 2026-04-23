import { lazy, memo, Suspense, useEffect, useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  clearAdminSessionToken,
  exportAuditLogRequest,
  hasAdminSessionToken,
  listApiKeysRequest,
  listAuditLogRequest,
  setAdminSessionToken
} from "../lib/api";
import { hydrateLoadedPayload, stepLabels, type AuditLogEntry } from "../lib/experiment";
import type { ToastType } from "../hooks/useToast";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useWizardStore } from "../stores/wizardStore";
import Icon from "./Icon";
import InlineConfirmButton from "./InlineConfirmButton";
import ProjectListFilters from "./ProjectListFilters";
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

function formatOptionalTimestamp(timestamp: string | null | undefined, emptyLabel: string): string {
  return timestamp ? formatProjectTimestamp(timestamp) : emptyLabel;
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

function formatRevisionSource(
  source: string,
  labels: {
    importedWorkspaceSnapshot: string;
    projectUpdate: string;
    initialSave: string;
  }
): string {
  if (source === "workspace_import") {
    return labels.importedWorkspaceSnapshot;
  }
  return source === "update" ? labels.projectUpdate : labels.initialSave;
}

function downloadBlob(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}

const ApiKeyManager = lazy(() => import("./ApiKeyManager"));
const WebhookManager = lazy(() => import("./WebhookManager"));

const SidebarPanel = memo(function SidebarPanel() {
  const { t } = useTranslation();
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
    savedProjects: allSavedProjects,
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
    projectMultiComparison,
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
  const [activeTab, setActiveTab] = useState<"projects" | "system" | "apiKeys">("projects");
  const [projectQuery, setProjectQuery] = useState("");
  const [projectStatus, setProjectStatus] = useState<"active" | "archived" | "all">("active");
  const [projectMetricType, setProjectMetricType] = useState<"all" | "binary" | "continuous">("all");
  const [projectSortBy, setProjectSortBy] = useState<"updated_desc" | "name_asc" | "duration_asc">("updated_desc");
  const [selectedComparisonProjectIds, setSelectedComparisonProjectIds] = useState<string[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [auditProjectId, setAuditProjectId] = useState("");
  const [adminTokenDraft, setAdminTokenDraft] = useState("");
  const [adminTokenConfigured, setAdminTokenConfigured] = useState(hasAdminSessionToken());
  const [adminTokenStatus, setAdminTokenStatus] = useState("");
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
    analysis.showError(backendMutationMessage || t("sidebarPanel.status.readOnlyMode"), "warning");
    return true;
  }

  async function loadAuditLog(projectId: string) {
    try {
      setAuditLoading(true);
      setAuditError("");
      const response = await listAuditLogRequest(projectId ? { projectId } : {});
      setAuditEntries(response.entries);
      setAuditTotal(response.total);
    } catch (error) {
      setAuditEntries([]);
      setAuditTotal(0);
      setAuditError(error instanceof Error ? error.message : t("sidebarPanel.auditLog.unavailable"));
    } finally {
      setAuditLoading(false);
    }
  }

  async function onExportAuditLog() {
    try {
      const { blob, filename } = await exportAuditLogRequest(auditProjectId ? { projectId: auditProjectId } : {});
      downloadBlob(blob, filename);
      analysis.showStatus(t("sidebarPanel.status.auditExported"), "success");
    } catch (error) {
      analysis.showError(error instanceof Error ? error.message : t("sidebarPanel.status.auditExportFailed"), "error");
    }
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
        ? t("sidebarPanel.status.returnedToCurrentResults")
        : t("sidebarPanel.status.closedSnapshotPreview"),
      "info"
    );
  }

  async function onOpenHistoryRun(runId: string) {
    if (!project.openHistoryRun(runId)) {
      return;
    }
    analysis.clearFeedback();
    analysis.showStatus(t("sidebarPanel.status.openedSnapshotFromHistory"), "info");
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

  async function onCompareSelectedProjects() {
    if (selectedComparisonProjectIds.length < 2 || selectedComparisonProjectIds.length > 5) {
      return;
    }
    const message = await project.compareProjects(selectedComparisonProjectIds);
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
    analysis.showStatus(
      t("sidebarPanel.status.loadedProjectIntoWizard", { projectName: String(loaded.project_name) }),
      "info"
    );
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
      analysis.showStatus(t("sidebarPanel.status.projectArchivedCurrentDraft", { projectName }), "success");
      return;
    }
    analysis.showStatus(t("sidebarPanel.status.projectArchived", { projectName }), "success");
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
    analysis.showStatus(
      t("sidebarPanel.status.projectRestored", { projectName: String(restored.project_name) }),
      "success"
    );
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
      analysis.showStatus(t("sidebarPanel.status.projectDeletedCurrentDraft", { projectName }), "success");
      return;
    }
    analysis.showStatus(t("sidebarPanel.status.projectDeleted", { projectName }), "success");
  }
  const filteredProjects = allSavedProjects
    .filter((project) => {
      if (projectStatus === "archived") {
        return project.is_archived;
      }
      if (projectStatus === "all") {
        return true;
      }
      return !project.is_archived;
    })
    .filter((project) => (
      projectMetricType === "all" ? true : project.metric_type === projectMetricType
    ))
    .filter((project) => {
      if (normalizedQuery.length === 0) {
        return true;
      }
      const hypothesis = String(project.hypothesis ?? "").toLowerCase();
      return project.project_name.toLowerCase().includes(normalizedQuery) || hypothesis.includes(normalizedQuery);
    })
    .sort((left, right) => {
      if (projectSortBy === "name_asc") {
        return left.project_name.localeCompare(right.project_name);
      }
      if (projectSortBy === "duration_asc") {
        return (left.duration_days ?? Number.MAX_SAFE_INTEGER) - (right.duration_days ?? Number.MAX_SAFE_INTEGER);
      }
      return right.updated_at.localeCompare(left.updated_at);
    });
  const compareCandidates = filteredProjects.filter((savedProject) => savedProject.has_analysis_snapshot && !savedProject.is_archived);
  const compareCandidateIdsKey = compareCandidates.map((savedProject) => savedProject.id).join("|");
  const canCompareSelected = selectedComparisonProjectIds.length >= 2 && selectedComparisonProjectIds.length <= 5;
  const savedProjectsTotal = allSavedProjects.length;
  const archivedProjectsTotal = allSavedProjects.filter((project) => project.is_archived).length;
  const projectsWithSnapshots = allSavedProjects.filter((project) => project.has_analysis_snapshot).length;
  const projectsWithoutSnapshots = savedProjectsTotal - projectsWithSnapshots;
  const projectsWithExports = allSavedProjects.filter((project) => Boolean(project.last_exported_at)).length;
  const projectsWithMultipleRevisions = allSavedProjects.filter((project) => (project.revision_count ?? 0) > 1).length;
  const latestWorkspaceUpdate =
    backendDiagnostics?.storage.latest_project_updated_at ??
    (allSavedProjects[0]?.updated_at ?? null);
  const showArchivedSection = projectStatus === "active" && normalizedQuery.length === 0 && projectMetricType === "all";
  const hasMoreAnalysisHistory = Boolean(
    projectHistory && projectHistory.analysis_runs.length < projectHistory.analysis_total
  );
  const hasMoreExportHistory = Boolean(
    projectHistory && projectHistory.export_events.length < projectHistory.export_total
  );
  const hasMoreProjectRevisions = Boolean(
    projectRevisions && projectRevisions.revisions.length < projectRevisions.total
  );
  const formatOptionalProjectTimestamp = (timestamp: string | null | undefined) =>
    formatOptionalTimestamp(timestamp, t("sidebarPanel.common.notRecordedYet"));
  const translateMetricType = (metricType: string | null | undefined) => {
    if (!metricType) {
      return t("sidebarPanel.common.unknownMetric");
    }
    if (metricType === "binary") {
      return t("projectListFilters.metricType.binary");
    }
    if (metricType === "continuous") {
      return t("projectListFilters.metricType.continuous");
    }
    return metricType;
  };
  const translateRevisionSource = (source: string) =>
    formatRevisionSource(source, {
      importedWorkspaceSnapshot: t("sidebarPanel.revisions.sources.importedWorkspaceSnapshot"),
      projectUpdate: t("sidebarPanel.revisions.sources.projectUpdate"),
      initialSave: t("sidebarPanel.revisions.sources.initialSave")
    });

  useEffect(() => {
    setSelectedComparisonProjectIds((current) => {
      const next = current.filter((projectId) => compareCandidates.some((projectItem) => projectItem.id === projectId));
      return next.length === current.length ? current : next;
    });
  }, [compareCandidateIdsKey]);

  useEffect(() => {
    if (activeTab !== "system") {
      return;
    }
    void loadAuditLog(auditProjectId);
  }, [activeTab, auditProjectId]);

  useEffect(() => {
    if (adminTokenConfigured || activeTab !== "apiKeys") {
      return;
    }
    setActiveTab("system");
  }, [activeTab, adminTokenConfigured]);

  async function onSaveAdminToken() {
    const normalizedToken = adminTokenDraft.trim();
    if (!normalizedToken) {
      return;
    }

    setAdminTokenStatus(t("sidebarPanel.status.verifyingAdminToken"));
    setAdminSessionToken(normalizedToken);

    try {
      await listApiKeysRequest();
      setAdminTokenConfigured(true);
      setAdminTokenDraft("");
      setAdminTokenStatus(t("sidebarPanel.status.adminTokenAccepted"));
      setActiveTab("apiKeys");
    } catch (error) {
      clearAdminSessionToken();
      setAdminTokenConfigured(false);
      setAdminTokenStatus(error instanceof Error ? error.message : t("sidebarPanel.status.adminTokenVerificationFailed"));
    }
  }

  function onClearAdminToken() {
    clearAdminSessionToken();
    setAdminTokenConfigured(false);
    setAdminTokenDraft("");
    setAdminTokenStatus(t("sidebarPanel.status.adminTokenCleared"));
  }

  return (
    <aside className={`panel ${styles.sidebar}`}>
      <input
        ref={workspaceImportRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label={t("wizardPanel.aria.importWorkspaceFile")}
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
          {t("sidebarPanel.tabs.projects")}
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
          {t("sidebarPanel.tabs.system")}
        </button>
        {adminTokenConfigured ? (
          <button
            type="button"
            className="btn"
            style={{
              background: activeTab === "apiKeys" ? "var(--color-secondary)" : "transparent",
              color: activeTab === "apiKeys" ? "#ffffff" : "var(--muted)",
              boxShadow: activeTab === "apiKeys" ? "0 10px 24px rgba(79, 70, 229, 0.2)" : "none"
            }}
            onClick={() => setActiveTab("apiKeys")}
          >
            {t("sidebarPanel.tabs.apiKeys")}
          </button>
        ) : null}
      </div>

      {activeTab === "apiKeys" ? (
        <Suspense
          fallback={
            <div className="card">
              <h3>{t("sidebarPanel.apiKeysFallback.title")}</h3>
              <p className="muted">{t("sidebarPanel.apiKeysFallback.loading")}</p>
            </div>
          }
        >
          <ApiKeyManager />
          <WebhookManager />
        </Suspense>
      ) : activeTab === "system" ? (
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
            placeholder={adminTokenConfigured
              ? t("sidebarPanel.adminToken.placeholderConfigured")
              : t("sidebarPanel.adminToken.placeholderEmpty")}
            value={adminTokenDraft}
            onChange={(event) => setAdminTokenDraft(event.target.value)}
          />
        </div>
        <div className="actions">
          <button className="btn secondary" disabled={adminTokenDraft.trim().length === 0} onClick={onSaveAdminToken}>
            {t("sidebarPanel.adminToken.save")}
          </button>
          <button className="btn ghost" disabled={!adminTokenConfigured && adminTokenDraft.trim().length === 0} onClick={onClearAdminToken}>
            {t("sidebarPanel.adminToken.clear")}
          </button>
        </div>
        <div className="actions">
          <span className="pill">
            {adminTokenConfigured
              ? t("sidebarPanel.adminToken.configured")
              : t("sidebarPanel.adminToken.disabled")}
          </span>
        </div>
        {adminTokenStatus ? <div className="status">{adminTokenStatus}</div> : null}
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
            <button className="btn ghost" disabled={auditLoading} onClick={() => void loadAuditLog(auditProjectId)}>
              {auditLoading ? t("sidebarPanel.auditLog.refreshing") : t("sidebarPanel.auditLog.refresh")}
            </button>
            <button className="btn secondary" disabled={!canMutateBackend} onClick={() => void onExportAuditLog()}>
              {t("sidebarPanel.auditLog.export")}
            </button>
          </div>
        </div>
        <div className="field">
          <label htmlFor="audit-project-filter">{t("sidebarPanel.auditLog.projectFilter")}</label>
          <select
            id="audit-project-filter"
            value={auditProjectId}
            onChange={(event) => setAuditProjectId(event.target.value)}
          >
            <option value="">{t("sidebarPanel.auditLog.allProjects")}</option>
            {allSavedProjects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </div>
        {auditError ? (
          <div className="status">{t("sidebarPanel.auditLog.unavailable")} {auditError}</div>
        ) : auditLoading && auditEntries.length === 0 ? (
          <p className="muted">{t("sidebarPanel.auditLog.loading")}</p>
        ) : (
          <>
            <p className="muted">
              {t("sidebarPanel.auditLog.showingEntries", {
                count: auditTotal,
                visible: auditEntries.length,
                total: auditTotal
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
                {auditEntries.length > 0 ? (
                  auditEntries.map((entry) => (
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

        </>
      ) : null}

      {activeTab === "projects" ? (
        <>
      <div className="card">
        <h3>{t("sidebarPanel.activeProject.title")}</h3>
        {activeProjectId ? (
          <>
            <div className="actions">
              <span className="pill">
                {hasUnsavedChanges
                  ? t("sidebarPanel.activeProject.unsavedChanges")
                  : t("sidebarPanel.activeProject.savedLocally")}
              </span>
            </div>
            <ul className="list">
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.projectName")}:</strong>{" "}
                {activeProject?.project_name ?? t("sidebarPanel.activeProject.unknownProject")}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.projectId")}:</strong> {activeProjectId}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.status")}:</strong>{" "}
                {hasUnsavedChanges
                  ? t("sidebarPanel.activeProject.statusNeedsLocalUpdate")
                  : t("sidebarPanel.activeProject.statusInSync")}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.payloadSchema")}:</strong>{" "}
                {String(activeProject?.payload_schema_version ?? 1)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.savedRevisions")}:</strong>{" "}
                {String(activeProject?.revision_count ?? 0)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastSave")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_revision_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastAnalysis")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_analysis_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.lastExport")}:</strong>{" "}
                {formatOptionalProjectTimestamp(activeProject?.last_exported_at)}
              </li>
              <li>
                <strong>{t("sidebarPanel.activeProject.labels.snapshotStored")}:</strong>{" "}
                {activeProject?.has_analysis_snapshot ? t("wizardDraft.common.yes") : t("wizardDraft.common.no")}
              </li>
            </ul>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.activeProject.empty")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.projectHistory.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.projectHistory.description")}</p>
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
            {loadingProjectHistory ? t("sidebarPanel.projectHistory.refreshing") : t("sidebarPanel.projectHistory.refresh")}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">{t("sidebarPanel.projectHistory.empty")}</p>
        ) : projectHistoryError ? (
          <div className="status">{t("sidebarPanel.projectHistory.unavailable")} {projectHistoryError}</div>
        ) : loadingProjectHistory && !projectHistory ? (
          <p className="muted">{t("sidebarPanel.projectHistory.loading")}</p>
        ) : projectHistory ? (
          <>
            <p className="muted">
              {t("sidebarPanel.projectHistory.summary", {
                analysisVisible: projectHistory.analysis_runs.length,
                analysisTotal: projectHistory.analysis_total,
                exportVisible: projectHistory.export_events.length,
                exportTotal: projectHistory.export_total
              })}
            </p>
            {selectedHistoryRunId ? (
              <div className="actions">
                <button className="btn secondary" onClick={onClearHistoryRunSelection}>
                  {t("sidebarPanel.projectHistory.closeOpenedSnapshot")}
                </button>
              </div>
            ) : null}
            <div className={styles["timeline-card"]}>
              <h3>{t("sidebarPanel.projectHistory.analysisRunsTitle")}</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.analysis_runs.length > 0 ? (
                  projectHistory.analysis_runs.map((run) => (
                    <div key={run.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(run.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {translateMetricType(run.summary.metric_type)}
                        {" | "}n={String(run.summary.total_sample_size ?? "-")}
                        {" | "}
                        {t("sidebarPanel.common.daysShort", { value: String(run.summary.estimated_duration_days ?? "-") })}
                        {" | "}
                        {t("sidebarPanel.projectHistory.warningsCount", { count: run.summary.warnings_count })}
                        {run.summary.advice_available ? ` | ${t("sidebarPanel.projectHistory.aiAdvice")}` : ""}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onOpenHistoryRun(run.id)}>
                          {selectedHistoryRunId === run.id
                            ? t("sidebarPanel.projectHistory.opened")
                            : t("sidebarPanel.projectHistory.openSnapshot")}
                        </button>
                        {selectedHistoryRunId === run.id ? <span className="pill">{t("sidebarPanel.projectHistory.viewing")}</span> : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.projectHistory.noAnalysisHistory")}</div>
                  </div>
                )}
              </div>
              {hasMoreAnalysisHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreAnalysisHistory(activeProjectId)}>
                    {t("sidebarPanel.projectHistory.loadOlderAnalysisRuns")}
                  </button>
                </div>
              ) : null}
            </div>
            <div className={styles["timeline-card"]}>
              <h3>{t("sidebarPanel.projectHistory.exportEventsTitle")}</h3>
              <div className={styles["timeline-list"]}>
                {projectHistory.export_events.length > 0 ? (
                  projectHistory.export_events.map((event) => (
                    <div key={event.id} className={styles["timeline-item"]}>
                      <div className={styles["timeline-title"]}>
                        <strong>{formatProjectTimestamp(event.created_at)}</strong>
                      </div>
                      <div className="muted">
                        {event.format.toUpperCase()}
                        {event.analysis_run_id
                          ? ` | ${t("sidebarPanel.projectHistory.linkedSnapshot")}`
                          : ` | ${t("sidebarPanel.projectHistory.unlinkedExport")}`}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.projectHistory.noExportHistory")}</div>
                  </div>
                )}
              </div>
              {hasMoreExportHistory && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreExportHistory(activeProjectId)}>
                    {t("sidebarPanel.projectHistory.loadOlderExportEvents")}
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.projectHistory.notLoaded")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.revisions.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.revisions.description")}
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
            {loadingProjectRevisions ? t("sidebarPanel.revisions.refreshing") : t("sidebarPanel.revisions.refresh")}
          </button>
        </div>
        {!activeProjectId ? (
          <p className="muted">{t("sidebarPanel.revisions.empty")}</p>
        ) : projectRevisionsError ? (
          <div className="status">{t("sidebarPanel.revisions.unavailable")} {projectRevisionsError}</div>
        ) : loadingProjectRevisions && !projectRevisions ? (
          <p className="muted">{t("sidebarPanel.revisions.loading")}</p>
        ) : projectRevisions ? (
          <>
            <p className="muted">
              {t("sidebarPanel.revisions.summary", {
                visible: projectRevisions.revisions.length,
                total: projectRevisions.total
              })}
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
                        {translateRevisionSource(revision.source)}
                        {" | "}
                        {revision.payload.project.project_name}
                      </div>
                      <div className="actions">
                        <button className="btn secondary" onClick={() => onLoadProjectRevision(revision.id)}>
                          {t("sidebarPanel.revisions.loadIntoWizard")}
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={styles["timeline-item"]}>
                    <div>{t("sidebarPanel.revisions.noEntries")}</div>
                  </div>
                )}
              </div>
              {hasMoreProjectRevisions && activeProjectId ? (
                <div className="actions">
                  <button className="btn ghost" onClick={() => onLoadMoreProjectRevisions(activeProjectId)}>
                    {t("sidebarPanel.revisions.loadOlder")}
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.revisions.notLoaded")}</p>
        )}
      </div>

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.savedProjects.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.savedProjects.description")}</p>
          </div>
          <button className="btn ghost" disabled={loadingProjects} onClick={onLoadProjects}>
            {loadingProjects ? t("sidebarPanel.savedProjects.loading") : t("sidebarPanel.savedProjects.load")}
          </button>
        </div>
        <div className="actions">
          <span className="pill">{t("sidebarPanel.savedProjects.savedCount", { count: savedProjectsTotal })}</span>
          <span className="pill">
            {t("sidebarPanel.savedProjects.withoutSavedAnalysisCount", { count: projectsWithoutSnapshots })}
          </span>
        </div>
        {loadingProjects ? (
          <ProjectListSkeleton />
        ) : allSavedProjects.length > 0 ? (
          <>
            <ProjectListFilters
              query={projectQuery}
              status={projectStatus}
              metricType={projectMetricType}
              sortBy={projectSortBy}
              onQueryChange={setProjectQuery}
              onStatusChange={setProjectStatus}
              onMetricTypeChange={setProjectMetricType}
              onSortByChange={setProjectSortBy}
              onClearFilters={() => {
                setProjectQuery("");
                setProjectStatus("active");
                setProjectMetricType("all");
                setProjectSortBy("updated_desc");
              }}
            />
            <p className="muted">
              {t("sidebarPanel.savedProjects.shownExperiments", { count: filteredProjects.length })}
            </p>
            {compareCandidates.length > 0 ? (
              <>
                <p className="muted">{t("sidebarPanel.savedProjects.compareDescription")}</p>
                <div className="actions">
                  <span className="pill">{t("sidebarPanel.savedProjects.selectedForComparison", { count: selectedComparisonProjectIds.length })}</span>
                  <button
                    className="btn secondary"
                    id="compare-selected-projects-button"
                    type="button"
                    disabled={!canCompareSelected || loadingProjectComparison}
                    onClick={() => void onCompareSelectedProjects()}
                  >
                    {loadingProjectComparison
                      ? t("sidebarPanel.savedProjects.actions.comparing")
                      : t("sidebarPanel.savedProjects.actions.compareSelected")}
                  </button>
                </div>
                {projectMultiComparison ? (
                  <p className="muted">{t("sidebarPanel.savedProjects.currentDashboard", { count: projectMultiComparison.projects.length })}</p>
                ) : projectComparison ? (
                  <p className="muted">
                    {t("sidebarPanel.savedProjects.currentComparison", {
                      baseProject: projectComparison.base_project.project_name,
                      candidateProject: projectComparison.candidate_project.project_name
                    })}
                  </p>
                ) : null}
                {projectComparisonError ? (
                  <div className="status">{t("sidebarPanel.savedProjects.comparisonUnavailable")} {projectComparisonError}</div>
                ) : null}
              </>
            ) : (
              <p className="muted">{t("sidebarPanel.savedProjects.compareRequiresSnapshot")}</p>
            )}
            <div className={styles["project-card-list"]}>
              {filteredProjects.map((project) => (
                <div
                  key={project.id}
                  className={[styles["project-card"], project.id === activeProjectId ? styles.active : ""].filter(Boolean).join(" ")}
                >
                  <div className={styles["project-card-head"]}>
                    {project.is_archived ? (
                      <strong>{project.project_name}</strong>
                    ) : (
                      <button className={`btn ghost ${styles["project-load-btn"]}`} onClick={() => onLoadProject(project.id)}>
                        {project.project_name}
                      </button>
                    )}
                    <div className={styles["project-badges"]}>
                      {project.id === activeProjectId ? <span className="pill">{t("sidebarPanel.savedProjects.badges.loaded")}</span> : null}
                      {project.has_analysis_snapshot ? <span className="pill">{t("sidebarPanel.savedProjects.badges.snapshot")}</span> : null}
                      {project.is_archived ? <span className="pill">{t("sidebarPanel.savedProjects.badges.archived")}</span> : null}
                    </div>
                  </div>
                  <div className={styles["project-meta"]}>
                    <div className="muted">
                      {t("sidebarPanel.savedProjects.updatedAt", { timestamp: formatProjectTimestamp(project.updated_at) })}
                      {project.last_revision_at
                        ? ` | ${t("sidebarPanel.savedProjects.savedAt", { timestamp: formatProjectTimestamp(project.last_revision_at) })}`
                        : ""}
                      {project.last_analysis_at
                        ? ` | ${t("sidebarPanel.savedProjects.analyzedAt", { timestamp: formatProjectTimestamp(project.last_analysis_at) })}`
                        : ""}
                    </div>
                    <div className="muted">
                      {project.hypothesis ? `${project.hypothesis} | ` : ""}
                      {project.metric_type ? `${translateMetricType(project.metric_type)} | ` : ""}
                      {project.duration_days
                        ? `${t("sidebarPanel.common.daysShort", { value: String(project.duration_days) })} | `
                        : ""}
                      {t("sidebarPanel.savedProjects.revisionsCount", { count: project.revision_count ?? 0 })}
                      {" | "}
                      {project.last_exported_at
                        ? t("sidebarPanel.savedProjects.exportedAt", { timestamp: formatProjectTimestamp(project.last_exported_at) })
                        : t("sidebarPanel.savedProjects.noExportsYet")}
                      {project.id === activeProjectId ? ` | ${t("sidebarPanel.savedProjects.loadedInWizard")}` : ""}
                    </div>
                  </div>
                  <div className="actions">
                    {project.has_analysis_snapshot && !project.is_archived ? (
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={selectedComparisonProjectIds.includes(project.id)}
                          onChange={(event) => {
                            setSelectedComparisonProjectIds((current) => {
                              if (event.target.checked) {
                                return current.includes(project.id) || current.length >= 5 ? current : [...current, project.id];
                              }
                              return current.filter((projectId) => projectId !== project.id);
                            });
                          }}
                        />
                        <span>{t("sidebarPanel.savedProjects.actions.selectForComparison")}</span>
                      </label>
                    ) : null}
                    {activeProjectId && project.id !== activeProjectId && project.has_analysis_snapshot && !project.is_archived ? (
                      <button
                        className="btn secondary"
                        type="button"
                        disabled={loadingProjectComparison}
                        onClick={() => void onCompareProject(project.id)}
                      >
                        {loadingProjectComparison && comparingProjectId === project.id
                          ? t("sidebarPanel.savedProjects.actions.comparing")
                          : t("sidebarPanel.savedProjects.actions.compare")}
                      </button>
                    ) : null}
                    {project.is_archived ? (
                      <button
                        className="btn secondary"
                        disabled={!canMutateBackend || restoringProjectId === project.id}
                        onClick={() => onRestoreProject(project.id, project.project_name)}
                      >
                        {restoringProjectId === project.id
                          ? t("sidebarPanel.savedProjects.actions.restoring")
                          : t("sidebarPanel.savedProjects.actions.restore")}
                      </button>
                    ) : (
                      <>
                        <InlineConfirmButton
                          label={t("sidebarPanel.savedProjects.actions.archive")}
                          disabled={!canMutateBackend || deletingProjectId === project.id}
                          ariaLabel={t("sidebarPanel.savedProjects.archiveAriaLabel", { projectName: project.project_name })}
                          onConfirm={() => onDeleteProject(project.id, project.project_name)}
                        />
                        <InlineConfirmButton
                          label={t("sidebarPanel.savedProjects.actions.delete")}
                          disabled={!canMutateBackend || deletingProjectId === project.id}
                          ariaLabel={t("sidebarPanel.savedProjects.deleteAriaLabel", { projectName: project.project_name })}
                          onConfirm={() => onPermanentlyDeleteProject(project.id, project.project_name)}
                        />
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {filteredProjects.length === 0 ? (
              <div className="actions">
                <p className="muted">{t("sidebarPanel.savedProjects.noMatches")}</p>
                <button
                  className="btn ghost"
                  type="button"
                  onClick={() => {
                    setProjectQuery("");
                    setProjectStatus("active");
                    setProjectMetricType("all");
                    setProjectSortBy("updated_desc");
                  }}
                >
                  {t("projectListFilters.clear")}
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p className="muted">{t("sidebarPanel.savedProjects.empty")}</p>
        )}
      </div>

      {showArchivedSection ? (
      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.archivedProjects.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>{t("sidebarPanel.archivedProjects.description")}</p>
          </div>
        </div>
        {archivedProjects.length > 0 ? (
          <div className={styles["project-card-list"]}>
            {archivedProjects.map((project) => (
              <div key={project.id} className={styles["project-card"]}>
                <div className={styles["project-card-head"]}>
                  <strong>{project.project_name}</strong>
                  <div className={styles["project-badges"]}>
                    <span className="pill">{t("sidebarPanel.savedProjects.badges.archived")}</span>
                  </div>
                </div>
                <div className={styles["project-meta"]}>
                  <div className="muted">
                    {t("sidebarPanel.archivedProjects.archivedAt", {
                      timestamp: formatOptionalProjectTimestamp(project.archived_at)
                    })}
                    {project.last_analysis_at
                      ? ` | ${t("sidebarPanel.archivedProjects.lastAnalysisAt", {
                        timestamp: formatProjectTimestamp(project.last_analysis_at)
                      })}`
                      : ""}
                  </div>
                  <div className="muted">
                    {t("sidebarPanel.savedProjects.revisionsCount", { count: project.revision_count ?? 0 })}
                    {" | "}
                    {project.last_exported_at
                      ? t("sidebarPanel.savedProjects.exportedAt", { timestamp: formatProjectTimestamp(project.last_exported_at) })
                      : t("sidebarPanel.savedProjects.noExportsYet")}
                  </div>
                </div>
                <div className="actions">
                  <button
                    className="btn secondary"
                    disabled={!canMutateBackend || restoringProjectId === project.id}
                    onClick={() => onRestoreProject(project.id, project.project_name)}
                  >
                    {restoringProjectId === project.id
                      ? t("sidebarPanel.savedProjects.actions.restoring")
                      : t("sidebarPanel.savedProjects.actions.restore")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">{t("sidebarPanel.archivedProjects.empty")}</p>
        )}
      </div>
      ) : null}

      <div className="card">
        <div className="section-heading">
          <div>
            <h3>{t("sidebarPanel.workspaceBackup.title")}</h3>
            <p className={`muted ${styles["compact-text"]}`}>
              {t("sidebarPanel.workspaceBackup.projectsDescription")}
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

        </>
      ) : null}

      {activeTab === "system" ? (
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
      ) : null}
    </aside>
  );
});

export default SidebarPanel;
